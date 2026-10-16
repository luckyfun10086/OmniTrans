# -*- coding: utf-8 -*-
"""入口路由测试：拖拽/选择 支持文件夹、音频、视频、漫画、游戏格式，
文件夹按内容识别；单文件拖入按"拖的是它"判意图（不看邻居）。
分两层：① mt_config.detect_engine 纯逻辑矩阵；② GUI on_drop 真实路由（Tk）。
运行：python tests/_test_routing.py
"""
import os, sys, io, json, time, shutil, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import mt_config

FAILS = []
def check(name, cond, info=""):
    print(("✓ " if cond else "✗ ") + name + (f"  {info}" if info and not cond else ""))
    if not cond:
        FAILS.append(name)

tmp = tempfile.mkdtemp(prefix="route_")

def mkfiles(folder, *names, content=b""):
    os.makedirs(folder, exist_ok=True)
    for n in names:
        p = os.path.join(folder, n)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(content)
    return folder

# ---------- ① 检测矩阵 ----------
manga = mkfiles(os.path.join(tmp, "Manga"), *[f"p{i:03d}.jpg" for i in range(30)])
check("图片文件夹 → comic", mt_config.detect_engine(manga)[0] == "comic")

nested = mkfiles(os.path.join(tmp, "Nested"),
                 *["ch_001/p1.jpg", "ch_001/p2.jpg", "ch_002/p1.jpg", "ch_002/p2.jpg"])
check("章节子目录结构 → comic", mt_config.detect_engine(nested)[0] == "comic")

few = mkfiles(os.path.join(tmp, "Few"), "a.jpg", "b.png", "c.webp")
check("3 张散图不误判 comic", mt_config.detect_engine(few)[0] == "unknown")

cbz = os.path.join(tmp, "one.cbz"); open(cbz, "wb").write(b"PK")
check("单个 .cbz 文件 → comic", mt_config.detect_engine(cbz)[0] == "comic")

# 单文件意图优先于父目录内容：游戏目录里拖一个字幕，识别的必须是字幕
gamedir = mkfiles(os.path.join(tmp, "RealGame"), "Game.exe", "data.xp3")
srt_next_to_game = os.path.join(gamedir, "ending.srt"); open(srt_next_to_game, "wb").write(b"1")
check("游戏目录里的 .srt 文件 → subtitle（拖的是它）",
      mt_config.detect_engine(srt_next_to_game)[0] == "subtitle")
check("游戏目录本身 → kirikiri（目录看内容）",
      mt_config.detect_engine(gamedir)[0] == "kirikiri")
check("拖 .exe → 按父目录识别",
      mt_config.detect_engine(os.path.join(gamedir, "Game.exe"))[0] == "kirikiri")

mkv = os.path.join(tmp, "ep01.mkv"); open(mkv, "wb").write(b"0")
check("单个 .mkv 文件 → media", mt_config.detect_engine(mkv)[0] == "media")

mv = mkfiles(os.path.join(tmp, "MixedMedia"), "ep01.mp4", "ep01.srt")
check("视频+字幕混合目录 → media（字幕复用）", mt_config.detect_engine(mv)[0] == "media")
so = mkfiles(os.path.join(tmp, "SubsOnly"), "a.srt", "b.ass")
check("纯字幕目录 → subtitle", mt_config.detect_engine(so)[0] == "subtitle")
gj = mkfiles(os.path.join(tmp, "GameJpg"), "data/Map001.json", *[f"img{i}.png" for i in range(9)])
check("游戏目录带图片 → 游戏引擎优先", mt_config.detect_engine(gj)[0] == "rpg_mvmz")

junk = mkfiles(os.path.join(tmp, "Junk"), "nothing.txt")
eng, _, ok, reason = mt_config.detect_engine(os.path.join(junk, "nothing.txt"))
check("未识别提示列出全部支持格式", eng == "unknown" and "漫画" in reason and "音视频" in reason, reason)

# ---------- ② GUI 路由（真实 on_drop 链路） ----------
import mt_gui
warns = []
mt_gui.messagebox.askyesno = lambda *a, **k: False     # 不自动提取，只看路由结果
mt_gui.messagebox.showwarning = lambda *a, **k: warns.append(str(a))
mt_gui.messagebox.showinfo = lambda *a, **k: None
mt_gui.messagebox.showerror = lambda *a, **k: warns.append("ERR:" + str(a))

from tkinterdnd2 import TkinterDnD
root = TkinterDnD.Tk()
app = mt_gui.App(root)
app._check_and_install_fw = lambda: True               # 防止测试机触发 pip 安装
app._check_and_install_comic = lambda: True

class FakeEvent:
    def __init__(self, data):
        self.data = data

def drop(payload):
    app._on_dnd_drop(FakeEvent(payload))
    for _ in range(6):
        root.update()
        time.sleep(0.03)

def reset():
    app.src_file = app.out_file = app.game_path = None
    app.game_engine = None
    app.game_extract_script = app.apply_script = None
    warns.clear()

# 单个字幕文件（旁边就是游戏 exe + xp3）→ subtitle，且只处理这个文件
reset()
drop(srt_next_to_game)
check("GUI: 游戏目录里拖 .srt → subtitle 引擎",
      app.game_engine == "subtitle", app.game_engine)
check("GUI: game_path = 拖入的文件本身（不是父目录）",
      os.path.isfile(app.game_path or "") and
      os.path.abspath(app.game_path) == os.path.abspath(srt_next_to_game), app.game_path)

# 单个视频文件 → media
reset()
drop(mkv)
check("GUI: 拖 .mkv → media 引擎，game_path=文件",
      app.game_engine == "media" and app.game_path == mkv, (app.game_engine, app.game_path))

# 漫画 → comic 引擎（OCR/嵌字），只处理拖入的这一个文件
reset()
drop(cbz)
check("GUI: 拖 .cbz → comic 引擎，game_path=文件",
      app.game_engine == "comic" and app.game_path == cbz
      and app.game_extract_script.endswith("comic_extract.py")
      and app.apply_script.endswith("comic_apply.py"),
      (app.game_engine, app.game_path))

# 多文件拖入 → 取第一个
reset()
two = "{" + srt_next_to_game + "} {" + mkv + "}"
drop(two)
check("GUI: 多文件 {a} {b} → 取第一个", app.game_engine == "subtitle" and app.game_path == srt_next_to_game,
      (app.game_engine, app.game_path))

root.destroy()
shutil.rmtree(tmp)

if FAILS:
    print("\nFAILED:", FAILS); sys.exit(1)
print("ALL TESTS PASS")
