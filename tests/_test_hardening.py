# -*- coding: utf-8 -*-
"""加固项自测：原子落盘 / AI 批量 id 容错 / 提示词 / 管线兜底 / GUI 点击防护
====================================================================
覆盖近期加固修改：
  1. mt_config.dump_json_atomic —— 原子写 + 目录自动创建 + 无 .tmp 残留
  2. _extract_json_items —— 字符串/浮点 id 容错（避免整组降级逐条）
  3. AI 提示词含语气/纯输出约束（单条与批量两处）
  4. Pipe.run 全部已翻 → loose 解析 + 污染修复 + 原样输出
  5. CLI 管线缺文件 → 友好报错退出码 2（不是 traceback）
  6. GUI 点击：图书馆删除二次确认、无文件点开始提示、回车快捷键守卫
运行：python tests/_test_hardening.py
"""
import os, sys, io, json, time, shutil, tempfile, threading, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENG = os.path.join(ROOT, "engines")
sys.path.insert(0, ROOT)
sys.path.insert(0, ENG)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import mt_config, mt_gui

FAILS = []
def check(name, cond, info=""):
    print(("✓ " if cond else "✗ ") + name + (f"  {info}" if info and not cond else ""))
    if not cond:
        FAILS.append(name)

# ========== 1) 原子落盘 ==========
tmp = tempfile.mkdtemp(prefix="hardening_")
p = os.path.join(tmp, "nested", "dir", "data.json")
mt_config.dump_json_atomic(p, {"k": "中文值"})
d1 = json.load(open(p, encoding="utf-8"))
check("原子写：内容正确", d1 == {"k": "中文值"})
check("原子写：嵌套目录自动创建", os.path.isfile(p))
check("原子写：无 .tmp 残留", not os.path.exists(p + ".tmp"))
mt_config.dump_json_atomic(p, {"k": "覆盖"})
check("原子写：覆盖旧文件", json.load(open(p, encoding="utf-8")) == {"k": "覆盖"})
try:
    json.dumps(None)  # noqa -- keep json imported
    mt_config.dump_json_atomic(os.path.join(tmp, "x.json"), {"a": 1}, indent=2)
    check("原子写：indent 参数生效", open(os.path.join(tmp, "x.json"), encoding="utf-8").read().startswith('{\n  "a"'))
except Exception as e:
    check("原子写：indent 参数生效", False, str(e))

# ========== 2) AI 批量 id 容错 ==========
f = mt_config._extract_json_items
check("id 容错：字符串 id", f('{"items":[{"id":"2","zh":"乙"},{"id":"1","zh":"甲"}]}', 2) == ["甲", "乙"])
check("id 容错：浮点 id", f('{"items":[{"id":2.0,"zh":"乙"},{"id":1,"zh":"甲"}]}', 2) == ["甲", "乙"])
try:
    f('{"items":[{"id":true,"zh":"乙"},{"id":1,"zh":"甲"}]}', 2)
    check("id 容错：布尔 id 拒绝", False)
except ValueError:
    check("id 容错：布尔 id 拒绝", True)

# ========== 3) 提示词约束 ==========
check("批量提示词：自然口吻规则", "conversational" in mt_config.AI_BATCH_SYS)
_captured = {}
class _FakeResp:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return json.dumps({"choices": [{"message": {"content": "你好"}}]}).encode("utf-8")
def _fake_opener(req, timeout=None):
    _captured["body"] = req.data.decode("utf-8")
    return _FakeResp()
mt_config.translate_once("hi", "en", "zh-CN", endpoint="https://x/chat/completions",
                         api_type="openai", opener=_fake_opener)
check("单条提示词：自然口吻规则", "conversational" in _captured.get("body", ""))

# ========== 4) 管线全部已翻 → 原样输出（loose + 污染修复） ==========
work = os.path.join(tmp, "pipe_work")
src = os.path.join(tmp, "src.json")
with open(src, "w", encoding="utf-8") as fo:
    fo.write('{\n  // 外层注释应被宽容解析\n  "k1": "bonjour",\n  "k2": "[\'円\', \'ja\' ]"\n}\n')
pipe = mt_gui.Pipe(src, work, "en", "zh-CN", threading.Event(),
                   lambda *a: None, lambda m: None)
dst, ok, drop = pipe.run()
check("no_trans 路径：零翻零弃", ok == 0 and drop == 0, f"ok={ok} drop={drop}")
out = json.load(open(dst, encoding="utf-8"))
check("no_trans 路径：污染值已修复", out.get("k2") == "円", str(out.get("k2")))
check("no_trans 路径：原子写产物存在", os.path.isfile(dst) and not os.path.exists(dst + ".tmp"))

# ========== 5) CLI 缺文件友好报错 ==========
empty = tempfile.mkdtemp(prefix="cli_empty_")
for script, arg in (("mt_apply.py", None), ("mt_translate.py", None)):
    r = subprocess.run([sys.executable, os.path.join(ROOT, script)],
                       cwd=empty, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    blob = (r.stdout or "") + (r.stderr or "")
    check(f"CLI {script}：缺文件退出码 2", r.returncode == 2, str(r.returncode))
    check(f"CLI {script}：友好提示无 traceback",
          "找不到" in blob and "Traceback" not in blob, blob[:200])
shutil.rmtree(empty, ignore_errors=True)

# ========== 6) GUI 点击防护 ==========
from tkinterdnd2 import TkinterDnD
import tkinter as tk

answers = {"yesno": True, "infos": []}
mt_gui.messagebox.askyesno = lambda *a, **k: answers["yesno"]
mt_gui.messagebox.showinfo = lambda *a, **k: answers["infos"].append(str(a))
mt_gui.messagebox.showerror = lambda *a, **k: answers["infos"].append("ERR:" + str(a))
mt_gui.messagebox.showwarning = lambda *a, **k: answers["infos"].append("WARN:" + str(a))

root = TkinterDnD.Tk() if mt_gui.HAS_DND else tk.Tk()
root.withdraw()
app = mt_gui.App(root)

def click(w):
    w.update()
    w.event_generate("<ButtonPress-1>", x=5, y=5)
    w.event_generate("<ButtonRelease-1>", x=5, y=5)

# 6a) 图书馆删除：二次确认
app.library = {"games": [{"name": "测试游戏A", "translated": 3}]}
app._library_refresh()
root.update()
app.lib_tree.selection_set("lib0")
answers["yesno"] = False
click(app.lib_del_btn); root.update()
check("图书馆删除：拒绝确认 → 记录保留", len(app.library["games"]) == 1)
answers["yesno"] = True
click(app.lib_del_btn); root.update()
check("图书馆删除：确认后删除", len(app.library["games"]) == 0)

# 6b) 无文件点「开始」→ 明确提示（原先静默无反应）
app.src_file = None
app.start_btn.config(state="normal")
answers["infos"].clear()
click(app.start_btn); root.update()
time.sleep(0.1); root.update()
check("无文件点开始 → 提示先选文件",
      any(app.T("msg_nofile").splitlines()[0] in i for i in answers["infos"]), str(answers["infos"]))

# 6c) 回车快捷键：输入框内不触发；就绪状态下触发
calls = []
app.start = lambda: calls.append(1)
app.rv_search.focus_set(); root.update()
root.event_generate("<Return>"); root.update()
check("回车守卫：输入框内不触发", not calls)
app.src_file = "whatever.json"
app.start_btn.config(state="normal")
app.cancel_btn.config(state="disabled")
root.focus_set(); root.update()
root.event_generate("<Return>"); root.update()
check("回车快捷键：就绪后触发开始", len(calls) == 1, str(calls))

root.destroy()
shutil.rmtree(tmp, ignore_errors=True)

print()
if FAILS:
    print(f"✗ {len(FAILS)} 项失败: {FAILS}")
    sys.exit(1)
print("ALL HARDENING TESTS PASS")
