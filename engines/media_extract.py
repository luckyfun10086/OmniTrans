# -*- coding: utf-8 -*-
r"""
音视频听译提取器（faster-whisper，本地 ASR）
=============================================
没有字幕的视频/音频也能进 OmniTrans 流水线：
拖入视频目录 → 逐个听译生成同名 .srt（UTF-8）→ 与已有字幕一起走字幕引擎全链路。
已有同名 .srt 的媒体自动复用，绝不重复听译。

- 模型本地运行（CPU int8），不上传任何音频；首跑自动下载（small ≈ 244MB）
- .env 可调：MT_ASR_MODEL=tiny|base|small|medium|large-v3（默认 small）
- 国内下载慢可设系统环境变量 HF_ENDPOINT=https://hf-mirror.com
- MT_SL 设了具体语言（非 auto）时按它听译，否则逐文件自动检测

用法：
    python media_extract.py <目录或单个媒体文件>
依赖：
    pip install faster-whisper        （GUI 拖入时会弹窗自动安装）
"""
import os, sys
_ENG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_ENG))    # 项目根：mt_config 等
sys.path.insert(0, _ENG)                     # 引擎同目录：subtitle_lib 等
import json
import mt_config
import subtitle_extract as sx

VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".mpg", ".mpeg", ".ts",
              ".m2ts", ".webm", ".flv", ".m4v", ".3gp", ".ogv", ".rmvb", ".vob")
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".wma", ".aac", ".amr")
MEDIA_EXTS = VIDEO_EXTS + AUDIO_EXTS

_MODEL = None    # 进程内缓存：多个文件不重复加载模型

def get_model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        size = mt_config.load_env().get("MT_ASR_MODEL", "").strip() or "small"
        print(f"加载听译模型 {size}（首次运行会自动下载）…")
        _MODEL = WhisperModel(size, device="cpu", compute_type="int8")
    return _MODEL

def fmt_ts(sec):
    """秒 → SRT 时间码 00:00:01,000"""
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def transcribe_to_srt(path, out_srt):
    """听译单个媒体 → 写 UTF-8 SRT（CRLF）。返回 (条数, 语言)。"""
    model = get_model()
    kwargs = {"vad_filter": True}
    sl = mt_config.load_env().get("MT_SL", "auto").strip()
    if sl and sl.lower() != "auto":
        kwargs["language"] = sl
    segments, info = model.transcribe(path, **kwargs)
    if getattr(info, "duration", 0):
        print(f"  ~ {os.path.basename(path)}: {info.language}"
              f"（{getattr(info, 'language_probability', 0):.0%}），"
              f"{info.duration / 60:.0f} 分钟，开始听译…")
    cues = []
    next_report = 120.0
    for seg in segments:
        txt = (getattr(seg, "text", "") or "").strip()
        if txt:
            cues.append((fmt_ts(seg.start), fmt_ts(seg.end), txt))
        if seg.end >= next_report:
            print(f"    … {seg.end / 60:.0f} 分钟处，已 {len(cues)} 条")
            next_report = seg.end + 120.0
    with open(out_srt, "w", encoding="utf-8", newline="") as f:
        for i, (a, b, t) in enumerate(cues, 1):
            f.write(f"{i}\r\n{a} --> {b}\r\n{t}\r\n\r\n")
    return len(cues), getattr(info, "language", "?")

def collect_media(path):
    """目录 → 递归收集音视频（排序保证确定性）；文件 → [该文件]。"""
    if os.path.isfile(path):
        return [path]
    out = []
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for f in sorted(files):
            if f.lower().endswith(MEDIA_EXTS):
                out.append(os.path.join(root, f))
    return out

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    files = collect_media(path)
    if not files:
        raise SystemExit("未找到音视频文件（支持 " + "/".join(VIDEO_EXTS[:6]) + " 等）。"
                         "若已有 .srt 字幕请直接拖字幕目录。")
    nasr = 0
    for f in files:
        srt = os.path.splitext(f)[0] + ".srt"
        if os.path.exists(srt):
            print(f"  = {os.path.basename(f)} 已有字幕 {os.path.basename(srt)}，直接复用")
            continue
        try:
            n, lang = transcribe_to_srt(f, srt)
            nasr += 1
            print(f"  + {os.path.basename(f)} → {os.path.basename(srt)}（{n} 条，{lang}）")
        except ImportError:
            raise SystemExit("缺少 faster-whisper：请 pip install faster-whisper"
                             "（GUI 拖入音视频时会弹窗自动安装）")
        except Exception as e:
            print(f"  ! 听译失败 {os.path.basename(f)}，跳过: {e}")
    # 新生成的 + 原有的 .srt 统一走字幕引擎提取（同一个 sidecar/回写链路）
    out, entries, ncue = sx.extract(path)
    base = sx.base_name(path)
    dst = os.path.join(mt_config.base_dir(), f"{base}_extracted.json")
    side = os.path.join(mt_config.base_dir(), f"{base}_subs.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"files": entries}, open(side, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    chars = sum(len(k) for k in out)
    print(f"听译 {nasr} 个文件；共 {len(entries)} 个字幕源，唯一台词 {len(out)} 条"
          f"（{chars} 字符，{ncue} 处引用）")
    print(f"输出: {dst}")
    print(f"sidecar: {side}")
    print("下一步: 翻译后 python subtitle_apply.py <目录> \"" +
          os.path.basename(dst).replace("_extracted.json", "_extracted_translated.json") + "\"")

if __name__ == "__main__":
    main()
