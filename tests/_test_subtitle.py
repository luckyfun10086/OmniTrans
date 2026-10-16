# -*- coding: utf-8 -*-
"""字幕引擎测试：SRT/VTT/ASS 提取→假翻译→回写 全链路 + 编码探测 + 去重 + 双语 + sidecar 兜底"""
import io, sys, json, os, tempfile, shutil, importlib.util
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "engines", f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

lib = load("subtitle_lib")
sx = load("subtitle_extract")
sa = load("subtitle_apply")
import mt_config

# ---------- 1) 编码探测 ----------
txt, enc = lib.smart_decode("你们好，这个世界。".encode("gb18030"))
assert enc == "gb18030" and "你们好" in txt, (enc, txt)
txt, enc = lib.smart_decode("こんにちは、世界。".encode("shift_jis"))
assert enc == "shift_jis" and "こんにちは" in txt, (enc, txt)
txt, enc = lib.smart_decode("你們好，這個世界。".encode("big5"))
assert enc == "big5" and "你們好" in txt, (enc, txt)
txt, enc = lib.smart_decode("L'été était très chaud, et nous avons mangé.".encode("cp1252"))
assert enc == "cp1252" and "été" in txt, (enc, txt)
assert lib.smart_decode("ハロー".encode("utf-16"))[1] == "utf-16"
assert lib.smart_decode("ハロー".encode("utf-8-sig"))[1] == "utf-8-sig"
print("编码探测 ✓  GBK / Shift-JIS / Big5 / cp1252 / UTF-16 / BOM")

# ---------- 2) 构造视频目录 ----------
tmp = tempfile.mkdtemp()
anime = os.path.join(tmp, "MyAnime")
os.makedirs(anime)

srt = "\r\n".join([
    "1", "00:00:01,000 --> 00:00:03,000", "<i>Hello there.</i>", "General Kenobi!", "",
    "2", "00:00:04,000 --> 00:00:05,500", "Hello there.", "",
    "3", "00:00:06,000 --> 00:00:08,000", "<i>Hello there.</i>", "General Kenobi!", "",
    "4", "00:00:09,000 --> 00:00:10,000", "♪ ~ ♪", "",
    "5", "00:00:11,000 --> 00:00:12,000", "{\\an8}Top positioned line", "",
]) + "\r\n"
open(os.path.join(anime, "ep01.srt"), "wb").write(srt.encode("utf-8"))
# GBK 编码的中文源字幕（LF 行尾）
open(os.path.join(anime, "ep02.srt"), "wb").write(
    "1\n00:00:01,000 --> 00:00:02,000\n你们好，这个世界。\n\n".encode("gb18030"))
vtt = ("WEBVTT\n\nNOTE 留个注释\n\nintro-cue\n"
       "00:00:01.000 --> 00:00:02.000\nWelcome.\n\n"
       "00:00:03.000 --> 00:00:04.000\n<v Bob>Hi!</v>\n\n")
open(os.path.join(anime, "movie.vtt"), "w", encoding="utf-8", newline="").write(vtt)
ass = ("[Script Info]\nTitle: OP\n\n[V4+ Styles]\nFormat: Name, Fontname\n"
       "Style: Default,Arial\n\n[Events]\n"
       "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
       "Dialogue: 0,0:00:01.00,0:00:03.00,Default,Bob,0,0,0,,{\\pos(100,200)}Yes, captain.\\NRoger that.\n")
open(os.path.join(anime, "op.ass"), "w", encoding="utf-8", newline="").write(ass)
# 本工具上次的输出（.zh.srt）不应被再次提取
open(os.path.join(anime, "ep01.zh.srt"), "wb").write(b"1\r\nx --> y\r\nold\r\n")

# ---------- 3) 提取 ----------
out, entries, ncue = sx.extract(anime)
expect = {
    "Hello there.\nGeneral Kenobi!",   # cue1 与 cue3 去重合并
    "Hello there.",
    "Top positioned line",             # {\an8} 已剥离
    "你们好，这个世界。",
    "Welcome.",
    "Hi!",                             # <v Bob> 已剥离
    "Yes, captain.\nRoger that.",      # ASS {\pos} 剥离、\N→换行、逗号保留
}
assert set(out.keys()) == expect, (set(out.keys()) ^ expect)
assert ncue == 8 and len(entries) == 4, (ncue, len(entries))  # 8 处引用 / 4 个源文件（.zh.srt 排除）
assert all(v == "" for v in out.values())
print(f"提取 ✓  唯一台词 {len(out)} 条（重复去重），{ncue} 处引用，"
      f"{len(entries)} 个文件（自身输出 .zh.srt 已排除），音符条目未送翻")

# ---------- 4) 假翻译 + sidecar 落盘 ----------
tr = {k: "译[" + k + "]" for k in out}
del tr["Welcome."]    # 留一条未翻译 → 回写保持原文
trfile = os.path.join(tmp, "MyAnime_extracted_translated.json")
side = os.path.join(tmp, "MyAnime_subs.json")
json.dump(tr, open(trfile, "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"files": entries}, open(side, "w", encoding="utf-8"), ensure_ascii=False)

# 目标语言钉死为 zh-CN（不受本机 .env 影响）
_old_env = mt_config.load_env
mt_config.load_env = lambda: {"MT_TL": "zh-CN"}
try:
    # ---------- 5) 回写（走 main 全流程） ----------
    sys.argv = ["subtitle_apply.py", anime, trfile]
    sa.main()

    o1 = os.path.join(anime, "ep01.zh.srt")
    assert os.path.exists(o1), "ep01.zh.srt 未生成"
    t1 = open(o1, encoding="utf-8", newline="").read()
    assert t1.startswith("1\r\n00:00:01,000 --> 00:00:03,000\r\n"), t1[:80]
    assert "译[Hello there.\r\nGeneral Kenobi!]" in t1          # 多行译文 + CRLF 保留
    assert t1.count("译[") == 4, t1                              # cue 1/2/3/5 共 4 处替换
    assert "♪ ~ ♪" in t1                                         # 音符条目保持原文
    assert "{\\an8}" not in t1 and "<i>" not in t1               # 标记不外漏
    assert "00:00:04,000 --> 00:00:05,500" in t1                 # 时间轴原样

    o2 = os.path.join(anime, "ep02.zh.srt")
    t2 = open(o2, encoding="utf-8", newline="").read()                       # 输出一律 UTF-8
    assert "译[你们好，这个世界。]" in t2 and "00:00:01,000 --> 00:00:02,000" in t2

    ov = os.path.join(anime, "movie.zh.vtt")
    tv = open(ov, encoding="utf-8", newline="").read()
    assert tv.startswith("WEBVTT") and "NOTE 留个注释" in tv      # 头/注释放保留
    assert "intro-cue" in tv and "00:00:01.000 --> 00:00:02.000" in tv
    assert "Welcome." in tv and "译[Welcome.]" not in tv          # 未翻译 → 原文
    assert "译[Hi!]" in tv

    oa = os.path.join(anime, "op.zh.ass")
    ta = open(oa, encoding="utf-8", newline="").read()
    assert "[Script Info]" in ta and "Style: Default,Arial" in ta  # 样式段原样
    assert "Dialogue: 0,0:00:01.00,0:00:03.00,Default,Bob,0,0,0,,译[Yes, captain.\\NRoger that.]" in ta
    assert "{\\pos" not in ta                                      # 覆盖标签不外漏
    print("回写 ✓  SRT(CRLF/多行/时间轴) + GBK→UTF-8 + VTT(头/NOTE/未翻回退) + ASS(样式/\\N)")

    # ---------- 6) 双语模式 ----------
    parsed = lib.parse(open(os.path.join(anime, "ep01.srt"), "rb").read(), "srt")
    tbi, ap, tot = lib.rebuild(parsed, tr, bi=True)
    assert ap == 4 and tot == 5
    assert "译[Hello there.\r\nGeneral Kenobi!]\r\nHello there.\r\nGeneral Kenobi!" in tbi
    print("双语 ✓  译文在上、原文在下")

    # ---------- 7) sidecar 丢失 → 重新解析原文件兜底 ----------
    os.remove(side)
    os.remove(o1)
    sa.main()
    assert os.path.exists(o1) and "译[Hello there." in open(o1, encoding="utf-8", newline="").read()
    print("sidecar 兜底 ✓  丢失后重新解析原字幕重建")
finally:
    mt_config.load_env = _old_env

# ---------- 8) 引擎识别：字幕命中 / 不抢游戏目录 ----------
eng, name, ok, _ = mt_config.detect_engine(anime)
assert eng == "subtitle" and ok, (eng, ok)
game = os.path.join(tmp, "FakeGame")
os.makedirs(os.path.join(game, "data"))
json.dump({}, open(os.path.join(game, "data", "Map001.json"), "w", encoding="utf-8"))
open(os.path.join(game, "cutscene.srt"), "wb").write(b"1\nx --> y\nhi\n")
eng2, _, ok2, _ = mt_config.detect_engine(game)
assert eng2 == "rpg_mvmz", eng2    # 游戏引擎优先，字幕垫底
print(f"引擎识别 ✓  字幕目录→{eng}；带过场字幕的游戏目录→{eng2}（不被抢占）")

shutil.rmtree(tmp)
print("ALL TESTS PASS")
