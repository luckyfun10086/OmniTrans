# -*- coding: utf-8 -*-
"""
Wolf RPG Editor (ウディタ) 回写器
=================================
把译文写回 WolfTL dump JSON → WolfTL patch 生成新 Data → 覆盖游戏数据。

安全机制：
- 原 .wolf（若曾解包）已备份为 .wolf.automt.bak
- 覆盖 Data/ 前整体备份为 Data.automt.bak（只备份一次）
- 未命中的文本保持原文；行结构由 WolfTL 保证

用法：
    python engines/wolf_apply.py <游戏目录> <译文json>
"""
import os, sys

_ENG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_ENG))    # 项目根：mt_config 等
sys.path.insert(0, _ENG)                     # 引擎同目录
import json, io, re, glob, shutil
import mt_config
from wolf_extract import ensure_tools, run_tool, TEXT_CODES, JP
from ain_apply import convert as _s2j_convert   # 简体→CP932 可存字形（Wolf 2.x 用）


def _apply_events(node, tr, stats):
    if isinstance(node, dict):
        if node.get("codeStr") in TEXT_CODES and isinstance(node.get("stringArgs"), list):
            sa = node["stringArgs"]
            for i, s in enumerate(sa):
                if isinstance(s, str):
                    zh = tr.get(s, "")
                    if isinstance(zh, str) and zh.strip():
                        sa[i] = zh
                        stats["applied"] += 1
                    elif s.strip() and JP.search(s):
                        stats["missed"] += 1
        for v in node.values():
            _apply_events(v, tr, stats)
    elif isinstance(node, list):
        for v in node:
            _apply_events(v, tr, stats)


def _apply_db(node, tr, stats):
    if isinstance(node, dict):
        if "data" in node and isinstance(node["data"], list):
            nm = node.get("name")
            if isinstance(nm, str) and JP.search(nm):
                zh = tr.get(nm, "")
                if isinstance(zh, str) and zh.strip():
                    node["name"] = zh
                    stats["applied"] += 1
            for c in node["data"]:
                if isinstance(c, dict):
                    v = c.get("value")
                    if isinstance(v, str) and JP.search(v):
                        zh = tr.get(v, "")
                        if isinstance(zh, str) and zh.strip():
                            c["value"] = zh
                            stats["applied"] += 1
        for v in node.values():
            _apply_db(v, tr, stats)
    elif isinstance(node, list):
        for v in node:
            _apply_db(v, tr, stats)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    game = os.path.abspath(sys.argv[1])
    trfile = sys.argv[2]
    tr = mt_config.load_loose_json(trfile)
    base = os.path.basename(game.rstrip("/\\"))
    wf = os.path.join(mt_config.base_dir(), f"{base}_wolfwork.json")
    if not os.path.exists(wf):
        raise SystemExit(f"未找到工作目录记录 {wf}——请先运行 wolf_extract.py")
    work = json.load(open(wf, encoding="utf-8"))["work"]
    dump = os.path.join(work, "dump")
    if not os.path.isdir(dump):
        raise SystemExit(f"工作目录缺失 {dump}——请重新运行 wolf_extract.py")

    def apply_pass(mapping):
        """把译文（可经字形映射）写进 dump → patch → 回读验证。返回 (patched, lost)。"""
        stats = {"applied": 0, "missed": 0}
        for sub in ("common", "mps"):
            for f in sorted(glob.glob(os.path.join(dump, sub, "*.json"))):
                d = json.load(open(f, encoding="utf-8-sig"))
                _apply_events(d, mapping, stats)
                json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False)
        for f in sorted(glob.glob(os.path.join(dump, "db", "*.json"))):
            d = json.load(open(f, encoding="utf-8-sig"))
            _apply_db(d, mapping, stats)
            json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False)
        if stats["applied"] == 0:
            print("没有命中的译文（译文为空或文本已变化）")
            raise SystemExit(1)
        print(run_tool("WolfTL.exe", os.path.abspath(data_dir_for_patch), work, "patch")[-200:])
        patched = os.path.join(work, "patched", "data")
        if not os.path.isdir(patched):
            raise SystemExit("WolfTL patch 未产出 patched/data")
        # 编码实测回读：Wolf 2.x 的 .dat 按 CP932 存储，无法存储的字符会被静默丢弃
        verify = os.path.join(work, "_verify")
        shutil.rmtree(verify, ignore_errors=True)
        markers = set()
        for zh in mapping.values():
            if isinstance(zh, str) and zh.strip():
                for seg in zh.split("\n"):
                    for ch in seg.strip()[:6]:
                        if ord(ch) > 0x7F:
                            markers.add(ch)
        try:
            run_tool("WolfTL.exe", os.path.abspath(patched), verify, "create")
            body = "".join(open(f, encoding="utf-8").read()
                           for f in glob.glob(os.path.join(verify, "dump", "**", "*.json"),
                                              recursive=True))
            lost = [m for m in sorted(markers) if m not in body]
        finally:
            shutil.rmtree(verify, ignore_errors=True)
        return stats, patched, lost

    ensure_tools()
    from wolf_extract import find_data_dir
    data_dir_for_patch = find_data_dir(game)

    # 第一段：原样写入。若回读发现丢字（Wolf 2.x CP932 存储），
    # 第二段用简体→JIS 字形映射重写（可读汉字体中文），仍丢者仅剩罕见字。
    stats, patched, lost = apply_pass(tr)
    if lost:
        tr2 = {}
        for k, v in tr.items():
            conv, _l = (_s2j_convert(v) if isinstance(v, str) and v.strip() else (v, []))
            tr2[k] = conv
        print(f"检测到 CP932 存储丢字（多为 Wolf 2.x）：{''.join(lost[:15])} …"
              f"用 JIS 字形映射重写一遍")
        # 重新生成干净 dump 再套用映射译文
        shutil.rmtree(dump, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        print(run_tool("WolfTL.exe", os.path.abspath(data_dir_for_patch), work, "create")[-200:])
        stats, patched, lost2 = apply_pass(tr2)
        mapped_note = (f"字形映射后仍丢 {len(lost2)} 字：" + "".join(lost2[:15])
                       if lost2 else "字形映射后全部可存储")
        print(mapped_note)
        lost = lost2

    # 备份并覆盖游戏 Data
    bak = os.path.join(game, "Data.automt.bak")
    if not os.path.exists(bak) and os.path.isdir(data_dir_for_patch):
        shutil.copytree(data_dir_for_patch, bak)
    for item in os.listdir(patched):
        dst = os.path.join(game, "Data", item)
        src = os.path.join(patched, item)
        if os.path.isdir(src):
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    print(f"回写完成：{stats['applied']} 处已翻译，{stats['missed']} 处无译文保持原文")
    if lost:
        print(f"⚠ 编码警告：该游戏按 CP932 存储（Wolf 2.x），仍有 "
              f"{''.join(lost[:20])} 等字符无法写入（已替换/丢失）。")
        print("  完整简体显示建议：「导出 MTool 用 json」+ MTool 运行时挂载。")
    print(f"游戏数据已更新（Data.automt.bak 为改前备份；.wolf.automt.bak 为原始封包）")


if __name__ == "__main__":
    main()
