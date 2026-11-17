# -*- coding: utf-8 -*-
"""全引擎模拟矩阵测试（纯合成样本，零真实素材/零网络翻译/零窗口）
====================================================================
对 mt_config.ENGINES 里每个引擎做模拟测试：
  0) 注册表完整性：supported 必有 extract/apply 脚本；unsupported 必有 reason；
     _DETECT_ORDER 覆盖全部带 detect 的引擎
  1) 识别矩阵：合成游戏目录/文件 → detect_engine 全部命中正确引擎
  2) 载体格式矩阵：_MEDIA_EXTS/字幕/漫画档案 每个扩展名单投 → 正确路由
  3) Ren'Py 合成全链路：自写 RPC2 容器 + renpy.ast 桩 pickle → 提取 → 模拟翻译
     → tl 翻译包回写断言（含 PyExpr 界面字符串回归）
  4) Wolf 合成阶段链路：WolfTL dump JSON → _collect_dump 收集 → _apply_events 回写
  5) SRPG 合成阶段链路：patch JSON → walk_patch → chunk_back/apply_file 切回
  6) Unity 逻辑链路：scan_prefixed_strings → rebuild_prefixed → TextAsset JSON 回写
     （资产容器层需真实样本，这里覆盖纯逻辑）
  7) 音视频合成正向链路：Windows SAPI TTS 合成语音 → 本地 faster-whisper 听译
     → SRT → 模拟翻译 → 字幕回写（全合成音频，无任何真实素材）
运行：python tests/_test_engine_matrix.py
"""
import os, sys, io, json, time, pickle, zlib, struct, shutil, tempfile, subprocess
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENG = os.path.join(ROOT, "engines")
sys.path.insert(0, ROOT)
sys.path.insert(0, ENG)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import mt_config
import mt_coverage

FAILS = []
def check(name, cond, info=""):
    print(("✓ " if cond else "✗ ") + name + (f"  {info}" if info and not cond else ""))
    if not cond:
        FAILS.append(name)

tmp = tempfile.mkdtemp(prefix="mtx_")

# ========== 0) 注册表完整性 ==========
for key, e in mt_config.ENGINES.items():
    if e.get("supported"):
        ok = all(os.path.exists(os.path.join(ROOT, e[k])) for k in ("extractor", "applier") if e.get(k))
        check(f"注册表 {key}：提取/回写脚本齐备", ok)
    else:
        check(f"注册表 {key}：不支持项有 reason", bool(e.get("reason")))
detectable = {k for k, e in mt_config.ENGINES.items() if e.get("detect")}
check("注册表：_DETECT_ORDER 覆盖全部 detect",
      detectable == set(mt_config._DETECT_ORDER),
      str(detectable ^ set(mt_config._DETECT_ORDER)))

# ========== 1) 引擎识别矩阵（合成目录） ==========
def mkgame(name, files=(), dirs=()):
    g = os.path.join(tmp, name)
    os.makedirs(g, exist_ok=True)
    for d in dirs:
        os.makedirs(os.path.join(g, d), exist_ok=True)
    for f in files:
        p = os.path.join(g, f)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").close()
    return g

DETECT_CASES = [
    ("kirikiri",    mkgame("g_krkr", files=("data.xp3",))),
    ("wolf",        mkgame("g_wolf", files=("Game.exe", "Data.wolf"))),
    ("rpg_vxace",   mkgame("g_vxace", dirs=("Data",), files=("Data/Map001.rvdata2", "Game.exe"))),
    ("srpg_studio", mkgame("g_srpg", files=("data.dts", "Game.exe"))),
    ("rpg_mvmz",    mkgame("g_mvmz", dirs=("data",), files=("data/Map001.json", "Game.exe"))),
    ("renpy",       mkgame("g_renpy", dirs=("game",), files=("game/script.rpyc", "Game.exe"))),
    ("tyrano",      mkgame("g_tyrano", dirs=("data/scenario",), files=("data/scenario/first.ks",))),
    ("alice",       mkgame("g_alice", dirs=("Data",), files=("flow.ain", "Game.exe"))),
    ("unity",       mkgame("g_unity", dirs=("MyGame_Data",), files=("MyGame_Data/level0", "Game.exe"))),
    ("siglus",      mkgame("g_siglus", files=("Gameexe.dat",))),
    ("exhibit",     mkgame("g_exhibit", files=("ExHIBIT.exe",))),
    ("nscripter",   mkgame("g_nscr", files=("nscript.dat",))),
    ("exstia",      mkgame("g_exstia", files=("_CONFIG.MED",))),
]
for want, g in DETECT_CASES:
    got = mt_config.detect_engine(g)[0]
    check(f"识别 {want}", got == want, f"got={got}")

# ========== 2) 载体格式矩阵 ==========
for ext in mt_config._MEDIA_EXTS:
    f = os.path.join(tmp, "clip" + ext)
    open(f, "wb").close()
    got = mt_config.detect_engine(f)[0]
    if got != "media":
        check(f"格式路由 {ext} → media", False, got)
n_media_ok = sum(1 for ext in mt_config._MEDIA_EXTS
                 if mt_config.detect_engine(os.path.join(tmp, "clip" + ext))[0] == "media")
check(f"音视频格式路由 {n_media_ok}/{len(mt_config._MEDIA_EXTS)}", n_media_ok == len(mt_config._MEDIA_EXTS))
for ext in (".srt", ".vtt", ".ass", ".ssa"):
    f = os.path.join(tmp, "ep" + ext)
    open(f, "wb").close()
    check(f"字幕路由 {ext} → subtitle", mt_config.detect_engine(f)[0] == "subtitle")
for ext in mt_config._COMIC_ARCHIVES:
    f = os.path.join(tmp, "vol" + ext)
    open(f, "wb").close()
    check(f"漫画档案路由 {ext} → comic", mt_config.detect_engine(f)[0] == "comic")
imgd = mkgame("g_imgs")
for i in range(4):
    open(os.path.join(imgd, f"p{i}.png"), "wb").close()
check("漫画图片文件夹 → comic", mt_config.detect_engine(imgd)[0] == "comic")

# ========== 3) Ren'Py 合成全链路（自写 RPC2 + renpy.ast 桩 pickle） ==========
def _ensure_pkg(name):
    """pickle 序列化 GLOBAL 引用会 __import__(module)：父包也必须占位可导入"""
    if name not in sys.modules:
        m = types.ModuleType(name)
        m.__path__ = []
        sys.modules[name] = m
for _p in ("renpy", "renpy.ast", "renpy.ast.support"):
    _ensure_pkg(_p)

def _ast_stub(module, name):
    m = sys.modules[module]
    def __init__(self, *a, **k):
        self._args = a
        if k:
            self.__dict__.update(k)
    def __reduce__(self):
        # 类自身按 GLOBAL renpy.ast.<Name> 序列化；载入侧 _SafeUnpickler 映射为桩类。
        # 注意不能用 copyreg._reconstructor：pickler 按真实模块名 copy_reg 写出，
        # 载入侧白名单只认 copyreg，整个 REDUCE 会被吃成桩。
        return (type(self), (), dict(self.__dict__))
    cls = type(name, (), {"__init__": __init__, "__reduce__": __reduce__,
                          "__module__": module})
    setattr(m, name, cls)
    return cls

def write_rpyc(path, stmts):
    meta = {"bytecode": "mtx-synth"}
    b1 = zlib.compress(pickle.dumps(meta, protocol=2))
    b2 = zlib.compress(pickle.dumps((meta, stmts), protocol=2))
    magic = b"RENPY RPC2"
    off1 = len(magic) + 12 * 3
    off2 = off1 + len(b1)
    out = magic + struct.pack("<III", 1, off1, len(b1)) \
        + struct.pack("<III", 2, off2, len(b2)) + struct.pack("<III", 0, 0, 0) \
        + b1 + b2
    open(path, "wb").write(out)

Say = _ast_stub("renpy.ast", "Say")
TranslateSay = _ast_stub("renpy.ast", "TranslateSay")
Menu = _ast_stub("renpy.ast", "Menu")
PyExpr = _ast_stub("renpy.ast.support", "PyExpr")

stmts = [
    Say(who="アリス", what="おはよう、先輩！", identifier="say_mtx0001"),
    TranslateSay(who=None, what="また会えるかな。", identifier="say_mtx0002"),
    Menu(identifier="menu_mtx01", items=[
        ["はい", "True", []],
        ["いいえ", "False", [Say(who=None, what="やめておくよ。", identifier="say_mtx0003")]],
    ]),
    PyExpr('_("図書館")'),
    Say(who="シスター", what="おはよう、先輩！", identifier="say_mtx0004"),  # 同文不同 identifier
]
game_rp = os.path.join(tmp, "mtx_renpy")
mkgame(os.path.relpath(game_rp, tmp), dirs=("game",))
write_rpyc(os.path.join(game_rp, "game", "script.rpyc"), stmts)
# 纯 Python 解桩自检（不经 CLI）
import renpy_rpyc as RC
_, rstmts = RC.read_rpyc(os.path.join(game_rp, "game", "script.rpyc"))
dlg = RC.collect_dialogue(rstmts)
py = RC.collect_py_strings(rstmts)
# 5 条：2 同文 say（不同 identifier 都收）+ 1 say + 2 选项；
# Menu 嵌套 block 深处的 say 不在遍历范围（walk 只下钻一层 list，引擎设计如此）
check("renpy 合成：对话收集 5 条", len(dlg) == 5, str(len(dlg)))
check("renpy 合成：菜单选项收集", any(d["kind"] == "choice" and d["what"] == "はい" for d in dlg))
check("renpy 合成：PyExpr 界面字符串（桩名回归）", "図書館" in py, str(py))

def run_cli(script, *args):
    r = subprocess.run([sys.executable, os.path.join(ENG, script)] + list(args),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180, cwd=ROOT)
    if r.returncode != 0:
        print("  [cli]", (r.stderr or r.stdout)[-400:])
    return r

r = run_cli("renpy_extract.py", game_rp)
ext_json = os.path.join(ROOT, "mtx_renpy_extracted.json")
check("renpy 提取 CLI 成功", r.returncode == 0 and os.path.exists(ext_json))
if os.path.exists(ext_json):
    d = mt_config.load_loose_json(ext_json)
    check("renpy 提取：唯一文本 5 条", len(d) == 5, f"{len(d)} {sorted(d)[:6]}")
    tr = {k: "【译】" + k for k in d}
    tr_json = os.path.join(ROOT, "mtx_renpy_extracted_translated.json")
    json.dump(tr, open(tr_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    r = run_cli("renpy_apply.py", game_rp, tr_json, "chinese")
    tl = os.path.join(game_rp, "game", "tl", "chinese", "omnitrans_script.rpy")
    check("renpy 回写：tl 包生成", r.returncode == 0 and os.path.exists(tl))
    if os.path.exists(tl):
        txt = open(tl, encoding="utf-8").read()
        check("renpy tl：say 块（identifier 定位）", "translate chinese say_mtx0001:" in txt)
        check("renpy tl：同文双 identifier 都回填",
              txt.count("【译】おはよう、先輩！") == 2, str(txt.count("【訳】")))
        check("renpy tl：strings 块（选项/界面）",
              'old "はい"' in txt and 'new "【译】はい"' in txt and 'new "【译】図書館"' in txt)

# ========== 4) Wolf 合成阶段链路（WolfTL dump JSON → 收集 → 回写） ==========
import wolf_extract as WE
import wolf_apply as WA
dump = os.path.join(tmp, "dump")
for sub in ("common", "mps", "db"):
    os.makedirs(os.path.join(dump, sub), exist_ok=True)
json.dump([
    {"code": 401, "codeStr": "Message", "stringArgs": ["こんにちは、冒険者よ", "今日もいい天気ですね"]},
    {"code": 1102, "codeStr": "Choices", "stringArgs": ["はい", "いいえ"]},
    {"code": 0, "codeStr": "Set", "stringArgs": ["変数操作"]},   # 非文本指令：不收
], open(os.path.join(dump, "common", "e1.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"events": [{"codeStr": "Message", "stringArgs": ["魔物が現れた！"]}]},
          open(os.path.join(dump, "mps", "m1.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"CDatabase": [[{"name": "武器", "data": [
    {"name": "名前", "value": "鉄の剣"},
    {"name": "説明", "value": "攻撃力が５上がる。"}]}]]},
    open(os.path.join(dump, "db", "db1.json"), "w", encoding="utf-8"), ensure_ascii=False)
collected = {}
n = WE._collect_dump(dump, collected)
check("wolf 收集：事件+数据库 8 条", n == 8 and len(collected) == 8, f"n={n} {len(collected)}")
check("wolf 收集：非文本指令跳过", "変数操作" not in collected)
evs = json.load(open(os.path.join(dump, "common", "e1.json"), encoding="utf-8"))
tr_wolf = {k: "【狼】" + k for k in collected}
stats = {"applied": 0, "missed": 0}
WA._apply_events(evs, tr_wolf, stats)
check("wolf 回写：stringArgs 全替换", stats["applied"] == 4 and stats["missed"] == 0, str(stats))
check("wolf 回写：值已写入", evs[0]["stringArgs"][0] == "【狼】こんにちは、冒険者よ")
conv, lost = __import__("ain_apply").convert("汉化测试")
check("wolf/ain JIS 字形映射可用", isinstance(conv, str) and conv, str(conv))

# ========== 5) SRPG 合成阶段链路（patch JSON → walk_patch → 切回） ==========
import srpg_extract as SE
import srpg_apply as SA
patch = os.path.join(tmp, "patch")
os.makedirs(os.path.join(patch, "scenario"), exist_ok=True)
json.dump({"events": [
    {"type": "message", "data": ["おはよう", "今日もいい天気ですね"]},
    {"type": "choice", "data": ["はい", "いいえ"]},
    {"type": "event", "command": "wait"},                      # 非文本
]}, open(os.path.join(patch, "scenario", "s1.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"units": [{"type": "unit", "name": "アリス", "speaker": "跳过我", "message": "行くわよ！"}]},
          open(os.path.join(patch, "scenario", "u1.json"), "w", encoding="utf-8"), ensure_ascii=False)
msgs, fields, nfiles = SE.walk_patch(patch)
joined = "おはよう\n今日もいい天気ですね"
check("srpg 收集：消息按整段合并", joined in msgs)
check("srpg 收集：消息+选项+字段", joined in msgs and "はい\nいいえ" in msgs and "アリス" in fields,
      f"msgs={sorted(msgs)} fields={sorted(fields)}")
check("srpg 收集：SKIP_KEYS 跳过 speaker", "跳过我" not in fields and "跳过我" not in msgs)
# 译文按行前缀：真实管线中掩码记号保证译文换行数与原文一致
tr_s = {k: "\n".join("【SR】" + ln for ln in k.split("\n"))
        for k in list(msgs) + list(fields)}
d1 = json.load(open(os.path.join(patch, "scenario", "s1.json"), encoding="utf-8"))
stat = {"msg": 0, "skip": 0, "fld": 0}
SA.apply_file(d1, tr_s, stat)
ev = d1["events"][0]
check("srpg 回写：消息按原始边界切回", ev["data"] == ["【SR】おはよう", "【SR】今日もいい天気ですね"], str(ev["data"]))
check("srpg 回写：选项替换", d1["events"][1]["data"] == ["【SR】はい", "【SR】いいえ"])
d2 = json.load(open(os.path.join(patch, "scenario", "u1.json"), encoding="utf-8"))
SA.apply_file(d2, tr_s, stat)
check("srpg 回写：字段替换+speaker 保留",
      d2["units"][0]["name"] == "【SR】アリス" and d2["units"][0]["message"] == "【SR】行くわよ！"
      and d2["units"][0]["speaker"] == "跳过我")

# ========== 6) Unity 逻辑链路（无 UnityPy 依赖的纯字节/JSON 层） ==========
try:
    import unity_extract as UE
    import unity_apply as UA
    HAVE_UNITYPY = True
except SystemExit:
    HAVE_UNITYPY = False
if HAVE_UNITYPY:
    def mk_prefixed(s):
        b = s.encode("utf-8")
        return len(b).to_bytes(4, "little") + b + b"\x00" * ((len(b) + 3) // 4 * 4 - len(b))
    decoy = b"\x01\x00\x00\x00"                                  # 非 JP：不收
    tmp_line = mk_prefixed("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホ"
                           "マミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデド")
    # ↑ TMP 排版表：60 字全异长串（>50 且多样性>0.6）→ 引擎按设计跳过
    s1, s2 = "魔王城の鍵を手に入れた。", "レベルが上がった！"
    # 长度前缀串按 4 字节对齐摆放：引擎按 4 步进扫描（Unity 资产天然 4 对齐，docstring 同）
    raw = decoy + mk_prefixed(s1) + tmp_line + mk_prefixed(s2) + b"\x00" * 8
    hits = UE.scan_prefixed_strings(raw)
    check("unity 扫描：JP 长度前缀串 2 处", sorted(s for _, s in hits) == sorted([s1, s2]), str(hits))
    tr_u = {s1: "【U】获得了魔王城之钥。", s2: "【U】升级了！"}
    items = [{"off": o, "s": s} for o, s in hits]
    raw2, ok, skip = UA.rebuild_prefixed(raw, items, tr_u, {})
    hits2 = UE.scan_prefixed_strings(raw2)
    check("unity 回写：译文原位替换+4字节对齐",
          ok == 2 and skip == 0 and sorted(s for _, s in hits2) == sorted(tr_u.values()), str(hits2))
    ta = json.dumps({"script": [{"name": "アリス", "line": "こんにちは", "id": 3}]}, ensure_ascii=False)
    out_txt, n = UA.apply_textasset_json(ta, {"アリス": "【U】爱丽丝", "こんにちは": "【U】你好"})
    out_d = json.loads(out_txt)
    check("unity 回写：TextAsset JSON 值替换",
          n == 2 and out_d["script"][0]["name"] == "【U】爱丽丝" and out_d["script"][0]["id"] == 3)
else:
    print("△ UnityPy 未安装：unity 逻辑链路跳过（GUI 拖入时会提示自动安装）")

# ========== 7) 音视频合成正向链路（SAPI TTS → 本地 whisper → 字幕回写） ==========
try:
    import media_extract as ME
    HAVE_FW = mt_config.check_fasterwhisper()
except SystemExit:
    HAVE_FW = False
if HAVE_FW:
    wav = os.path.join(tmp, "tts.wav")
    ps = ("Add-Type -AssemblyName System.Speech; "
          "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"$s.SetOutputToWaveFile('{wav}'); "
          "$s.Rate = -1; "
          "$s.Speak('The chest contains a silver key and a healing potion. Thank you for playing.'); "
          "$s.Dispose()")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=90)
    tts_ok = r.returncode == 0 and os.path.exists(wav) and os.path.getsize(wav) > 20000
    t0 = time.time()
    if tts_ok:
        check("media：SAPI TTS 合成语音", True, f"{os.path.getsize(wav)} bytes")
        srt = os.path.join(tmp, "tts.srt")
        cues, lang = ME.transcribe_to_srt(wav, srt)
        check(f"media：本地听译出 {cues} 条 cue（{time.time()-t0:.0f}s，lang={lang}）", cues >= 1)
        txt = open(srt, encoding="utf-8").read().lower()
        kw = "silver" in txt or "chest" in txt or "potion" in txt
        print(f"  （听译关键词命中: {kw}）")
        check("media：听译文本含测试句关键词", kw, txt[:200])
        # 字幕全链路：解析 → sidecar → 模拟翻译 → 回写 .zh.srt
        import subtitle_extract as SX
        import subtitle_apply as SA2
        import subtitle_lib as SL
        out_d, entries, ncue = SX.extract(srt)
        check("media→字幕：srt 解析出全部台词", len(out_d) >= 1 and len(entries) == 1)
        tr_m = {k: "【影】" + k for k in out_d}
        trf = os.path.join(tmp, "tts_translated.json")
        json.dump(tr_m, open(trf, "w", encoding="utf-8"), ensure_ascii=False)
        json.dump({"files": entries}, open(os.path.join(tmp, "tts_subs.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
        parsed = {"format": entries[0]["format"], "eol": entries[0]["eol"],
                  "items": entries[0]["items"]}
        text, applied, total = SL.rebuild(parsed, tr_m)
        dst = os.path.join(tmp, "tts.zh.srt")
        open(dst, "w", encoding="utf-8", newline="").write(text)
        check("media→字幕：回写 .zh.srt 全量命中", applied == total and total >= 1,
              f"{applied}/{total}")
        zh_txt = open(dst, encoding="utf-8").read()
        check("media→字幕：时间轴保留", "-->" in zh_txt and zh_txt.count("-->") == total)
    else:
        # 无 SAPI 语音（罕见）：退化为静音正弦波 → 听译 0 条的健壮性路径
        import wave as _wave, math as _math
        with _wave.open(wav, "w") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
            frames = b"".join(struct.pack("<h", int(3000 * _math.sin(2 * 3.14 * 440 * i / 16000)))
                              for i in range(16000 * 2))
            wf.writeframes(frames)
        srt = os.path.join(tmp, "tts.srt")
        cues, lang = ME.transcribe_to_srt(wav, srt)
        check("media：静音/正弦波听译不崩且产出 srt", cues == 0 and os.path.exists(srt), str(cues))
else:
    print("△ faster-whisper 未安装：media 听译链路跳过（GUI 拖入时会提示自动安装）")

# ========== 清理 ==========
for f in ("mtx_renpy_extracted.json", "mtx_renpy_extracted_translated.json"):
    p = os.path.join(ROOT, f)
    if os.path.exists(p):
        os.remove(p)
shutil.rmtree(tmp, ignore_errors=True)

print()
if FAILS:
    print(f"✗ {len(FAILS)} 项失败: {FAILS}")
    sys.exit(1)
print("ALL ENGINE-MATRIX TESTS PASS")
