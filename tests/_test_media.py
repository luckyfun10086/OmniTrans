# -*- coding: utf-8 -*-
"""音视频听译引擎测试（离线：伪造 Whisper 模型，不安装不下载任何东西）
覆盖：时间码格式 / 听译→SRT 写出 / 已有字幕复用绝不重听 / 产物与 sidecar 落盘 /
引擎识别优先级（游戏 > 媒体 > 字幕）"""
import io, sys, json, os, tempfile, shutil, importlib.util
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "engines", f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

mx = load("media_extract")
import mt_config

# ---------- 1) 时间码 ----------
assert mx.fmt_ts(0) == "00:00:00,000"
assert mx.fmt_ts(3661.5) == "01:01:01,500"
assert mx.fmt_ts(3599.999) == "00:59:59,999"
print("时间码 ✓  时:分:秒,毫秒 进位正确")

# ---------- 2) 伪造模型 ----------
class FakeSeg:
    def __init__(self, a, b, t):
        self.start, self.end, self.text = a, b, t

class FakeInfo:
    language, language_probability, duration = "ja", 0.99, 300.0

class FakeModel:
    calls = 0
    def transcribe(self, path, **kw):
        FakeModel.calls += 1
        return iter([FakeSeg(0.0, 2.5, " こんにちは "),
                     FakeSeg(3.0, 5.0, "Hello there.")]), FakeInfo()

mx._MODEL = FakeModel()    # 注入缓存：绕过 faster_whisper 导入与模型下载

tmp = tempfile.mkdtemp()
show = os.path.join(tmp, "MyShow")
os.makedirs(os.path.join(show, "Season 01"))
open(os.path.join(show, "Season 01", "ep01.mkv"), "wb").write(b"")
open(os.path.join(show, "trailer.mp4"), "wb").write(b"")

_old_base = mt_config.base_dir
mt_config.base_dir = lambda: tmp          # 产物写进临时目录，不污染仓库
_old_env = mt_config.load_env
mt_config.load_env = lambda: {"MT_TL": "zh-CN", "MT_SL": "auto"}
try:
    sys.argv = ["media_extract.py", show]
    mx.main()

    # 听译产物：视频名.replace(扩展名,.srt)——播放器可自动加载
    s1 = os.path.join(show, "Season 01", "ep01.srt")
    s2 = os.path.join(show, "trailer.srt")
    assert os.path.exists(s1) and os.path.exists(s2), (s1, s2)
    t1 = open(s1, encoding="utf-8", newline="").read()
    assert t1 == ("1\r\n00:00:00,000 --> 00:00:02,500\r\nこんにちは\r\n\r\n"
                  "2\r\n00:00:03,000 --> 00:00:05,000\r\nHello there.\r\n\r\n"), repr(t1)
    out = json.load(open(os.path.join(tmp, "MyShow_extracted.json"), encoding="utf-8"))
    assert set(out) == {"こんにちは", "Hello there."}, out
    side = json.load(open(os.path.join(tmp, "MyShow_subs.json"), encoding="utf-8"))
    assert len(side["files"]) == 2
    print(f"听译→字幕 ✓  SRT 时间码/编号/去空格/CRLF 正确，提取 {len(out)} 条，"
          f"sidecar {len(side['files'])} 文件（递归 Season 01/ 生效）")

    # ---------- 3) 已有字幕复用：模型零调用 ----------
    FakeModel.calls = 0
    reuse = os.path.join(tmp, "ReuseShow")
    os.makedirs(reuse)
    open(os.path.join(reuse, "ep02.mp4"), "wb").write(b"")
    with open(os.path.join(reuse, "ep02.srt"), "wb") as f:
        f.write("1\r\n00:00:01,000 --> 00:00:02,000\r\nHi!\r\n\r\n".encode("utf-8"))
    before = open(os.path.join(reuse, "ep02.srt"), "rb").read()
    sys.argv = ["media_extract.py", reuse]
    mx.main()
    assert FakeModel.calls == 0, "已有同名 .srt 的媒体不应触发听译"
    assert open(os.path.join(reuse, "ep02.srt"), "rb").read() == before
    out2 = json.load(open(os.path.join(tmp, "ReuseShow_extracted.json"), encoding="utf-8"))
    assert set(out2) == {"Hi!"}, out2
    print("复用 ✓  已有 .srt 的媒体零听译、原字幕一字节未动")
finally:
    mt_config.base_dir = _old_base
    mt_config.load_env = _old_env

# ---------- 4) 引擎识别优先级 ----------
def mktree(name, *paths):
    d = os.path.join(tmp, name)
    for p in paths:
        fp = os.path.join(d, p)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        open(fp, "wb").write(b"{}" if p.endswith(".json") else b"")
    return d

d_srt = mktree("SrtOnly", "ep01.srt")
assert mt_config.detect_engine(d_srt)[0] == "subtitle"
d_mix = mktree("Mixed", "ep01.mp4", "ep01.srt")
assert mt_config.detect_engine(d_mix)[0] == "media"     # 有视频 → media（字幕会被复用）
d_game = mktree("GamePlusMovie", "data/Map001.json", "Movies/Intro.mp4")
assert mt_config.detect_engine(d_game)[0] == "rpg_mvmz" # 游戏签名永远优先
d_season = mktree("SeasonOnly", "Season 01/ep01.mkv")
assert mt_config.detect_engine(d_season)[0] == "media"  # 一层子目录也算
print("识别优先级 ✓  游戏引擎 > 媒体 > 字幕；Season 子目录命中")

# ---------- 5) 注册表：回写共用字幕链路 ----------
assert mt_config.ENGINES["media"]["applier"] == "engines/subtitle_apply.py"
assert "faster-whisper" in mt_config.ENGINES["media"]["deps"]
assert "MT_ASR_MODEL" in mt_config.ENV_KEYS
print("注册表 ✓  media 引擎与 subtitle 共用回写器，依赖/配置已登记")

shutil.rmtree(tmp)
print("ALL TESTS PASS")
