# -*- coding: utf-8 -*-
"""OmniTrans 配置层：.env 读写 + 自定义翻译接口支持。

隐私设计（开源友好）：
- 一切个人配置（自定义接口 URL / API Key / 请求头）都放 .env，.env 进 .gitignore
- 不填则使用内置免费端点（公开、无需密钥）
- 代码中不包含任何密钥、个人路径

.env 支持的变量：
    MT_ENDPOINT=https://xxx/translate?sl={sl}&tl={tl}&q={q}
        {sl}=源语言 {tl}=目标语言 {q}=URL编码后的原文，三个占位符必须出现 {q} 至少一次
    MT_API_KEY=你的密钥          （可选）
    MT_API_HEADER=Authorization  （可选，默认 Authorization，值以 Bearer 方式发送；
                                  指定其他头名则以原值发送）
响应格式自动识别：谷歌 /t 列表、DeepL {"translations":[{"text":..}]}、纯文本
"""
import os, re, sys, json, urllib.parse

DEFAULT_ENDPOINT = ("https://clients5.google.com/translate_a/t"
                    "?client=dict-chrome-ex&sl={sl}&tl={tl}&q={q}")

ENV_KEYS = ("MT_ENDPOINT", "MT_API_KEY", "MT_API_HEADER", "MT_SL", "MT_TL",
            "MT_AUTO_NAMES", "MT_LANG", "MT_API_TYPE", "MT_MODEL", "MT_FALLBACK",
            "MT_THEME", "MT_BG", "MT_CONTEXT", "MT_ASR_MODEL", "MT_FONT",
            "MT_COMIC_OCR")

class ApiError(Exception):
    """kind: 'fatal' 立即终止（401/402/404 等，重试无意义）
            'skip'  跳过该条保持原文（内容安全策略拦截）
            'retry' 可重试（限流/网络抖动）"""
    def __init__(self, kind, msg):
        super().__init__(msg)
        self.kind = kind

def classify_error(exc, body=""):
    """把底层异常翻译成 (kind, 双语友好提示)。body 为 HTTP 响应体（若有）。"""
    code = getattr(exc, "code", None)
    text = (body or "")[:800].lower()
    if code == 401 or "invalid api key" in text or "invalid_api_key" in text \
            or "incorrect api key" in text or "authentication" in text and "fail" in text:
        return "fatal", "API Key 无效或未填写（401 Invalid API key）——请检查 Key / Invalid API key"
    if code == 402 or "insufficient" in text or "balance" in text or "quota" in text \
            or "arrearage" in text or "余额" in text:
        return "fatal", ("账户余额/配额不足（402 Insufficient balance/quota）——"
                         "请充值或更换 Key / Insufficient balance or quota")
    if code == 404 or ("model" in text and "not found" in text) or "does not exist" in text:
        return "fatal", "模型不存在（404 Model not found）——请检查 Model 名称 / Model not found"
    if "content_policy" in text or "content policy" in text or "content_filter" in text \
            or "sensitive" in text or "敏感" in text or "blocked by" in text and "policy" in text:
        return "skip", ("内容被服务方安全策略拦截（敏感词）——该条保持原文 / "
                        "Content blocked by provider safety policy, string kept as-is")
    if code == 429 or "rate" in text and "limit" in text:
        return "retry", "请求过快被限流（429）——自动退避重试 / Rate limited, backing off"
    if "html" in text[:200] or "<html" in text[:200].lower() or code == 403:
        return "retry", ("端点返回异常（可能被反爬/接口变更 403）——将重试，"
                         "持续失败请更换接口 / Endpoint returned unexpected content")
    return "retry", f"{type(exc).__name__}: {exc}"

def translate_once(text, sl, tl, endpoint=None, api_key=None, api_header=None,
                   api_type="get", model=None, timeout=30, opener=None):
    """统一翻译调用。
    api_type='get'    —— 机翻：GET 模板端点（{sl}/{tl}/{q} 占位符）
    api_type='openai' —— AI 翻译：OpenAI 兼容 chat/completions（POST + JSON）
    网络/鉴权类错误统一转成 ApiError(kind, 双语提示)。
    """
    import urllib.request
    import urllib.error
    opener = opener or urllib.request.urlopen

    def run():
        if api_type == "openai":
            url = (endpoint or "").strip()
            if not url:
                raise ApiError("fatal", "AI 翻译需要填写完整接口地址，"
                               "例如 https://api.deepseek.com/chat/completions / URL is empty")
            sys_prompt = ("You are a professional game translator. Translate the user's text "
                          f"from {sl} to {tl}. Output ONLY the translation, nothing else. "
                          "Keep placeholder tokens like 〔T1a2b3c4〕 EXACTLY unchanged and in "
                          "the corresponding places. Preserve line breaks where they appear as tokens.")
            body = json.dumps({
                "model": model or "gpt-4o-mini",
                "messages": [{"role": "system", "content": sys_prompt},
                             {"role": "user", "content": text}],
                "temperature": 0.3,
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if api_key:
                h = (api_header or "Authorization").strip() or "Authorization"
                headers[h] = f"Bearer {api_key}" if h.lower() == "authorization" else api_key
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with opener(req, timeout=max(timeout, 120)) as r:
                return parse_response(r.read().decode("utf-8", "replace"))
        url = build_url(endpoint or DEFAULT_ENDPOINT, text, sl, tl)
        req = urllib.request.Request(url, headers=build_headers(api_key, api_header))
        with opener(req, timeout=timeout) as r:
            return parse_response(r.read().decode("utf-8", "replace"))

    try:
        return run()
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        kind, msg = classify_error(e, body)
        raise ApiError(kind, msg) from None
    except urllib.error.URLError as e:
        raise ApiError("retry", f"网络错误（{e.reason}）——将重试 / Network error, retrying") from None
    except ApiError:
        raise
    except Exception as e:
        kind, msg = classify_error(e)
        raise ApiError(kind, msg) from None

def _strip_json_comments(txt):
    """剥离 JSON 外层的 // 注释（整行/行尾），字符串内的 // 原样保留。

    逐字符扫描维护 in-string 状态；游戏文本键完全可能以 "//" 开头
    （如 Wolf 提取出的注释型台词），正则方案会误杀。
    """
    out, i, n = [], 0, len(txt)
    in_str = False
    while i < n:
        c = txt[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:          # 转义序列（含 \"）整体保留
                out.append(txt[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
        elif c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif c == "/" and txt.startswith("//", i):
            j = txt.find("\n", i)
            i = n if j < 0 else j                # 注释吃到行尾（保留 \n）
        else:
            out.append(c)
            i += 1
    return "".join(out)


def load_loose_json(path):
    """加载 MTool 翻译文件：宽容处理 BOM、CRLF、JSON 外层 // 注释、控制字符。"""
    txt = open(path, encoding="utf-8-sig", errors="replace").read()
    return json.loads(_strip_json_comments(txt), strict=False)   # strict=False: 允许字符串内的原始控制字符


# ---------- AI 批量翻译（OpenAI 兼容；N 条打包 + 等长校验） ----------
AI_BATCH_SYS = (
    "You are a professional game localizer. Translate each item's \"text\" from "
    "{sl} to {tl}.\n"
    "STRICT RULES:\n"
    "- Return ONLY a JSON object: {{\"items\":[{{\"id\":<same id>,\"zh\":\"<translation>\"}}]}}\n"
    "- Every input id must appear exactly once. Never add, drop, merge or reorder items.\n"
    "- Keep placeholder tokens like 〔T1a2b3c4〕 EXACTLY unchanged and in their positions.\n"
    "- Preserve line breaks and trailing quotation marks such as 」』\".\n"
    "- If an item has a \"ctx\" field, it is surrounding dialogue provided as context "
    "ONLY — never translate it and never include it in your output."
)


def _extract_json_items(content, n):
    """从模型回复中提取 n 条译文（按 id 对齐）。失败抛 ValueError。"""
    s = content.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)          # 去 markdown 围栏
    if s.startswith("[") or s.startswith("{"):
        try:
            d = json.loads(s)
        except Exception:
            # 宽容：截取首个 { 到末个 }
            i, j = s.find("{"), s.rfind("}")
            k, l = s.find("["), s.rfind("]")
            lo, hi = max(i, k), min(j if j >= 0 else len(s), l if l >= 0 else len(s))
            if lo < 0 or hi <= lo:
                raise ValueError("no JSON found")
            d = json.loads(s[lo:hi + 1])
    else:
        raise ValueError("not JSON")
    items = None
    if isinstance(d, dict):
        for key in ("items", "translations", "data", "results"):
            if isinstance(d.get(key), list):
                items = d[key]
                break
    elif isinstance(d, list):
        items = d
    if not items:
        raise ValueError("no items array")
    out = {}
    for it in items:
        if isinstance(it, dict):
            idx = it.get("id")
            txt = it.get("zh", it.get("translation", it.get("text", it.get("译文"))))
            if isinstance(idx, int) and isinstance(txt, str):
                out[idx] = txt
        elif isinstance(it, str) and len(items) == n:
            out[len(out) + 1] = it
    if len(out) != n or set(out) != set(range(1, n + 1)):
        raise ValueError(f"item count mismatch {len(out)}/{n}")
    return [out[i] for i in range(1, n + 1)]


def translate_batch_openai(texts, sl, tl, endpoint, ctxs=None,
                           api_key=None, api_header=None, model=None,
                           timeout=180, opener=None):
    """AI 批量翻译：N 条打包为带 id 的 JSON 请求，返回与输入等长的译文列表。
    结构不符抛 ValueError（调用方降级）；网络/鉴权错误统一 ApiError。"""
    import urllib.request
    import urllib.error
    opener = opener or urllib.request.urlopen
    if not (endpoint or "").strip():
        raise ApiError("fatal", "AI 翻译需要填写完整接口地址 / URL is empty")
    items = []
    for i, t in enumerate(texts, 1):
        it = {"id": i, "text": t}
        if ctxs and ctxs[i - 1]:
            it["ctx"] = ctxs[i - 1]
        items.append(it)
    body = json.dumps({
        "model": model or "gpt-4o-mini",
        "messages": [
            {"role": "system",
             "content": AI_BATCH_SYS.format(sl=sl, tl=tl)},
            {"role": "user",
             "content": json.dumps({"items": items}, ensure_ascii=False)},
        ],
        "temperature": 0.3,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        h = (api_header or "Authorization").strip() or "Authorization"
        headers[h] = f"Bearer {api_key}" if h.lower() == "authorization" else api_key
    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with opener(req, timeout=timeout) as r:
            content = parse_response(r.read().decode("utf-8", "replace"))
        return _extract_json_items(content, len(texts))
    except urllib.error.HTTPError as e:
        try:
            b = e.read().decode("utf-8", "replace")
        except Exception:
            b = ""
        kind, msg = classify_error(e, b)
        raise ApiError(kind, msg) from None
    except urllib.error.URLError as e:
        raise ApiError("retry", f"网络错误（{e.reason}）——将重试 / Network error, retrying") from None
    except ApiError:
        raise
    except ValueError:
        raise
    except Exception as e:
        kind, msg = classify_error(e)
        raise ApiError(kind, msg) from None

# ---------- 引擎注册表（识别/提取/回写/依赖 统一登记，GUI 与 CLI 共用） ----------
# 字段：name 显示名 / supported 是否支持静态提取回写 / extractor+applier 脚本 /
#       deps 依赖（pip 包名列表）/ detect 判定函数（入参 game_dir, files → bool）
def _has_ext(files, *exts):
    return any(f.lower().endswith(exts) for f in files)

def _det_kirikiri(game_dir, files):
    # .xp3 封包（也可能藏在 exe 同级；data.xp3/patch*.xp3 最常见）
    return _has_ext(files, ".xp3")

def _det_vxace(game_dir, files):
    # .rvdata2(VX Ace) / .rvdata(VX) / Data/*.rxdata(XP) —— Data 目录判定兜底
    if _has_ext(files, ".rvdata2", ".rvdata"):
        return True
    d = os.path.join(game_dir, "Data")
    return os.path.isdir(d) and _has_ext(set(os.listdir(d)), ".rxdata", ".rvdata2", ".rvdata")

def _det_mvmz(game_dir, files):
    for sub in ("data", "www/data"):
        p = os.path.join(game_dir, sub)
        if os.path.isdir(p) and any(f.startswith("Map") and f.endswith(".json")
                                    for f in os.listdir(p)):
            return True
    return False

def _det_srpg(game_dir, files):
    return "data.dts" in files and ("runtime.rts" in files or "environment.evs" in files
                                    or "game.exe" in files)

def _det_unity(game_dir, files):
    return any(f.endswith("_Data") and os.path.isdir(os.path.join(game_dir, f))
               for f in files)

def _det_renpy(game_dir, files):
    if _has_ext(files, ".rpa", ".rpyc"):
        return True
    # 解包后的 Ren'Py：game/ 下有脚本
    g = os.path.join(game_dir, "game")
    return os.path.isdir(g) and _has_ext(set(os.listdir(g)), ".rpa", ".rpyc", ".rpy")

def _det_tyrano(game_dir, files):
    # TyranoScript：data/scenario/*.ks + tyrano.js（或 data/system 配置）
    d = os.path.join(game_dir, "data", "scenario")
    if os.path.isdir(d) and any(f.endswith(".ks") for f in os.listdir(d)):
        return True
    return any(f.lower() == "tyrano.js" for f in files)

def _det_exhibit(game_dir, files):
    return _has_ext(files, ".rld") or "ExHIBIT.ini" in files or "ExHIBIT.exe" in files

def _det_wolf(game_dir, files):
    return _has_ext(files, ".wolf") or "wolf.dat" in files

def _det_siglus(game_dir, files):
    # Key 社 SiglusEngine：Scene.pck / Gameexe.dat / SiglusEngine.exe
    # （不泛匹配 *.pck：Godot 也用 .pck，会误判）
    return "Scene.pck" in files or "Gameexe.dat" in files or any(
        f.lower().startswith("siglusengine") for f in files)

def _det_alicesoft(game_dir, files):
    # AliceSoft：.ain 系统脚本 + .ex 资源
    return _has_ext(files, ".ain") or _has_ext(files, ".ex")

def _det_nscripter(game_dir, files):
    # NScripter：nscript.dat / *.nsa
    return "nscript.dat" in files or _has_ext(files, ".nsa")

def _det_exstia(game_dir, files):
    # Liar-soft 系 EXSTIA：_CONFIG.MED / install.dat
    return "_CONFIG.MED" in files or _has_ext(files, ".med")

def _det_subtitle(game_dir, files):
    # 字幕文件（.srt/.vtt/.ass/.ssa）：也看一层子目录（Season 01/ 结构）
    if _has_ext(files, ".srt", ".vtt", ".ass", ".ssa"):
        return True
    for d in files:
        p = os.path.join(game_dir, d)
        if os.path.isdir(p):
            try:
                if _has_ext(set(os.listdir(p)), ".srt", ".vtt", ".ass", ".ssa"):
                    return True
            except OSError:
                pass
    return False

_MEDIA_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".mpg", ".mpeg", ".ts",
               ".m2ts", ".webm", ".flv", ".m4v", ".3gp", ".ogv", ".rmvb", ".vob",
               ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".wma", ".aac", ".amr")

def _det_media(game_dir, files):
    # 音视频（faster-whisper 听译）：一层子目录（Season 01/ 结构）也算
    if _has_ext(files, *_MEDIA_EXTS):
        return True
    for d in files:
        p = os.path.join(game_dir, d)
        if os.path.isdir(p):
            try:
                if _has_ext(set(os.listdir(p)), *_MEDIA_EXTS):
                    return True
            except OSError:
                pass
    return False

_IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif")
_COMIC_ARCHIVES = (".cbz", ".cbr", ".cb7")

def _det_comic(game_dir, files):
    # 漫画：CBZ/CBR/CB7 档，或以页图为主的文件夹（含一层子目录，ch_001/ 结构）
    if _has_ext(files, *_COMIC_ARCHIVES):
        return True
    n = sum(1 for f in files if f.lower().endswith(_IMG_EXTS))
    if n >= 4:
        return True
    for d in files:
        p = os.path.join(game_dir, d)
        if os.path.isdir(p):
            try:
                n += sum(1 for f in os.listdir(p) if f.lower().endswith(_IMG_EXTS))
            except OSError:
                pass
            if n >= 4:
                return True
    return False

ENGINES = {
    # ---- 已支持（提供 extract/apply 全链路） ----
    "rpg_mvmz":   {"name": "RPG Maker MV/MZ", "supported": True,
                   "extractor": "engines/rpg_extract.py", "applier": "engines/rpg_apply.py",
                   "deps": [], "detect": _det_mvmz},
    "rpg_vxace":  {"name": "RPG Maker VX Ace / VX / XP", "supported": True,
                   "extractor": "engines/rva_extract.py", "applier": "engines/rva_apply.py",
                   "deps": [], "detect": _det_vxace},
    "srpg_studio": {"name": "SRPG Studio", "supported": True,
                    "extractor": "engines/srpg_extract.py", "applier": "engines/srpg_apply.py",
                    "deps": [], "detect": _det_srpg},
    "kirikiri":   {"name": "Kirikiri (吉里吉里)", "supported": True,
                   "extractor": "engines/krkr_extract.py", "applier": "engines/krkr_apply.py",
                   "deps": [], "detect": _det_kirikiri},
    "renpy":      {"name": "Ren'Py", "supported": True,
                   "extractor": "engines/renpy_extract.py", "applier": "engines/renpy_apply.py",
                   "deps": [], "detect": _det_renpy},
    "tyrano":     {"name": "TyranoScript", "supported": True,
                   "extractor": "engines/tyrano_extract.py", "applier": "engines/tyrano_apply.py",
                   "deps": [], "detect": _det_tyrano},
    "unity":      {"name": "Unity", "supported": True,
                   "extractor": "engines/unity_extract.py", "applier": "engines/unity_apply.py",
                   "deps": ["UnityPy"], "detect": _det_unity},
    # ---- 可识别、暂不支持（给出替代方案） ----
    "siglus":     {"name": "SiglusEngine (Key)", "supported": False, "detect": _det_siglus,
                   "reason": "私有加密格式（Scene.pck）。请使用 MTool 运行时翻译。"},
    "alice":      {"name": "AliceSoft (.ain/.ex)", "supported": False, "detect": _det_alicesoft,
                   "reason": "私有二进制格式（.ain 系统脚本）。可用 AIN 系工具（如 aindec）配合 MTool。"},
    "exhibit":    {"name": "ExHIBIT 私有引擎", "supported": False, "detect": _det_exhibit,
                   "reason": "私有二进制格式（.rld/.rnf/.JP），无公开文档，静态提取不可行。请使用 MTool 运行时翻译。"},
    "wolf":       {"name": "Wolf RPG Editor (ウディタ)", "supported": True,
                   "extractor": "engines/wolf_extract.py", "applier": "engines/wolf_apply.py",
                   "deps": [],
                   "detect": _det_wolf},
    "nscripter":  {"name": "NScripter", "supported": False, "detect": _det_nscripter,
                   "reason": "暂不支持（nscript.dat 加密封包）。可用 NSDEC 解包后翻译，或使用 MTool。"},
    "exstia":    {"name": "EXSTIA (.MED)", "supported": False, "detect": _det_exstia,
                   "reason": "暂不支持（Liar-soft 私有 .MED/install.dat 格式）。请使用 MTool 运行时翻译。"},
    # ---- 非游戏载体（放最后，避免抢走自带过场媒体的游戏目录） ----
    # media 在 subtitle 前：既有视频又有字幕的目录走 media（已有字幕自动复用，缺的听译补上）
    "media":      {"name": "Video / Audio (Whisper ASR)", "supported": True,
                   "extractor": "engines/media_extract.py",
                   "applier": "engines/subtitle_apply.py",
                   "deps": ["faster-whisper"], "detect": _det_media},
    "subtitle":  {"name": "Subtitle files (SRT/ASS/VTT)", "supported": True,
                  "extractor": "engines/subtitle_extract.py",
                  "applier": "engines/subtitle_apply.py",
                  "deps": [], "detect": _det_subtitle},
    # ---- 漫画（图片文件夹 / CBZ：OCR → 机翻 → 嵌字回写） ----
    "comic":     {"name": "Comics (images / CBZ)", "supported": True,
                  "extractor": "engines/comic_extract.py",
                  "applier": "engines/comic_apply.py",
                  "deps": ["rapidocr-onnxruntime", "Pillow"], "detect": _det_comic},
}

# 检测顺序：最具体的签名在前（避免 Unity 的 *_Data 等宽泛规则抢跑）；
# media/subtitle/comic 最宽泛（带视频/.srt/成堆图片的目录都命中），必须垫底
_DETECT_ORDER = ["exhibit", "siglus", "nscripter", "exstia", "kirikiri", "wolf",
                 "rpg_vxace", "srpg_studio", "rpg_mvmz", "renpy", "tyrano",
                 "alice", "unity", "media", "subtitle", "comic"]

def detect_engine(path):
    """传入游戏目录 / exe / 任意内容文件，返回 (engine_key, display_name, supported, reason)。
    文件路径先按自身扩展名判意图（拖的是字幕/视频/漫画档就是它，不看邻居），
    其余（如 .exe）回退到所在目录的内容识别。"""
    if os.path.isfile(path):
        fake = {os.path.basename(path)}
        for key in ("subtitle", "media", "comic"):
            e = ENGINES[key]
            try:
                if e["detect"](os.path.dirname(path), fake):
                    return (key, e["name"], e["supported"], e.get("reason", ""))
            except Exception:
                continue
    game_dir = path if os.path.isdir(path) else os.path.dirname(path)
    files = set(os.listdir(game_dir)) if os.path.isdir(game_dir) else set()
    for key in _DETECT_ORDER:
        e = ENGINES[key]
        try:
            if e["detect"](game_dir, files):
                return (key, e["name"], e["supported"], e.get("reason", ""))
        except Exception:
            continue
    return ("unknown", "未知内容", False,
            "无法识别内容。支持：游戏目录/EXE、字幕（.srt/.ass/.vtt）、音视频"
            "（.mp4/.mkv/.mp3…）、漫画（图片文件夹/.cbz）；MTool 导出的 json 可直接拖入。")

# 兼容旧接口：支持的引擎 → 提取脚本
def engine_extractor(key):
    return ENGINES.get(key, {}).get("extractor")

def engine_applier(key):
    return ENGINES.get(key, {}).get("applier")

ENGINE_EXTRACTORS = {k: e["extractor"] for k, e in ENGINES.items() if e.get("extractor")}

# ---------- UnityPy 检测与安装（GUI 用；不在此 import UnityPy 以免 PyInstaller 打包） ----------
def check_unitypy():
    """检测 UnityPy 是否可用（含系统 site-packages 补找）。返回 True/False。"""
    import importlib.util
    if importlib.util.find_spec("UnityPy") is not None:
        return True
    # 补找系统安装路径（打包 exe 不含 pip 包路径）
    import site as _site
    paths = list(_site.getsitepackages()) if hasattr(_site, 'getsitepackages') else []
    usp = _site.getusersitepackages()
    if usp:
        paths.append(usp)
    for sp in paths:
        if os.path.isdir(sp) and os.path.exists(os.path.join(sp, "UnityPy")):
            sys.path.insert(0, sp)
            if importlib.util.find_spec("UnityPy") is not None:
                return True
    return False

def install_unitypy():
    """pip install UnityPy。返回 (成功, 信息)。"""
    return pip_install("UnityPy")

def check_fasterwhisper():
    """检测 faster-whisper 是否可用（听译功能用；同 UnityPy 的补找逻辑）。"""
    import importlib.util
    if importlib.util.find_spec("faster_whisper") is not None:
        return True
    import site as _site
    paths = list(_site.getsitepackages()) if hasattr(_site, 'getsitepackages') else []
    usp = _site.getusersitepackages()
    if usp:
        paths.append(usp)
    for sp in paths:
        if os.path.isdir(sp) and os.path.exists(os.path.join(sp, "faster_whisper")):
            sys.path.insert(0, sp)
            if importlib.util.find_spec("faster_whisper") is not None:
                return True
    return False

def install_fasterwhisper():
    """pip install faster-whisper。返回 (成功, 信息)。"""
    return pip_install("faster-whisper")

def check_rapidocr():
    """检测 rapidocr-onnxruntime 是否可用（漫画 OCR 用；含系统 site-packages 补找）。"""
    import importlib.util
    if importlib.util.find_spec("rapidocr_onnxruntime") is not None:
        return True
    import site as _site
    paths = list(_site.getsitepackages()) if hasattr(_site, 'getsitepackages') else []
    usp = _site.getusersitepackages()
    if usp:
        paths.append(usp)
    for sp in paths:
        if os.path.isdir(sp) and os.path.exists(os.path.join(sp, "rapidocr_onnxruntime")):
            sys.path.insert(0, sp)
            if importlib.util.find_spec("rapidocr_onnxruntime") is not None:
                return True
    return False

def install_rapidocr():
    """pip install rapidocr-onnxruntime。返回 (成功, 信息)。"""
    return pip_install("rapidocr-onnxruntime")

def check_mangaocr():
    """检测 manga-ocr（日漫专用识别增强）是否已安装。"""
    import importlib.util
    return importlib.util.find_spec("manga_ocr") is not None

def install_mangaocr():
    """pip install manga-ocr（含 torch，较大）。返回 (成功, 信息)。"""
    return pip_install("manga-ocr")

def check_pillow():
    """检测 Pillow 是否可用（背景图功能用，GUI 可选依赖）。"""
    import importlib.util
    return importlib.util.find_spec("PIL") is not None

def install_pillow():
    """pip install Pillow。返回 (成功, 信息)。"""
    return pip_install("Pillow")

def pip_install(pkg):
    """pip install <pkg>。返回 (成功, 信息)。"""
    import subprocess
    for cmd in ([sys.executable if not getattr(sys, 'frozen', False) else "python",
                 "-m", "pip", "install", pkg],
                ["pip", "install", pkg]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=300)
            if r.returncode == 0:
                return True, (r.stdout or "")[-200:]
            last_err = (r.stderr or r.stdout or "pip failed")[-200:]
        except FileNotFoundError:
            last_err = "python/pip not found"
        except Exception as e:
            last_err = str(e)
    return False, last_err

def base_dir():
    """exe 旁边（PyInstaller 打包后 __file__ 在临时目录，须用 exe 自身位置）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def env_path():
    return os.path.join(base_dir(), ".env")

def load_env():
    """极简 .env 解析（无第三方依赖），不存在则返回空 dict"""
    cfg = {}
    p = env_path()
    if os.path.exists(p):
        for line in open(p, encoding="utf-8-sig"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k in ENV_KEYS:
                cfg[k] = v
    return cfg

def save_env(cfg):
    """把指定键写回 .env（保留原有注释与其他行）"""
    p = env_path()
    keep = []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8-sig"):
            s = line.strip()
            if s and not s.startswith("#") and "=" in s and s.partition("=")[0].strip() in cfg:
                continue
            keep.append(line.rstrip("\n"))
    while keep and not keep[-1]:
        keep.pop()
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        if keep:
            f.write("\n".join(keep) + "\n")
        for k in ENV_KEYS:
            if k in cfg and cfg[k]:
                f.write(f"{k}={cfg[k]}\n")

# ---------- 自动人名识别（按语言分治） ----------
# en 等拉丁文字：人名几乎总是首字母大写、几乎从不小写；普通词大小写混现
#                + 内置高频词库兜底（滤掉 thanks/sorry/doctor 这类习惯大写词）
# ja：片假名串 ≥3 字且高频 —— 日式游戏人名几乎全是片假名（硬特征），附带游戏术语停用表
# ru 等变格语言：同一人名有多个词形（Алиса/Алисы/Алисе），按大写前缀聚类合并
# zh/ko：无大小写、无假名 —— 无法零依赖可靠识别，跳过并提示用 names.txt
# 任何语言：names.txt 人工词条永远优先（含 =译名）
_AUTO_STOP = set("""i ok oh ah ha eh um hey you she he it they we the and but or not is are
was were be been do does did don cant can will would just so if then well now here there this
that these those what when where who how why yes no chapter part day days night gold silver
thanks sorry please hello goodbye today tomorrow yesterday maybe actually of course
mr mrs ms dr let get got go going come came take took make made know think see saw look want
need say said tell told ask asked feel felt find found give gave tell told never always ever
still even much many more most less least own same other another such only just quite very""".split())

# 英语高频词（经典 GSL 高频段 + 常见实词），把"习惯性大写的普通词"彻底滤掉
_EN_COMMON = set("""the be to of and a in that have i it for not on with he as you do at this
but his by from they we say her she or an will my one all would there their what so up out if
about who get which go me when make can like time no just him know take people into year your
good some could them see other than then now look only come its over think also back after use
two how our work first well way even new want because any these give day most us man thing
woman life child world school state family student group country problem hand part place case
week company system program question work government number night point home water room mother
area money story fact month lot right study book eye job word business issue side kind head
house service friend father power hour game line end member law car city community name
president team minute idea kid body information back parent face others level office door
health person art war history party result change morning reason research girl guide moment
air teacher force education foot boy age policy process music market sense nation plan college
interest death experience effect use class control care field development role effort rate
heart drug show leader light voice wife whole police mind price report decision son view
relationship town road arm difference value building action model season society tax director
position player record paper space ground form event official matter center couple site
project activity star table need court oil situation cost industry figure street image
itself phone either data cover quite picture clear practice piece land recent describe
product doctor wall patient worker news test movie certain north love personal open
support""".split())

# 日语：常见游戏术语片假名（这些是普通词不是人名）
_JA_KATA_STOP = set("""アイテム ダメージ ゴールド レベル メニュー スキル モンスター ゲーム
パーティー キャラクター ゲージ メッセージ システム イベント ミッション クエスト
セーブ ロード ボス アイコン サウンド データ ファイル ストーリー チャプター
バトル フィールド マジック ポーション エリア マップ キャンプ タウン ショップ
ホテル ダンジョン クラス ジョブ アビリティ チェスト キー アイテムボックス
レシピ テクニック コマンド ヘルプ セット アップ スタート エンド オープン
クローズ クリック タッチ パスワード ユーザー バージョン アップデート
ニュース インフォメーション ライブラリー ミュージック ボイス ボリューム
コスト パワー スピード ディフェンス アタック ヒール リカバリー チャンス
ピンチ ストップ リセット キャンセル オプション セレクト コンティニュー
プロローグ エピローグ シナリオ トーク テキスト ログ ヘッダー フッター
ウィンドウ アイコン バー バッジ トークン チェック レポート カテゴリー
タイプ ランク スコア ボーナス ペナルティ アイアン シルバー ブロンズ
ダイヤ ルビー サファイア エメラルド クリスタル オーブ リング アミュレット""".split())

# 俄语：句首高频词（防聚类误报）
_RU_STOP = set("""что как это они весь который когда даже если уже только очень можно нужно
быть он она они мы вы не да нет ну вот там здесь тогда зачем почему кто что-то
спасибо пожалуйста извини извините здравствуйте пока хорошо плохо может надо
скажи скажите знаю думаю посмотри""".split())

_KATA_RE = re.compile(r"[ァ-ヺー]{3,}")

def detect_names(texts, lang="en", min_count=2, min_ratio=0.65):
    """按语言自动发现专有名词候选。返回 [(name, count), ...] 按频率降序。"""
    from collections import Counter
    lang = (lang or "en").split("-")[0].lower()

    if lang == "ja":
        cnt = Counter()
        for t in texts:
            for w in _KATA_RE.findall(t):
                if w not in _JA_KATA_STOP:
                    cnt[w] += 1
        return [(w, c) for w, c in cnt.most_common() if c >= min_count]

    if lang in ("ru", "bg", "uk"):
        clusters = Counter()
        formcnt = Counter()
        for t in texts:
            for w in re.findall(r"[А-ЯЁ][а-яё]{3,}", t):
                clusters[w[:4]] += 1
                formcnt[w] += 1
        out = []
        for k, c in clusters.most_common():
            if c >= max(min_count, 3) and k.lower() not in _RU_STOP:
                members = [w for w in formcnt if w[:4] == k]
                best = max(members, key=lambda f: formcnt[f])  # 取最常见词形（多为原形）
                out.append((best, c))
        return out

    if lang in ("zh", "ko"):
        return []  # 无大小写/假名特征，零依赖无法可靠识别

    # 拉丁文字（en 等）
    cap, low, allcap = Counter(), Counter(), Counter()
    for t in texts:
        for w in re.findall(r"[A-Za-z][A-Za-z']*", t):
            if len(w) < 2:
                continue
            if w.isupper():
                allcap[w] += 1
            elif w[0].isupper():
                cap[w] += 1
            else:
                low[w] += 1
    out = []
    for w, c in cap.most_common():
        lw = w.lower()
        total = c + low.get(lw, 0)
        if (c >= min_count and c / total >= min_ratio
                and lw not in _AUTO_STOP and lw not in _EN_COMMON):
            out.append((w, c))
    for w, c in allcap.most_common():
        if c >= min_count and w.lower() not in _AUTO_STOP:
            out.append((w, c))
    return out

def build_url(endpoint, q, sl, tl):
    if "{q}" not in endpoint:
        raise ValueError("接口 URL 缺少 {q} 占位符（还需要 {sl} {tl} 可选占位符），"
                         "示例：https://xxx/t?sl={sl}&tl={tl}&q={q}")
    return (endpoint.replace("{sl}", urllib.parse.quote(sl or "auto"))
                    .replace("{tl}", urllib.parse.quote(tl or "zh-CN"))
                    .replace("{q}", urllib.parse.quote(q)))

def build_headers(api_key=None, api_header=None):
    if not api_key:
        return {}
    name = (api_header or "Authorization").strip() or "Authorization"
    if name.lower() == "authorization":
        return {name: f"Bearer {api_key}"}
    return {name: api_key}

def parse_response(raw):
    """自动识别常见机翻响应格式"""
    raw = raw.strip()
    try:
        d = json.loads(raw)
    except Exception:
        return raw  # 纯文本
    if isinstance(d, list):
        # 谷歌 dict-chrome-ex 现行格式：每项 [译文, 检测语言] → 取译文
        if d and isinstance(d[0], list):
            out = []
            for x in d:
                if isinstance(x, list) and x:
                    v = x[0]
                    out.append(v if isinstance(v, str) else "".join(str(i) for i in v))
                else:
                    out.append(str(x))
            return "".join(out)
        # 扁平列表：剥掉尾部的检测语言码（["译文","ja"] 变体兼容）
        if len(d) >= 2 and re.fullmatch(r"[a-z]{2}(?:-[A-Za-z0-9]+){0,2}", str(d[-1])):
            d = d[:-1]
        return "".join(str(x) for x in d)
    if isinstance(d, dict):
        # OpenAI 兼容 chat/completions
        ch = d.get("choices")
        if isinstance(ch, list) and ch:
            m = ch[0].get("message") if isinstance(ch[0], dict) else None
            if isinstance(m, dict) and isinstance(m.get("content"), str):
                return m["content"].strip()
            if isinstance(ch[0], dict) and isinstance(ch[0].get("text"), str):
                return ch[0]["text"].strip()  # legacy completions
        for path in (("translations",), ("data", "translations"), ("result",)):
            node = d
            ok = True
            for k in path:
                if isinstance(node, dict) and k in node:
                    node = node[k]
                else:
                    ok = False
                    break
            if ok and isinstance(node, list) and node and isinstance(node[0], dict):
                return "".join(str(t.get("text", t.get("translatedText", ""))) for t in node)
        for k in ("translatedText", "text", "result"):
            if isinstance(d.get(k), str):
                return d[k]
    return raw

# ---------- 历史污染修复 ----------
# 谷歌端点改版后，旧的批量解析把每条 [译文, 检测语言] 整只 str() 成了
# "['译文', 'ja']"。repair_value 修复存量译文数据（新数据不会再产生该形态）。
_QUOTED_RE = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"")

def repair_value(v):
    """\"['译文', 'ja']\" → \"译文\"；非该形态原样返回（绝不误伤方括号正常译文）。"""
    if not isinstance(v, str) or not (v.startswith("[") and v.endswith("]")):
        return v
    parts = [a or b for a, b in _QUOTED_RE.findall(v[1:-1])]
    return parts[0] if parts else v
