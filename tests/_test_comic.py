# -*- coding: utf-8 -*-
"""漫画引擎测试（离线：伪造 OCR 引擎，不安装 rapidocr；渲染用真实 Pillow）
覆盖：页收集/去重/符号过滤 → 嵌字回写（横排白底黑字、黑底白字反色、竖排、
未翻译回退）→ 文件夹与 CBZ 两路输出 → 原文件一字节不动
运行：python tests/_test_comic.py
"""
import os, sys, io, json, time, zipfile, hashlib, importlib.util, tempfile, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("SKIP: Pillow 未安装（渲染测试需要）")
    sys.exit(0)

def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "engines", f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

cl = load("comic_lib")
ce = load("comic_extract")
ca = load("comic_apply")
import mt_config

if cl.find_font(20) is None:
    print("SKIP: 系统未找到 CJK 字体（可用 .env MT_FONT 指定后重跑）")
    sys.exit(0)

# ---------- 造测试页 ----------
tmp = tempfile.mkdtemp(prefix="comic_")

def make_page(path, boxes):
    """白底页；boxes 里的区域涂黑（模拟气泡描边/底）"""
    img = Image.new("RGB", (400, 600), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for b in boxes:
        d.rectangle(b, fill=(20, 20, 20))
    img.save(path, "PNG")
    return open(path, "rb").read()

p1_bytes = make_page(os.path.join(tmp, "page1.png"), [(50, 80, 350, 220)])
p2_bytes = make_page(os.path.join(tmp, "page2.png"), [(300, 50, 360, 550)])

def R(x1, y1, x2, y2, t, conf=0.99):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], t, conf

MAP = {
    p1_bytes: [R(50, 80, 350, 220, "Hello there."),
               R(200, 300, 380, 360, "Goodbye."),
               R(10, 560, 60, 590, "♪", 0.9)],          # 纯符号：不送翻不动
    p2_bytes: [R(300, 50, 360, 550, "縦書きテスト"),
               R(50, 80, 350, 220, "Hello there.")],     # 重复台词
}

class FakeOCR:
    def __call__(self, target):
        key = target if isinstance(target, bytes) else open(target, "rb").read()
        return MAP.get(key, []), []
    def close(self):
        pass

ce.lib._OCR = FakeOCR()      # 注入 comic_extract 实际使用的 comic_lib 实例，不 import rapidocr

# ---------- ① 文件夹流：提取 ----------
comic = os.path.join(tmp, "MyComic")
os.makedirs(comic)
open(os.path.join(comic, "page1.png"), "wb").write(p1_bytes)
open(os.path.join(comic, "page2.png"), "wb").write(p2_bytes)

_old_base, _old_env = mt_config.base_dir, mt_config.load_env
mt_config.base_dir = lambda: tmp
mt_config.load_env = lambda: {"MT_TL": "zh-CN", "MT_SL": "auto"}
try:
    sys.argv = ["comic_extract.py", comic]
    ce.main()
    out = json.load(open(os.path.join(tmp, "MyComic_extracted.json"), encoding="utf-8"))
    assert set(out) == {"Hello there.", "Goodbye.", "縦書きテスト"}, set(out)
    side = json.load(open(os.path.join(tmp, "MyComic_comic.json"), encoding="utf-8"))
    assert len(side["pages"]) == 2
    assert [len(p["regions"]) for p in side["pages"]] == [2, 2]   # ♪ 已滤掉
    print(f"提取 ✓  3 条唯一台词（跨页去重），纯符号未送翻，sidecar {len(side['pages'])} 页")

    # ---------- ② 嵌字回写 ----------
    tr = {"Hello there.": "你好呀。", "縦書きテスト": "竖排测试文字"}   # Goodbye. 不翻 → 原文重绘
    trfile = os.path.join(tmp, "MyComic_extracted_translated.json")
    json.dump(tr, open(trfile, "w", encoding="utf-8"), ensure_ascii=False)
    h1 = hashlib.md5(open(os.path.join(comic, "page1.png"), "rb").read()).hexdigest()

    sys.argv = ["comic_apply.py", comic, trfile]
    ca.main()

    outdir = comic + ".zh"
    o1 = os.path.join(outdir, "page1.png")
    o2 = os.path.join(outdir, "page2.png")
    assert os.path.exists(o1) and os.path.exists(o2), os.listdir(outdir)

    def count_pred(img, box, pred):
        n = 0
        for x in range(box[0], box[2], 3):
            for y in range(box[1], box[3], 3):
                if pred(img.getpixel((x, y))):
                    n += 1
        return n

    i1 = Image.open(o1).convert("RGB")
    # 黑底气泡（填充取样≈黑）→ 白字
    white_in_bubble = count_pred(i1, (55, 85, 345, 215), lambda p: min(p) > 200)
    assert white_in_bubble > 10, white_in_bubble
    # 白底区域 → 黑字（Goodbye. 未翻译，按原文重绘也是黑字）
    dark_in_white = count_pred(i1, (205, 305, 375, 355), lambda p: max(p) < 90)
    assert dark_in_white > 5, dark_in_white

    i2 = Image.open(o2).convert("RGB")
    # 竖长黑底框 + 中文 → 竖排白字（框内出现白像素即文字）
    white_in_v = count_pred(i2, (305, 55, 355, 545), lambda p: min(p) > 200)
    assert white_in_v > 10, white_in_v
    # ♪ 符号区域不在 sidecar，页1 对应位置保持原样（该区域本来就是白色边缘，不校验内容）

    assert hashlib.md5(open(os.path.join(comic, "page1.png"), "rb").read()).hexdigest() == h1
    print("嵌字 ✓  黑底白字反色 / 白底黑字 / 竖排 / 未翻译回退 / 原图一字节未动")

    # ---------- ③ CBZ 流 ----------
    cbz = os.path.join(tmp, "vol1.cbz")
    with zipfile.ZipFile(cbz, "w") as z:
        z.writestr("p1.png", p1_bytes)
        z.writestr("p2.png", p2_bytes)
    hz = hashlib.md5(open(cbz, "rb").read()).hexdigest()
    sys.argv = ["comic_extract.py", cbz]
    ce.main()
    outz = json.load(open(os.path.join(tmp, "vol1_extracted.json"), encoding="utf-8"))
    assert set(outz) == {"Hello there.", "Goodbye.", "縦書きテスト"}, set(outz)
    json.dump(tr, open(os.path.join(tmp, "vol1_extracted_translated.json"), "w",
                       encoding="utf-8"), ensure_ascii=False)
    sys.argv = ["comic_apply.py", cbz, os.path.join(tmp, "vol1_extracted_translated.json")]
    ca.main()
    outcbz = os.path.join(tmp, "vol1.zh.cbz")
    assert os.path.exists(outcbz)
    with zipfile.ZipFile(outcbz) as z:
        names = z.namelist()
        assert sorted(names) == ["p1.png", "p2.png"], names
        Image.open(io.BytesIO(z.read("p2.png"))).verify()
    assert hashlib.md5(open(cbz, "rb").read()).hexdigest() == hz
    print("CBZ ✓  成员保持原名，输出 vol1.zh.cbz，原档案未动")
finally:
    mt_config.base_dir = _old_base
    mt_config.load_env = _old_env

shutil.rmtree(tmp, ignore_errors=True)   # Windows 下句柄释放或有延迟，容错清理
print("ALL TESTS PASS")
