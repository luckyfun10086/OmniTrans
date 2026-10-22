# -*- coding: utf-8 -*-
"""
AliceSoft (.ain) 文本提取器
===========================
桥接 nunuhara 的 alice-tools（GPL-2.0 命令行工具，独立进程调用、首次运行
自动下载到 bin/alice/，不进入本项目源码）：
  alice ain dump -t   → 自动解密 AI2 加密头，导出全部 strings/messages（UTF-8）

提取范围：
  m[]（玩家可见消息）全部 + s[]（代码字符串）中含日文的条目
  （s[] 大量是内部标识符如 "Asra_TotalPlayTime"，按日文过滤）

用法：
    python engines/ain_extract.py <游戏目录>     # → <游戏名>_extracted.json
"""
import os, sys

_ENG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_ENG))    # 项目根：mt_config 等
sys.path.insert(0, _ENG)                     # 引擎同目录
import json, io, re, glob, subprocess, zipfile, urllib.request
import mt_config

TOOL_DIR = os.path.join(mt_config.base_dir(), "bin", "alice")
ALICE_VER = "0.13.0"
ALICE_URL = (f"https://github.com/nunuhara/alice-tools/releases/download/"
             f"{ALICE_VER}/alice-tools-{ALICE_VER}.zip")

# dump -t 行形如：  ;m[123] = "テキスト"  （初始全部注释掉，函数头为 "; funcName"）
LINE_RE = re.compile(r'^;\s*([ms])\[(\d+)\]\s*=\s*"(.*)"\s*$')
JP = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def ensure_tools(log=print):
    exe = os.path.join(TOOL_DIR, f"alice-tools-{ALICE_VER}", "alice.exe")
    if os.path.isfile(exe):
        return exe
    os.makedirs(TOOL_DIR, exist_ok=True)
    zp = os.path.join(TOOL_DIR, "alice-tools.zip")
    log(f"下载 alice-tools {ALICE_VER}（GPL-2.0, nunuhara/alice-tools）…")
    urllib.request.urlretrieve(ALICE_URL, zp)
    with zipfile.ZipFile(zp) as z:
        z.extractall(TOOL_DIR)
    os.remove(zp)
    if not os.path.isfile(exe):
        raise RuntimeError("alice.exe 解压失败，请检查 bin/alice/ 目录")
    return exe


def run_alice(exe, args):
    p = subprocess.run([exe] + args, capture_output=True)
    out = (p.stdout + p.stderr).decode("utf-8", "replace")
    if p.returncode != 0:
        raise RuntimeError(f"alice {' '.join(args[:2])} 失败: {out[-400:]}")
    return out


def dump_text(exe, ain, dst):
    """dump -t：UTF-8 文本，;m[N]/;s[N] 注释行 + 函数头。"""
    run_alice(exe, ["ain", "dump", "-t", "-o", dst, ain])


def unescape(s):
    """alice 转义（\\n \\t \\" \\\\）→ 真实字符，单趟扫描避免连消。"""
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(n, n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def escape(s):
    out = []
    for c in s:
        out.append({"\n": r"\n", "\t": r"\t", '"': r"\"", "\\": r"\\"}.get(c, c))
    return "".join(out)


def parse_dump(txt_path):
    """[(kind, idx, text)]；kind 'm'=玩家消息，'s'=代码字符串。"""
    items = []
    with open(txt_path, encoding="utf-8") as f:
        for line in f:
            m = LINE_RE.match(line.rstrip("\n"))
            if m:
                items.append((m.group(1), int(m.group(2)), unescape(m.group(3))))
    return items


def find_ains(game_dir):
    """顶层 .ain，按体积降序（主脚本在前）。"""
    ains = glob.glob(os.path.join(game_dir, "*.ain"))
    return sorted(ains, key=os.path.getsize, reverse=True)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    game = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    base = os.path.basename(game.rstrip("/\\"))
    ains = find_ains(game)
    if not ains:
        print("未找到 .ain 文件（AliceSoft 游戏通常在游戏根目录）")
        sys.exit(1)
    exe = ensure_tools()
    work = os.path.join(mt_config.base_dir(), "ain_work", base)
    os.makedirs(work, exist_ok=True)

    out = {}
    for ain in ains:
        name = os.path.splitext(os.path.basename(ain))[0]
        txt = os.path.join(work, name + ".txt")
        dump_text(exe, ain, txt)
        n = 0
        for kind, _idx, text in parse_dump(txt):
            if not text.strip():
                continue
            if kind == "m" or JP.search(text):
                if text not in out:
                    out[text] = ""
                    n += 1
        print(f"{os.path.basename(ain)}: {n} 条（共 {os.path.getsize(ain):,} 字节）")

    dst = os.path.join(mt_config.base_dir(), f"{base}_extracted.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"ains": ains, "work": work},
              open(os.path.join(mt_config.base_dir(), f"{base}_ainwork.json"), "w",
                   encoding="utf-8"), ensure_ascii=False)
    chars = sum(len(k) for k in out)
    print(f"合计 {len(out)} 条 / {chars} 字符 → {os.path.basename(dst)}")
    print(f"下一步：翻译后 python engines/ain_apply.py <游戏目录> <译文json>")


if __name__ == "__main__":
    main()
