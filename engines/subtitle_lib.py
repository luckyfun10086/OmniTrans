# -*- coding: utf-8 -*-
r"""
字幕解析/重建共享库（SRT / WebVTT / ASS·SSA）
================================================
subtitle_extract.py 与 subtitle_apply.py 共用。

设计（sidecar 方案，配合 OmniTrans 管线）：
- 解析结果 = 有序 items 列表，每个 item 是
    {"kind": "raw", "lines": [...]}                      原样保留的块（VTT 头/NOTE/STYLE/垃圾行）
    {"kind": "cue", "id": ..., "timing": ..., "text": ..} SRT/VTT 字幕条（text 为去标签后的送翻文本）
    {"kind": "dlg", "pre": "Dialogue:..9字段..,", "text": .., "orig": ..}  ASS 对话行（只换 Text 字段）
- 提取端把所有 cue/dlg 的 text 汇入扁平 {"原文": ""} 字典（重复台词自动去重，只翻一次）
- 回写端按 items 顺序重建文件：查字典换文本，未翻译/缺失保持原文 —— 整个过程非破坏性，
  输出写到 <原名>.<目标语言>.<原扩展>（如 ep01.zh.srt），原字幕文件不动
- 行内标记（<i>、{\an8}、ASS \N 与 {\...} 覆盖标签）在送翻前剥离：机翻极易吃掉它们，
  且剥离后译文仍可读；时间轴/样式字段原样保留
"""
import re

SUB_EXTS = (".srt", ".vtt", ".ass", ".ssa")

# ---------------- 编码探测（零依赖启发式） ----------------
# 现代字幕几乎都是 UTF-8；老资源常见 GBK / Big5 / Shift_JIS / cp1252。
# BOM → UTF-8 严格 → 按文字特征打分（假名=日、简体独有字=GBK、繁体独有字=Big5）。

_KANA_RE = re.compile(r"[ぁ-んァ-ヶ]")
_CJK_RE = re.compile(r"[ぁ-んァ-ヶ一-龯豈-﫿]")
# 简体/繁体独有高频字（避开日文新字体共用的 国/会/画 等）
_SIMP_MARKERS = "们时说对发过还进应见车长东门马风飞关观华价开无书业网义乐习这为记电话动经"
_TRAD_MARKERS = "們時說對發過還進應見車長東門馬風飛關觀華價開無書業網義樂習這為記電話動經"

def _fmt_of(name):
    n = name.lower()
    if n.endswith(".vtt"):
        return "vtt"
    if n.endswith(".ass") or n.endswith(".ssa"):
        return "ass"
    return "srt"

def smart_decode(data):
    """bytes → (文本, 编码名)。按 BOM / UTF-8 / CJK 特征分 / cp1252 兜底。"""
    import codecs
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig"), "utf-8-sig"
    for bom, enc in ((codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
                     (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16")):
        if data.startswith(bom):
            try:
                return data.decode(enc), enc
            except UnicodeDecodeError:
                break
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    cands = {}
    for enc in ("shift_jis", "gb18030", "big5"):
        try:
            cands[enc] = data.decode(enc)
        except UnicodeDecodeError:
            pass
    # 假名是日文的硬特征（GBK/Big5 字节解不出成串假名）
    ja = cands.get("shift_jis")
    if ja is not None and len(_KANA_RE.findall(ja)) >= 3:
        return ja, "shift_jis"
    gb, b5 = cands.get("gb18030"), cands.get("big5")

    def _marks(t, chars):
        return sum(t.count(c) for c in chars)

    if b5 is not None and gb is not None and _marks(b5, _TRAD_MARKERS) > _marks(gb, _SIMP_MARKERS):
        return b5, "big5"
    # CJK 字符占比 ≥10% 才认为是中文（避免把西文 accented 字节误判成汉字垃圾）
    if gb is not None and len(_CJK_RE.findall(gb)) * 10 > len(gb):
        return gb, "gb18030"
    if b5 is not None and len(_CJK_RE.findall(b5)) * 10 > len(b5):
        return b5, "big5"
    if ja is not None:
        return ja, "shift_jis"          # 无假名的纯汉字日文兜底
    return data.decode("cp1252", "replace"), "cp1252"

def detect_eol(data):
    return "\r\n" if b"\r\n" in data[:8192] else "\n"

# ---------------- 送翻文本清洗（剥标记） ----------------

_HTML_TAG = re.compile(r"</?[A-Za-z0-9][^<>]*>")   # <i> </b> <font ..> <c.x> <v 名字> <00:01.000>
_SRT_CTRL = re.compile(r"\{\\[^}]*\}")              # SRT 定位/特效 {\an8}
_ASS_OVR = re.compile(r"\{[^}]*\}")                 # ASS 覆盖标签 {\pos(..)}

def clean_text(t, fmt):
    """字幕原始文本 → 送翻文本：剥标记、统一换行、去首尾空白行。"""
    if fmt == "ass":
        t = _ASS_OVR.sub("", t)
        t = t.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
    else:
        t = _HTML_TAG.sub("", t)
        t = _SRT_CTRL.sub("", t)
    lines = [ln.rstrip() for ln in t.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)

# 判断是否含有可翻译内容（纯音符/数字/符号的条目不值得送翻）
_WORD_RE = re.compile(r"[0-9A-Za-z\u00c0-\u024f\u0370-\u03ff\u0400-\u04ff\u3040-\u30ff"
                      r"\u3400-\u9fff\uac00-\ud7af\uff66-\uff9f]")

def has_word(t):
    return bool(_WORD_RE.search(t))

# ---------------- SRT / VTT 解析 ----------------

def _parse_srt_vtt(text):
    """行扫描：timing 行（含 -->）前一行视为条目 id，其后到空行为文本；
    NOTE/STYLE/REGION 块与其余散行原样保留为 raw。"""
    lines = text.splitlines()
    items, pend = [], []
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if not ln.strip():
            if pend:
                items.append({"kind": "raw", "lines": pend})
                pend = []
            i += 1
            continue
        if "-->" in ln:
            cue_id = None
            if pend:
                if len(pend) == 1:
                    cue_id = pend[0]
                else:
                    items.append({"kind": "raw", "lines": pend})
                pend = []
            raw = []
            i += 1
            while i < n and lines[i].strip():
                raw.append(lines[i])
                i += 1
            items.append({"kind": "cue", "id": cue_id, "timing": ln.strip(),
                          "text": raw and clean_text("\n".join(raw), "srt") or ""})
            continue
        u = ln.lstrip().upper()
        if u.startswith(("NOTE", "STYLE", "REGION")) and not u.startswith("NOTES"):
            block = [ln]
            i += 1
            while i < n and lines[i].strip():
                block.append(lines[i])
                i += 1
            items.append({"kind": "raw", "lines": block})
            continue
        pend.append(ln)
        i += 1
    if pend:
        items.append({"kind": "raw", "lines": pend})
    return items

# ---------------- ASS / SSA 解析 ----------------

def _parse_ass(text):
    """整文件按行分类：Dialogue: 行解析为 dlg（前 9 字段原样保留），其余原样 raw。
    Comment:/Title: 等行不受影响，样式段完整保留。"""
    items = []
    for ln in text.splitlines():
        if ln.lstrip().lower().startswith("dialogue:"):
            head, _, body = ln.partition(":")
            fields = body.split(",", 9)
            if len(fields) == 10:
                items.append({"kind": "dlg",
                              "pre": head + ":" + ",".join(fields[:9]) + ",",
                              "orig": fields[9],
                              "text": clean_text(fields[9], "ass")})
                continue
        items.append({"kind": "raw", "lines": [ln]})
    return items

def parse(data, fmt):
    """bytes + 格式 → {"format","eol","items"}。"""
    text, enc = smart_decode(data)
    if fmt == "ass":
        items = _parse_ass(text)
    else:
        items = _parse_srt_vtt(text)
    return {"format": fmt, "eol": detect_eol(data), "enc": enc, "items": items}

def iter_texts(parsed):
    """产出所有可翻译条目文本。"""
    for it in parsed["items"]:
        if it["kind"] in ("cue", "dlg") and it["text"]:
            yield it["text"]

# ---------------- 重建（回写） ----------------

def _pick(tr, key):
    """查译文：缺失/空白/类型不对一律视为未翻译。"""
    v = tr.get(key, "")
    return v.strip() if isinstance(v, str) else ""

def rebuild(parsed, tr, bi=False):
    """按 items 重建完整字幕文本。tr 为 {"原文": "译文"}；未翻译保持原文。"""
    eol = parsed["eol"]
    out = []
    applied = 0
    total = 0
    for it in parsed["items"]:
        if it["kind"] == "raw":
            out.extend(it["lines"])
            out.append("")
            continue
        total += 1
        zh = _pick(tr, it["text"])
        if zh:
            applied += 1
            txt = zh + "\n" + it["text"] if bi else zh
        else:
            txt = it["text"]
        if it["kind"] == "dlg":
            out.append(it["pre"] + txt.replace("\n", "\\N"))
        else:
            if it.get("id") is not None:
                out.append(it["id"])
            out.append(it["timing"])
            out.extend(txt.split("\n"))
        out.append("")
    while out and out[-1] == "":
        out.pop()
    return eol.join(out) + eol, applied, total
