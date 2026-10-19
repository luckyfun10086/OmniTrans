# -*- coding: utf-8 -*-
r"""
漫画解析/渲染共享库（图片文件夹 / CBZ）
======================================
comic_extract.py 与 comic_apply.py 共用。

链路（sidecar 方案，与字幕引擎同哲学）：
- 提取端：逐页 OCR（rapidocr-onnxruntime）→ 文本区域框 + 台词；
  汇成扁平 {"原文": ""} 字典（重复台词去重），框/页信息存 sidecar（<名>_comic.json）
- 翻译：走 OmniTrans 既有管线（掩码/术语表/断点续传全保留）
- 回写端：Pillow 把每个区域用"边缘取样的底色"填充（气泡≈白，画面≈近似底色），
  再把译文按框自动排版绘制——竖长框（h ≥ 1.3w）且目标语言为中日文时自动竖排
  （列从右到左），否则横排自动换行；字号二分收缩到放得下为止。
  输出非破坏性：文件夹 → 同级 <名>.<tl>/；CBZ → 同级 <名>.<tl>.cbz

已知边界（v1 如实声明）：
- OCR 用 PP-OCR 通用模型：横排/网页漫画效果好，日漫竖排原文的识别率有限
  （译文竖排渲染不受影响）；高质量路线（manga-ocr/manga-image-translator 桥接）在路线图上
- 框外艺术字、特效字不在 OCR 结果里，不会被改动
"""
import os, re, io, zipfile

IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif")

def nat_key(s):
    """自然排序（p2 < p10）"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

def collect_pages(path):
    """目录 → 递归收集页图（自然排序）；.cbz/.zip → 成员页。返回页描述列表。"""
    if os.path.isfile(path):
        pages = []
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.lower().endswith(IMG_EXTS) and "__macosx" not in n.lower():
                    pages.append(n)
        return [{"kind": "zip", "zip": os.path.abspath(path), "ref": n}
                for n in sorted(pages, key=nat_key)]
    pages = []
    for root, dirs, files in os.walk(path):
        dirs.sort(key=nat_key)
        for f in sorted(files, key=nat_key):
            if f.lower().endswith(IMG_EXTS):
                pages.append({"kind": "file", "ref": os.path.join(root, f)})
    return pages

# ---------------- OCR（rapidocr-onnxruntime，懒加载 + 进程内缓存） ----------------
_OCR = None

def get_ocr():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        print("加载 OCR 引擎（rapidocr-onnxruntime）…")
        _OCR = RapidOCR()
    return _OCR

# ---------------- manga-ocr 混合识别（日漫专用，可选） ----------------
# rapidocr 通用模型检测框可靠，但竖排日文识别很差（实测乱码）；
# 装了 manga-ocr 就自动启用混合模式：框用 rapidocr，整气泡裁片交给 manga-ocr 重识别。
_MOCR = None

def get_mocr():
    global _MOCR
    if _MOCR is None:
        from manga_ocr import MangaOcr
        print("加载 manga-ocr 模型（首次运行自动下载，约 440MB）…")
        _MOCR = MangaOcr()
    return _MOCR

def mocr_available():
    import importlib.util
    return importlib.util.find_spec("manga_ocr") is not None

def hybrid_enabled():
    """MT_COMIC_OCR=auto（默认，装了 manga-ocr 就用）/ manga / rapid"""
    import mt_config
    mode = mt_config.load_env().get("MT_COMIC_OCR", "auto").strip().lower()
    if mode == "rapid":
        return False
    if mode == "manga":
        return True
    return mocr_available()

def enhance_with_mocr(clusters, target):
    """对每个气泡级簇：裁片 → manga-ocr 整体重识别（竖排可靠）。
    target = 页路径或图片 bytes。识别为空则保留 rapidocr 行文本。"""
    from PIL import Image
    if isinstance(target, bytes):
        img = Image.open(io.BytesIO(target)).convert("RGB")
    else:
        img = Image.open(target).convert("RGB")
    mocr = get_mocr()
    ex = 8
    for r in clusters:
        x1, y1, x2, y2 = r["box"]
        crop = img.crop((max(0, x1 - ex), max(0, y1 - ex),
                         min(img.width, x2 + ex), min(img.height, y2 + ex)))
        try:
            t = str(mocr(crop)).strip()
        except Exception:
            t = ""
        if t and has_word(t):
            r["text"] = t
    return clusters

def ocr_regions(target):
    """对一张页做 OCR（整页 + 分块放大双重检测，框取并集）。
    target = 文件路径或图片 bytes。高分辨率页上整页检测会把图缩到检测上限，
    小字/艺术字/标题成为盲区（实测漏掉整列竖排）；分块放大 1.5x 补上，
    相邻碎列由 cluster_regions 拼回、manga-ocr 对合并框整句重识别。
    返回 [{"box":[x1,y1,x2,y2], "text": str}]，过滤低分/过小条目。"""
    from PIL import Image
    if isinstance(target, bytes):
        img = Image.open(io.BytesIO(target)).convert("RGB")
    else:
        img = Image.open(target).convert("RGB")
    W, H = img.size
    items = list(get_ocr()(target)[0] or [])
    if max(W, H) > 1200:
        items += _ocr_tiled(img)
    # 中心距去重（整页结果优先，分块补漏）
    out, seen = [], []
    for box, text, conf in sorted(
            [(i[0], str(i[1]), float(i[2] or 0)) for i in items],
            key=lambda t: -t[2]):
        if conf < 0.5 or not text.strip():
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx, cy = sum(xs) / 4, sum(ys) / 4
        if any((cx - px) ** 2 + (cy - py) ** 2 < 30 ** 2 for px, py in seen):
            continue
        seen.append((cx, cy))
        r = {"box": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
             "text": text.strip()}
        if r["box"][2] - r["box"][0] < 8 or r["box"][3] - r["box"][1] < 8:
            continue
        out.append(r)
    return out

def _ocr_tiled(img, scale=1.5, overlap=0.2):
    """竖切两块（全宽、带重叠）各自放大后 OCR，框坐标映射回整页。
    实测对竖排日漫的高分页盲区有效（整页检测把图缩到上限会漏整列小字）；
    2×2 切法实测无效，勿改。"""
    from PIL import Image
    ocr = get_ocr()
    W, H = img.size
    ov = int(H * overlap)
    tiles = [(0, 0, W, H // 2 + ov), (0, H // 2 - ov, W, H)]
    items = []
    for x1, y1, x2, y2 in tiles:
        tile = img.crop((x1, y1, x2, y2))
        tw, th = tile.size
        tile = tile.resize((int(tw * scale), int(th * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        tile.save(buf, "PNG")
        for it in (ocr(buf.getvalue())[0] or []):
            box = [[p[0] / scale + x1, p[1] / scale + y1] for p in it[0]]
            items.append([box, it[1], it[2]])
    return items

# 判断是否含有可翻译内容（复用字幕引擎的词字符判定）
_WORD_RE = re.compile(r"[0-9A-Za-z\u00c0-\u024f\u0370-\u03ff\u0400-\u04ff\u3040-\u30ff"
                      r"\u3400-\u9fff\uac00-\ud7af\uff66-\uff9f]")

def has_word(t):
    return bool(_WORD_RE.search(t))

# ---------------- 气泡级聚类 ----------------
# OCR 返回的是行级框：竖排日漫的每一列都是一根独立的窄长条。
# 直接逐条回写会把气泡切成条纹、译文塞进单列。实证标定（真实漫画 sidecar）：
# 同气泡相邻列的水平间隙中位 ≈8px、跨气泡 ≈30px、列宽中位 ≈50px——据此合并。

def _mergeable(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    xgap = max(0, max(ax1, bx1) - min(ax2, bx2))
    ygap = max(0, max(ay1, by1) - min(ay2, by2))
    if xgap and ygap:
        return False                                  # 对角分离：不同气泡
    if not xgap and not ygap:
        return True                                   # 实体重叠（嵌套/误检）
    if ygap == 0:                                     # 左右相邻 → 竖排的列
        yo = min(ay2, by2) - max(ay1, by1)
        minh = min(ay2 - ay1, by2 - by1)
        minw = min(ax2 - ax1, bx2 - bx1)
        return xgap <= max(20, minw * 0.5) and yo >= 0.4 * minh
    # 上下相邻 → 横排的行；只有"行高"级别的框才允许跨行合并（防把上下两只气泡并掉）
    xo = min(ax2, bx2) - max(ax1, bx1)
    minh = min(ay2 - ay1, by2 - by1)
    minw = min(ax2 - ax1, bx2 - bx1)
    return ygap <= max(10, minh * 0.5) and minh <= 90 and xo >= 0.3 * minw

def cluster_regions(regions):
    """行级区域 → 气泡级区域（连通合并）。竖排簇文本按列右→左拼接（日文阅读序），
    横排簇按行拼接（行间以 \n）。"""
    if not regions:
        return []
    n = len(regions)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if _mergeable(regions[i]["box"], regions[j]["box"]):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for idxs in groups.values():
        rs = [regions[i] for i in idxs]
        box = [min(r["box"][0] for r in rs), min(r["box"][1] for r in rs),
               max(r["box"][2] for r in rs), max(r["box"][3] for r in rs)]
        if box[3] - box[1] >= box[2] - box[0]:
            ordered = sorted(rs, key=lambda r: (-r["box"][0], r["box"][1]))
            text = "".join(r["text"] for r in ordered)
        else:
            ordered = sorted(rs, key=lambda r: (r["box"][1], r["box"][0]))
            text = "\n".join(r["text"] for r in ordered)
        out.append({"box": box, "text": text})
    out.sort(key=lambda r: (r["box"][1], r["box"][0]))
    return out

# ---------------- 渲染（Pillow，仅回写端需要） ----------------
_FONT_CACHE = {}
_FONT_PATH = "?"
_ZIPS = {}

def find_font(size):
    """系统 CJK 字体（可用 .env MT_FONT 指定路径）。找不到返回 None。"""
    global _FONT_PATH
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    if _FONT_PATH == "?":
        _FONT_PATH = _resolve_font_path()
    if _FONT_PATH is None:
        return None
    from PIL import ImageFont
    f = ImageFont.truetype(_FONT_PATH, size)
    _FONT_CACHE[size] = f
    return f

def _resolve_font_path():
    import mt_config
    p = mt_config.load_env().get("MT_FONT", "").strip()
    if p and os.path.exists(p):
        return p
    cands = ["msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc", "Deng.ttf",
             "simkai.ttf", "NotoSansCJK-Regular.ttc", "NotoSansCJKsc-Regular.otf",
             "SourceHanSansSC-Regular.otf", "wqy-microhei.ttc", "wqy-zenhei.ttc"]
    dirs = [r"C:\Windows\Fonts", "/usr/share/fonts", "/System/Library/Fonts"]
    for d in dirs:
        for c in cands:
            q = os.path.join(d, c)
            if os.path.exists(q):
                return q
    return None

def load_page_image(pg):
    """页描述 → PIL RGB 图（zip 成员缓存 ZipFile 句柄）。"""
    from PIL import Image
    if pg["kind"] == "zip":
        z = _ZIPS.get(pg["zip"])
        if z is None:
            z = _ZIPS[pg["zip"]] = zipfile.ZipFile(pg["zip"])
        return Image.open(io.BytesIO(z.read(pg["ref"]))).convert("RGB")
    return Image.open(pg["ref"]).convert("RGB")

def close_zips():
    """关掉缓存的 ZipFile 句柄（Windows 下不关会锁住原档案）。"""
    for z in _ZIPS.values():
        try:
            z.close()
        except Exception:
            pass
    _ZIPS.clear()

def page_bytes(pg, img):
    """渲染后的页 → bytes（沿用原始格式；JPEG 用高质量 92，防整页画质劣化）。"""
    buf = io.BytesIO()
    fmt = (pg.get("fmt") or "PNG").upper()
    if fmt == "JPG":
        fmt = "JPEG"
    if fmt not in ("JPEG", "PNG", "WEBP", "BMP"):
        fmt = "PNG"
    try:
        img.save(buf, fmt, quality=92)
    except Exception:
        buf = io.BytesIO()
        img.save(buf, "PNG")
    return buf.getvalue(), (".jpg" if fmt == "JPEG" else "." + fmt.lower())

def border_color(img, box):
    """区域边缘像素的中位色——气泡≈白，画面≈近似底色。"""
    x1, y1, x2, y2 = [int(v) for v in box]
    w, h = max(1, x2 - x1), max(1, y2 - y1)
    x1c, y1c = max(0, x1 + min(2, w // 4)), max(0, y1 + min(2, h // 4))
    x2c, y2c = min(img.width, x2 - min(2, w // 4)), min(img.height, y2 - min(2, h // 4))
    px = img.load()
    rs, gs, bs = [], [], []
    step = max(1, (x2c - x1c) // 24)
    for x in range(x1c, x2c, step):
        for y in (y1c, y2c - 1):
            r, g, b = px[x, y][:3]
            rs.append(r); gs.append(g); bs.append(b)
    step = max(1, (y2c - y1c) // 24)
    for y in range(y1c, y2c, step):
        for x in (x1c, x2c - 1):
            r, g, b = px[x, y][:3]
            rs.append(r); gs.append(g); bs.append(b)
    if not rs:
        return (255, 255, 255)
    rs.sort(); gs.sort(); bs.sort()
    m = len(rs) // 2
    return (rs[m], gs[m], bs[m])

_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]")

# ---------------- 文本清洗 ----------------
# manga-ocr 的日文标点（．．．『』「」）会原样进词条，机翻又会保留到译文，
# 嵌出来的字前后就挂着符号。源文本入词典前归一省略号（顺带让
# 'では．．'/'では．．．' 去重成同一条）；译文绘制前剥掉两端装饰符号。

_ELLI_RUN = re.compile(r"[．。]{2,}|\.{3,}")
# 两端可剥的装饰：角引号/圆方括号/省略号/句读/破折号（成对循环剥，保留 ？！～♡ 等语气符）
_EDGE_STRIP = "「」『』【】《》〈〉〔〕[]［］（）()\"'“”‘’…．。，、,.—―ー"

def clean_source(t):
    """OCR 文本入词典前：省略号归一为 ……，去首尾空白。"""
    t = _ELLI_RUN.sub("……", t.strip())
    return t.replace("...", "……").strip()

def clean_target(t):
    """译文/原文绘制前：剥掉两端的引号、省略号、句读装饰。"""
    t = _ELLI_RUN.sub("……", t)
    t = t.replace("...", "……")
    for _ in range(3):
        t = t.strip().strip(_EDGE_STRIP)
    return t.strip()

def _h_layout(draw, text, font, maxw):
    """横排自动换行（拉丁按词、CJK 逐字，支持 \n 分段）。返回行列表。"""
    lines = []
    for para in text.split("\n"):
        cur, curw = "", 0
        for tok in re.findall(r"\s+|\S+", para):
            tw = draw.textlength(tok, font=font)
            if cur and curw + tw > maxw and tok.strip():
                lines.append(cur.rstrip())
                cur, curw = (tok if tok.strip() else ""), tw
            else:
                cur += tok
                curw += tw
            while curw > maxw and len(cur) > 1:      # 超长词硬拆
                lo, hi = 1, len(cur)
                while lo < hi:
                    mid = (lo + hi) // 2
                    if draw.textlength(cur[:mid], font=font) <= maxw:
                        lo = mid + 1
                    else:
                        hi = mid
                cut = max(1, lo - 1)
                lines.append(cur[:cut])
                cur, curw = cur[cut:], draw.textlength(cur[cut:], font=font)
        if cur.strip() or not lines:
            lines.append(cur.rstrip() or " ")
    return lines or [" "]

# ---------------- 排版度量（fits 与 draw 必须共用，否则溢出） ----------------
# 紧凑密度：行高/列宽 ≈ 1.1×字号（漫画嵌字常规），同框能排出更大的字
def _pad(size):
    return max(2, size // 8)

def _hlh(size):            # 横排行高
    return size + max(2, size // 8)

def _vch(size):            # 竖排每字行高
    return size + max(2, size // 10)

def _vcolw(size):          # 竖排列宽
    return size + max(2, size // 8)

def _draw_h(draw, box, text, font, size, color):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    pad = _pad(size)
    lines = _h_layout(draw, text, font, w - pad * 2)
    lh = _hlh(size)
    th = lh * len(lines)
    y = y1 + max(pad, (h - th) // 2)
    for ln in lines:
        lw = draw.textlength(ln, font=font)
        draw.text((x1 + max(pad, (w - lw) // 2), y), ln, font=font, fill=color)
        y += lh

def _draw_v(draw, box, text, font, size, color):
    """竖排：列自右向左，每列自上而下。"""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    pad = _pad(size)
    chars = list(text.replace(" ", "").replace("\n", ""))
    ch = _vch(size)
    colw = _vcolw(size)
    per = max(1, int((h - pad * 2) // ch))
    ncols = (len(chars) + per - 1) // per
    tw = colw * ncols
    x = x2 - pad - colw - max(0, (w - tw) // 2)
    for j in range(ncols):
        col = chars[j * per:(j + 1) * per]
        y = y1 + pad + max(0, (h - pad * 2 - ch * len(col)) // 2)
        for c in col:
            cw = draw.textlength(c, font=font)
            draw.text((x + (colw - size) // 2 + (size - cw) // 2, y), c,
                      font=font, fill=color)
            y += ch
        x -= colw

def _v_fits(draw, box, text, font, size):
    x1, y1, x2, y2 = box
    pad = _pad(size)
    per = max(1, int((y2 - y1 - pad * 2) // _vch(size)))
    ncols = (len(text.replace(" ", "").replace("\n", "")) + per - 1) // per
    return ncols * _vcolw(size) <= (x2 - x1) - pad * 2

def _h_fits(draw, box, text, font, size):
    x1, y1, x2, y2 = box
    pad = _pad(size)
    lines = _h_layout(draw, text, font, (x2 - x1) - pad * 2)
    return _hlh(size) * len(lines) <= (y2 - y1) - pad * 2

def draw_region(draw, img, box, text, tl):
    """填充框底色并排版绘制文本。竖长框 + 中日文 → 竖排。
    填充用圆角矩形并向外扩 3px 盖住原字边缘残墨。"""
    fill = border_color(img, box)
    x1, y1, x2, y2 = box
    ex = 3
    rad = max(4, min(x2 - x1, y2 - y1) // 10)
    try:
        draw.rounded_rectangle([x1 - ex, y1 - ex, x2 + ex, y2 + ex],
                               radius=rad, fill=fill)
    except AttributeError:                       # 旧版 Pillow 无圆角
        draw.rectangle([x1 - ex, y1 - ex, x2 + ex, y2 + ex], fill=fill)
    lum = 0.299 * fill[0] + 0.587 * fill[1] + 0.114 * fill[2]
    color = (0, 0, 0) if lum > 128 else (255, 255, 255)
    w, h = x2 - x1, y2 - y1
    vertical = (tl in ("zh", "ja") and h >= w * 1.3 and _CJK_RE.search(text))
    start = max(9, min(96, int(min(w, h) * 0.85)))
    for size in range(start, 7, -1):
        font = find_font(size)
        if font is None:
            return False
        fits = _v_fits(draw, box, text, font, size) if vertical \
            else _h_fits(draw, box, text, font, size)
        if fits:
            (_draw_v if vertical else _draw_h)(draw, box, text, font, size, color)
            return True
    font = find_font(8)
    if font is None:
        return False
    (_draw_v if vertical else _draw_h)(draw, box, text, font, 8, color)
    return True
