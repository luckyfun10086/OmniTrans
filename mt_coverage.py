# -*- coding: utf-8 -*-
"""OmniTrans 覆盖率统计（单一事实源 = mt_config.ENGINES + 各引擎格式常量）
==========================================================================
统计两类覆盖：
  ① 内容引擎覆盖：游戏引擎 / 音视频 / 字幕 / 漫画 —— 是否可提取回写（全链路）、
     是否仅识别、依赖、合成测试覆盖到哪一级
     （FULL=合成样本全链路 / STAGE=合成样本覆盖核心阶段 / REAL=需真实样本）
  ② 载体格式覆盖：字幕容器、音视频封装、漫画容器/页图 各格式是否进检测矩阵
用法：
    python mt_coverage.py            # 打印表格
    python mt_coverage.py --md docs/COVERAGE.md   # 同步写 Markdown
"""
import os, sys, io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mt_config

# 合成测试覆盖（模拟样本，不依赖真实游戏）——key → (测试文件, 级别)
E2E = {
    "kirikiri":    ("tests/_test_krkr.py", "FULL"),
    "rpg_mvmz":    ("tests/_test_rpg.py", "FULL"),
    "rpg_vxace":   ("tests/_test_rva_pipeline.py", "FULL"),
    "renpy":       ("tests/_test_engine_matrix.py", "FULL"),
    "tyrano":      ("tests/_test_tyrano.py", "FULL"),
    "alice":       ("tests/_test_ain.py", "FULL"),
    "subtitle":    ("tests/_test_subtitle.py", "FULL"),
    "comic":       ("tests/_test_comic.py", "FULL"),
    "media":       ("tests/_test_engine_matrix.py", "FULL"),
    "srpg_studio": ("tests/_test_engine_matrix.py", "STAGE"),
    "wolf":        ("tests/_test_wolf.py + tests/_test_engine_matrix.py", "STAGE"),
    "unity":       ("tests/_test_unity.py + tests/_test_engine_matrix.py", "STAGE"),
}
LEVEL_NOTE = {
    "FULL":  "合成样本全链路（提取→翻译→回写全部模拟验证）",
    "STAGE": "合成样本覆盖核心阶段（解析/收集/回写逻辑）；封包层需真实样本",
    "REAL":  "需真实游戏样本",
}

def coverage():
    """→ (engine_rows, fmt_rows, summary dict)。engine_rows:
    key, 名称, 状态, 依赖, 提取脚本, 回写脚本, 模拟测试, 级别"""
    rows = []
    for key, e in mt_config.ENGINES.items():
        sup = e.get("supported")
        dep = ", ".join(e.get("deps", [])) or "-"
        ext = e.get("extractor", "-")
        app = e.get("applier", "-")
        test, lv = E2E.get(key, ("—", "REAL" if sup else "—"))
        rows.append((key, e["name"],
                     "✓ 全链路" if sup else "仅识别·不支持",
                     dep, ext, app, test, lv))
    fmts = [
        ("字幕", "SRT / VTT / ASS / SSA", ".srt .vtt .ass .ssa", "✓ 全链路"),
        ("音视频", "faster-whisper 本地听译（无需云/物理样本）",
         " ".join(mt_config._MEDIA_EXTS), "✓ 全链路"),
        ("漫画", "OCR→翻译→嵌字（图片文件夹 / CBZ·CBR·CB7）",
         " ".join(mt_config._IMG_EXTS) + "  " + " ".join(mt_config._COMIC_ARCHIVES),
         "✓ 全链路"),
        ("MTool json", "ManualTransFile.json 运行时挂载导出", ".json", "✓ 全链路"),
    ]
    n_full = sum(1 for r in rows if r[2] == "✓ 全链路")
    n_stage = sum(1 for r in rows if r[7] == "STAGE")
    n_unsup = sum(1 for r in rows if r[2] != "✓ 全链路")
    summary = {
        "engines": len(rows), "full": n_full, "stage": n_stage, "unsup": n_unsup,
        "subtitles": 4, "media": len(mt_config._MEDIA_EXTS),
        "comic": len(mt_config._IMG_EXTS) + len(mt_config._COMIC_ARCHIVES),
    }
    return rows, fmts, summary


def render_md(rows, fmts, summary):
    L = []
    L.append("# OmniTrans 覆盖率报告\n")
    L.append(f"> 由 `python mt_coverage.py` 从 `mt_config.ENGINES` 生成（单一事实源，随代码更新重跑即可）。\n")
    L.append("## 总览\n")
    L.append(f"- 内容引擎 **{summary['engines']}** 项：全链路 **{summary['full']}**，"
             f"其中 {summary['stage']} 项的封包层依赖真实样本（核心阶段已由合成样本覆盖）；"
             f"仅识别·暂不支持 {summary['unsup']} 项（均给出替代方案）")
    L.append(f"- 载体格式：字幕 {summary['subtitles']} 种、音视频 {summary['media']} 种封装、"
             f"漫画 {summary['comic']} 种容器/图型、MTool json 1 种\n")
    L.append("## 内容引擎矩阵\n")
    L.append("| 引擎 | 状态 | 依赖 | 提取 → 回写 | 模拟测试 | 级别 |")
    L.append("|---|---|---|---|---|---|")
    for key, name, st, dep, ext, app, test, lv in rows:
        chain = "—" if ext == "-" else f"`{ext}` → `{app}`"
        L.append(f"| {name} | {st} | {dep} | {chain} | `{test}` | {lv} |")
    L.append("\n级别说明：" + "；".join(f"**{k}**={v}" for k, v in LEVEL_NOTE.items()) + "\n")
    L.append("## 载体格式矩阵\n")
    L.append("| 载体 | 处理方式 | 格式 | 状态 |")
    L.append("|---|---|---|---|")
    for name, how, exts, st in fmts:
        L.append(f"| {name} | {how} | `{exts}` | {st} |")
    L.append("")
    return "\n".join(L)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # 控制台防 GBK 乱码；不换 wrapper 避免 GC 关流
    except Exception:
        pass
    rows, fmts, summary = coverage()
    print("=" * 88)
    print(f"OmniTrans 覆盖率总览：引擎 {summary['engines']}（全链路 {summary['full']}"
          f" / 阶段覆盖 {summary['stage']} / 仅识别 {summary['unsup']}）；"
          f"格式：字幕 {summary['subtitles']} · 音视频 {summary['media']} · "
          f"漫画 {summary['comic']} · json 1")
    print("=" * 88)
    w = (18, 26, 12, 16, 30, 22)
    print(f"{'引擎':<{w[0]}}{'状态':<{w[2]}}{'依赖':<{w[3]}}{'模拟测试':<{w[4]}}级别")
    print("-" * 88)
    for key, name, st, dep, ext, app, test, lv in rows:
        print(f"{name[:24]:<{w[0]}}{st:<{w[2]}}{dep:<{w[3]}}{test[:28]:<{w[4]}}{lv}")
    print("-" * 88)
    for name, how, exts, st in fmts:
        print(f"[{st}] {name}（{how}）：{exts}")
    if "--md" in sys.argv:
        out = sys.argv[sys.argv.index("--md") + 1]
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(render_md(rows, fmts, summary))
        print(f"\nMarkdown 已写: {out}")


if __name__ == "__main__":
    main()
