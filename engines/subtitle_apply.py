# -*- coding: utf-8 -*-
"""
字幕回写器（SRT / WebVTT / ASS·SSA）
====================================
把译文 {"原文": "译文"} 重建为新字幕文件，写到原文件旁边：
    ep01.srt → ep01.zh.srt（后缀 = 当前目标语言，非破坏性，原文件不动）

- 时间轴 / VTT 头 / ASS 样式完整保留（sidecar 或重新解析原文件）
- 未翻译或译文为空的条目自动保持原文 —— 半成品也能安全输出
- --bi 追加参数生成双语字幕（译文在上，原文在下）

用法：
    python subtitle_apply.py <目录或单个字幕文件> <译文json> [--bi]
"""
import os, sys
_ENG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_ENG))    # 项目根：mt_config 等
sys.path.insert(0, _ENG)                     # 引擎同目录：subtitle_lib 等
import json, glob
import mt_config
import subtitle_lib as lib
import subtitle_extract as sx

def find_sidecar(trfile):
    """译文文件名推导 sidecar；找不到就取同目录最新的 *_subs.json。"""
    cands = [trfile.replace("_extracted_translated.json", "_subs.json"),
             trfile.replace("_translated.json", "_subs.json")]
    for c in cands:
        if c != trfile and os.path.exists(c):
            return c
    g = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(trfile)), "*_subs.json")),
               key=os.path.getmtime, reverse=True)
    return g[0] if g else None

def out_path(fname, tl):
    stem, ext = os.path.splitext(fname)
    return f"{stem}.{tl}{ext}"

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Windows 控制台防 GBK 乱码；不换 wrapper 避免 GC 关流
    except Exception:
        pass
    path = sys.argv[1]
    trfile = sys.argv[2]
    bi = "--bi" in sys.argv
    tr = mt_config.load_loose_json(trfile)
    tl = sx.tl_suffix()

    side = find_sidecar(trfile)
    if side:
        entries = json.load(open(side, encoding="utf-8"))["files"]
        print(f"sidecar: {side}（{len(entries)} 个文件的时间轴）")
    else:
        print("未找到 sidecar，重新解析原字幕文件…")
        _, entries, _ = sx.extract(path)

    nfiles = napplied = ntotal = 0
    for entry in entries:
        src = entry["file"]
        if not os.path.exists(src):               # 用户挪动过文件：尝试按文件名重新收集
            print(f"  ! 原文件已不存在，跳过: {src}")
            continue
        parsed = {"format": entry["format"], "eol": entry["eol"], "items": entry["items"]}
        text, applied, total = lib.rebuild(parsed, tr, bi=bi)
        dst = out_path(src, tl)
        if os.path.abspath(dst) == os.path.abspath(src):
            dst = out_path(src, tl + ".new")
        with open(dst, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        nfiles += 1
        napplied += applied
        ntotal += total
        print(f"  + {os.path.basename(src)} → {os.path.basename(dst)}  "
              f"{applied}/{total} 条已翻译")
    mode = "（双语：译文在上原文在下）" if bi else ""
    print(f"字幕回写完成：{napplied}/{ntotal} 条已翻译，其余保持原文；"
          f"输出 {nfiles} 个文件（.{tl}. 后缀，原文件未改动）{mode}")

if __name__ == "__main__":
    main()
