# -*- coding: utf-8 -*-
"""
OmniTrans 第三步：替换原文（还原回填）
====================================
把机翻结果还原记号、校验、清理，写回 MTool 格式的译文文件。

核心经验（来自实弹项目）：
1. 记号校验必须按【计数】比较（Counter）而非存在性——同一记号出现多次时
2. 机翻会把 〔〕 规范化成 【】（）[]、加空格、全角Ｔ——canon() 容错归一
3. 清理正则绝不能含 \\s（会把真实换行吃掉！）只允许 [ \\t]
4. 机翻会注入非法转义（\\空格、\\-、\\~）——按 RPG Maker 合法集消毒去反斜杠
5. 校验失败的条目保持译文为空（MTool 自动回退原文显示，绝不崩游戏）

用法：
    python mt_apply.py [原ManualTransFile.json路径]   默认当前目录 ManualTransFile.json
输出：
    ManualTransFile_translated.json   可直接给 MTool 导入/放回游戏目录
"""
import json, re, sys, io, os
from collections import Counter
import mt_config

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

src = sys.argv[1] if len(sys.argv) > 1 else "ManualTransFile.json"
orig = mt_config.load_loose_json(src)
data = json.load(open("mt_work/masked.json", encoding="utf-8"))
tokens = json.load(open("mt_work/tokens.json", encoding="utf-8"))
try:
    name_zh = json.load(open("mt_work/names_map.json", encoding="utf-8"))
except FileNotFoundError:
    name_zh = {}

tokre = re.compile(r"〔T[0-9a-f]{8}〕")
# 容错匹配：括号变形/空格/全角Ｔ/全角数字
loose = re.compile(r"[〔【\[\(（]\s*[TtＴ]\s*([0-9a-fA-F]{8})\s*[〕】\]\)）]")
FW = str.maketrans("０１２３４５６７８９ａｂｃｄｅｆＡＢＣＤＥＦ", "0123456789abcdefABCDEF")

def canon(s):
    s = s.translate(FW)
    return loose.sub(lambda m: f"〔T{m.group(1).lower()}〕", s)

def unmask_key(s):
    """键（原文匹配键）必须还原成英文原词，MTool 按精确原文匹配"""
    return tokre.sub(lambda m: tokens.get(m.group(0), m.group(0)), canon(s))

def unmask_val(s):
    """值（译文）里人名替换为中文译名"""
    def r(m):
        o = tokens.get(m.group(0))
        return name_zh.get(o, o) if o is not None else m.group(0)
    return tokre.sub(r, canon(s))

# RPG Maker 合法转义后续字符集；之外的一律去掉反斜杠
VALID_NEXT = set('nNvVcCiIpPGFSfuwMLjsbot' + chr(92) + '{}<>|.^^$[]()')

ok = drop_tok = drop_nl = empty = 0
# 保留原有已翻译条目（顺带修复历史批量解析污染：\"['译文','ja']\" → 译文）
out = {k: mt_config.repair_value(v) for k, v in orig.items()}
for k, v in data.items():
    v = mt_config.repair_value(v)
    data[k] = v
    if not (isinstance(v, str) and v.strip()):
        empty += 1
        continue
    ktoks = tokre.findall(k)
    if Counter(ktoks) != Counter(tokre.findall(canon(v))):
        drop_tok += 1
        data[k] = ""   # 清掉坏值，让下次 mt_translate.py（--seg）重翻
        continue  # 记号丢失：留空回退原文
    en = unmask_key(k)
    zh = unmask_val(v)
    # 机翻痕迹清理（注意：只用 [ \t]，绝不碰换行）
    zh = re.sub(r'(?<=[\u4e00-\u9fff〔])[ \t]+(?=[\u4e00-\u9fff〔〕])', '', zh)
    zh = re.sub(r'[ \t]*([。！？，、：；…～—])[ \t]*', r'\1', zh)
    # 非法转义消毒
    zh = re.sub(r'\\(.)', lambda m: m.group(0) if m.group(1) in VALID_NEXT else m.group(1), zh)
    if en.count("\n") != zh.count("\n"):
        drop_nl += 1
        data[k] = ""
        continue
    out[en] = zh
    ok += 1

dst = os.path.splitext(src)[0] + "_translated.json"
json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(data, open("mt_work/masked.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)  # 回写：清掉坏值供重翻
print(f"回填成功: {ok}；记号丢失留空: {drop_tok}；换行异常留空: {drop_nl}；未翻: {empty}")
print(f"输出: {dst}")
if drop_tok:
    print("提示: 记号丢失的条目可重跑 mt_translate.py --seg 扫尾后再 mt_apply.py")
