# -*- coding: utf-8 -*-
"""AliceSoft (.ain) 引擎测试：解析/转义/字形映射单元测试 + 真实文件集成（缺样本自动 SKIP）。

集成样本：E:\\Ggame\\超昂神騎エクシール（AI2 加密 AIN，alice-tools 0.13.0）。
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "engines"))
import mt_config  # noqa: E402
from ain_extract import parse_dump, escape, unescape, LINE_RE  # noqa: E402
import ain_apply  # noqa: E402

FAILED = []
SAMPLE = r"E:\Ggame\超昂神騎エクシール"


def check(name, cond, info=""):
    print(("[PASS] " if cond else "[FAIL] ") + name + (f"  {info}" if info and not cond else ""))
    if not cond:
        FAILED.append(name)


# ---------- 1. dump 行解析 ----------
lines = '\n; func::Name\n;s[1] = "Asra_TotalPlayTime"\n;m[10] = "・ゲー\\nム\\"クリア\\""\n\n'
open(os.path.join(tempfile.gettempdir(), "_ain_t.txt"), "w", encoding="utf-8").write(lines)
items = parse_dump(os.path.join(tempfile.gettempdir(), "_ain_t.txt"))
check("行解析：s/m/函数头", items == [("s", 1, "Asra_TotalPlayTime"),
                                  ("m", 10, "・ゲー\nム\"クリア\"")], repr(items))

# ---------- 2. 转义往返 ----------
tricky = '第一行\n第二行\t有"引号"和\\反斜杠\\'
check("escape/unescape 往返", unescape(escape(tricky)) == tricky)
check("escape 换行", escape("A\nB") == 'A\\nB')

# ---------- 3. 字形映射（CP932 存储） ----------
check("简体映射：这为说吗", ain_apply.convert("这为说吗好吗")[0] == "這為説嘛好嘛")
check("她→伊 你→君", ain_apply.convert("她对你")[0] == "伊對君")
check("日文微调形：每步查晚", ain_apply.convert("每步查晚")[0] == "毎歩査晩")
check("本就兼容的字不变", ain_apply.convert("的一是了")[0] == "的一是了")
conv, lost = ain_apply.convert("垫")
check("无对应字→？+计数", conv == "？" and lost == ["垫"])
for ch in "這為説嘛君伊毎歩査晩絶縁録":
    check(f"映射目标 {ch} 可 CP932 编码", ain_apply._cp932_ok(ch))
# 映射表所有目标都必须可编码（过滤器保证）
check("S2J 全表目标可编码",
      all(ain_apply._cp932_ok(v) for v in ain_apply.S2J.values()))

# ---------- 4. 注册表 ----------
eng = mt_config.ENGINES["alice"]
check("注册表：supported=True", eng["supported"] is True)
check("注册表：extractor/applier 就位",
      eng.get("extractor", "").endswith("ain_extract.py") and
      eng.get("applier", "").endswith("ain_apply.py"))
fake = {f.name for f in os.scandir(SAMPLE)} if os.path.isdir(SAMPLE) else set()
if fake:
    check("检测：真实目录识别为 alice", mt_config.detect_engine(SAMPLE)[0] == "alice")

# ---------- 5. 真实文件集成（Ixseal：AI2 解密 → 提取 → 回写 → 回读） ----------
ains = glob.glob(os.path.join(SAMPLE, "*.ain")) if os.path.isdir(SAMPLE) else []
exe = glob.glob(os.path.join(ROOT, "bin", "alice", "*", "alice.exe"))
if not (ains and exe):
    print("SKIP：AliceSoft 样本或 alice-tools 不可用（离线/未下载）")
elif not shutil.which("python"):
    print("SKIP")
else:
    ain = ains[0]
    exe = exe[0]
    td = tempfile.mkdtemp()
    cur = os.path.join(td, "cur.txt")
    subprocess.run([exe, "ain", "dump", "-t", "-o", cur, ain], check=True,
                   capture_output=True)
    items = parse_dump(cur)
    msgs = [t for k, _i, t in items if k == "m" and t.strip()]
    check("AI2 解密 dump 成功", len(items) > 1000, f"{len(items)} 条")
    check("m[] 消息非空", len(msgs) > 100, f"{len(msgs)} 条")
    # 回写：拿前 2 条消息做假翻译（在副本上，不动游戏目录）
    tr = {msgs[0]: "・這是回写测试。", msgs[1]: "君能做到嘛？"}
    mod = os.path.join(td, "mod.txt")
    with open(mod, "w", encoding="utf-8", newline="\n") as f:
        for kind, idx, text in items:
            if text in tr:
                f.write(f'{kind}[{idx}] = "{escape(ain_apply.convert(tr[text])[0])}"\n')
    out = os.path.join(td, "out.ain")
    p = subprocess.run([exe, "ain", "edit", "-t", mod, "-o", out, ain],
                       capture_output=True)
    check("edit 重建成功", p.returncode == 0 and os.path.isfile(out),
          (p.stdout + p.stderr).decode("utf-8", "replace")[-200:])
    if os.path.isfile(out):
        v = os.path.join(td, "v.txt")
        subprocess.run([exe, "ain", "dump", "-t", "-o", v, out], check=True,
                       capture_output=True)
        after = {t for _k, _i, t in parse_dump(v)}
        want = {ain_apply.convert(v)[0] for v in tr.values()}
        check("回读：译文在重建文件中", want <= after, f"want={want} got={len(after)}")
        check("AI2 加密保持", open(out, "rb").read(4) == open(ain, "rb").read(4) == b"AI2\x00")
    shutil.rmtree(td, ignore_errors=True)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项: {FAILED}")
    sys.exit(1)
print("ALL AIN TESTS PASS")
