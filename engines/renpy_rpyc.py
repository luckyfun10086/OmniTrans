# -*- coding: utf-8 -*-
"""Ren'Py .rpyc 读取与 .rpa 解包（纯 Python、零依赖）
=====================================================
.rpyc（"RENPY RPC2" 格式，Ren'Py 6.99+ / 7 / 8）：
  头: b"RENPY RPC2" + 若干 slot 记录 [u32 idx, u32 offset, u32 length]
  slot 1 = 编译元数据，slot 2 = zlib(pickle(语句树))
  语句树用受限 Unpickler 还原（renpy.ast.* → 通用桩对象，属性在 state[1]）
  对话节点: TranslateSay(8.x 默认)/Say —— .who/.what/.identifier
  菜单节点: Menu —— .identifier/.items[(label, condition, block)]

.rpa（RPA-2.0 / RPA-3.0）：
  首行 "RPA-3.0 <hex偏移> <hex密钥>" / "RPA-2.0 <hex偏移>"
  偏移处 zlib(pickle({名: [(偏移^密钥, 长度, 前缀), ...]}))
"""
import os, sys
_ENG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_ENG))    # 项目根：mt_config 等
sys.path.insert(0, _ENG)                     # 引擎同目录：krkr_xp3 等
import io as _io
import pickle as _pickle
import re
import zlib as _zlib

RPC_MAGIC = b"RENPY RPC2"


class _Stub:
    """renpy.* 类的占位对象：module.name 记录原名，属性从 state[1] 恢复"""
    def __init__(self, *a, **k):
        self._args = a
    def __setstate__(self, state):
        if isinstance(state, dict):
            self.__dict__.update(state)
        elif isinstance(state, (tuple, list)) and len(state) >= 2 \
                and isinstance(state[1], dict):
            self.__dict__.update(state[1])
        else:
            self._state = state


class _SafeUnpickler(_pickle.Unpickler):
    """只放行内建/容器类型；renpy.* 与其余模块一律给桩类（绝不执行任意代码）"""
    def find_class(self, module, name):
        if module in ("builtins", "collections", "copyreg"):
            import builtins, collections, copyreg
            src = {"builtins": builtins, "collections": collections,
                   "copyreg": copyreg}[module]
            return getattr(src, name)
        if module == "renpy.revertable":
            if "Dict" in name and "Sort" not in name:
                return dict
            if "List" in name:
                return list
            if "Set" in name:
                return set
        cn = f"S_{module}_{name}".replace(".", "_")
        return type(cn, (_Stub,), {})


def read_rpyc(path):
    """读取 .rpyc → (meta_dict, 语句树列表)。失败抛 ValueError。"""
    raw = open(path, "rb").read()
    if raw[:10] == RPC_MAGIC:
        # RPC2: slot 表 [u32 idx, u32 offset, u32 length]×N，全零项终止
        pos = 10
        stmts = None
        meta = None
        while pos + 12 <= len(raw):
            idx, off, ln = _rpyc_u32x3(raw, pos)
            pos += 12
            if idx == 0 and off == 0 and ln == 0:
                break
            try:
                blob = _zlib.decompress(raw[off:off + ln])
            except Exception as e:
                raise ValueError(f"slot{idx} zlib 失败: {e}")
            try:
                obj = _SafeUnpickler(_io.BytesIO(blob)).load()
            except Exception as e:
                raise ValueError(f"slot{idx} pickle 失败: {e}")
            if idx == 1:
                meta = obj
            elif idx == 2:
                meta2, stmts = obj if isinstance(obj, tuple) and len(obj) == 2 \
                    else (None, obj)
        if stmts is None:
            raise ValueError("未找到语句 slot")
        return (meta2 if isinstance(meta2, dict) else {}), stmts
    # 旧格式：整个文件是 zlib(pickle)
    try:
        d = _zlib.decompress(raw)
        obj = _SafeUnpickler(_io.BytesIO(d)).load()
        if isinstance(obj, tuple) and len(obj) == 2:
            return (obj[0] if isinstance(obj[0], dict) else {}), obj[1]
        return {}, obj
    except Exception as e:
        raise ValueError(f"无法解析 rpyc: {e}")


def _rpyc_u32x3(buf, pos):
    return (int.from_bytes(buf[pos:pos + 4], "little"),
            int.from_bytes(buf[pos + 4:pos + 8], "little"),
            int.from_bytes(buf[pos + 8:pos + 12], "little"))


def node_kind(n):
    """桩类名 → renpy 类短名（如 Say/TranslateSay/Menu/Label）"""
    cn = type(n).__name__
    pre = "S_renpy_ast_"
    return cn[len(pre):] if cn.startswith(pre) else ""


def walk_stmts(nodes, depth=0):
    """深度优先产出 (node, kind)"""
    if depth > 12:
        return
    for n in nodes if isinstance(nodes, (list, tuple)) else []:
        if hasattr(n, "__dict__"):
            k = node_kind(n)
            if k:
                yield n, k
            for v in vars(n).values():
                if isinstance(v, (list, tuple)):
                    yield from walk_stmts(v, depth + 1)


def collect_dialogue(stmts):
    """语句树 → [{kind, identifier, who, what}]（say / choice / pystring）"""
    out = []
    seen = set()
    for node, kind in walk_stmts(stmts):
        v = vars(node)
        if kind in ("TranslateSay", "Say"):
            what = v.get("what")
            if not isinstance(what, str) or not what.strip():
                continue
            item = {"kind": "say", "identifier": v.get("identifier"),
                    "who": v.get("who"), "what": what}
            key = ("say", item["identifier"], what)
            if key not in seen:
                seen.add(key)
                out.append(item)
        elif kind == "Menu":
            ident = v.get("identifier")
            for it in v.get("items") or []:
                if isinstance(it, (list, tuple)) and it and isinstance(it[0], str) \
                        and it[0].strip():
                    key = ("choice", it[0])
                    if key not in seen:
                        seen.add(key)
                        out.append({"kind": "choice", "identifier": ident,
                                    "who": None, "what": it[0]})
    return out


def collect_py_strings(stmts):
    """PyExpr 源码里的 _("...") / __("...") 字符串（角色名/界面文本）"""
    pat = re.compile(r"""(?:^|[^A-Za-z_])(__|_)\(\s*(['"])((?:\\.|(?!\2).)*)\2""")

    def rec(n, out, depth=0):
        if depth > 12:
            return
        # 桩名来自 find_class：module="renpy.ast.support" → "S_renpy_ast_support_PyExpr"
        # （旧版还比对过 "S_renpy_astsupport_PyExpr"，两种写法都认，防旧数据漏收）
        if type(n).__name__ in ("S_renpy_ast_support_PyExpr", "S_renpy_astsupport_PyExpr"):
            args = getattr(n, "_args", ())
            if args and isinstance(args[0], str):
                for m in pat.finditer(args[0]):
                    out.append(m.group(3))
            return
        if isinstance(n, (list, tuple)):
            for x in n:
                rec(x, out, depth + 1)
        elif hasattr(n, "__dict__"):
            for v in vars(n).values():
                rec(v, out, depth + 1)

    raw = []
    rec(stmts, raw)
    seen = set()
    out = []
    for s in raw:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


# ---------------------------------------------------------------- .rpa
def read_rpa(path):
    """读取 .rpa 档案 → {内部名: bytes}（RPA-2.0 / RPA-3.0）"""
    f = open(path, "rb")
    header = f.readline().decode("ascii", "replace").split()
    if not header or not header[0].startswith("RPA-"):
        raise ValueError(f"不是 RPA 档案: {header[:1]}")
    offset = int(header[1], 16)
    key = int(header[2], 16) if len(header) > 2 else 0
    f.seek(offset)
    index = _SafeUnpickler(_io.BytesIO(_zlib.decompress(f.read()))).load()
    if not isinstance(index, dict):
        raise ValueError("RPA 索引格式异常")

    out = {}
    for name, entries in index.items():
        if isinstance(name, bytes):
            name = name.decode("utf-8", "replace")
        data = bytearray()
        for ent in entries:
            off, dlen = ent[0] ^ key, ent[1]
            start = ent[2] if len(ent) > 2 else 0
            f.seek(off)
            blob = f.read(dlen)
            try:
                data += _zlib.decompress(blob[start:] if start else blob)
            except _zlib.error:
                try:
                    data += _zlib.decompressobj().decompress(blob[start:] if start else blob)
                except _zlib.error:
                    data += blob[start:] if start else blob   # 原始存储兜底
        out[name] = bytes(data)
    f.close()
    return out
