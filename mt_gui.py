# -*- coding: utf-8 -*-
"""
OmniTrans 上位机（GUI，中英双语，三大功能分区）
=============================================
- 标签页分区：⚡快速翻译（json 管线）/ 🎮游戏汉化（引擎识别→提取→翻译→导入）
  / ⚙设置（翻译接口配置）
- 顶部 中/EN 切换按钮，所有界面文字即时切换，选择持久化到 .env (MT_LANG)
- 拖拽 json 走翻译管线；拖游戏目录/EXE/字幕/音视频/漫画自动按内容识别路由：
  单文件按扩展名判意图（拖的是它），目录按内容判（游戏 > 媒体 > 字幕 > 漫画）
- 拖拽支持需要 tkinterdnd2：pip install tkinterdnd2（未装时用「选择文件」按钮）
"""
import json, re, sys, io, os, time, queue, random, hashlib, threading, traceback
import urllib.request, urllib.parse
from collections import Counter

import mt_config

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

try:
    import sv_ttk                # Sun Valley 主题（Windows 11 风格，亮/暗）
    HAS_SVTTK = True
except ImportError:
    HAS_SVTTK = False

# ---------------- 界面文案（中/英） ----------------
S = {
    "zh": {
        "title": "OmniTrans — 游戏一键机翻汉化",
        "lang_btn": "EN", "lang_of": "中文",
        "src": "源语言:", "tgt": "→ 目标语言:",
        "names_hint": "（人名表：json 同目录或本工具目录 names.txt）",
        "autonames": "自动识别人名并保持一致",
        "api_frame": "翻译接口（个人配置，保存到本机 .env，不会上传）",
        "url": "URL:", "key": "Key:", "header": "请求头:",
        "save_env": "保存到 .env",
        "api_hint": "MT·GET：URL 用 {sl}/{tl}/{q} 占位符，留默认=免费端点 | AI·OpenAI：URL 填 chat/completions 地址+模型名，支持 DeepSeek/Kimi/GLM/OpenRouter/Ollama 等",
        "drop": "拖入 JSON / 游戏目录 / 字幕 / 音视频 / 漫画\n（或点击选择文件）",
        "drop_nodnd": "\n（提示：pip install tkinterdnd2 可启用拖拽）",
        "start": "开始翻译", "cancel": "取消", "open_out": "打开输出文件夹",
        "waiting": "等待文件…", "ready": "已就绪：{}", "done_stage": "③ 完成！",
        "stage_clean": "① 文本清洗", "stage_trans": "② 机翻翻译", "stage_apply": "③ 回填校验",
        "cancelled": "已取消", "error": "出错了",
        "msg_done_t": "翻译完成", "msg_done_b": "已翻译 {} 条（{} 条校验失败保持原文）。\n\n输出文件：\n{}",
        "msg_badurl": "接口 URL 有误", "msg_saved": "已保存",
        "msg_saved_b": "配置已写入：\n{}", "msg_savefail": "保存失败",
        "msg_type": "文件类型", "msg_type_b": "请拖入 .json 文件（MTool 导出的 ManualTransFile.json）",
        "sel_file": "选择 MTool 导出的 json",
        "no_trans": "没有需要翻译的条目（可能上次已全部翻完），已直接输出。",
        # 管线日志
        "log_auton": "自动识别专有名词 {} 个（已自动保持原文一致）: {}",
        "log_auton_off": "自动人名识别已关闭：仅使用 names.txt 中的人工词条",
        "log_zhko": "源语言为中文/韩文：无法自动识别人名，建议在 names.txt 中列出以保持一致",
        "log_clean": "清洗完成：待翻 {} 条，人名表 {} 词",
        "log_trans_b": "机翻开始（批量模式）：{} 条",
        "log_trans_s": "机翻开始（分段模式）：{} 条",
        "log_trans_ok": "机翻完成：{} 条，用时 {:.1f} 分钟",
        "log_apply": "回填：成功 {}，记号丢失 {}，换行异常 {}",
        "log_seg": "自动进入分段扫尾模式重翻失败条目…",
        "log_speed": "{:.1f}条/秒 剩余{:.0f}分", "log_calc": "计算中",
        "log_cancel": "正在取消…（等待当前请求结束）",
        "log_cancelled": "已取消。进度已保存，重新开始可断点续翻。",
        "log_cfg": "配置已保存到 {}（.env 已被 .gitignore 排除，不会上传）",
        "log_start": "开始：{} → {}",
        # ---- 游戏汉化页 ----
        "tab_quick": "⚡ 快速翻译",
        "tab_game": "🎮 游戏汉化",
        "tab_cfg": "⚙ 设置",
        "g_title": "一键翻译（拖入游戏目录/EXE、字幕、音视频、漫画，自动识别）",
        "g_drop": "拖入游戏目录 / EXE / 字幕 / 音视频 / 漫画到窗口任意位置",
        "g_engine": "引擎：{}",
        "g_unknown": "未识别",
        "g_steps": "流程：① 识别引擎 → ② 提取文本 → ③ 机器翻译 → ④ 导入游戏",
        "g_extract": "② 提取文本",
        "g_translate": "③ 开始翻译",
        "g_apply": "④ 导入游戏",
        "g_need_extract": "请先提取文本",
        "g_need_translate": "请先完成翻译",
        "g_extracting": "提取中…",
        "g_extracted": "已提取：{}",
        "g_backup_note": "回写自动备份：Kirikiri/Ren'Py 非破坏（patch/tl 包）；其余引擎备份 .automt.bak / *_backup",
        "g_supported": "已支持",
        "g_unsupported": "可识别·暂不支持",
        "g_engine_table": "引擎支持总览",
        "g_col_engine": "引擎 Engine",
        "g_col_status": "支持状态",
        # ---- 背景图 ----
        "bg_label": "背景图片:", "bg_pick": "选择图片…", "bg_clear": "清除",
        "bg_none": "（未设置；设置后显示在「快速翻译」页投放卡）",
        "bg_hint": "PNG/JPG，自动裁切铺满投放卡；需 Pillow（缺失时自动提示安装）",
        "bg_title": "选择背景图片",
        "bg_pillow_q": ("背景图片功能需要 Pillow 库（当前未检测到）。\n\n"
                        "是否自动安装？（需要 Python 和 pip）\n"
                        "Background images require Pillow (not found). Install automatically?"),
        "bg_pillow_fail": "Pillow 安装失败",
        # ---- 图书馆 ----
        "tab_lib": "📚 图书馆",
        "lib_title": "本地翻译记录（library.json，保存在本工具目录；翻译完成自动收录）",
        "lib_col_name": "游戏名", "lib_col_engine": "引擎",
        "lib_col_count": "条数", "lib_col_status": "状态", "lib_col_date": "日期",
        "lib_st_done": "已翻译", "lib_st_applied": "✓ 已导入游戏",
        "lib_open_game": "打开游戏目录", "lib_open_out": "打开译文", "lib_del": "删除记录",
        "lib_empty": "还没有记录——去翻译一个游戏吧（翻译完成会自动出现在这里）",
        "lib_sel": "请先在表中选中一个游戏",
        # ---- 译文微调 ----
        "tab_review": "✏️ 译文微调",
        "rv_title": "翻译完成后、导入游戏前，在这里检查并修改译文（双击译文编辑）",
        "rv_load": "加载译文", "rv_save": "保存修改",
        "rv_col_orig": "原文", "rv_col_zh": "译文",
        "rv_search": "搜索原文/译文…",
        "rv_none": "未加载。点击「加载译文」（默认找最新的 *_translated.json）",
        "rv_dirty": "本次已修改 {} 条",
        "rv_limit": "文件共 {} 条，先显示前 {} 条——输入关键词可筛选全部",
        "rv_saved": "已保存到 {}（{} 条，含修改 {} 条）",
        "rv_pick": "选择译文 json",
        "rv_edit_t": "修改译文",
        "rv_orig": "原文（只读）", "rv_new": "译文（可编辑）",
        "rv_ok": "保存此条", "rv_cancel": "取消",
        # ---- MTool 导出 ----
        "g_mtool": "📤 导出 MTool 用 json",
        "g_mtool_no": "未找到已翻译的 json（先完成翻译）",
        "g_mtool_ok": ("已导出 {} 键（含形态变体）→ {}\n\n"
                       "MTool 用法：文件已在游戏目录且名为 ManualTransFile.json，\n"
                       "用「与工具一同启动.bat」启动游戏即可加载。"),
        "g_mtool_nogame": "未识别游戏目录——将导出到译文同目录",
    },
    "en": {
        "title": "OmniTrans — One-click Game Translator",
        "lang_btn": "中文", "lang_of": "EN",
        "src": "Source:", "tgt": "→ Target:",
        "names_hint": "(names list: names.txt next to the json or next to this tool)",
        "autonames": "Auto-detect names & keep consistent",
        "api_frame": "Translation API (personal config, saved to local .env, never uploaded)",
        "url": "URL:", "key": "Key:", "header": "Header:",
        "save_env": "Save to .env",
        "api_hint": "MT·GET: URL with {sl}/{tl}/{q} placeholders, default = free endpoint | AI·OpenAI: full chat/completions URL + model (DeepSeek/Kimi/GLM/OpenRouter/Ollama…)",
        "drop": "Drop JSON / a game folder / subtitles / video / comics here\n(or click to browse)",
        "drop_nodnd": "\n(tip: pip install tkinterdnd2 enables drag & drop)",
        "start": "Start", "cancel": "Cancel", "open_out": "Open output folder",
        "waiting": "Waiting for a file…", "ready": "Ready: {}", "done_stage": "③ Done!",
        "stage_clean": "① Clean & mask", "stage_trans": "② Translate", "stage_apply": "③ Validate & apply",
        "cancelled": "Cancelled", "error": "Error",
        "msg_done_t": "Translation complete",
        "msg_done_b": "Translated {} strings ({} failed validation, kept original).\n\nOutput file:\n{}",
        "msg_badurl": "Invalid API URL", "msg_saved": "Saved",
        "msg_saved_b": "Configuration written to:\n{}", "msg_savefail": "Save failed",
        "msg_type": "File type", "msg_type_b": "Please drop a .json file (MTool-exported ManualTransFile.json)",
        "sel_file": "Select MTool-exported json",
        "no_trans": "Nothing to translate (possibly all done in a previous run); output written directly.",
        "log_auton": "Auto-detected {} proper nouns (kept consistent): {}",
        "log_auton_off": "Auto name detection off: using only manual names.txt entries",
        "log_zhko": "Source is Chinese/Korean: no auto name detection, list names in names.txt for consistency",
        "log_clean": "Clean done: {} strings to translate, names list {} entries",
        "log_trans_b": "Translating (batch mode): {} strings",
        "log_trans_s": "Translating (segment mode): {} strings",
        "log_trans_ok": "Translation done: {} strings in {:.1f} min",
        "log_apply": "Apply: ok {}, token-lost {}, newline-mismatch {}",
        "log_seg": "Falling back to segment-wise mode for failed strings…",
        "log_speed": "{:.1f}/s, ~{:.0f} min left", "log_calc": "calculating",
        "log_cancel": "Cancelling… (waiting for current request)",
        "log_cancelled": "Cancelled. Progress saved; restart to resume.",
        "log_cfg": "Config saved to {} (.env is gitignored, never uploaded)",
        "log_start": "Start: {} → {}",
        # ---- Game localization tab ----
        "tab_quick": "⚡ Quick Translate",
        "tab_game": "🎮 Game Localization",
        "tab_cfg": "⚙ Settings",
        "g_title": "One-click translation (drop a game folder/EXE, subtitles, video or comics — auto-detected)",
        "g_drop": "Drop a game folder / EXE / subtitles / video / comics anywhere in the window",
        "g_engine": "Engine: {}",
        "g_unknown": "Not detected",
        "g_steps": "Flow: ① Detect → ② Extract → ③ Translate → ④ Apply to game",
        "g_extract": "② Extract text",
        "g_translate": "③ Translate",
        "g_apply": "④ Apply to game",
        "g_need_extract": "Extract text first",
        "g_need_translate": "Finish translation first",
        "g_extracting": "Extracting…",
        "g_extracted": "Extracted: {}",
        "g_backup_note": "Backups: Kirikiri/Ren'Py non-destructive (patch/tl packages); other engines keep .automt.bak / *_backup",
        "g_supported": "Supported",
        "g_unsupported": "Detected · not supported",
        "g_engine_table": "Engine support overview",
        "g_col_engine": "Engine",
        "g_col_status": "Status",
        # ---- Background image ----
        "bg_label": "Background:", "bg_pick": "Choose image…", "bg_clear": "Clear",
        "bg_none": "(not set — shown on the Quick Translate drop card)",
        "bg_hint": "PNG/JPG, cover-cropped onto the drop card; needs Pillow (auto-install prompt if missing)",
        "bg_title": "Choose a background image",
        "bg_pillow_q": ("Background images require the Pillow library (not found).\n\n"
                        "Install automatically? (requires Python & pip)"),
        "bg_pillow_fail": "Pillow installation failed",
        # ---- Library ----
        "tab_lib": "📚 Library",
        "lib_title": "Local translation records (library.json next to the exe; entries are added automatically when a translation finishes)",
        "lib_col_name": "Game", "lib_col_engine": "Engine",
        "lib_col_count": "Strings", "lib_col_status": "Status", "lib_col_date": "Date",
        "lib_st_done": "Translated", "lib_st_applied": "✓ Applied to game",
        "lib_open_game": "Open game folder", "lib_open_out": "Open output", "lib_del": "Delete entry",
        "lib_empty": "No records yet — translate a game and it will appear here automatically",
        "lib_sel": "Select a game in the table first",
        # ---- Review / fine-tune ----
        "tab_review": "✏️ Review",
        "rv_title": "Check & fix translations after translating, before applying to the game (double-click a row to edit)",
        "rv_load": "Load output", "rv_save": "Save changes",
        "rv_col_orig": "Original", "rv_col_zh": "Translation",
        "rv_search": "Search original/translation…",
        "rv_none": "Nothing loaded. Click [Load output] (picks the newest *_translated.json)",
        "rv_dirty": "{} entries edited this session",
        "rv_limit": "{} entries in file, showing first {} — type a keyword to filter all",
        "rv_saved": "Saved to {} ({} entries, {} edited)",
        "rv_pick": "Choose a translated json",
        "rv_edit_t": "Edit translation",
        "rv_orig": "Original (read-only)", "rv_new": "Translation (editable)",
        "rv_ok": "Save entry", "rv_cancel": "Cancel",
        # ---- MTool export ----
        "g_mtool": "📤 Export for MTool",
        "g_mtool_no": "No translated json found (finish a translation first)",
        "g_mtool_ok": ("Exported {} keys (with form variants) → {}\n\n"
                       "For MTool: keep the file in the game folder as ManualTransFile.json\n"
                       "and launch via the MTool launcher bat."),
        "g_mtool_nogame": "No game folder detected — exporting next to the json",
    },
}

# ---------------- 翻译管线（与命令行版同源） ----------------
BS = chr(92)
MASK_PATTERNS = [
    re.compile(BS * 2 + r'js<[^>]*>'),
    re.compile(BS * 2 + r'js\[[^\]]*\]'),
    re.compile(BS * 2 + r'[cCvVnNiI]\[\d+\]'),
    re.compile(BS * 2 + r'[fgFf][bBiI]\[[^\]]*\]'),
    re.compile(BS * 2 + r'.'),
]
tokre = re.compile(r"〔T[0-9a-f]{8}〕")
loose = re.compile(r"[〔【\[\(（]\s*[TtＴ]\s*([0-9a-fA-F]{8})\s*[〕】\]\)）]")
FW = str.maketrans("０１２３４５６７８９ａｂｃｄｅｆＡＢＣＤＥＦ", "0123456789abcdefABCDEF")
VALID_NEXT = set('nNvVcCiIpPGFSfuwMLjsbot' + BS + '{}<>|.^^$[]()')
LANGS = [("English", "en"), ("Auto · 自动", "auto"), ("日本語", "ja"), ("한국어", "ko"),
         ("Русский", "ru"), ("Français", "fr"), ("Deutsch", "de"), ("Español", "es"),
         ("Português", "pt"), ("Italiano", "it"), ("ไทย", "th"), ("Tiếng Việt", "vi"),
         ("Bahasa", "id"), ("中文(简)", "zh-CN"), ("中文(繁)", "zh-TW")]

def stable_tok(orig):
    return "〔T" + hashlib.md5(orig.encode("utf-8")).hexdigest()[:8] + "〕"

def canon(s):
    return loose.sub(lambda m: f"〔T{m.group(1).lower()}〕", s.translate(FW))

class Cancel(Exception):
    pass

class _NoCloseBytesIO(io.BytesIO):
    """close() 恒为 no-op：旧引擎脚本丢弃其 stdout wrapper 时，GC 的 flush 保留、
    对底层的 close 拦下——否则 BytesIO 被关死，缓存输出再也读不回来。"""
    def close(self):
        pass

class _StreamCap:
    """worker 线程里的 stdout 代理：整行实时转发到 GUI 日志队列（长任务如 Whisper
    听译能看到进度，不再"假死"）。兼容两类引擎脚本：
    - 新脚本调用 sys.stdout.reconfigure(...) → no-op（str 直通，天然无编码问题）
    - 旧脚本 sys.stdout = TextIOWrapper(sys.stdout.buffer, ...) → 落到 self.buffer
      （BytesIO），跑完后按旧逻辑取末尾行，行为不变
    """
    def __init__(self, q):
        self.q = q
        self.lines = []                        # 已流出的整行（错误路径复用）
        self.buffer = _NoCloseBytesIO()        # 旧引擎替换 stdout 后的落点
        self._buf = ""

    def write(self, s):
        if not isinstance(s, str):
            return len(s)
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip("\r")
            if line.strip():
                self.lines.append(line)
                self.q.put(("log", "  | " + line))
        return len(s)

    def flush(self):
        if self._buf.strip():
            self.lines.append(self._buf.rstrip())
            self.q.put(("log", "  | " + self._buf.rstrip()))
        self._buf = ""

    def reconfigure(self, **kw):     # 新引擎的 utf-8 reconfigure 在代理上无意义
        pass

    def buf_tail(self, n=6):
        """旧引擎通道（BytesIO）末尾行——成功路径只补这一通道，避免与流式重复。"""
        try:
            self.buffer.seek(0)
            return [l for l in self.buffer.read().decode("utf-8", "replace").splitlines()
                    if l.strip()][-n:]
        except Exception:
            return []

    def tail(self, n=6):
        """新旧两条通道合并取末尾 n 行。"""
        lines = list(self.lines)
        try:
            self.buffer.seek(0)
            lines += [l for l in self.buffer.read().decode("utf-8", "replace").splitlines()
                      if l.strip()]
        except Exception:
            pass
        return [l for l in lines if l.strip()][-n:]

class Pipe:
    """三段式管线；cb(stage, done, total, note)；log(msg)"""
    def __init__(self, src_json, workdir, sl, tl, cancel, cb, log,
                 endpoint=None, api_key=None, api_header=None, auto_names=True, lang="zh",
                 api_type="get", model=None, fallback=True, fallback_endpoint=None):
        self.src, self.work, self.sl, self.tl = src_json, workdir, sl, tl
        self.cancel, self.cb, self.log = cancel, cb, log
        self.api_type = api_type
        self.model = model
        self.api_key = api_key
        self.api_header = api_header
        self.endpoint = (endpoint or "").strip() or mt_config.DEFAULT_ENDPOINT
        self.headers = mt_config.build_headers(api_key, api_header)
        self.auto_names = auto_names
        self.fallback = fallback
        self.fallback_endpoint = (fallback_endpoint or "").strip() or mt_config.DEFAULT_ENDPOINT
        self.policy_skips = 0
        self.fallback_saved = 0
        self.ai_degraded = 0
        self._no_ctx = False
        self.L = S[lang if lang in S else "zh"]

    def load_names(self):
        names = []
        base = mt_config.base_dir()
        for cand in (os.path.join(os.path.dirname(self.src), "names.txt"),
                     os.path.join(base, "names.txt")):
            if os.path.exists(cand):
                for line in open(cand, encoding="utf-8-sig"):
                    n = line.strip()
                    if n and not n.startswith("#"):
                        names.append(n)
                break
        return names

    def mask(self, s, tokens, names, name_zh):
        parts = s.split("\n")
        out = []
        for pi, part in enumerate(parts):
            if pi:
                t = stable_tok("\n")
                tokens[t] = "\n"
                out.append(t)
            buf = part
            changed = True
            while changed:
                changed = False
                for pat in MASK_PATTERNS:
                    m = pat.search(buf)
                    if m:
                        t = stable_tok(m.group(0))
                        tokens[t] = m.group(0)
                        buf = buf[:m.start()] + t + buf[m.end():]
                        changed = True
                        break
            for entry in sorted(names, key=len, reverse=True):
                en, _, zh = entry.partition("=")
                if en and en in buf:
                    t = stable_tok(en)
                    tokens[t] = en          # 键还原：永远英文原词
                    if zh:
                        name_zh[en] = zh     # 值还原：中文译名
                    buf = buf.replace(en, t)
            out.append(buf)
        return "".join(out)

    # ---------- 第一段：清洗 ----------
    def clean(self):
        os.makedirs(self.work, exist_ok=True)
        orig = mt_config.load_loose_json(self.src)
        names = self.load_names()
        todo = [k for k, v in orig.items()
                if isinstance(k, str) and k.strip() and not (isinstance(v, str) and v.strip())]
        user_set = {n.partition("=")[0].strip().lower() for n in names}
        if self.auto_names:
            auto = [(w, c) for w, c in mt_config.detect_names(todo, self.sl)
                    if w.lower() not in user_set]
            if not auto and self.sl.split("-")[0].lower() in ("zh", "ko"):
                self.log(self.L["log_zhko"])
            names.extend(w for w, _ in auto)
            if auto:
                self.log(self.L["log_auton"].format(
                    len(auto), ", ".join(f"{w}×{c}" for w, c in auto[:30])))
        elif user_set:
            self.log(self.L["log_auton_off"])
        tokens, name_zh, masked = {}, {}, {}
        for i, k in enumerate(todo):
            if self.cancel.is_set():
                raise Cancel()
            masked[self.mask(k, tokens, names, name_zh)] = ""
            if i % 500 == 0:
                self.cb("clean", i, len(todo), "")
        mp, tp = os.path.join(self.work, "masked.json"), os.path.join(self.work, "tokens.json")
        if os.path.exists(mp):   # 断点：保留旧译文
            prev = json.load(open(mp, encoding="utf-8"))
            for k in masked:
                if k in prev and isinstance(prev[k], str) and prev[k].strip():
                    masked[k] = prev[k]
        if os.path.exists(tp):
            old = json.load(open(tp, encoding="utf-8"))
            old.update(tokens)
            tokens = old
        json.dump(masked, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(tokens, open(tp, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        json.dump(name_zh, open(os.path.join(self.work, "names_map.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=0)
        self.log(self.L["log_clean"].format(len(masked), len(names)))
        return masked, tokens

    # ---------- 端点 ----------
    def _open(self, url):
        req = urllib.request.Request(url, headers=self.headers)
        return urllib.request.urlopen(req, timeout=30)

    def mt_one(self, text, tries=5):
        for a in range(tries):
            if self.cancel.is_set():
                raise Cancel()
            try:
                r = mt_config.translate_once(
                    text, self.sl, self.tl, endpoint=self.endpoint,
                    api_key=self.api_key, api_header=self.api_header,
                    api_type=self.api_type, model=self.model)
                return r
            except Cancel:
                raise
            except mt_config.ApiError as e:
                if e.kind == "fatal":
                    raise                      # 401/402/404：立即终止，不浪费重试
                if e.kind == "skip":
                    # 敏感词被服务方拦截 → 机翻免费端点兜底（不审查内容）
                    self.policy_skips += 1
                    if self.policy_skips == 1:
                        self.log(e.args[0] + "（后续同类拦截不再逐条提示，结束时汇总）")
                    r = self._fallback_translate(text)
                    if r is not None:
                        return r
                    return ""                  # 兜底也失败：留空保原文
                if a == tries - 1:             # retry：退避重试
                    raise
                time.sleep(3 + 3 * a + random.random() * 2)
            except Exception:
                if a == tries - 1:
                    raise
                time.sleep(3 + 3 * a + random.random() * 2)
        return ""

    def _fallback_translate(self, text):
        """主接口内容拦截后，用内置免费机翻端点兜底；成功返回译文，失败返回 None。"""
        if not self.fallback:
            return None
        if self.api_type == "get" and self.endpoint == self.fallback_endpoint:
            return None                        # 主接口已是免费端点，无路可退
        try:
            r = mt_config.translate_once(text, self.sl, self.tl,
                                         endpoint=self.fallback_endpoint,
                                         api_type="get")
            if isinstance(r, str) and r.strip():
                self.fallback_saved += 1
                if self.fallback_saved == 1:
                    self.log("[fallback] 内容拦截 → 已自动改用免费机翻兜底 "
                             "(quality=MT) / blocked string retranslated via free MT")
                return r
        except Exception:
            pass
        return None

    def mt_batch(self, qs, tries=5):
        """多条合并请求——仅内置谷歌端点支持；自定义/AI 接口自动退化为逐条"""
        if self.api_type != "get" or self.endpoint != mt_config.DEFAULT_ENDPOINT:
            return [self.mt_one(q) for q in qs]
        u = (self.endpoint.replace("{sl}", self.sl).replace("{tl}", self.tl)
             .replace("&q={q}", "") + "".join("&q=" + urllib.parse.quote(q) for q in qs))
        for a in range(tries):
            if self.cancel.is_set():
                raise Cancel()
            try:
                with self._open(u) as r:
                    d = json.loads(r.read().decode("utf-8", "replace"))
                if isinstance(d, list) and len(d) == len(qs):
                    out = []
                    for x in d:
                        if isinstance(x, list) and x and isinstance(x[0], str):
                            out.append(x[0])    # [译文, 检测语言]
                        else:
                            out.append(x if isinstance(x, str) else str(x))
                    return out
                raise ValueError("shape")
            except Cancel:
                raise
            except Exception:
                if a == tries - 1:
                    raise
                time.sleep(3 + 3 * a + random.random() * 2)

    # ---------- 第二段：机翻 ----------
    def translate(self, masked, seg=False):
        keys = [k for k, v in masked.items() if not (isinstance(v, str) and v.strip())]
        total, t0, done = len(keys), time.time(), 0
        self.log(self.L["log_trans_s" if seg else "log_trans_b"].format(total))
        if seg:
            segre = re.compile(r"(〔T[0-9a-f]{8}〕)")
            for k in keys:
                if self.cancel.is_set():
                    raise Cancel()
                parts = segre.split(k)
                out = []
                for p in parts:
                    if segre.fullmatch(p) or not p.strip():
                        out.append(p)
                    else:
                        out.append(self.mt_one(p))
                        time.sleep(0.15)
                masked[k] = "".join(out)
                done += 1
                if done % 10 == 0 or done >= total:
                    self._save(masked)
                    self.cb("trans", done, total, self._eta(t0, done, total))
        elif self.api_type == "openai":
            self._translate_ai_batch(masked, keys, t0)
        else:
            B = 8
            gi = 0
            while gi < len(keys):
                if self.cancel.is_set():
                    raise Cancel()
                group = keys[gi:gi + B]
                if len("".join(group)) > 6000:
                    group = group[:max(1, len(group) // 2)]
                try:
                    vals = self.mt_batch(group)
                except Exception:
                    vals = [self.mt_one(g) for g in group]
                for k, v in zip(group, vals):
                    masked[k] = v
                done += len(group)
                gi += len(group)
                if (gi // B) % 2 == 0 or done >= total:
                    self._save(masked)
                    self.cb("trans", done, total, self._eta(t0, done, total))
                time.sleep(0.45 + random.random() * 0.5)
        self._save(masked)
        self.log(self.L["log_trans_ok"].format(done, (time.time() - t0) / 60))
        return masked

    # ---------- AI 批量模式：N 条打包 + 上下文注入 + 分级降级 ----------
    def _ctx_for(self, idx, keys):
        """上下文：同文件顺序的前后各 2 条（掩码态原文），仅供模型参考。"""
        if self._no_ctx:
            return ""
        parts = []
        for j in (idx - 2, idx - 1):
            if j >= 0:
                parts.append(keys[j][:120])
        pre = parts
        post = []
        for j in (idx + 1, idx + 2):
            if j < len(keys):
                post.append(keys[j][:120])
        ctx = ""
        if pre:
            ctx += "前文 prev:\n" + "\n".join(pre) + "\n"
        if post:
            ctx += "后文 next:\n" + "\n".join(post)
        return ctx[:600]

    def _ai_group(self, group, ctxs, depth=0):
        """一组批量翻译：结构错误先重试，仍失败则半组递归，最终逐条。"""
        for attempt in range(3):
            if self.cancel.is_set():
                raise Cancel()
            try:
                return mt_config.translate_batch_openai(
                    group, self.sl, self.tl, self.endpoint, ctxs=ctxs,
                    api_key=self.api_key, api_header=self.api_header,
                    model=self.model)
            except Cancel:
                raise
            except mt_config.ApiError as e:
                if e.kind == "fatal":
                    raise
                if e.kind == "skip":
                    # 整组被拦 → 降级逐条，由 mt_one 精确拦敏感的那条（计数在彼处）
                    return [self.mt_one(g) for g in group]
                if attempt == 2:
                    break
                time.sleep(3 + 3 * attempt + random.random() * 2)
            except ValueError:
                if attempt == 2:
                    break
                time.sleep(1 + attempt)
        if len(group) > 2 and depth < 3:
            h = len(group) // 2
            return (self._ai_group(group[:h], ctxs[:h], depth + 1)
                    + self._ai_group(group[h:], ctxs[h:], depth + 1))
        self.ai_degraded += len(group)
        return [self.mt_one(g) for g in group]

    def _translate_ai_batch(self, masked, keys, t0):
        total = len(keys)
        if total == 0:
            return
        env = mt_config.load_env()
        self._no_ctx = env.get("MT_CONTEXT", "1") == "0"
        self.ai_degraded = 0
        pos = {k: i for i, k in enumerate(keys)}
        B = 24
        gi = 0
        while gi < len(keys):
            if self.cancel.is_set():
                raise Cancel()
            group = keys[gi:gi + B]
            while len(group) > 1 and len("".join(group)) > 9000:
                group = group[:max(1, len(group) // 2)]
            ctxs = [self._ctx_for(pos[k], keys) for k in group]
            vals = self._ai_group(group, ctxs)
            for k, v in zip(group, vals):
                masked[k] = v
            gi += len(group)
            self._save(masked)
            self.cb("trans", gi, total, self._eta(t0, gi, total))
            time.sleep(0.4 + random.random() * 0.3)
        if self.ai_degraded:
            self.log(f"[ai-batch] {self.ai_degraded} 条降级为逐条翻译（模型结构输出不符）")

    def _save(self, masked):
        json.dump(masked, open(os.path.join(self.work, "masked.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    def _eta(self, t0, done, total):
        r = done / (time.time() - t0)
        return self.L["log_speed"].format(r, (total - done) / r / 60) if r > 0 else self.L["log_calc"]

    # ---------- 第三段：回填 ----------
    def apply(self, masked, tokens, auto_seg_sweep=True):
        try:
            name_zh = json.load(open(os.path.join(self.work, "names_map.json"), encoding="utf-8"))
        except FileNotFoundError:
            name_zh = {}

        def key_of(k):
            return tokre.sub(lambda m: tokens.get(m.group(0), m.group(0)), canon(k))

        def val_of(v):
            def r(m):
                o = tokens.get(m.group(0))
                return name_zh.get(o, o) if o is not None else m.group(0)
            return tokre.sub(r, canon(v))

        result = {}
        for round_ in range(2):
            ok = drop_tok = drop_nl = 0
            result = {}
            for k, v in list(masked.items()):
                v = mt_config.repair_value(v)   # 修复历史批量解析污染值
                masked[k] = v
                if not (isinstance(v, str) and v.strip()):
                    continue
                ktoks = tokre.findall(k)
                if Counter(ktoks) != Counter(tokre.findall(canon(v))):
                    drop_tok += 1
                    masked[k] = ""
                    continue
                en, zh = key_of(k), val_of(v)
                zh = re.sub(r'(?<=[\u4e00-\u9fff〔])[ \t]+(?=[\u4e00-\u9fff〔〕])', '', zh)
                zh = re.sub(r'[ \t]*([。！？，、：；…～—])[ \t]*', r'\1', zh)
                zh = re.sub(r'\\(.)', lambda m: m.group(0) if m.group(1) in VALID_NEXT else m.group(1), zh)
                if en.count("\n") != zh.count("\n"):
                    drop_nl += 1
                    masked[k] = ""
                    continue
                result[k] = zh
                ok += 1
            self.cb("apply", ok, max(ok + drop_tok + drop_nl, 1), "")
            self.log(self.L["log_apply"].format(ok, drop_tok, drop_nl))
            if not auto_seg_sweep or (drop_tok + drop_nl) == 0 or round_ == 1:
                break
            self.log(self.L["log_seg"])
            masked = self.translate(masked, seg=True)
        orig = mt_config.load_loose_json(self.src)
        out = {k: mt_config.repair_value(v) for k, v in orig.items()}
        for k, zh in result.items():
            out[key_of(k)] = zh
        dst = os.path.splitext(self.src)[0] + "_translated.json"
        json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        self._save(masked)
        return dst, ok, drop_tok + drop_nl

    def run(self):
        masked, tokens = self.clean()
        if not masked:
            orig = json.load(open(self.src, encoding="utf-8"))
            dst = os.path.splitext(self.src)[0] + "_translated.json"
            json.dump(orig, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            self.log(self.L["no_trans"])
            return dst, 0, 0
        masked = self.translate(masked)
        if self.policy_skips:
            msg = (f"[safety-policy] {self.policy_skips} blocked by content policy"
                   f" / {self.policy_skips} 条被内容策略拦截")
            if self.fallback_saved:
                msg += (f"；其中 {self.fallback_saved} 条已由免费机翻兜底重译"
                        f" / {self.fallback_saved} salvaged via free MT")
            else:
                msg += "，保持原文 / kept as original"
            self.log(msg)
        return self.apply(masked, tokens)

# ---------------- GUI ----------------
ACCENT = "#2563eb"          # 亮色主色
ACCENT_DARK = "#4f8cff"     # 暗色主色
LIGHT = {
    "accent": ACCENT, "accent_hover": "#1d4ed8",
    "bg": "#f5f6f8", "fg": "#1f2937", "hint": "#8a93a3",
    "labelframe_fg": "#374151",
    "drop_bg": "#eef2ff", "drop_fg": "#4b5563", "drop_border": "#c7d2fe",
    "log_bg": "#ffffff", "log_fg": "#111827",
    "btn_bg": "#e5e7eb", "btn_fg": "#374151", "btn_active": "#d1d5db",
    "ok": "#15803d", "muted": "#6b7280",
}
DARK = {
    "accent": ACCENT_DARK, "accent_hover": "#6ea0ff",
    "bg": "#1c1d22", "fg": "#e6e7ec", "hint": "#9aa1ad",
    "labelframe_fg": "#c3c8d4",
    "drop_bg": "#20263a", "drop_fg": "#b9c2d6", "drop_border": "#3b4a78",
    "log_bg": "#14161a", "log_fg": "#d4d7de",
    "btn_bg": "#2a2d35", "btn_fg": "#cdd2dc", "btn_active": "#33363f",
    "ok": "#34d399", "muted": "#8b93a3",
    "err": "#f87171",
}

# 接口类型（语言中立标签）
API_TYPES = [("MT · GET", "get"), ("AI · OpenAI", "openai")]

class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.src_file = None
        self.out_file = None
        env = mt_config.load_env()
        self.lang = env.get("MT_LANG", "zh")
        if self.lang not in S:
            self.lang = "zh"
        self.theme = env.get("MT_THEME", "dark" if HAS_SVTTK else "light")
        if self.theme not in ("dark", "light"):
            self.theme = "light"
        self.pal = DARK if self.theme == "dark" else LIGHT
        self.bg_path = env.get("MT_BG", "")
        self._drop_note = ""
        self._bg_after = None
        self.library = self._library_load()
        self._apply_theme()
        self._build()
        self._apply_widget_colors()
        self.root.after(100, self._poll)

    def T(self, key):
        return S[self.lang][key]

    def _apply_theme(self):
        """主题层：sv-ttk（有则用）+ 自定义配色与样式覆盖"""
        if HAS_SVTTK:
            try:
                sv_ttk.set_theme(self.theme)
            except Exception:
                pass
        st = ttk.Style()
        if not HAS_SVTTK:
            try:
                st.theme_use("clam")
            except tk.TclError:
                pass
        pal = self.pal
        self.lang_font = ("Microsoft YaHei UI", 10) if self.lang == "zh" else ("Segoe UI", 10)
        self.root.option_add("*Font", self.lang_font)
        self.root.configure(bg=pal["bg"])
        st.configure("TFrame", background=pal["bg"])
        st.configure("TLabelframe", background=pal["bg"], borderwidth=1, relief="solid")
        st.configure("TLabelframe.Label", background=pal["bg"],
                     foreground=pal["labelframe_fg"], font=(self.lang_font[0], 10, "bold"))
        st.configure("TLabel", background=pal["bg"], foreground=pal["fg"])
        st.configure("Hint.TLabel", foreground=pal["hint"], font=(self.lang_font[0], 8))
        st.configure("TButton", padding=(10, 5))
        st.configure("Accent.TButton", foreground="#ffffff", background=pal["accent"],
                     padding=(16, 6), font=(self.lang_font[0], 10, "bold"))
        st.map("Accent.TButton",
               background=[("active", pal["accent_hover"]), ("disabled", "#9db4f5")])
        if not HAS_SVTTK:
            # 无 sv-ttk 时自己补进度条/表格的配色；有 sv-ttk 时交给主题
            st.configure("TProgressbar", thickness=14, background=pal["accent"],
                         troughcolor=pal["drop_bg"])
            st.configure("Treeview", background=pal["log_bg"], foreground=pal["log_fg"],
                         fieldbackground=pal["log_bg"], rowheight=26)
            st.configure("Treeview.Heading", font=(self.lang_font[0], 9, "bold"))
        st.configure("TCombobox", padding=(4, 3))
        st.configure("TNotebook.Tab", padding=(14, 6))
        # 标题类命名样式：主题切换时随调色板重着色（行内 foreground 不会跟着变）
        st.configure("Title.TLabel", background=pal["bg"], foreground=pal["fg"])
        st.configure("CardTitle.TLabel", background=pal["bg"], foreground=pal["fg"])

    def _apply_widget_colors(self):
        """tk 原生控件（非 ttk）按主题着色；在 _build 之后调用"""
        pal = self.pal
        for attr in ("drop", "lang_btn", "theme_btn", "logbox", "lbl_stage"):
            w = getattr(self, attr, None)
            if w is None:
                continue
            if attr == "drop":
                if isinstance(w, tk.Canvas):
                    w.config(bg=pal["drop_bg"], highlightbackground=pal["drop_border"])
                    self._render_drop_image()
                else:
                    w.config(bg=pal["drop_bg"], fg=pal["drop_fg"],
                             highlightbackground=pal["drop_border"])
            elif attr in ("lang_btn", "theme_btn"):
                w.config(bg=pal["btn_bg"], fg=pal["btn_fg"],
                         activebackground=pal["btn_active"])
            elif attr == "logbox":
                w.config(bg=pal["log_bg"], fg=pal["log_fg"])
            elif attr == "lbl_stage":
                w.config(foreground=pal["accent"])

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self.pal = DARK if self.theme == "dark" else LIGHT
        mt_config.save_env({"MT_THEME": self.theme})
        self._apply_theme()
        self._apply_widget_colors()
        self.theme_btn.config(text="☀" if self.theme == "dark" else "🌙")

    # ---------------- 投放卡（普通 Label / 背景图 Canvas） ----------------
    def _build_drop_card(self, parent):
        """构建投放卡：设置了背景图且 Pillow 可用时用 Canvas 绘制图片+蒙层+文字，
        否则普通 Label。重复调用时先销毁旧卡。"""
        if getattr(self, "drop", None) is not None:
            self.drop.destroy()
        use_img = bool(self.bg_path) and mt_config.check_pillow()
        if use_img:
            self.drop = tk.Canvas(parent, height=220, highlightthickness=2,
                                  highlightbackground=self.pal["drop_border"],
                                  bg=self.pal["drop_bg"], cursor="hand2")
            self.drop.pack(fill="x", pady=4)
            self.drop.bind("<Configure>", self._on_drop_resize)
            self._render_drop_image()
        else:
            drop_text = self.T("drop") + (self.T("drop_nodnd") if not HAS_DND else "")
            self.drop = tk.Label(parent, text=drop_text, relief="flat",
                                 bg=self.pal["drop_bg"], fg=self.pal["drop_fg"],
                                 padx=16, pady=26,
                                 font=("Microsoft YaHei UI", 12), cursor="hand2",
                                 highlightthickness=2,
                                 highlightbackground=self.pal["drop_border"])
            self.drop.pack(fill="x", pady=4)
        self.drop.bind("<Button-1>", lambda e: self.pick())
        self.drop.bind("<Enter>", lambda e: self.drop.config(
            highlightbackground=self.pal["accent"]))
        self.drop.bind("<Leave>", lambda e: self.drop.config(
            highlightbackground=self.pal["drop_border"]))
        if self._drop_note:
            self._set_drop_note(self._drop_note)

    def _on_drop_resize(self, event):
        """投放卡尺寸变化 → 防抖 150ms 重绘背景图"""
        if not isinstance(self.drop, tk.Canvas):
            return
        if getattr(self, "_bg_after", None):
            self.root.after_cancel(self._bg_after)
        self._bg_after = self.root.after(150, self._render_drop_image)

    def _render_drop_image(self):
        """把 MT_BG 图片 cover-fit 绘制到投放 Canvas + 蒙层 + 提示文字"""
        self._bg_after = None
        cv = self.drop
        if not isinstance(cv, tk.Canvas) or not self.bg_path:
            return
        try:
            from PIL import Image, ImageTk
            with Image.open(self.bg_path) as fh:
                img = fh.copy()                  # 句柄即开即关，避免锁住文件
        except Exception as e:
            self.log(f"[bg] 背景图加载失败，回退普通卡片 / failed to load: {e}")
            self.bg_path = ""
            self._build_drop_card(self._t1)
            return
        w = max(cv.winfo_width(), 200)
        h = max(cv.winfo_height() or 220, 120)
        iw, ih = img.size
        scale = max(w / iw, h / ih)
        nw, nh = int(iw * scale) + 1, int(ih * scale) + 1
        img = img.resize((nw, nh), Image.LANCZOS)
        left, top = (nw - w) // 2, (nh - h) // 2
        img = img.crop((left, top, left + w, top + h))
        photo = ImageTk.PhotoImage(img)
        cv.delete("all")
        cv._bgphoto = photo                      # 防 GC
        cv.create_image(0, 0, image=photo, anchor="nw")
        cv.create_rectangle(0, 0, w, h, fill="#0b0e16", stipple="gray50",
                            outline="")
        main = self.T("drop").split("\n")[0]
        sub = self.T("drop_nodnd").strip() if not HAS_DND else ""
        cv.create_text(w // 2, h // 2 - 8, text=main, fill="#ffffff",
                       font=("Microsoft YaHei UI", 13, "bold"), justify="center")
        if sub:
            cv.create_text(w // 2, h // 2 + 20, text=sub, fill="#cdd5e4",
                           font=("Microsoft YaHei UI", 9), justify="center")
        if self._drop_note:
            cv.create_text(w // 2, h - 16, text=self._drop_note,
                           fill="#8fe3b0", font=("Microsoft YaHei UI", 9))

    def _set_drop_note(self, text):
        """投放卡状态角标（完成/取消等）；Label 模式变色，Canvas 模式画底部小字"""
        self._drop_note = text
        if isinstance(self.drop, tk.Canvas):
            self._render_drop_image()
        else:
            try:
                self.drop.config(fg=text and self.pal["ok"] or self.pal["drop_fg"])
            except tk.TclError:
                pass

    # ---------------- 背景图设置 ----------------
    BG_NORMAL_MAX = 1600          # 标准化：最长边上限（投放卡渲染上限的 2 倍余量）
    BG_NORMAL_DPI = (96, 96)      # 统一分辨率参数

    def _hex_rgb(self, hx):
        hx = hx.lstrip("#")
        return tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))

    def _normalize_bg(self, src):
        """背景图导入标准化：EXIF 转正 → 压平透明（垫当前主题底色）→ RGB
        → 最长边 ≤1600 LANCZOS 缩放 → 96 DPI → PNG/JPEG 择小存储。
        返回标准化文件路径；失败抛异常。"""
        from PIL import Image, ImageOps
        with Image.open(src) as fh:              # copy 全量读入并立即关闭句柄
            img = fh.copy()                      # （Windows 下残留句柄会锁文件）
        src_kb = os.path.getsize(src) / 1024
        ow, oh = img.size
        try:                                   # 手机照片按 EXIF 方向转正
            t = ImageOps.exif_transpose(img)
            if t is not None:
                img = t
        except Exception:
            pass
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            base = Image.new("RGBA", img.size, self._hex_rgb(self.pal["bg"]) + (255,))
            base.alpha_composite(img)
            img = base.convert("RGB")
        else:
            img = img.convert("RGB")
        w, h = img.size
        scale = min(1.0, self.BG_NORMAL_MAX / max(w, h))
        if scale < 1.0:
            img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                             Image.LANCZOS)
        stem = os.path.join(mt_config.base_dir(), "bg_image.omnitrans")
        p_png, p_jpg = stem + ".png", stem + ".jpg"
        img.save(p_png, dpi=self.BG_NORMAL_DPI)
        img.save(p_jpg, quality=88, dpi=self.BG_NORMAL_DPI)
        keep, drop = (p_png, p_jpg) if os.path.getsize(p_png) <= os.path.getsize(p_jpg) \
            else (p_jpg, p_png)
        try:
            os.remove(drop)
        except OSError:
            pass
        self.log(f"[bg] 标准化 {ow}x{oh} {src_kb:.0f}KB → "
                 f"{img.size[0]}x{img.size[1]} {os.path.getsize(keep)/1024:.0f}KB "
                 f"({os.path.basename(keep)}, RGB, 96dpi) / normalized")
        return keep

    def bg_pick(self):
        if not mt_config.check_pillow():
            if not messagebox.askyesno("Pillow", self.T("bg_pillow_q")):
                self.log("[bg] 用户取消安装 Pillow")
                return
            self.log("[bg] 正在安装 Pillow…")
            ok, msg = mt_config.install_pillow()
            if not ok:
                messagebox.showerror(self.T("bg_pillow_fail"), msg)
                return
        p = filedialog.askopenfilename(title=self.T("bg_title"),
                                       filetypes=[("Image", "*.png *.jpg *.jpeg *.webp *.bmp"),
                                                  ("All files", "*.*")])
        if not p:
            return
        try:
            norm = self._normalize_bg(p)
        except Exception as e:
            messagebox.showerror(self.T("error"), f"{p}\n{e}")
            return
        self.bg_path = norm
        mt_config.save_env({"MT_BG": norm})
        self.bg_name_var.set(os.path.basename(p))
        self._build_drop_card(self._t1)
        self.log(f"[bg] 背景图已设置: {os.path.basename(p)}")

    def bg_clear(self):
        # 一并清掉标准化产物（只删本工具生成的）
        for ext in (".png", ".jpg"):
            p = os.path.join(mt_config.base_dir(), "bg_image.omnitrans" + ext)
            if self.bg_path and os.path.abspath(self.bg_path) == os.path.abspath(p)                     and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        self.bg_path = ""
        mt_config.save_env({"MT_BG": ""})     # 空值 = 删除该行
        self.bg_name_var.set(self.T("bg_none"))
        self._build_drop_card(self._t1)
        self.log("[bg] 背景图已清除")

    # ---------------- 图书馆（本地翻译记录） ----------------
    def _library_path(self):
        return os.path.join(mt_config.base_dir(), "library.json")

    def _library_load(self):
        try:
            d = json.load(open(self._library_path(), encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("games"), list):
                return d
        except Exception:
            pass
        return {"games": []}

    def _library_save(self):
        try:
            json.dump(self.library, open(self._library_path(), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception as e:
            self.log(f"[library] 保存失败: {e}")

    @staticmethod
    def _game_title_of(src_file, game_path):
        """提取游戏名：游戏目录名优先；否则源文件名去掉管线后缀"""
        if game_path:
            return os.path.basename(os.path.abspath(game_path).rstrip("/\\"))
        b = os.path.basename(src_file or "")
        for suf in ("_extracted_translated.json", "_extracted.json",
                    "_translated.json", ".json"):
            if b.lower().endswith(suf):
                b = b[:-len(suf)]
                break
        return b or "Untitled"

    def library_add(self, src_file, ok, drop):
        """翻译完成 → 收录/更新条目"""
        name = self._game_title_of(src_file, self.game_path)
        eng_key = self.game_engine or ""
        eng_name = (mt_config.ENGINES.get(eng_key, {}) or {}).get("name", eng_key or "?")
        entry = next((g for g in self.library["games"] if g.get("name") == name), None)
        if entry is None:
            entry = {"name": name, "applied": False}
            self.library["games"].insert(0, entry)
        entry.update({
            "engine": eng_key, "engine_name": eng_name,
            "translated": ok, "skipped": drop,
            "translated_at": time.strftime("%Y-%m-%d %H:%M"),
            "game_path": self.game_path or "",
            "output": src_file or "",
        })
        self._library_save()
        self._library_refresh()
        self.log(f"[library] 已收录「{name}」（{eng_name}，{ok} 条）")

    def library_mark_applied(self, game_path):
        name = self._game_title_of(None, game_path)
        entry = next((g for g in self.library["games"] if g.get("name") == name), None)
        if entry:
            entry["applied"] = True
            entry["applied_at"] = time.strftime("%Y-%m-%d %H:%M")
            self._library_save()
            self._library_refresh()

    def _library_refresh(self):
        t = getattr(self, "lib_tree", None)
        if t is None:
            return
        for iid in t.get_children():
            t.delete(iid)
        for i, g in enumerate(self.library["games"]):
            st = self.T("lib_st_applied") if g.get("applied") else self.T("lib_st_done")
            t.insert("", "end", iid=f"lib{i}", values=(
                g.get("name", "?"), g.get("engine_name", "?"),
                g.get("translated", 0), st, g.get("translated_at", "")))
        if not self.library["games"]:
            t.insert("", "end", iid="libempty", values=(self.T("lib_empty"), "", "", "", ""))

    def _lib_selected(self):
        sel = self.lib_tree.selection()
        if not sel or sel[0] == "libempty":
            messagebox.showinfo("Info", self.T("lib_sel"))
            return None
        idx = int(sel[0][3:])
        return self.library["games"][idx] if idx < len(self.library["games"]) else None

    def lib_open_game(self):
        g = self._lib_selected()
        if g and g.get("game_path") and os.path.isdir(g["game_path"]):
            os.startfile(g["game_path"])
        elif g:
            self.lib_open_out()

    def lib_open_out(self):
        g = self._lib_selected()
        if not g:
            return
        p = g.get("output", "")
        d = p if os.path.isdir(p) else os.path.dirname(p)
        if d and os.path.isdir(d):
            os.startfile(d)

    def lib_delete(self):
        g = self._lib_selected()
        if not g:
            return
        self.library["games"] = [x for x in self.library["games"] if x is not g]
        self._library_save()
        self._library_refresh()

    # ---------------- 译文微调 ----------------
    def rv_load(self, path=None):
        if path is None:
            import glob as g
            cands = sorted(g.glob(os.path.join(mt_config.base_dir(), "*_translated.json")),
                            key=os.path.getmtime, reverse=True)
            path = cands[0] if cands else filedialog.askopenfilename(
                title=self.T("rv_pick"), filetypes=[("JSON", "*_translated.json"),
                                                    ("JSON", "*.json")])
        if not path or not os.path.exists(path):
            return
        try:
            d = mt_config.load_loose_json(path)
        except Exception as e:
            messagebox.showerror(self.T("error"), str(e))
            return
        self.review_data = [[k, v if isinstance(v, str) else ""] for k, v in d.items()]
        self.review_path = path
        self.review_dirty = 0
        self.rv_path_var.set(f"{os.path.basename(path)}  ({len(self.review_data)} 条)")
        self.rv_save_btn.config(state="normal")
        self.rv_search_var.set("")
        self.rv_refresh()
        self.log(f"[review] 已加载 {os.path.basename(path)}（{len(self.review_data)} 条）")

    def rv_refresh(self):
        t = self.rv_tree
        for iid in t.get_children():
            t.delete(iid)
        kw = self.rv_search_var.get().strip().lower()
        LIMIT = 2000
        shown = 0
        for i, (o, z) in enumerate(self.review_data):
            if kw and kw not in o.lower() and kw not in z.lower():
                continue
            shown += 1
            if shown > LIMIT:
                break
            t.insert("", "end", iid=f"r{i}", values=(o[:120], z[:120]))
        if kw:
            self.rv_path_var.set(
                f"{os.path.basename(self.review_path)}  筛选 {min(shown, LIMIT)}/{len(self.review_data)} 条")
        elif len(self.review_data) > LIMIT:
            self.rv_path_var.set(
                self.T("rv_limit").format(len(self.review_data), LIMIT))

    def rv_edit(self):
        sel = self.rv_tree.selection()
        if not sel or not self.review_data:
            return
        idx = int(sel[0][1:])
        orig, zh = self.review_data[idx]
        win = tk.Toplevel(self.root)
        win.title(self.T("rv_edit_t"))
        win.geometry("760x420")
        win.transient(self.root)
        ttk.Label(win, text=self.T("rv_orig")).pack(anchor="w", padx=10, pady=(8, 0))
        to = tk.Text(win, height=6, wrap="word", font=("Microsoft YaHei UI", 10))
        to.pack(fill="x", padx=10)
        to.insert("1.0", orig)
        to.config(state="disabled")
        ttk.Label(win, text=self.T("rv_new")).pack(anchor="w", padx=10, pady=(8, 0))
        tz = tk.Text(win, height=8, wrap="word", font=("Microsoft YaHei UI", 10))
        tz.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        tz.insert("1.0", zh)

        def save():
            new = tz.get("1.0", "end-1c")
            self.review_data[idx][1] = new
            if new != zh:
                self.review_dirty += 1
                self.rv_dirty_var.set(self.T("rv_dirty").format(self.review_dirty))
            if self.rv_tree.exists(sel[0]):
                self.rv_tree.item(sel[0], values=(orig[:120], new[:120]))
            win.destroy()

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(btns, text=self.T("rv_ok"), command=save,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(btns, text=self.T("rv_cancel"), command=win.destroy).pack(
            side="left", padx=8)
        tz.focus_set()

    def rv_save(self):
        if not self.review_path or not self.review_data:
            return
        out = {k: v for k, v in self.review_data}
        try:
            json.dump(out, open(self.review_path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror(self.T("error"), str(e))
            return
        msg = self.T("rv_saved").format(self.review_path, len(out), self.review_dirty)
        self.log(f"[review] {msg}")
        self.review_dirty = 0
        self.rv_dirty_var.set("")
        messagebox.showinfo(self.T("msg_saved"), msg)

    def _build(self):
        self.root.title(self.T("title"))
        # 引擎识别结果（拖游戏目录时记录）
        self.game_path = None
        self.game_engine = None       # engine key
        self.game_extract_script = None
        self.apply_script = None

        self.root.geometry("900x720")
        self.root.minsize(820, 660)
        self.root.configure(bg=self.pal["bg"])

        # ---- 顶栏：标题 + 主题切换 + 语言切换 ----
        head = ttk.Frame(self.root, padding=(14, 10, 14, 0))
        head.pack(fill="x")
        ttk.Label(head, text=self.T("title"),
                  style="Title.TLabel",
                  font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        self.lang_btn = tk.Button(head, text=self.T("lang_btn"), command=self.toggle_lang,
                                  relief="flat", bg=self.pal["btn_bg"], fg=self.pal["btn_fg"],
                                  activebackground=self.pal["btn_active"], padx=12, pady=2,
                                  cursor="hand2", font=("Segoe UI", 9, "bold"))
        self.lang_btn.pack(side="right")
        self.theme_btn = tk.Button(head,
                                   text="☀" if self.theme == "dark" else "🌙",
                                   command=self.toggle_theme,
                                   relief="flat", bg=self.pal["btn_bg"], fg=self.pal["btn_fg"],
                                   activebackground=self.pal["btn_active"], padx=10, pady=2,
                                   cursor="hand2", font=("Segoe UI", 11))
        self.theme_btn.pack(side="right", padx=(0, 8))

        # ---- 全局：源/目标语言 + 人名选项 ----
        row1 = ttk.Frame(self.root, padding=(14, 8))
        row1.pack(fill="x")
        self.lbl_src = ttk.Label(row1, text=self.T("src"))
        self.lbl_src.pack(side="left")
        self.sl_var = tk.StringVar(value="Auto · 自动")
        names_list = [n for n, _ in LANGS]
        ttk.Combobox(row1, textvariable=self.sl_var, values=names_list,
                     width=11, state="readonly").pack(side="left", padx=(4, 10))
        self.lbl_tgt = ttk.Label(row1, text=self.T("tgt"))
        self.lbl_tgt.pack(side="left")
        self.tl_var = tk.StringVar(value="中文(简)")
        ttk.Combobox(row1, textvariable=self.tl_var, values=names_list,
                     width=11, state="readonly").pack(side="left", padx=4)
        self.autonames_var = tk.BooleanVar(value=True)
        self.ck_autonames = ttk.Checkbutton(row1, text=self.T("autonames"),
                                            variable=self.autonames_var)
        self.ck_autonames.pack(side="left", padx=14)
        self.lbl_names_hint = ttk.Label(row1, text=self.T("names_hint"), style="Hint.TLabel")
        self.lbl_names_hint.pack(side="left")

        # ---- 功能分区：三标签页 ----
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        # ===== Tab1 快速翻译 =====
        t1 = ttk.Frame(self.nb, padding=4)
        self.nb.add(t1, text=self.T("tab_quick"))
        self._t1 = t1
        self._build_drop_card(t1)

        prog = ttk.Frame(t1, padding=(4, 2))
        prog.pack(fill="x")
        self.stage_var = tk.StringVar(value=self.T("waiting"))
        self.lbl_stage = ttk.Label(prog, textvariable=self.stage_var,
                                   font=("Microsoft YaHei UI", 10, "bold"))
        self.lbl_stage.pack(anchor="w")
        self.bar = ttk.Progressbar(prog, maximum=100, style="TProgressbar")
        self.bar.pack(fill="x", pady=5)
        self.detail_var = tk.StringVar(value="")
        ttk.Label(prog, textvariable=self.detail_var, style="Hint.TLabel").pack(anchor="w")

        btns = ttk.Frame(t1, padding=(4, 4))
        btns.pack(fill="x")
        self.start_btn = ttk.Button(btns, text=self.T("start"), style="Accent.TButton",
                                    command=self.start, state="disabled")
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text=self.T("cancel"), command=self.cancel_now,
                                     state="disabled")
        self.cancel_btn.pack(side="left", padx=8)
        self.open_btn = ttk.Button(btns, text=self.T("open_out"), command=self.open_out,
                                   state="disabled")
        self.open_btn.pack(side="left")

        self.logbox = ScrolledText(t1, height=8, font=("Consolas", 9),
                                   state="disabled", bg=self.pal["log_bg"],
                                   fg=self.pal["log_fg"], relief="flat",
                                   highlightthickness=1, highlightbackground=self.pal["drop_border"])
        self.logbox.pack(fill="both", expand=True, pady=(6, 2))

        # ===== Tab2 游戏汉化 =====
        t2 = ttk.Frame(self.nb, padding=10)
        self.nb.add(t2, text=self.T("tab_game"))
        ttk.Label(t2, text=self.T("g_title"),
                  style="CardTitle.TLabel",
                  font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        self.g_hint_lbl = ttk.Label(t2, text=self.T("g_drop") + "\n" + self.T("g_steps"),
                                    style="Hint.TLabel", wraplength=760, justify="left")
        self.g_hint_lbl.pack(anchor="w", pady=(2, 8))

        info = ttk.Frame(t2)
        info.pack(fill="x", pady=4)
        self.g_engine_var = tk.StringVar(value=self.T("g_engine").format(self.T("g_unknown")))
        self.lbl_g_engine = ttk.Label(info, textvariable=self.g_engine_var,
                                      font=("Microsoft YaHei UI", 11, "bold"))
        self.lbl_g_engine.pack(side="left")
        self.g_path_var = tk.StringVar(value="")
        ttk.Label(info, textvariable=self.g_path_var, style="Hint.TLabel").pack(
            side="left", padx=10)

        gbtns = ttk.Frame(t2, padding=(0, 6))
        gbtns.pack(fill="x")
        self.g_extract_btn = ttk.Button(gbtns, text=self.T("g_extract"),
                                        style="Accent.TButton",
                                        command=self.game_extract, state="disabled")
        self.g_extract_btn.pack(side="left")
        self.g_translate_btn = ttk.Button(gbtns, text=self.T("g_translate"),
                                          command=self.start, state="disabled")
        self.g_translate_btn.pack(side="left", padx=8)
        self.apply_btn = ttk.Button(gbtns, text=self.T("g_apply"),
                                    command=self.apply_to_game, state="disabled")
        self.apply_btn.pack(side="left", padx=8)
        self.mtool_btn = ttk.Button(gbtns, text=self.T("g_mtool"),
                                    command=self.export_mtool)
        self.mtool_btn.pack(side="left", padx=8)
        self.g_note_lbl = ttk.Label(t2, text=self.T("g_backup_note"), style="Hint.TLabel",
                                    wraplength=760, justify="left")
        self.g_note_lbl.pack(anchor="w", pady=(2, 6))

        # 引擎支持总览表
        ttk.Label(t2, text=self.T("g_engine_table"),
                  font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
        cols = ("engine", "status")
        self.engine_tree = ttk.Treeview(t2, columns=cols, show="headings", height=9)
        self.engine_tree.heading("engine", text=self.T("g_col_engine"))
        self.engine_tree.column("engine", width=300, anchor="w")
        self.engine_tree.heading("status", text=self.T("g_col_status"))
        self.engine_tree.column("status", width=200, anchor="w")
        for key, e in mt_config.ENGINES.items():
            self.engine_tree.insert("", "end", iid=key,
                                    values=(e["name"],
                                            self.T("g_supported") if e["supported"]
                                            else self.T("g_unsupported")))
        self.engine_tree.pack(fill="both", expand=True, pady=(0, 4))

        # ===== Tab3 设置 =====
        t3 = ttk.Frame(self.nb, padding=8)
        self.nb.add(t3, text=self.T("tab_cfg"))
        cfg = ttk.LabelFrame(t3, text=self.T("api_frame"), padding=8)
        cfg.pack(fill="x")
        self._cfg_frame = cfg
        # 类型 + 模型行
        self.type_var = tk.StringVar(value="MT · GET")
        ttk.Label(cfg, text="Type:").grid(row=0, column=0, sticky="w")
        self.type_cmb = ttk.Combobox(cfg, textvariable=self.type_var,
                                     values=[n for n, _ in API_TYPES],
                                     width=13, state="readonly")
        self.type_cmb.grid(row=0, column=1, columnspan=2, sticky="w", padx=4, pady=2)
        ttk.Label(cfg, text="Model:").grid(row=0, column=3, sticky="e")
        self.model_var = tk.StringVar(value="")
        self.model_entry = ttk.Entry(cfg, textvariable=self.model_var, width=18)
        self.model_entry.grid(row=0, column=4, sticky="w", padx=4)
        self.lbl_url = ttk.Label(cfg, text=self.T("url"))
        self.lbl_url.grid(row=1, column=0, sticky="w")
        self.url_var = tk.StringVar(value=mt_config.DEFAULT_ENDPOINT)
        ttk.Entry(cfg, textvariable=self.url_var).grid(row=1, column=1, columnspan=3,
                                                       sticky="we", padx=4, pady=2)
        self.lbl_key = ttk.Label(cfg, text=self.T("key"))
        self.lbl_key.grid(row=2, column=0, sticky="w")
        self.key_var = tk.StringVar(value="")
        ttk.Entry(cfg, textvariable=self.key_var, show="*").grid(row=2, column=1,
                                                                 sticky="we", padx=4, pady=2)
        self.lbl_header = ttk.Label(cfg, text=self.T("header"))
        self.lbl_header.grid(row=2, column=3, sticky="e")
        self.hdr_var = tk.StringVar(value="Authorization")
        ttk.Entry(cfg, textvariable=self.hdr_var, width=18).grid(row=2, column=4,
                                                                 sticky="w", padx=4)
        self.save_btn = ttk.Button(cfg, text=self.T("save_env"), command=self.save_env)
        self.save_btn.grid(row=1, column=5, rowspan=2, padx=(8, 0), sticky="ns")
        self.lbl_api_hint = ttk.Label(cfg, text=self.T("api_hint"), style="Hint.TLabel",
                                      wraplength=700, justify="left")
        self.lbl_api_hint.grid(row=3, column=0, columnspan=6, sticky="we",
                               pady=(4, 0))
        cfg.columnconfigure(1, weight=1)
        # 提示文字随窗口宽度自动换行，永不溢出
        cfg.bind("<Configure>", lambda e: self.lbl_api_hint.configure(
            wraplength=max(320, e.width - 60)))

        # ---- 背景图行 ----
        bgrow = ttk.Frame(cfg, padding=(0, 8, 0, 0))
        bgrow.grid(row=5, column=0, columnspan=6, sticky="w")
        self.lbl_bg = ttk.Label(bgrow, text=self.T("bg_label"))
        self.lbl_bg.pack(side="left")
        self.bg_pick_btn = ttk.Button(bgrow, text=self.T("bg_pick"), command=self.bg_pick)
        self.bg_pick_btn.pack(side="left", padx=(6, 4))
        self.bg_clear_btn = ttk.Button(bgrow, text=self.T("bg_clear"), command=self.bg_clear)
        self.bg_clear_btn.pack(side="left", padx=(0, 10))
        self.bg_name_var = tk.StringVar(
            value=os.path.basename(self.bg_path) if self.bg_path else self.T("bg_none"))
        ttk.Label(bgrow, textvariable=self.bg_name_var, style="Hint.TLabel").pack(side="left")
        self.lbl_bg_hint = ttk.Label(cfg, text=self.T("bg_hint"), style="Hint.TLabel",
                                     wraplength=700, justify="left")
        self.lbl_bg_hint.grid(row=6, column=0, columnspan=6, sticky="we", pady=(2, 4))
        cfg.bind("<Configure>", lambda e: self.lbl_bg_hint.configure(
            wraplength=max(320, e.width - 60)), add="+")

        env = mt_config.load_env()
        if env.get("MT_ENDPOINT"):
            self.url_var.set(env["MT_ENDPOINT"])
        if env.get("MT_API_KEY"):
            self.key_var.set(env["MT_API_KEY"])
        if env.get("MT_API_HEADER"):
            self.hdr_var.set(env["MT_API_HEADER"])
        if env.get("MT_AUTO_NAMES"):
            self.autonames_var.set(env["MT_AUTO_NAMES"] == "1")
        if env.get("MT_API_TYPE"):
            for n, v in API_TYPES:
                if v == env["MT_API_TYPE"]:
                    self.type_var.set(n)
        if env.get("MT_MODEL"):
            self.model_var.set(env["MT_MODEL"])

        # ===== Tab4 图书馆 =====
        t4 = ttk.Frame(self.nb, padding=10)
        self.nb.add(t4, text=self.T("tab_lib"))
        ttk.Label(t4, text=self.T("lib_title"), style="CardTitle.TLabel",
                  font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        lcols = ("name", "engine", "count", "status", "date")
        self.lib_tree = ttk.Treeview(t4, columns=lcols, show="headings", height=12)
        for cid, txt, w in (("name", self.T("lib_col_name"), 260),
                            ("engine", self.T("lib_col_engine"), 190),
                            ("count", self.T("lib_col_count"), 70),
                            ("status", self.T("lib_col_status"), 120),
                            ("date", self.T("lib_col_date"), 130)):
            self.lib_tree.heading(cid, text=txt)
            self.lib_tree.column(cid, width=w, anchor="w")
        self.lib_tree.pack(fill="both", expand=True, pady=(6, 6))
        lbtns = ttk.Frame(t4)
        lbtns.pack(fill="x")
        self.lib_open_game_btn = ttk.Button(lbtns, text=self.T("lib_open_game"),
                                            command=self.lib_open_game)
        self.lib_open_game_btn.pack(side="left")
        self.lib_open_out_btn = ttk.Button(lbtns, text=self.T("lib_open_out"),
                                           command=self.lib_open_out)
        self.lib_open_out_btn.pack(side="left", padx=8)
        self.lib_del_btn = ttk.Button(lbtns, text=self.T("lib_del"),
                                      command=self.lib_delete)
        self.lib_del_btn.pack(side="left")
        self._library_refresh()

        # ===== Tab5 译文微调 =====
        t5 = ttk.Frame(self.nb, padding=10)
        self.nb.add(t5, text=self.T("tab_review"))
        ttk.Label(t5, text=self.T("rv_title"), style="CardTitle.TLabel",
                  font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        rrow = ttk.Frame(t5, padding=(0, 6))
        rrow.pack(fill="x")
        self.rv_load_btn = ttk.Button(rrow, text=self.T("rv_load"),
                                      command=self.rv_load, style="Accent.TButton")
        self.rv_load_btn.pack(side="left")
        self.rv_save_btn = ttk.Button(rrow, text=self.T("rv_save"),
                                      command=self.rv_save, state="disabled")
        self.rv_save_btn.pack(side="left", padx=8)
        self.rv_dirty_var = tk.StringVar(value="")
        ttk.Label(rrow, textvariable=self.rv_dirty_var, style="Hint.TLabel").pack(
            side="left", padx=10)
        self.rv_search_var = tk.StringVar()
        self.rv_search = ttk.Entry(rrow, textvariable=self.rv_search_var)
        self.rv_search.pack(side="right", fill="x", expand=True, padx=(10, 0))
        self.rv_path_var = tk.StringVar(value=self.T("rv_none"))
        ttk.Label(t5, textvariable=self.rv_path_var, style="Hint.TLabel").pack(
            anchor="w", pady=(0, 4))
        rcols = ("orig", "zh")
        self.rv_tree = ttk.Treeview(t5, columns=rcols, show="headings", height=13)
        self.rv_tree.heading("orig", text=self.T("rv_col_orig"))
        self.rv_tree.column("orig", width=400, anchor="w")
        self.rv_tree.heading("zh", text=self.T("rv_col_zh"))
        self.rv_tree.column("zh", width=400, anchor="w")
        self.rv_tree.pack(fill="both", expand=True, pady=(0, 4))
        self.rv_tree.bind("<Double-1>", lambda e: self.rv_edit())
        self.rv_search_var.trace_add("write", lambda *a: self.rv_refresh())
        self.review_data = []          # [(原文, 译文)]，保序
        self.review_path = None
        self.review_dirty = 0

        # ---- 全局拖放 ----
        if HAS_DND:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_dnd_drop)

    def _on_dnd_drop(self, event):
        """tkdnd <<Drop>> 回调（测试注入点：FakeEvent(data=…) 直调即全链路）"""
        self.on_drop(self._dnd_clean(event.data))

    # ---- 语言切换 ----
    def toggle_lang(self):
        self.lang = "en" if self.lang == "zh" else "zh"
        mt_config.save_env({"MT_LANG": self.lang})
        self._apply_theme()
        self._apply_widget_colors()
        self.root.title(self.T("title"))
        self.lang_btn.config(text=self.T("lang_btn"))
        self.lbl_src.config(text=self.T("src"))
        self.lbl_tgt.config(text=self.T("tgt"))
        self.ck_autonames.config(text=self.T("autonames"))
        self.lbl_names_hint.config(text=self.T("names_hint"))
        self._rebuild_texts()

    def _rebuild_texts(self):
        for w in (self.lbl_url, self.lbl_key, self.lbl_header, self.save_btn, self.lbl_api_hint):
            w.destroy()
        cfg = self._cfg_frame
        self.lbl_url = ttk.Label(cfg, text=self.T("url"))
        self.lbl_url.grid(row=1, column=0, sticky="w")
        self.lbl_key = ttk.Label(cfg, text=self.T("key"))
        self.lbl_key.grid(row=2, column=0, sticky="w")
        self.lbl_header = ttk.Label(cfg, text=self.T("header"))
        self.lbl_header.grid(row=2, column=3, sticky="e")
        self.save_btn = ttk.Button(cfg, text=self.T("save_env"), command=self.save_env)
        self.save_btn.grid(row=1, column=5, rowspan=2, padx=(8, 0), sticky="ns")
        self.lbl_api_hint = ttk.Label(cfg, text=self.T("api_hint"), style="Hint.TLabel",
                                      wraplength=700, justify="left")
        self.lbl_api_hint.grid(row=3, column=0, columnspan=6, sticky="we", pady=(4, 0))
        cfg.config(text=self.T("api_frame"))
        self._build_drop_card(self._t1)
        self.start_btn.config(text=self.T("start"))
        self.cancel_btn.config(text=self.T("cancel"))
        self.open_btn.config(text=self.T("open_out"))
        # 标签页与游戏汉化页文案
        self.bg_pick_btn.config(text=self.T("bg_pick"))
        self.bg_clear_btn.config(text=self.T("bg_clear"))
        self.lbl_bg.config(text=self.T("bg_label"))
        if not self.bg_path:
            self.bg_name_var.set(self.T("bg_none"))
        self.lbl_bg_hint.config(text=self.T("bg_hint"))
        self.nb.tab(0, text=self.T("tab_quick"))
        self.nb.tab(1, text=self.T("tab_game"))
        self.nb.tab(2, text=self.T("tab_cfg"))
        if len(self.nb.tabs()) > 3:
            self.nb.tab(3, text=self.T("tab_lib"))
        if len(self.nb.tabs()) > 4:
            self.nb.tab(4, text=self.T("tab_review"))
        self.rv_load_btn.config(text=self.T("rv_load"))
        self.rv_save_btn.config(text=self.T("rv_save"))
        self.rv_tree.heading("orig", text=self.T("rv_col_orig"))
        self.rv_tree.heading("zh", text=self.T("rv_col_zh"))
        if not self.review_data:
            self.rv_path_var.set(self.T("rv_none"))
        for cid, key in (("name", "lib_col_name"), ("engine", "lib_col_engine"),
                         ("count", "lib_col_count"), ("status", "lib_col_status"),
                         ("date", "lib_col_date")):
            self.lib_tree.heading(cid, text=self.T(key))
        self.lib_open_game_btn.config(text=self.T("lib_open_game"))
        self.lib_open_out_btn.config(text=self.T("lib_open_out"))
        self.lib_del_btn.config(text=self.T("lib_del"))
        self._library_refresh()
        self.g_extract_btn.config(text=self.T("g_extract"))
        self.g_translate_btn.config(text=self.T("g_translate"))
        self.apply_btn.config(text=self.T("g_apply"))
        self.mtool_btn.config(text=self.T("g_mtool"))
        eng_name = (mt_config.ENGINES.get(self.game_engine, {}).get("name")
                    if self.game_engine else None)
        self.g_engine_var.set(self.T("g_engine").format(
            eng_name or self.T("g_unknown")))
        for key, e in mt_config.ENGINES.items():
            self.engine_tree.item(key, values=(
                e["name"], self.T("g_supported") if e["supported"]
                else self.T("g_unsupported")))
        self.engine_tree.heading("engine", text=self.T("g_col_engine"))
        self.engine_tree.heading("status", text=self.T("g_col_status"))
        if not self.worker or not self.worker.is_alive():
            if self.stage_var.get() in (S["zh"]["waiting"], S["en"]["waiting"]):
                self.stage_var.set(self.T("waiting"))
            elif self.src_file and self.stage_var.get().startswith((S["zh"]["ready"][:3], S["en"]["ready"][:5])):
                self.stage_var.set(self.T("ready").format(os.path.basename(self.src_file)))

    @staticmethod
    def _dnd_clean(data):
        return data.strip("{}").split("} {")[0].strip()

    def log(self, msg):
        self.q.put(("log", msg))

    def on_drop(self, path):
        path = path.strip().strip('"')
        if not path.lower().endswith(".json"):
            # 不是 json → 尝试引擎识别（目录 / exe / 字幕 / 音视频 / 漫画档）
            eng, name, ok, reason = mt_config.detect_engine(path)
            if ok:
                extract = mt_config.engine_extractor(eng)
                if extract:
                    # 记录游戏信息（后续回写用）并切到游戏汉化页。
                    # 字幕/媒体/漫画文件：只处理拖进来的这一个文件；exe 等其余：按目录
                    if os.path.isdir(path):
                        self.game_path = path
                    elif path.lower().endswith((".srt", ".vtt", ".ass", ".ssa")
                                               + mt_config._MEDIA_EXTS
                                               + mt_config._COMIC_ARCHIVES):
                        self.game_path = path
                    else:
                        self.game_path = os.path.dirname(path)
                    self.game_engine = eng
                    self.game_extract_script = extract
                    self.apply_script = mt_config.engine_applier(eng)
                    self.g_engine_var.set(self.T("g_engine").format(name))
                    self.g_path_var.set(self.game_path)
                    self.g_extract_btn.config(state="normal")
                    self.apply_btn.config(state="disabled")
                    self.nb.select(1)
                    # Unity 引擎需检查 UnityPy
                    if eng == "unity":
                        if not self._check_and_install_unitypy():
                            return
                    # 音视频听译需检查 faster-whisper
                    if eng == "media":
                        if not self._check_and_install_fw():
                            return
                    # 漫画嵌字需检查 rapidocr + Pillow
                    if eng == "comic":
                        if not self._check_and_install_comic():
                            return
                    if messagebox.askyesno(
                            f"✅ {name}",
                            f"检测到 {name}，是否自动提取文本？\n\n"
                            f"将运行 {extract}（可能需要几分钟）"):
                        self.game_extract()
                        return
                    # 用户选"否"→ 仍启用导入按钮
                    self.apply_btn.config(state="normal")
                    self.log(f"[engine] {name} 已识别。可点击「提取文本」开始。")
                    return
            else:
                messagebox.showwarning(
                    f"❌ {name} — 不支持",
                    f"引擎：{name}\n\n{reason}")
                self.log(f"[engine] {name}: 不支持 — {reason}")
                return
        self.set_file(path)
        self.nb.select(0)

    def game_extract(self):
        """游戏汉化页：② 提取文本"""
        if not self.game_path or not self.game_extract_script:
            messagebox.showwarning("Info", self.T("g_drop"))
            return
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("Info", "busy / 正忙")
            return
        self.g_extract_btn.config(state="disabled")
        self.stage_var.set(self.T("g_extracting"))
        self.lbl_stage.config(foreground=self.pal["accent"])
        self._run_extractor(self.game_path, self.game_extract_script)

    def _check_and_install_unitypy(self):
        """检测 UnityPy；缺失时弹窗询问是否自动安装。返回 True=可用。"""
        if mt_config.check_unitypy():
            return True    # 已安装（或系统路径中找到）
        # 弹窗
        answer = messagebox.askyesno(
            "UnityPy Required / 需要安装 UnityPy",
            "Unity 引擎文本提取需要 UnityPy 库（当前未检测到）。\n"
            "Unity text extraction requires the UnityPy library (not found).\n\n"
            "是否自动安装？（需要 Python 和 pip，约 50MB）\n"
            "Install automatically? (requires Python & pip, ~50MB)")
        if not answer:
            self.log("[unity] 用户取消安装 UnityPy")
            return False
        self.log("[unity] 正在安装 UnityPy…（可能需要 1-3 分钟）")
        self.stage_var.set("Installing UnityPy…")
        self.bar["value"] = 10
        self.root.update()
        ok, msg = mt_config.install_unitypy()
        if ok:
            self.log("[unity] UnityPy 安装成功 ✓")
            self.stage_var.set("UnityPy installed ✓")
            return True
        self.log(f"[unity] 安装失败: {msg}")
        messagebox.showerror(
            "Install Failed / 安装失败",
            f"UnityPy 安装失败:\n{msg}\n\n"
            "请手动运行 / Please run manually:\n  pip install UnityPy")
        return False

    def _check_and_install_fw(self):
        """检测 faster-whisper；缺失时弹窗询问是否自动安装。返回 True=可用。"""
        if mt_config.check_fasterwhisper():
            return True
        answer = messagebox.askyesno(
            "faster-whisper Required / 需要安装 faster-whisper",
            "音视频听译需要 faster-whisper 库（当前未检测到）。\n"
            "Video/audio transcription requires faster-whisper (not found).\n\n"
            "是否自动安装？（需要 Python 和 pip，约 150MB；\n"
            "首次听译还会自动下载语音模型，small 档约 244MB，之后有缓存）\n"
            "Install automatically? (~150MB via pip; a speech model\n"
            "(~244MB for 'small') is downloaded on first transcription, then cached)")
        if not answer:
            self.log("[media] 用户取消安装 faster-whisper")
            return False
        self.log("[media] 正在安装 faster-whisper…（可能需要几分钟）")
        self.stage_var.set("Installing faster-whisper…")
        self.bar["value"] = 10
        self.root.update()
        ok, msg = mt_config.install_fasterwhisper()
        if ok:
            self.log("[media] faster-whisper 安装成功 ✓")
            self.stage_var.set("faster-whisper installed ✓")
            return True
        self.log(f"[media] 安装失败: {msg}")
        messagebox.showerror(
            "Install Failed / 安装失败",
            f"faster-whisper 安装失败:\n{msg}\n\n"
            "请手动运行 / Please run manually:\n  pip install faster-whisper")
        return False

    def _check_and_install_comic(self):
        """检测漫画依赖（rapidocr-onnxruntime + Pillow）；缺失时弹窗询问是否自动安装。"""
        missing = []
        if not mt_config.check_rapidocr():
            missing.append(("rapidocr-onnxruntime", mt_config.install_rapidocr))
        if not mt_config.check_pillow():
            missing.append(("Pillow", mt_config.install_pillow))
        if not missing:
            return True
        names = " + ".join(n for n, _ in missing)
        answer = messagebox.askyesno(
            "Comic deps / 漫画翻译依赖",
            f"漫画嵌字需要 {names}（当前未检测到）。\n"
            f"Comics lettering requires {names} (not found).\n\n"
            "是否自动安装？（需要 Python 和 pip，约 100MB）\n"
            "Install automatically? (Python & pip required, ~100MB)")
        if not answer:
            self.log(f"[comic] 用户取消安装 {names}")
            return False
        for name, installer in missing:
            self.log(f"[comic] 正在安装 {name}…")
            self.stage_var.set(f"Installing {name}…")
            self.bar["value"] = 10
            self.root.update()
            ok, msg = installer()
            if not ok:
                self.log(f"[comic] 安装失败: {msg}")
                messagebox.showerror(
                    "Install Failed / 安装失败",
                    f"{name} 安装失败:\n{msg}\n\n"
                    "请手动运行 / Please run manually:\n"
                    f"  pip install {name}")
                return False
            self.log(f"[comic] {name} 安装成功 ✓")
        # 可选增强：日漫（竖排）识别专用模型
        if not mt_config.check_mangaocr():
            if messagebox.askyesno(
                    "manga-ocr — 日漫识别增强 / JA manga OCR",
                    "检测到日文漫画时，manga-ocr（漫画专用识别，竖排可靠）效果远好于默认 OCR。\n"
                    "manga-ocr greatly improves Japanese-manga (vertical text) recognition.\n\n"
                    "是否安装？（含 PyTorch 约 700MB，首次识别再下载模型约 440MB。\n"
                    "跳过也能翻译，但竖排日文识别质量有限）\n"
                    "Install? (PyTorch ~700MB + model ~440MB; skip = limited JA quality)"):
                self.log("[comic] 正在安装 manga-ocr…（较大，可能需要几分钟）")
                self.stage_var.set("Installing manga-ocr…")
                self.root.update()
                ok, msg = mt_config.install_mangaocr()
                self.log(f"[comic] manga-ocr 安装{'成功 ✓' if ok else '失败: ' + msg}")
        return True

    def _resolve_script(self, script):
        """定位引擎脚本：打包 exe 优先查 PyInstaller 数据区(_MEIPASS)，其次 exe 旁，最后源码目录"""
        cands = []
        if getattr(sys, "frozen", False):
            mp = getattr(sys, "_MEIPASS", "")
            if mp:
                cands.append(os.path.join(mp, script))
        cands.append(os.path.join(mt_config.base_dir(), script))
        for c in cands:
            if c and os.path.exists(c):
                return c
        return None

    def _run_extractor(self, game_path, script):
        """在线程中 import 提取脚本并调用 main()——避免 subprocess 在打包 exe 里打开新窗口"""
        script_path = self._resolve_script(script)
        base = mt_config.base_dir()
        if not script_path:
            messagebox.showerror(
                "Error", f"引擎脚本缺失: {script}\n\n"
                f"Engine script missing — 请把 OmniTrans.exe 与发行文件放在一起，"
                f"或重新下载完整发行包 / keep the exe together with the release files")
            return
        self.log(f"[extract] 运行 {script} {game_path}")
        self.stage_var.set("提取中… / Extracting…")
        self.bar["value"] = 0
        def worker():
            import importlib.util
            cap = _StreamCap(self.q)    # stdout 代理：整行实时进日志区（听译长任务可见进度）
            old_argv = sys.argv
            old_stdout = sys.stdout
            try:
                mod_name = script.replace(".py", "")
                spec = importlib.util.spec_from_file_location(mod_name, script_path)
                mod = importlib.util.module_from_spec(spec)
                sys.argv = [script, game_path]
                sys.stdout = cap
                spec.loader.exec_module(mod)
                mod.main()
                sys.argv = old_argv
                sys.stdout = old_stdout
                for line in cap.buf_tail():   # 旧引擎替换 stdout 的输出补末尾；新引擎为空
                    self.log(f"  | {line}")
                # 找最新生成的提取产物（引擎命名不一：<game>_extracted.json /
                # game.extracted.json / <game>.extracted.json，统配 [_.]）
                import glob as g
                cands = sorted(g.glob(os.path.join(base, "*[_.]extracted*.json")),
                               key=os.path.getmtime, reverse=True)
                if cands:
                    newest = cands[0]
                    self.q.put(("extracted", newest))
                else:
                    self.q.put(("error", "提取完成但未找到输出文件: " +
                                ("; ".join(cap.tail(3)) or "no output")))
            except SystemExit:
                sys.stdout = old_stdout
                sys.argv = old_argv
                msg = "\n".join(cap.tail(5)) or "提取脚本退出（无输出）"
                self.q.put(("error", msg))
            except Exception:
                sys.stdout = old_stdout
                sys.argv = old_argv
                self.q.put(("error", traceback.format_exc()[-800:]))
            finally:
                try:
                    cap.flush()
                except Exception:
                    pass
        threading.Thread(target=worker, daemon=True).start()

    def pick(self):
        p = filedialog.askopenfilename(
            title=self.T("sel_file"),
            filetypes=[("JSON / MTool", "*.json"),
                       ("Games 游戏 / EXE", "*.exe"),
                       ("Subtitles 字幕", "*.srt *.ass *.ssa *.vtt"),
                       ("Video 视频", "*.mp4 *.mkv *.avi *.mov *.ts *.webm *.wmv"),
                       ("Audio 音频", "*.mp3 *.wav *.m4a *.flac *.ogg *.opus"),
                       ("Comics 漫画", "*.cbz *.cbr *.cb7"),
                       ("All files 全部", "*.*")])
        if not p:
            self.log("文件选择已取消——接下来选文件夹 / File dialog cancelled — pick a folder next")
            p = filedialog.askdirectory(
                title="Select folder 文件夹（游戏/字幕/视频/漫画均可）/ any folder")
        if p:
            self.on_drop(p)

    def set_file(self, p):
        self.src_file = p
        self.out_file = None
        self.stage_var.set(self.T("ready").format(os.path.basename(p)))
        self.detail_var.set(p)
        self.start_btn.config(state="normal")
        self.open_btn.config(state="disabled")
        self._set_drop_note("ok")
        self.log(f"[file] {p}")

    def start(self):
        if not self.src_file or (self.worker and self.worker.is_alive()):
            return
        sl = dict(LANGS)[self.sl_var.get()]
        tl = dict(LANGS)[self.tl_var.get()]
        try:
            mt_config.build_url(self.url_var.get().strip() or mt_config.DEFAULT_ENDPOINT,
                                "test", sl, tl)
        except ValueError as e:
            messagebox.showerror(self.T("msg_badurl"), str(e))
            return
        h = hashlib.md5(self.src_file.encode()).hexdigest()[:8]
        work = os.path.join(mt_config.base_dir(), "mt_work", h)
        pipe = Pipe(self.src_file, work, sl, tl, self.cancel, self._cb, self.log,
                    endpoint=self.url_var.get().strip(),
                    api_key=self.key_var.get().strip(),
                    api_header=self.hdr_var.get().strip(),
                    auto_names=self.autonames_var.get(),
                    lang=self.lang,
                    api_type=dict(API_TYPES)[self.type_var.get()],
                    model=self.model_var.get().strip())
        self.cancel.clear()
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self._set_drop_note("")
        self.log(self.T("log_start").format(self.sl_var.get(), self.tl_var.get()))
        self.worker = threading.Thread(target=self._work, args=(pipe,), daemon=True)
        self.worker.start()

    def _work(self, pipe):
        try:
            dst, ok, drop = pipe.run()
            self.q.put(("done", (dst, ok, drop)))
        except Cancel:
            self.q.put(("cancelled", None))
        except mt_config.ApiError as e:
            self.q.put(("error", e.args[0]))   # 友好双语提示，非 traceback
        except Exception:
            self.q.put(("error", traceback.format_exc()))

    def _cb(self, stage, done, total, note):
        self.q.put(("prog", (stage, done, total, note)))

    def cancel_now(self):
        self.cancel.set()
        self.log(self.T("log_cancel"))

    def export_mtool(self):
        """把最新译文导出为游戏目录下的 ManualTransFile.json（MTool 挂载用）"""
        import glob as g, subprocess as sp
        base = mt_config.base_dir()
        cands = sorted(g.glob(os.path.join(base, "*_translated.json")),
                       key=os.path.getmtime, reverse=True)
        if not cands:
            messagebox.showinfo("Info", self.T("g_mtool_no"))
            return
        trfile = cands[0]
        args = [sys.executable, self._resolve_script("engines/mtool_export.py"), trfile]
        if self.game_path and os.path.isdir(self.game_path):
            args += ["--dir", self.game_path]
        else:
            self.log("[mtool] " + self.T("g_mtool_nogame"))
        r = sp.run(args, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=base)
        self.log((r.stdout or "").strip())
        if r.returncode != 0:
            messagebox.showerror(self.T("error"), (r.stderr or "")[-400:])
            return
        import re as _re
        m = _re.search(r"导出 (\d+) 键.*?→ (.+)", r.stdout or "")
        if m:
            messagebox.showinfo(self.T("g_mtool"),
                                self.T("g_mtool_ok").format(m.group(1), m.group(2)))

    def apply_to_game(self):
        """点击「导入游戏」按钮：找译文 json + 游戏路径，运行对应 apply 脚本"""
        if not self.game_path or not self.apply_script:
            messagebox.showwarning("Info", "请先拖入游戏目录进行引擎识别 / Drag a game folder first")
            return
        # 找最新译文 json
        import glob as g
        base = mt_config.base_dir()
        cands = sorted(g.glob(os.path.join(base, "*_translated.json")),
                       key=os.path.getmtime, reverse=True)
        if not cands:
            # 退而求其次：找 *_extracted_translated.json
            cands = sorted(g.glob(os.path.join(base, "*_extracted_translated.json")),
                           key=os.path.getmtime, reverse=True)
        if not cands:
            messagebox.showinfo(
                "No Translation / 无译文",
                "未找到已翻译的 json 文件。\n"
                "请先完成翻译（开始翻译→完成），或手动选择译文文件。\n\n"
                "No translated json found. Complete translation first,\n"
                "or select a translated json file manually.")
            return
        trfile = cands[0]
        if messagebox.askyesno(
                "Apply to Game / 导入游戏",
                f"译文文件: {os.path.basename(trfile)}\n"
                f"游戏目录: {self.game_path}\n"
                f"回写脚本: {self.apply_script}\n\n"
                f"原文件将自动备份为 .automt.bak。确认导入？"):
            self._run_applier(self.game_path, trfile, self.apply_script)

    def _run_applier(self, game_path, trfile, script):
        """在线程中运行回写脚本"""
        script_path = self._resolve_script(script)
        if not script_path:
            messagebox.showerror("Error", f"引擎脚本缺失: {script}")
            return
        self.log(f"[apply] 运行 {script} {game_path} {trfile}")
        self.stage_var.set("回写中… / Applying…")
        self.lbl_stage.config(foreground=self.pal["accent"])
        self.bar["value"] = 50
        for b in (self.apply_btn, self.mtool_btn, self.g_extract_btn):
            b.config(state="disabled")
        def worker():
            import importlib.util
            cap = _StreamCap(self.q)    # stdout 代理：整行实时进日志区
            old_argv = sys.argv
            old_stdout = sys.stdout
            try:
                mod_name = script.replace(".py", "")
                spec = importlib.util.spec_from_file_location(mod_name, script_path)
                mod = importlib.util.module_from_spec(spec)
                sys.argv = [script, game_path, trfile]
                sys.stdout = cap
                spec.loader.exec_module(mod)
                if hasattr(mod, "main"):
                    mod.main()
                elif hasattr(mod, "apply_all"):
                    mod.apply_all()
                sys.stdout = old_stdout
                sys.argv = old_argv
                for line in cap.buf_tail():   # 旧引擎替换 stdout 的输出补末尾；新引擎为空
                    self.log(f"  | {line}")
                self.bar["value"] = 100
                self.stage_var.set("✅ 已导入游戏 / Applied to Game")
                self.q.put(("applied", game_path))
            except SystemExit:
                sys.stdout = old_stdout
                sys.argv = old_argv
                msg = "\n".join(cap.tail(5)) or "apply 脚本退出"
                self.q.put(("error", msg))
            except Exception:
                sys.stdout = old_stdout
                sys.argv = old_argv
                self.q.put(("error", traceback.format_exc()[-800:]))
            finally:
                try:
                    cap.flush()
                except Exception:
                    pass
        threading.Thread(target=worker, daemon=True).start()

    def open_out(self):
        if self.out_file and os.path.exists(self.out_file):
            os.startfile(os.path.dirname(self.out_file))

    def save_env(self):
        try:
            mt_config.save_env({
                "MT_ENDPOINT": self.url_var.get().strip(),
                "MT_API_KEY": self.key_var.get().strip(),
                "MT_API_HEADER": self.hdr_var.get().strip(),
                "MT_AUTO_NAMES": "1" if self.autonames_var.get() else "0",
                "MT_LANG": self.lang,
                "MT_API_TYPE": dict(API_TYPES)[self.type_var.get()],
                "MT_MODEL": self.model_var.get().strip(),
            })
            self.log(self.T("log_cfg").format(mt_config.env_path()))
            messagebox.showinfo(self.T("msg_saved"), self.T("msg_saved_b").format(mt_config.env_path()))
        except Exception as e:
            messagebox.showerror(self.T("msg_savefail"), str(e))

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.logbox.config(state="normal")
                    self.logbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {payload}\n")
                    self.logbox.see("end")
                    self.logbox.config(state="disabled")
                elif kind == "prog":
                    stage, done, total, note = payload
                    name = {"clean": self.T("stage_clean"), "trans": self.T("stage_trans"),
                            "apply": self.T("stage_apply")}[stage]
                    pct = done * 100 // max(total, 1)
                    self.stage_var.set(f"{name}  {done}/{total}  （{pct}%）")
                    self.bar["value"] = pct
                    self.detail_var.set(f"{note}    {pct}%")
                elif kind == "done":
                    dst, ok, drop = payload
                    self.out_file = dst
                    self.library_add(dst, ok, drop)
                    self.log("[hint] 可先在「✏️ 译文微调」页检查修改，再导入游戏 / "
                             "Review & fix translations before applying")
                    self.bar["value"] = 100
                    self.stage_var.set(self.T("done_stage"))
                    self.detail_var.set(f"ok={ok}, skipped={drop}")
                    self.log(f"[output] {dst}")
                    self.start_btn.config(state="normal")
                    self.g_translate_btn.config(state="normal")
                    self.cancel_btn.config(state="disabled")
                    self.open_btn.config(state="normal")
                    self._set_drop_note("ok")
                    # 翻译完成 → 如果之前识别过游戏引擎，询问是否立即导入
                    if self.game_path and self.apply_script:
                        self.apply_btn.config(state="normal")
                        self.nb.select(1)
                        if messagebox.askyesno(
                                "Apply to Game / 导入游戏",
                                f"翻译完成！是否立即导入游戏？\n"
                                f"Translation complete! Apply to game now?\n\n"
                                f"游戏: {os.path.basename(self.game_path)}\n"
                                f"引擎: {self.game_engine}\n"
                                f"原文件将自动备份。"):
                            self._run_applier(self.game_path, dst, self.apply_script)
                        else:
                            self.log("[hint] 可稍后点击「④ 导入游戏」按钮回写翻译 / "
                                     "Click 'Apply to game' later")
                    else:
                        messagebox.showinfo(self.T("msg_done_t"),
                                            self.T("msg_done_b").format(ok, drop, dst))
                elif kind == "applied":
                    self.log(f"[applied] ✓ 翻译已导入游戏: {payload}")
                    self.library_mark_applied(payload)
                    self._set_drop_note("ok")
                    self.lbl_stage.config(foreground=self.pal["ok"])
                    self.apply_btn.config(state="normal")
                    self.g_extract_btn.config(state="normal")
                    self.mtool_btn.config(state="normal")
                    messagebox.showinfo(
                        "Applied / 已导入",
                        f"翻译已成功导入游戏！\nTranslation applied successfully!\n\n"
                        f"游戏: {payload}\n"
                        f"（Kirikiri/Ren'Py 为非破坏补丁，删除补丁文件即还原；"
                        f"其余引擎原文件已备份 .automt.bak）")
                elif kind == "cancelled":
                    self.stage_var.set(self.T("cancelled"))
                    self.lbl_stage.config(foreground=self.pal["hint"])
                    self.start_btn.config(state="normal")
                    self.g_translate_btn.config(state="normal")
                    self.cancel_btn.config(state="disabled")
                    self.log(self.T("log_cancelled"))
                elif kind == "extracted":
                    self.set_file(payload)
                    self.g_translate_btn.config(state="normal")
                    self.g_extract_btn.config(state="normal")
                    self.apply_btn.config(state="disabled")
                    self.stage_var.set(self.T("g_extracted").format(os.path.basename(payload)))
                    self.lbl_stage.config(foreground=self.pal["ok"])
                    self.log(f"[extract] 提取完成，已加载: {payload}")
                    self.log("[hint] 点击「③ 开始翻译」继续；翻译完成会自动询问导入游戏")
                elif kind == "error":
                    self.stage_var.set("❌ " + self.T("error"))
                    self.lbl_stage.config(foreground=self.pal["err"])
                    self.start_btn.config(state="normal")
                    self.g_translate_btn.config(state="normal")
                    self.g_extract_btn.config(state="normal")
                    if self.game_path and self.apply_script:
                        self.apply_btn.config(state="normal")
                    self.mtool_btn.config(state="normal")
                    self.cancel_btn.config(state="disabled")
                    self.log(payload)
                    messagebox.showerror(self.T("error"), payload[:1500])
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

def main():
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
