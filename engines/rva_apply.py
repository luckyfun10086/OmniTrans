# -*- coding: utf-8 -*-
"""
RPG Maker VX Ace / VX / XP 独立回写器（无需 MTool）
===================================================
把译文 {"原文": "译文"} 写回游戏 Data/*.rvdata2（原文件备份到 Data_backup/）。

安全机制：
- 就地修改 MStr 节点内容 → 链接表/符号表/序列化顺序永不失效
- 未修改的文件不重写（磁盘字节原样）
- 对话/选项行数不齐一律跳过保持原文
- 回写后重新解析校验；写坏磁盘用临时文件+原子替换
- Table/Color 等二进制块按原始字节透传，绝不重编码

用法：
    python rva_apply.py <游戏目录> <译文json>
"""
import json, sys, io, os, glob, shutil, re, zlib

_ENG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_ENG))    # 项目根：mt_config 等
sys.path.insert(0, _ENG)                     # 引擎同目录：krkr_xp3 等
import rvdata as R
from rva_extract import find_data_dir, cmd_code, cmd_params


def set_text(node, text):
    """MStr 就地改写（编码随原串）。返回 True=成功。"""
    if not isinstance(node, R.MStr):
        return False
    return R.MStr.set_text(node, text)


def apply_to_list(cmds, tr, stats):
    i = 0
    items = cmds.items if isinstance(cmds, R.MArray) else []
    while i < len(items):
        c = items[i]
        if not isinstance(c, R.MObj):
            i += 1
            continue
        code = cmd_code(c)
        p = cmd_params(c)
        if code == 401 or code == 405:
            start = i
            lines = []
            while i < len(items) and isinstance(items[i], R.MObj) and cmd_code(items[i]) == code:
                pr = cmd_params(items[i])
                lines.append(pr[0] if pr and isinstance(pr[0], R.MStr) else None)
                i += 1
            block = "\n".join((ln.decode() if ln is not None else "") for ln in lines)
            zh = tr.get(block, "")
            if isinstance(zh, str) and zh.strip():
                parts = zh.split("\n")
                if len(parts) == len(lines) and all(ln is not None for ln in lines):
                    if all(set_text(ln, pt) for ln, pt in zip(lines, parts)):
                        stats["applied"] += 1
                    else:
                        stats["enc"] += 1
                else:
                    stats["skip_lines"] += 1
            continue
        elif code == 102 and p and isinstance(p[0], R.MArray):
            opts = [t if isinstance(t, R.MStr) else None for t in p[0].items]
            block = "\n".join((o.decode() if o is not None else "") for o in opts)
            zh = tr.get(block, "")
            if isinstance(zh, str) and zh.strip():
                parts = zh.split("\n")
                if len(parts) == len(opts) and all(o is not None for o in opts):
                    if all(set_text(o, pt) for o, pt in zip(opts, parts)):
                        stats["applied"] += 1
                else:
                    stats["skip_lines"] += 1
        elif code in (320, 324) and len(p) > 1 and isinstance(p[1], R.MStr):
            zh = tr.get(p[1].decode(), "")
            if isinstance(zh, str) and zh.strip():
                if set_text(p[1], zh):
                    stats["applied"] += 1
        i += 1


def apply_obj_strings(root, tr, stats):
    """物品/技能描述等单行字段"""
    if not isinstance(root, R.MArray):
        return
    for item in root.items:
        if not isinstance(item, R.MObj):
            continue
        for key in ("@description", "@message1", "@message2", "@nickname"):
            node = item.ivar(key)
            if isinstance(node, R.MStr):
                zh = tr.get(node.decode(), "")
                if isinstance(zh, str) and zh.strip():
                    if set_text(node, zh):
                        stats["applied"] += 1


def apply_file(path, tr, stats):
    """解析→改写→序列化。返回 (changed, new_bytes)。"""
    data = open(path, "rb").read()
    try:
        root = R.loads(data)
    except Exception as e:
        print(f"  ⚠ 解析失败（跳过）: {os.path.basename(path)}: {e}")
        return False, None
    before = stats["applied"] + stats["skip_lines"] + stats["enc"]
    fl = os.path.basename(path).lower()
    if fl.startswith("map") and not fl.startswith("mapinfos"):
        if isinstance(root, R.MObj):
            dn = root.ivar("@display_name")
            if isinstance(dn, R.MStr):
                zh = tr.get(dn.decode(), "")
                if isinstance(zh, str) and zh.strip() and set_text(dn, zh):
                    stats["applied"] += 1
            ev = root.ivar("@events")
            if isinstance(ev, R.MHash):
                for _, e in ev.pairs:
                    if not isinstance(e, R.MObj):
                        continue
                    pages = e.ivar("@pages")
                    if isinstance(pages, R.MArray):
                        for pg in pages.items:
                            if isinstance(pg, R.MObj):
                                apply_to_list(pg.ivar("@list"), tr, stats)
    elif fl == "mapinfos.rvdata2":
        if isinstance(root, R.MHash):
            for _, mi in root.pairs:
                if isinstance(mi, R.MObj):
                    node = mi.ivar("@name")
                    if isinstance(node, R.MStr):
                        zh = tr.get(node.decode(), "")
                        if isinstance(zh, str) and zh.strip() and set_text(node, zh):
                            stats["applied"] += 1
    elif fl == "commonevents.rvdata2":
        if isinstance(root, R.MArray):
            for ce in root.items:
                if isinstance(ce, R.MObj):
                    apply_to_list(ce.ivar("@list"), tr, stats)
    elif fl == "troops.rvdata2":
        if isinstance(root, R.MArray):
            for t in root.items:
                if not isinstance(t, R.MObj):
                    continue
                pages = t.ivar("@pages")
                if isinstance(pages, R.MArray):
                    for pg in pages.items:
                        if isinstance(pg, R.MObj):
                            apply_to_list(pg.ivar("@list"), tr, stats)
    else:
        apply_obj_strings(root, tr, stats)
    if stats["applied"] + stats["skip_lines"] + stats["enc"] == before:
        return False, None
    return True, R.dumps(root)


_FONT_ASGN = re.compile(rb"Font\.default_name\s*=\s*(\[?[^\r\n]{0,120})")
_FONT_STR = re.compile(rb'"([^"\x00-\x1f]{1,64})"')
# 常见日文字体（缺简体字形 → 游戏内显示口口方块）
_JP_ONLY = {"VL Gothic", "VL PGothic", "MS Gothic", "ＭＳ ゴシック", "MS Mincho",
            "ＭＳ 明朝", "MS PMincho", "Meiryo", "メイリオ", "Yu Gothic",
            "游ゴシック", " Hiragino Kaku Gothic", "Hiragino Sans", "UmePlus Gothic"}


def scan_fonts(data_dir):
    """从 Scripts 数据解出 Font.default_name 的字体名（只读，供缺字提醒）。"""
    fonts = set()
    for fn in ("Scripts.rgss3a", "Scripts.rvdata", "Scripts.rxdata"):
        p = os.path.join(data_dir, fn)
        if not os.path.isfile(p):
            continue
        try:
            arr = R.loads(open(p, "rb").read())
        except Exception:
            continue
        entries = getattr(arr, "items", None)
        if entries is None:
            continue
        for item in entries[1:]:            # entries[0] = magic number
            cells = getattr(item, "items", None)
            if not (isinstance(cells, list) and len(cells) >= 3):
                continue
            raw = getattr(cells[2], "data", None)
            if raw is None:
                continue
            try:
                code = zlib.decompress(raw)
            except Exception:
                continue
            for m in _FONT_ASGN.finditer(code):
                for nm in _FONT_STR.findall(m.group(1)):
                    try:
                        fonts.add(nm.decode("utf-8"))
                    except UnicodeDecodeError:
                        pass
    return fonts


def warn_fonts(data_dir):
    """中日字体缺字提醒（VX Ace/VX/XP 汉化后显示口口的常见原因）。"""
    try:
        fonts = scan_fonts(data_dir)
    except Exception:
        return
    risky = sorted(f for f in fonts if f.strip() in _JP_ONLY)
    if not risky:
        return
    print(f"ℹ 字体提示：脚本默认字体为 {'、'.join(risky)} —— 若进游戏看到口口方块，"
          f"是日文字体缺简体字形。")
    print("  处理：把脚本中 Font.default_name 改为中文字体（SimSun / 微软雅黑 / SimHei），"
          "或用 MTool 的字体补丁。")


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    game = sys.argv[1]
    trfile = sys.argv[2]
    tr = json.load(open(trfile, encoding="utf-8"))
    data_dir = find_data_dir(game)
    backup = os.path.join(os.path.dirname(os.path.abspath(data_dir)),
                          os.path.basename(data_dir) + "_backup")
    os.makedirs(backup, exist_ok=True)

    files = sorted(glob.glob(os.path.join(data_dir, "*.rvdata2")))
    files += sorted(glob.glob(os.path.join(data_dir, "*.rvdata")))
    files += sorted(glob.glob(os.path.join(data_dir, "*.rxdata")))
    stats = {"applied": 0, "skip_lines": 0, "enc": 0}
    n_written = 0
    for f in files:
        changed, new = apply_file(f, tr, stats)
        if not changed or new is None:
            continue
        # 校验：重新解析确认结构完好
        try:
            R.loads(new)
        except Exception as e:
            print(f"  ⚠ 回写校验失败（保持原文件）: {os.path.basename(f)}: {e}")
            continue
        shutil.copy2(f, os.path.join(backup, os.path.basename(f)))
        tmp = f + ".automt.tmp"
        with open(tmp, "wb") as fh:
            fh.write(new)
        os.replace(tmp, f)
        n_written += 1
    print(f"回写完成：{stats['applied']} 处已翻译，{stats['skip_lines']} 处行数不齐保持原文"
          + (f"，{stats['enc']} 处编码失败保持原文" if stats['enc'] else ""))
    print(f"改动文件 {n_written} 个；原文件备份到: {backup}")
    if n_written:
        warn_fonts(data_dir)


if __name__ == "__main__":
    main()
