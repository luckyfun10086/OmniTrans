# -*- coding: utf-8 -*-
"""rvdata.py（Ruby Marshal 4.8 编解码器）自测
================================================
1. 字节级 ground truth：与 Ruby 官方教程/文档中广为流传的 Marshal 字节串逐一比对
2. 随机树 fuzz：读→写 必须字节级还原
3. 链接语义：符号链接(';') / 对象链接('@') 的索引必须精确复现
运行：python _test_rva.py
"""
import random, sys, io, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'engines'))
import rvdata as R

FAILS = []

def check(name, cond, info=""):
    print(("✓ " if cond else "✗ ") + name + (f"  {info}" if info and not cond else ""))
    if not cond:
        FAILS.append(name)

# ---------------- 1. 字节级 ground truth（Ruby 规范字节串） ----------------
# Marshal.dump(nil) => "\x04\x080"
check("nil", R.dumps(R.loads(b"\x04\x080")) == b"\x04\x080")
check("true", R.dumps(R.loads(b"\x04\x08T")) == b"\x04\x08T")
check("false", R.dumps(R.loads(b"\x04\x08F")) == b"\x04\x08F")

# Fixnum 编码（w_long 同源）
INT_CASES = [
    (0,     b"\x00"),
    (1,     b"\x06"),
    (4,     b"\x09"),
    (5,     b"\x0A"),          # "hello" 长度字节，规范串证实
    (122,   b"\x7F"),
    (123,   b"\x01\x7B"),
    (-1,    b"\xFA"),          # (char)(-1-5)=0xFA；rvdata2 中参数-1的常见形态
    (-123,  b"\x80"),
    (-124,  b"\xFF\x7C"),
    (401,   b"\x02\x91\x01"),  # RPG 事件代码 401
    (1000,  b"\x02\xE8\x03"),
]
for v, expect in INT_CASES:
    n = R.MInt(v)
    got = R.dumps(n)
    want = b"\x04\x08i" + expect
    check(f"fixnum {v}", got == want, f"got {got.hex()} want {want.hex()}")
    # 读回
    back = R.loads(want)
    check(f"fixnum {v} 读回", isinstance(back, R.MInt) and back.v == v)

# Marshal.dump("hello") => "\x04\bI\"\nhello\x06:\x06ET"（教程公认字节串）
HELLO = b"\x04\x08I\"\nhello\x06:\x06ET"
s = R.loads(HELLO)
check("hello 类型", isinstance(s, R.MStr))
check("hello 内容", s.data == b"hello")
check("hello 编码", s.encoding() == "utf-8")
check("hello 回写", R.dumps(s) == HELLO)
check("hello 解码", s.decode() == "hello")

# Marshal.dump(:sym) => "\x04\b:\x08sym"
SYM = b"\x04\x08:\x08sym"
check(":sym", R.dumps(R.loads(SYM)) == SYM)

# Marshal.dump([1,2]) → '[' count(2→\a) i\x06 i\a
ARR = b"\x04\x08[\ai\x06i\a"
a = R.loads(ARR)
check("[1,2]", R.dumps(a) == ARR)
check("[1,2] 值", [x.v for x in a.items] == [1, 2])

# 符号链接：[:foo, :foo] => 5B 07 3A 08 'foo' 3B 00
SL = b"\x04\x08[\a:\x08foo;\x00"
sa = R.loads(SL)
check("符号链接", R.dumps(sa) == SL)
check("符号链接身份", sa.items[0] is sa.items[1])

# 对象链接：a="x"; [a,a] => '['(注册为0) I"(注册为1) x ... @(w_long(1)=06)
OL = b"\x04\x08[\aI\"\x06x\x06:\x06ET@\x06"
oa = R.loads(OL)
check("对象链接", R.dumps(oa) == OL)
check("对象链接身份", oa.items[0] is oa.items[1])

# Hash {"a"=>1}
HA = b"\x04\x08{\x06I\"\x06a\x06:\x06ETi\x06"
h = R.loads(HA)
check('{"a"=>1}', R.dumps(h) == HA)

# RPG::EventCommand 形状：@code=401 @indent=0 @parameters=["hi"]
EC = (b"\x04\x08o:\x16RPG::EventCommand\x08"
      b":\x0A@codei\x02\x91\x01"
      b":\x0C@indenti\x00"
      b":\x10@parameters[\x06I\"\x07hi\x06:\x06ET")
ec = R.loads(EC)
check("EventCommand 解析", isinstance(ec, R.MObj) and ec.cls.name == "RPG::EventCommand")
check("EventCommand @code", ec.ivar("@code").v == 401)
check("EventCommand 参数", ec.ivar("@parameters").items[0].decode() == "hi")
check("EventCommand 回写", R.dumps(ec) == EC)

# UserDef（Table 等原始字节透传）：'u' + :Table + len(3→\x08) + 3 字节
UD = b"\x04\x08u:\x0ATable\x08T\x00\x01"
ud = R.loads(UD)
check("UserDef", R.dumps(ud) == UD)

# ---------------- 2. 随机树 fuzz：读→写字节还原 ----------------
random.seed(20260930)

def rand_tree(depth=0, syms=None, objs=None):
    syms = syms if syms is not None else []
    objs = objs if objs is not None else []
    t = random.randrange(12 if depth < 3 else 6)
    if t == 0:
        return R.NIL
    if t == 1:
        return R.TRUE if random.random() < .5 else R.FALSE
    if t == 2:
        return R.MInt(random.randrange(-70000, 70000) if random.random() < .3
                      else random.randrange(-200, 200))
    if t == 3:  # 符号（复用制造链接）
        if syms and random.random() < .4:
            return random.choice(syms)
        s = R.MSym(f"@v{len(syms)}")
        syms.append(s)
        return s
    if t == 4:  # 字符串（带/不带编码 ivar；复用制造链接）
        if objs and random.random() < .25:
            return random.choice(objs)
        st = R.MStr(f"文本{random.randrange(999)}".encode("utf-8"),
                    [(R.MSym("E"), R.TRUE)] if random.random() < .7 else None)
        objs.append(st)
        return st
    if t == 5:
        return R.MFloat(b"3.14")
    if t == 6:
        return R.MUserDef(R.MSym("Table"), os.urandom(8))
    if t == 7:
        return R.MUserMarshal(R.MSym("Foo"), rand_tree(depth + 1, syms, objs))
    if t == 8:
        n = random.randrange(4)
        arr = R.MArray()
        objs.append(arr)
        for _ in range(n):
            arr.items.append(rand_tree(depth + 1, syms, objs))
        return arr
    if t == 9:
        n = random.randrange(3)
        hs = R.MHash()
        objs.append(hs)
        for _ in range(n):
            hs.pairs.append((rand_tree(depth + 1, syms, objs),
                             rand_tree(depth + 1, syms, objs)))
        if random.random() < .2:
            hs.default = rand_tree(depth + 1, syms, objs)
        return hs
    if t == 10:
        o = R.MObj(random.choice(syms) if syms and random.random() < .5 else R.MSym("RPG::X"),
                   [])
        objs.append(o)
        for _ in range(random.randrange(4)):
            o.ivars.append((R.MSym(f"@f{random.randrange(6)}"),
                            rand_tree(depth + 1, syms, objs)))
        return o
    return R.MStruct(R.MSym("S"), [(R.MSym("a"), R.MInt(1))])

ok = True
for i in range(300):
    tree = rand_tree()
    data = R.dumps(tree)
    try:
        back = R.loads(data)
        redump = R.dumps(back)
        if redump != data:
            ok = False
            print(f"  fuzz#{i} 不还原: {data[:60].hex()}")
            break
    except Exception as e:
        ok = False
        print(f"  fuzz#{i} 异常: {e}")
        break
check("随机树 fuzz 300 轮字节还原", ok)

# ---------------- 3. 修改字符串后链接仍然成立 ----------------
arr = R.MArray()
shared = R.MStr("共有".encode(), [(R.MSym("E"), R.TRUE)])
arr.items = [shared, R.MObj(R.MSym("RPG::EventCommand"),
                            [(R.MSym("@parameters"), R.MArray([shared]))])]
data = R.dumps(arr)
tree = R.loads(data)
# 两处引用同一字符串对象 → 对象链接
check("共享字符串→对象链接", b"@" in data[4:])
R.MStr.set_text(tree.items[0], "改写后")
data2 = R.dumps(tree)
tree2 = R.loads(data2)
check("改写后身份保持", tree2.items[0] is tree2.items[1].ivar("@parameters").items[0])
check("改写生效", tree2.items[0].decode() == "改写后"
      and tree2.items[1].ivar("@parameters").items[0].decode() == "改写后")

# ---------- 字体扫描（rva_apply.warn_fonts 依赖项） ----------
import zlib, tempfile, os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "engines"))
from rva_apply import scan_fonts
script = b'Font.default_name = "VL Gothic"\n'
entry = R.MArray([R.MInt(100), R.MStr(b"main"), R.MStr(zlib.compress(script))])
scripts_file = R.MArray([R.MInt(1), entry])
td = tempfile.mkdtemp()
open(_os.path.join(td, "Scripts.rgss3a"), "wb").write(R.dumps(scripts_file))
check("字体扫描：识别 Font.default_name", scan_fonts(td) == {"VL Gothic"})
open(_os.path.join(td, "Scripts.rgss3a"), "wb").write(
    R.dumps(R.MArray([R.MInt(1), R.MArray([R.MInt(1), R.MStr(b"s"),
                                           R.MStr(zlib.compress(b"Font.default_name = [\"MS Gothic\", \"SimSun\"]"))])])))
check("字体扫描：数组形式多字体", scan_fonts(td) == {"MS Gothic", "SimSun"})


print()
if FAILS:
    print(f"✗ {len(FAILS)} 项失败: {FAILS}")
    sys.exit(1)
print("ALL TESTS PASS")
