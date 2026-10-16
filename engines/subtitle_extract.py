# -*- coding: utf-8 -*-
r"""
字幕提取器（SRT / WebVTT / ASS·SSA）
====================================
把字幕文件里的台词汇成 OmniTrans 管线兼容的 {"原文": ""} 扁平字典：
- 重复台词自动去重（一部剧里说两遍的话只翻一次，且保证两次都替换）
- 行内标记（<i>、{\an8}、ASS {\...} 与 \N）剥离后再送翻
- 时间轴/样式完整保留在 sidecar（<名>_subs.json）里，回写由 subtitle_apply.py 负责
- 编码自动探测：BOM / UTF-8 / GBK / Big5 / Shift_JIS / cp1252

用法：
    python subtitle_extract.py <目录或单个字幕文件>     # 输出 <名>_extracted.json + <名>_subs.json
"""
import os, sys
_ENG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_ENG))    # 项目根：mt_config 等
sys.path.insert(0, _ENG)                     # 引擎同目录：subtitle_lib 等
import json
import mt_config
import subtitle_lib as lib

def tl_suffix():
    """当前目标语言的短码（zh-CN → zh），用于跳过我们自己生成的输出文件。"""
    tl = mt_config.load_env().get("MT_TL", "zh-CN")
    return tl.replace("_", "-").split("-")[0].lower() or "zh"

def is_own_output(fname):
    """排除本工具生成的 <原名>.<tl>.srt，防止重复提取自己上次的产物。"""
    tl = tl_suffix()
    low = fname.lower()
    return any(low.endswith(f".{tl}{ext}") for ext in lib.SUB_EXTS)

def collect(path):
    """目录 → 递归收集全部字幕文件（排序保证确定性）；文件 → [该文件]。"""
    if os.path.isfile(path):
        return [path]
    out = []
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for f in sorted(files):
            if f.lower().endswith(lib.SUB_EXTS) and not is_own_output(f):
                out.append(os.path.join(root, f))
    return out

def base_name(path):
    if os.path.isfile(path):
        return os.path.splitext(os.path.basename(path))[0]
    b = os.path.basename(os.path.normpath(path))
    return b if b else "subs"

def extract(path):
    """解析全部字幕 → (扁平字典, sidecar entries)。"""
    out, entries, ncue = {}, [], 0
    for f in collect(path):
        try:
            with open(f, "rb") as fp:
                data = fp.read()
            parsed = lib.parse(data, lib._fmt_of(f))
        except Exception as e:
            print(f"  ! 跳过无法解析的文件 {f}: {e}")
            continue
        cnt = 0
        for t in lib.iter_texts(parsed):
            if lib.has_word(t):
                out[t] = ""
                cnt += 1
        ncue += cnt
        entries.append({"file": os.path.abspath(f), "format": parsed["format"],
                        "eol": parsed["eol"], "items": parsed["items"]})
        print(f"  + {os.path.basename(f)}  [{parsed['format']}/{parsed['enc']}]  {cnt} 条")
    return out, entries, ncue

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Windows 控制台防 GBK 乱码；不换 wrapper 避免 GC 关流
    except Exception:
        pass
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    base = base_name(path)
    out, entries, ncue = extract(path)
    dst = os.path.join(mt_config.base_dir(), f"{base}_extracted.json")
    side = os.path.join(mt_config.base_dir(), f"{base}_subs.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"files": entries}, open(side, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    chars = sum(len(k) for k in out)
    print(f"扫描 {len(entries)} 个字幕文件，唯一台词 {len(out)} 条（{chars} 字符，{ncue} 处引用）")
    print(f"输出: {dst}")
    print(f"sidecar: {side}")
    print("下一步: python mt_clean.py \"" + os.path.basename(dst) + "\" && python mt_translate.py && python mt_apply.py \"" + os.path.basename(dst) + "\"")
    print("最后:   python subtitle_apply.py <目录或字幕> \"" +
          os.path.basename(dst).replace("_extracted.json", "_extracted_translated.json") + "\"")

if __name__ == "__main__":
    main()
