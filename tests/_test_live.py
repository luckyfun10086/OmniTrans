# -*- coding: utf-8 -*-
"""实弹翻译自测（真实免费端点，中性语料）
==========================================
走完整管线：清洗（记号掩码）→ 真实机翻（clients5.google.com 免费端点）
→ 回填校验。语料为自拟中性句子（无游戏文本、无图片，适合办公环境）。

断言：
  - 全部条目翻译成功、记号 0 丢失（含控制码 \\C[n]、换行、人名保持）
  - 译文为中文（含 CJK）
离线/端点不可达 → SKIP（不判失败）。
运行：python tests/_test_live.py
"""
import os, sys, io, json, shutil, tempfile, threading, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import mt_config, mt_gui

FAILS = []
def check(name, cond, info=""):
    print(("✓ " if cond else "✗ ") + name + (f"  {info}" if info and not cond else ""))
    if not cond:
        FAILS.append(name)

def _has_cjk(s):
    return any("\u4e00" <= c <= "\u9fff" for c in s)

# ---------- 预检：端点可达性（不可达 → SKIP） ----------
probe = mt_config.DEFAULT_ENDPOINT.replace("{sl}", "en").replace("{tl}", "zh-CN") \
    .replace("{q}", urllib.parse.quote("hello"))
try:
    with urllib.request.urlopen(urllib.request.Request(probe), timeout=15) as r:
        ok_probe = bool(json.loads(r.read().decode("utf-8", "replace")))
except Exception as e:
    ok_probe = False
    print(f"SKIP：翻译端点不可达（{type(e).__name__}），跳过实弹测试")
if not ok_probe:
    sys.exit(0 if True else 1)

# ---------- 中性语料（自拟，无任何游戏/敏感内容） ----------
ITEMS = [
    "Hello, traveler! Welcome to our village.",
    "The shop is open from morning to night.\\C[3]Please come again.",
    "Mira found an old map in the library.",
    "Line one of a letter.\\nLine two of the same letter.",   # \n 记号换行
    "You obtained a silver key.",
    "Mira said the festival starts tomorrow.",
    "HP and MP are fully restored.",
    "The northern cave is dangerous at night.",
]
src_json = {s: "" for s in ITEMS}
tmp = tempfile.mkdtemp(prefix="live_")
src = os.path.join(tmp, "sample.json")
json.dump(src_json, open(src, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

logs = []
pipe = mt_gui.Pipe(src, os.path.join(tmp, "work"), "en", "zh-CN",
                   threading.Event(), lambda *a: None, logs.append)
dst, ok, drop = pipe.run()

check("实弹：全部翻译成功", ok == len(ITEMS), f"ok={ok}/{len(ITEMS)}")
check("实弹：记号 0 丢失", drop == 0, f"drop={drop}")

out = mt_config.load_loose_json(dst)
check("实弹：输出条数一致", len(out) == len(ITEMS))
bad = [k for k, v in out.items() if not (isinstance(v, str) and v.strip() and _has_cjk(v))]
check("实弹：译文均为中文", not bad, str(bad[:2]))
check("实弹：控制码保留", all("\\C[3]" in v for k, v in out.items() if "\\C[3]" in k),
      str([v for k, v in out.items() if "\\C[3]" in k][:1]))
check("实弹：换行保留", all(v.count("\\n") == k.count("\\n")
                           for k, v in out.items() if "\\n" in k))
check("实弹：人名保持一致", all("Mira" in v for k, v in out.items() if "Mira" in k))

# 打印全部译文（自拟中性句，办公环境安全）
print("\n---- 中性语料 翻译结果（EN → ZH, 免费端点实弹） ----")
for k, v in out.items():
    print(f"  {k}\n    → {v}")
print("------------------------------------------------\n")

shutil.rmtree(tmp, ignore_errors=True)
if FAILS:
    print(f"✗ {len(FAILS)} 项失败: {FAILS}")
    sys.exit(1)
print("ALL LIVE TESTS PASS")
