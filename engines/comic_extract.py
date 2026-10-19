# -*- coding: utf-8 -*-
r"""
漫画提取器（图片文件夹 / CBZ → OCR）
====================================
逐页 OCR（rapidocr-onnxruntime，本地运行）收集台词：
- 重复台词去重（一话里出现两次只翻一次，且两处都替换）
- 纯符号区域（♪、拟声符号）不送翻、回写时也不动
- 页码/区域框存 sidecar（<名>_comic.json），回写由 comic_apply.py 负责

用法：
    python comic_extract.py <漫画文件夹或 .cbz 文件>
依赖：
    pip install rapidocr-onnxruntime     （GUI 拖入时会弹窗自动安装）
"""
import os, sys
_ENG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_ENG))    # 项目根：mt_config 等
sys.path.insert(0, _ENG)                     # 引擎同目录：comic_lib 等
import json
import mt_config
import comic_lib as lib

def page_target(pg):
    """OCR 输入：文件页给路径，zip 页给 bytes。"""
    if pg["kind"] == "zip":
        import zipfile
        with zipfile.ZipFile(pg["zip"]) as z:
            return z.read(pg["ref"])
    return pg["ref"]

def extract(path):
    """逐页 OCR → 气泡级聚类 → (扁平字典, sidecar pages)。"""
    pages = lib.collect_pages(path)
    out, side_pages = {}, []
    for i, pg in enumerate(pages, 1):
        try:
            target = page_target(pg)
            lines = [r for r in lib.ocr_regions(target)
                     if lib.has_word(r["text"])]
            regions = lib.cluster_regions(lines)    # 行级 → 气泡级（合并竖排列）
            if regions and lib.hybrid_enabled():
                try:
                    regions = lib.enhance_with_mocr(regions, target)
                except ImportError:
                    print("  ! manga-ocr 未安装，回退 rapidocr 识别文本")
                regions = [r for r in regions if lib.has_word(r["text"])]
        except ImportError:
            raise SystemExit("缺少 rapidocr-onnxruntime：请 pip install "
                             "rapidocr-onnxruntime（GUI 拖入漫画时会弹窗自动安装）")
        except Exception as e:
            print(f"  ! {os.path.basename(pg['ref'])} OCR 失败，跳过: {e}")
            continue
        for r in regions:
            out[r["text"]] = ""
        side_pages.append({"kind": pg["kind"], "zip": pg.get("zip"),
                           "ref": pg["ref"],
                           "fmt": os.path.splitext(pg["ref"])[1].lower().lstrip("."),
                           "regions": regions})
        if i % 5 == 0 or i == len(pages):
            print(f"    … {i}/{len(pages)} 页")
    return out, side_pages

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    pages = lib.collect_pages(path)
    if not pages:
        raise SystemExit("未找到漫画页（支持图片文件夹或 .cbz/.zip 档案）。")
    base = (os.path.splitext(os.path.basename(path))[0] if os.path.isfile(path)
            else (os.path.basename(os.path.normpath(path)) or "comic"))
    out, side_pages = extract(path)
    dst = os.path.join(mt_config.base_dir(), f"{base}_extracted.json")
    side = os.path.join(mt_config.base_dir(), f"{base}_comic.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"src": os.path.abspath(path), "pages": side_pages},
              open(side, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    chars = sum(len(k) for k in out)
    nreg = sum(len(p["regions"]) for p in side_pages)
    print(f"扫描 {len(side_pages)} 页，唯一台词 {len(out)} 条（{chars} 字符，{nreg} 处引用）")
    print(f"输出: {dst}")
    print(f"sidecar: {side}")
    print("下一步: python mt_clean.py \"" + os.path.basename(dst) +
          "\" && python mt_translate.py && python mt_apply.py \"" + os.path.basename(dst) + "\"")
    print("最后:   python comic_apply.py <漫画目录或.cbz> \"" +
          os.path.basename(dst).replace("_extracted.json", "_extracted_translated.json") + "\"")

if __name__ == "__main__":
    main()
