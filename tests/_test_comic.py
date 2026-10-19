# -*- coding: utf-8 -*-
"""漫画引擎测试（离线：伪造 OCR 引擎，不安装 rapidocr；渲染用真实 Pillow）
覆盖：气泡级聚类（同气泡竖列合并/阅读序拼接、跨气泡不合并、符号过滤）→
嵌字回写（横排、黑底白字反色、竖排、未翻译回退、圆角填充）→
文件夹与 CBZ 两路输出 → 原文件一字节不动
运行：python tests/_test_comic.py
"""
import os, sys, io, json, zipfile, hashlib, importlib.util, tempfile, shutil

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
p3_bytes = make_page(os.path.join(tmp, "page3.png"), [(280, 100, 395, 500)])

def R(x1, y1, x2, y2, t, conf=0.99):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], t, conf

MAP = {
    p1_bytes: [R(50, 80, 350, 220, "Hello there."),
               R(200, 300, 380, 360, "Goodbye."),
               R(10, 560, 60, 590, "♪", 0.9)],          # 纯符号：不送翻不动
    p2_bytes: [R(300, 50, 360, 550, "縦書きテスト"),
               R(50, 80, 250, 220, "Hello there.")],     # 与左侧气泡隔 50px：不合并
    p3_bytes: [R(280, 100, 330, 500, "左列"),
               R(345, 100, 395, 500, "右列")],           # 同气泡相邻竖列：必须合并
}

class FakeOCR:
    def __call__(self, target):
        key = target if isinstance(target, bytes) else open(target, "rb").read()
        return MAP.get(key, []), []
    def close(self):
        pass

ce.lib._OCR = FakeOCR()      # 注入 comic_extract 实际使用的 comic_lib 实例，不 import rapidocr

# ---------- ① 单元：聚类规则 ----------
two_cols = cl.cluster_regions([{"box": [300, 100, 350, 500], "text": "左列"},
                               {"box": [365, 100, 415, 500], "text": "右列"}])
assert len(two_cols) == 1 and two_cols[0]["text"] == "右列左列" \
       and two_cols[0]["box"] == [300, 100, 415, 500], two_cols
far = cl.cluster_regions([{"box": [50, 80, 350, 220], "text": "A"},
                          {"box": [300, 50, 360, 550], "text": "B"}])
# x 有交叠且 y 有交叠 → 重叠合并？(50..350)x(300..360) 与 (80..220)x(50..550)：实测重叠
# 设计上重叠即视为同一目标——这里改用真正分离的对来验证不合并：
far = cl.cluster_regions([{"box": [50, 80, 250, 220], "text": "A"},
                          {"box": [300, 50, 360, 550], "text": "B"}])
assert len(far) == 2, far
stacked_bubbles = cl.cluster_regions([{"box": [100, 50, 300, 400], "text": "上"},
                                      {"box": [100, 430, 300, 780], "text": "下"}])
assert len(stacked_bubbles) == 2, "上下两只气泡不能被并成一只"
print("聚类规则 ✓  同气泡竖列合并（右→左拼接）/ 分离气泡不合并 / 上下气泡不合并")

# ---------- ② 文件夹流：提取（聚类后） ----------
comic = os.path.join(tmp, "MyComic")
os.makedirs(comic)
open(os.path.join(comic, "page1.png"), "wb").write(p1_bytes)
open(os.path.join(comic, "page2.png"), "wb").write(p2_bytes)
open(os.path.join(comic, "page3.png"), "wb").write(p3_bytes)

_old_base, _old_env = mt_config.base_dir, mt_config.load_env
mt_config.base_dir = lambda: tmp
mt_config.load_env = lambda: {"MT_TL": "zh-CN", "MT_SL": "auto", "MT_COMIC_OCR": "rapid"}
try:
    sys.argv = ["comic_extract.py", comic]
    ce.main()
    out = json.load(open(os.path.join(tmp, "MyComic_extracted.json"), encoding="utf-8"))
    assert set(out) == {"Hello there.", "Goodbye.", "縦書きテスト", "右列左列"}, set(out)
    side = json.load(open(os.path.join(tmp, "MyComic_comic.json"), encoding="utf-8"))
    assert len(side["pages"]) == 3
    assert [len(p["regions"]) for p in side["pages"]] == [2, 2, 1]  # ♪ 滤掉 / 双列并一
    print("提取 ✓  4 条气泡级词条（双列合并成整句、跨气泡不合并、符号未送翻）")

    # ---------- ③ 嵌字回写 ----------
    tr = {"Hello there.": "你好呀。", "縦書きテスト": "竖排测试文字",
          "右列左列": "竖排合并测试"}                    # Goodbye. 不翻 → 原文重绘
    trfile = os.path.join(tmp, "MyComic_extracted_translated.json")
    json.dump(tr, open(trfile, "w", encoding="utf-8"), ensure_ascii=False)
    h1 = hashlib.md5(open(os.path.join(comic, "page1.png"), "rb").read()).hexdigest()

    sys.argv = ["comic_apply.py", comic, trfile]
    ca.main()

    outdir = comic + ".zh"
    for n in ("page1.png", "page2.png", "page3.png"):
        assert os.path.exists(os.path.join(outdir, n)), os.listdir(outdir)

    def count_pred(img, box, pred):
        n = 0
        for x in range(box[0], box[2], 3):
            for y in range(box[1], box[3], 3):
                if pred(img.getpixel((x, y))):
                    n += 1
        return n

    i1 = Image.open(os.path.join(outdir, "page1.png")).convert("RGB")
    assert count_pred(i1, (55, 85, 345, 215), lambda p: min(p) > 200) > 10   # 黑底白字
    assert count_pred(i1, (205, 305, 375, 355), lambda p: max(p) < 90) > 5   # 白底黑字（回退）
    i2 = Image.open(os.path.join(outdir, "page2.png")).convert("RGB")
    assert count_pred(i2, (305, 55, 355, 545), lambda p: min(p) > 200) > 10  # 竖排白字
    i3 = Image.open(os.path.join(outdir, "page3.png")).convert("RGB")
    assert count_pred(i3, (285, 105, 390, 495), lambda p: min(p) > 200) > 10  # 合并气泡竖排白字
    assert hashlib.md5(open(os.path.join(comic, "page1.png"), "rb").read()).hexdigest() == h1
    print("嵌字 ✓  黑底白字反色 / 白底黑字回退 / 竖排 / 合并气泡整句渲染 / 原图未动")

    # ---------- ④ CBZ 流 ----------
    cbz = os.path.join(tmp, "vol1.cbz")
    with zipfile.ZipFile(cbz, "w") as z:
        z.writestr("p1.png", p1_bytes)
        z.writestr("p2.png", p2_bytes)
        z.writestr("p3.png", p3_bytes)
    hz = hashlib.md5(open(cbz, "rb").read()).hexdigest()
    sys.argv = ["comic_extract.py", cbz]
    ce.main()
    outz = json.load(open(os.path.join(tmp, "vol1_extracted.json"), encoding="utf-8"))
    assert set(outz) == {"Hello there.", "Goodbye.", "縦書きテスト", "右列左列"}, set(outz)
    json.dump(tr, open(os.path.join(tmp, "vol1_extracted_translated.json"), "w",
                       encoding="utf-8"), ensure_ascii=False)
    sys.argv = ["comic_apply.py", cbz, os.path.join(tmp, "vol1_extracted_translated.json")]
    ca.main()
    outcbz = os.path.join(tmp, "vol1.zh.cbz")
    assert os.path.exists(outcbz)
    with zipfile.ZipFile(outcbz) as z:
        assert sorted(z.namelist()) == ["p1.png", "p2.png", "p3.png"], z.namelist()
        Image.open(io.BytesIO(z.read("p3.png"))).verify()
    assert hashlib.md5(open(cbz, "rb").read()).hexdigest() == hz
    print("CBZ ✓  成员保持原名，输出 vol1.zh.cbz，原档案未动")
finally:
    mt_config.base_dir = _old_base
    mt_config.load_env = _old_env

shutil.rmtree(tmp, ignore_errors=True)   # Windows 下句柄释放或有延迟，容错清理
print("ALL TESTS PASS")
