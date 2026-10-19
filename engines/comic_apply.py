# -*- coding: utf-8 -*-
r"""
漫画回写器（嵌字）
==================
把译文 {"原文": "译文"} 嵌回页面：每个 OCR 区域用边缘取样底色填充后，
按框自动排版绘制译文（竖长框 + 中日文 → 竖排；字号自动收缩）。
未翻译的条目保持原文重绘，半成品也能安全输出。

输出非破坏性：
    文件夹  MyManga/  → 同级 MyManga.zh/
    单档案  vol1.cbz  → 同级 vol1.zh.cbz

用法：
    python comic_apply.py <漫画文件夹或 .cbz> <译文json>
依赖：
    pip install Pillow     （GUI 会弹窗自动安装；字体用系统 CJK 字体，可用 .env MT_FONT 指定）
"""
import os, sys, zipfile
_ENG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_ENG))    # 项目根：mt_config 等
sys.path.insert(0, _ENG)                     # 引擎同目录：comic_lib 等
import json, glob
import mt_config
import comic_lib as lib
import subtitle_extract as sx    # tl_suffix 复用

def find_sidecar(trfile):
    cands = [trfile.replace("_extracted_translated.json", "_comic.json"),
             trfile.replace("_translated.json", "_comic.json")]
    for c in cands:
        if c != trfile and os.path.exists(c):
            return c
    g = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(trfile)),
                                      "*_comic.json")),
               key=os.path.getmtime, reverse=True)
    return g[0] if g else None

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    path = sys.argv[1]
    trfile = sys.argv[2]
    tr = mt_config.load_loose_json(trfile)
    tl = sx.tl_suffix()
    side = find_sidecar(trfile)
    if not side:
        raise SystemExit(f"未找到 sidecar（*_comic.json）。请先运行 comic_extract.py，"
                         f"译文应来自其输出 {os.path.basename(trfile)}。")
    src = json.load(open(side, encoding="utf-8"))
    pages = src["pages"]
    if not pages:
        raise SystemExit("sidecar 里没有页面数据（提取时一页都没 OCR 成功？）")
    if lib.find_font(20) is None:
        raise SystemExit("未找到可用的 CJK 字体。请在 .env 里用 MT_FONT 指定一个字体文件路径"
                         "（如 C:\\Windows\\Fonts\\msyh.ttc）。")

    from PIL import Image, ImageDraw

    def pick(tr_key):
        v = tr.get(tr_key, "")
        return v.strip() if isinstance(v, str) else ""

    def render_text(r):
        """译文优先，绘制前清洗两端装饰符号；洗成空串则保持原样不嵌。"""
        zh = pick(r["text"])
        txt = lib.clean_target(zh) if zh else ""
        if not txt:
            txt = lib.clean_target(r["text"])
        return txt, bool(zh)

    nreg = napplied = 0
    if src["src"].lower().endswith((".cbz", ".zip")):
        out_path = os.path.splitext(src["src"])[0] + f".{tl}.cbz"
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as zout:
            for pg in pages:
                img = lib.load_page_image(pg)
                d = ImageDraw.Draw(img)
                for r in pg["regions"]:
                    nreg += 1
                    txt, zh = render_text(r)
                    if txt:
                        lib.draw_region(d, img, r["box"], txt, tl)
                        napplied += bool(zh)
                data, _ = lib.page_bytes(pg, img)
                zout.writestr(pg["ref"], data)
    else:
        out_path = src["src"].rstrip("\\/") + f".{tl}"
        os.makedirs(out_path, exist_ok=True)
        for pg in pages:
            img = lib.load_page_image(pg)
            d = ImageDraw.Draw(img)
            for r in pg["regions"]:
                nreg += 1
                txt, zh = render_text(r)
                if txt:
                    lib.draw_region(d, img, r["box"], txt, tl)
                    napplied += bool(zh)
            rel = os.path.relpath(pg["ref"], src["src"])
            data, ext = lib.page_bytes(pg, img)
            dstf = os.path.join(out_path, rel)
            os.makedirs(os.path.dirname(dstf) or out_path, exist_ok=True)
            root, _ = os.path.splitext(dstf)
            with open(root + ext, "wb") as f:
                f.write(data)
    lib.close_zips()
    print(f"嵌字完成：{napplied}/{nreg} 处已翻译，其余按原文重绘；"
          f"输出 {len(pages)} 页 → {out_path}（原文件未改动）")

if __name__ == "__main__":
    main()
