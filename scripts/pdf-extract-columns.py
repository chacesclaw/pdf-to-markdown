# -*- coding: utf-8 -*-
"""学生论文/多栏 PDF 抽取：每块一行 + 首行缩进定段 + 动态分栏 + 英文版式适配

fork 自 lecture-notes skill 的 pdf-extract-columns.py（学术期刊双栏论文场景），
260922 用 Bloom NEC/HOSA 学生作品实测后针对「英文、更多栏、PPT 导出的封面/表单/信息图」
场景做了四处修复，不回写共享脚本（两个 skill 场景不同，分开维护）：

1. 分栏候选行判据从「中文字符 > 6」放宽成「字母字符（含中英文）> 6」。
   原判据对纯英文文档 cand 恒为空 → 分栏检测整体失效 → 退化成一个覆盖全页的伪单栏，
   英文封面/表单页因此被拼成一大段读不断句的文本。
2. 居中短行（表单字段行"Event Name: xxx"、封面署名行等）单独成块，
   不再被首行缩进逻辑并入相邻段落。
3. clean() 里去掉行内嵌入图片留下的对象替换符（U+FFFC）和私有区图标字符（U+E000-U+F8FF），
   避免正文夹带不可见的占位符垃圾字符。
4. 标题/大字号块做「无空格长英文串」乱码嫌疑检测，命中就用 Apple Vision OCR
   （chacesm2max ~/bin/vocr.swift）重新识别该区域替换掉。装饰字体 cmap 损坏时，
   PyMuPDF 取出来的字符本身就是错的，字符串清洗救不回来，只能换一种识别方式。
   OCR 不可用（非 Mac 环境/找不到 vocr.swift）时静默跳过，保留原文本，不阻断整体流程。
5. 260924 补：抠图表并按页面真实位置插入到正文对应处。原脚本只读 `type==0`（文字）块，
   `type==1`（图片/图表）块完全不碰，图表在产出里彻底消失，读者根本不知道正文提到的
   「如上图所示」指的是什么。做法：给每个文字块记录 (页码, y0)；额外扫一遍每页的
   `get_image_rects()`，过滤掉宽高 < 40pt 的小图标/项目符号（不是真正的图表插图），
   把留下的图表按 (页码, y0) 与文字块统一排序合并，输出 `["image", 相对路径]` 类型的块。
   图片用 `page.get_pixmap(clip=图片矩形)` 重新渲染导出，不用 `doc.extract_image()`
   直接抠原始字节——原始字节可能是 CMYK/其他非常规色彩空间，渲染导出能保证拿到的
   都是能直接打开看的标准 RGB PNG。
6. 260925 补：修复「双栏文档只要有图片就整页顺序错乱」的隐藏 bug。上一条的图文合并排序
   用的是 `(页码, y0, x0)`，对单栏文档没问题；但真双栏论文（如 AS0055，每栏各嵌一张图表）
   正文行在抽取主循环里本来是按“先走完左栏、再走完右栏”正确追加进 blocks 的，可一旦调用
   这个按 (页码, y0, x0) 的全局排序合并图片，就会把这个已经排好的栏序打散，退化成纯粹按
   y0 从上到下——结果是左栏读到一半，插入了右栏顶部的图片/文字，读起来整页错序，且不报错、
   不留痕迹，跟第 2 条修复过的 `home=None` 静默丢内容属于同一类「看起来跑完了，实际内容被
   悄悄破坏」的坑。改法：把排序键换成 `(页码, 该行所属栏的栏首 x 坐标, y0)`——栏首 x 天然
   左栏小右栏大，按它排序等价于「先走完左栏再走完右栏」，栏内仍按 y0 从上到下，且对单栏文档
   （只有一个栏首）完全退化成原来的按 y0 排序，不影响过去所有已验证过的单栏文档结果。
   文字块的栏归属在主循环里已知（就是 `for x in starts` 的那个 `x`），直接记录进 position；
   图片不参与分栏检测，按它自己的 x0 用跟文字行同样的“就近栏首”规则重新归位。
7. 260925 补：修复「跨栏内容被无声拼接成一段」的第二个 bug，跟第 6 条同一次真实踩坑
   （AS0055 页 6）一起发现，但是两个独立问题。第 6 条修的是「排序」，这一条修的是「分段」——
   即使排序已经对了（先左栏、后右栏），左栏最后一段和右栏第一段仍然会被段落合并逻辑粘成一段：
   `short_ended`/`gap` 两个判据都是拿当前行跟“上一行在同一栏的记录”比较，换栏后第一行在
   `last_bottom`/`last_line` 里还没有这一栏自己的记录，两个判据都不触发，于是循环不会在换栏处
   `flush()`，上一栏残留在 buf 里的段落就被下一栏的第一行接着往后拼。实测后果：左栏最后一句
   “...new economic structures will be required to sustain employment and social stability.”
   和右栏第一句“These findings mirror existing trends in corporate profitability...”被拼成了
   同一个 `p` block，读起来像是同一段里两件不相关的事被硬凑在一起。修法：`for x in starts:`
   刚进入每一栏时先无条件 `flush()` 一次，换栏（含换页后进入新页面第一栏）一律先了结上一栏的
   段落，不依赖 gap/indent 判据。代价是原文里偶尔真的从左栏一句话直接接到右栏（报纸式排版里
   确实存在的写法）会被拆成两个独立的 `p` block，但这只是「同一段落显示成了两段」的轻微代价，
   远好于「两段不相关内容被粘成一段、读者根本看不出分界」这种更严重的语义错误。
8. 260925 补：修复「项目符号悬挂缩进被当成首行缩进新段落」导致列表项被拆成碎块的问题，
   同一次 AS0055 页 6 排查里跟第 6、7 条一起发现的第三个独立问题。普通段落是「首行缩进、
   续行归零」，项目符号列表通常反过来——符号行缩进较浅，换行续行缩进更深（对齐到符号后文字
   起点），原来的「行首缩进超过阈值 = 新段落」判据认不出这种版式，把一条列表项的每一行续行
   都当成新段落，读出来像是把一句话拆成了好几个孤立的碎句。改法：新增 `is_bullet_start`
   （用 `BULLET_RE` 识别 •●○◦▪▫♦‣∙·- * 等常见符号开头）判断，只有真正的符号行才触发换段；
   期间维护一个 `in_hanging_item` 状态位，只要还在同一个列表项的续行里，缩进判据整体跳过，
   续行照常并入当前段落缓冲区，不再逐行拆散。

已知仍未解决（见 references/multi-column-notes.md）：信息图/问答气泡类版式（图文混排、
无规则文本框）本质上不是「有栏可分」的版式，这类页面即使跑了上述修复，多页内容仍可能被
拍扁成一个大段，正确做法是先探测再决定要不要放弃管线改截图，不是无限打补丁。
"""
import fitz, re, json, sys, os, subprocess, tempfile
from collections import Counter

FW = {chr(0xFF01 + i): chr(0x21 + i) for i in range(94)}
PUA_RE = re.compile("[" + chr(0xFFFC) + chr(0xE000) + "-" + chr(0xF8FF) + "]")

def clean(t):
    t = t.replace("’", "'").replace("＆", "&")
    t = "".join(FW.get(c, c) if FW.get(c, c).isalnum() else c for c in t)
    t = t.replace("．", ".")
    t = PUA_RE.sub('', t)
    t = re.sub(r'(?<=[一-鿿])([A-Za-z0-9(])', r' \1', t)
    t = re.sub(r'([A-Za-z0-9)%])(?=[一-鿿])', r'\1 ', t)
    t = re.sub(r'\s*([，。；：、？！])\s*', r'\1', t)
    t = re.sub(r'\s+([）》」』])', r'\1', t)
    t = re.sub(r'([（《「『])\s+', r'\1', t)
    t = re.sub(r'\(\s+', '(', t); t = re.sub(r'\s+\)', ')', t)
    t = re.sub(r'[ \t]{2,}', ' ', t)
    return t.strip()

def join(parts):
    r = ""
    for x in parts:
        if r.endswith(("⁃", "­")): r = r[:-1]
        elif r and re.search(r'[A-Za-z0-9.,&)]$', r) and re.match(r'^[A-Za-z(&]', x): r += " "
        r += x
    return r

def lines_of(pg):
    out = []
    for b in pg.get_text("dict")["blocks"]:
        if b["type"] != 0: continue
        for l in b["lines"]:
            t = "".join(s["text"] for s in l["spans"])
            if t.strip():
                out.append({"b": l["bbox"], "t": t, "sz": max(s["size"] for s in l["spans"])})
    return out

def merge_rows(col, tol):
    col.sort(key=lambda l: (round(l["b"][1] / tol), l["b"][0]))
    out, i = [], 0
    while i < len(col):
        j, y0 = i, col[i]["b"][1]
        while j < len(col) and abs(col[j]["b"][1] - y0) < tol: j += 1
        seg = sorted(col[i:j], key=lambda l: l["b"][0])
        parts = [seg[0]["t"]]
        for a, b2 in zip(seg, seg[1:]):
            gap = b2["b"][0] - a["b"][2]
            parts.append(("　" if gap > a["sz"] * 0.6 else "") + b2["t"])
        txt = "".join(parts)
        if len(seg) >= 4 and sum(c.isdigit() for c in txt) >= 6:
            i = j; continue                      # 表格行
        out.append({"b": (seg[0]["b"][0], y0, seg[-1]["b"][2], seg[-1]["b"][3]),
                    "t": txt, "sz": max(x["sz"] for x in seg)})
        i = j
    out.sort(key=lambda l: l["b"][1])
    return out

def looks_glyph_broken(t):
    """无空格的长英文串，大概率是装饰字体 cmap 错位导致的乱码（真实标题不会连续 15+ 字符无空格）"""
    core = re.sub(r'[^A-Za-z]', '', t)
    return len(t) >= 15 and " " not in t and len(core) >= 10

VOCR_CANDIDATES = [os.path.expanduser("~/bin/vocr.swift"),
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "vocr.swift")]

def ocr_region(doc, pno, bbox, pad=4, scale=4):
    vocr = next((p for p in VOCR_CANDIDATES if os.path.exists(p)), None)
    if not vocr: return None
    try:
        pg = doc[pno]
        r = fitz.Rect(bbox) + (-pad, -pad, pad, pad)
        r = r & pg.rect
        pix = pg.get_pixmap(clip=r, matrix=fitz.Matrix(scale, scale))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name
            pix.save(tmp_path)
        out = subprocess.run(["swift", vocr, tmp_path], capture_output=True, text=True, timeout=30)
        os.unlink(tmp_path)
        lines = [l for l in out.stdout.splitlines() if l and not l.startswith("=====")]
        text = " ".join(lines).strip()
        return text or None
    except Exception:
        return None

def is_centered(bbox, W, colw, width_ratio=0.65, margin_tol_ratio=0.1, min_margin_ratio=0.05):
    """两个条件都要满足才算居中字段行：
    1. 行宽明显短于正文栏宽（colw）——两端对齐的正文段落每行天然贴满栏宽，只看
       左右边距对称会把每一行两端对齐的普通段落全部误判成"居中"（两端对齐本身
       就会造成左右留白对称），必须先用"行宽 << 栏宽"把两端对齐的正常段落排除掉。
    2. 左右边距（相对页面）对称，且不贴着正文左边距。
    """
    x0, _, x1, _ = bbox
    if (x1 - x0) >= colw * width_ratio: return False
    left, right = x0, W - x1
    if left < W * min_margin_ratio: return False   # 贴着正文左边距，不算居中
    return abs(left - right) < W * margin_tol_ratio

FIELD_LABEL_RE = re.compile(r'^[A-Z][A-Za-z][A-Za-z /]{1,28}:\s')
BULLET_RE = re.compile(r'^[•●○◦▪▫♦‣∙·\-\*]\s')

def looks_like_field(t):
    """"Label: value" 式的表单字段行（如 "Team Member Names: ..."）——这类行有时会
    因为内容长（队员名单）导致行宽逼近正文栏宽，绕过 is_centered() 的宽度判据，
    改用内容模式单独兜底，不依赖几何位置"""
    return bool(FIELD_LABEL_RE.match(t))

def compute_body_and_dead(doc, top_frac=0.02, bot_frac=0.98):
    """算出全文档正文字号（BODY，出现次数最多的字号）和页眉页脚集合（dead，多页同一 y 位置
    反复出现的文本）。独立成模块级函数是 260925 补的——之前只在 run() 内部算，`verify-columns.py`
    这类需要单独核对分栏结果的诊断脚本没法复用，只能重新拷贝一份同样的逻辑，容易和 run() 里的
    版本悄悄跑偏（写这份诊断脚本时就因为手滑漏了几行细节，得到过跟真实抽取结果不一致的假象）。"""
    szs = Counter()
    for pg in doc:
        for l in lines_of(pg): szs[round(l["sz"], 1)] += 1
    BODY = szs.most_common(1)[0][0]
    rep = Counter()
    for pg in doc:
        for l in lines_of(pg):
            rep[(round(l["b"][1] / 6), re.sub(r'\d+', '#', l["t"].strip()))] += 1
    dead = {k for k, v in rep.items() if v >= max(3, len(doc) * 0.5)}
    return BODY, dead

def page_columns(pg, H, W, BODY, dead, top_frac=0.02, bot_frac=0.98):
    """按页拆分正文行分栏归组，抽取阶段和「摸底行距」阶段共用同一套逻辑，也是
    `verify-columns.py` 诊断脚本直接复用的同一份实现（260925 从 run() 内部的嵌套闭包
    提出来，变成显式传参的模块级函数——之前 SKILL.md 里说"page_columns() 是 run() 里现成的
    函数，可以直接调用"是不准确的，闭包捕获了 BODY/dead，外部脚本根本拿不到，只能重新抄一份
    逻辑，这次真的抄错过一次。现在外部脚本可以直接 `from pdf-extract-columns import page_columns`
    （用 importlib 按文件路径加载，因为文件名带连字符不能直接 import）拿到跟 run() 完全一致的
    实现，不会再有第二份可能跑偏的复制。"""
    ls = [l for l in lines_of(pg)
          if H * top_frac < l["b"][1] < H * bot_frac
          and (round(l["b"][1] / 6), re.sub(r'\d+', '#', l["t"].strip())) not in dead]
    if not ls: return None
    # 分栏候选：字母字符（中英文皆可）计数，不再只认中文——纯英文文档下这行原来恒为空
    cand = [l for l in ls if len(l["t"]) >= 12 and sum(c.isalpha() for c in l["t"]) > 6]
    cnt = Counter(round(l["b"][0]) for l in cand)
    wid = sorted(l["b"][2] - l["b"][0] for l in cand) or [BODY * 20]
    colw = wid[len(wid) // 2]              # 栏宽中位数，决定栏间距的判定尺度
    starts = []
    for x in sorted(cnt):
        if cnt[x] < 3: continue
        if starts and x - starts[-1] < colw * 0.5: continue
        starts.append(x)
    if len(starts) > 1:
        # 260925 补：过滤掉行数明显偏少的"假栏"。真正的学术双栏版式里，左右两栏的行数大致
        # 相当（同一页排满两栏正文，行数不会差太多）；但单栏文档里如果某处有一张图片、文字
        # 绕排变窄（§6.9a 那种场景），绕排的这几行只要凑够 3 行、x0 又稳定一致，就会被当成
        # 一个独立"栏"，可它的行数远少于真正贯穿全页的主栏。用 AS0128 实测复现：第 5 页一张
        # 图片右侧绕排的"V-III-II. Implications"段落被误判成第二栏，跟真正的主栏混在一起走
        # 栏优先排序，导致页面中段一对并排图表被排到了页面下方一张无关图片的后面，读序完全
        # 错乱。**先试过用纵向跨度（span）做判据，但跨度这个量纲在两种场景下区分度不够**——
        # 假栏虽然行数少，但两段内容（图注+绕排段落）之间跳得开，纵向跨度照样能有真栏的一半
        # 以上，滤不掉、等于没修。改成看行数比例，用两份真实文档各自的双栏页面数据校准过：
        # AS0055（真双栏）5 个页面两栏行数比最低 52%（40/77），AS0128（假栏）只有 26%（11/42），
        # 中间有将近 2 倍的安全边界。行数比不到「行数最多的候选栏」一半的，视为假栏丢弃、
        # 并入最近的真栏。
        home_n = {x: 0 for x in starts}
        for l in ls:
            home = None
            for x in starts:
                if l["b"][0] >= x - BODY * 0.7: home = x
            if home is None:
                home = min(starts, key=lambda x: abs(x - l["b"][0]))
            home_n[home] += 1
        max_n = max(home_n.values()) if home_n else 0
        if max_n > 0:
            kept = [x for x in starts if home_n[x] >= max_n * 0.5]
            if kept: starts = kept
    if not starts: starts = [round(min(l["b"][0] for l in ls))]
    groups = {x: [] for x in starts}
    for l in ls:
        home = None
        for x in starts:
            if l["b"][0] >= x - BODY * 0.7: home = x
        if home is None:
            # 行的 x0 比所有检测到的栏起点都靠左（常见于比正文更外凸的编号列表项/小标题，
            # 如「5.Activity 1: Role Play」缩进比正文栏浅）——原逻辑在这里直接不分配、
            # 静默丢弃整行，实测在 HOSA-1 上真丢过内容（编号标题+紧跟的一行正文完全消失，
            # 不报错、不留痕迹，只能靠逐页人工核对原文才发现）。改成找不到就退回「最近的栏」，
            # 不能允许任何一行没有归属。
            home = min(starts, key=lambda x: abs(x - l["b"][0]))
        groups[home].append(l)
    return starts, groups, colw

def run(path, top_frac=0.02, bot_frac=0.98, ocr_fix=True, img_out_dir=None):
    # 260923 从 0.075/0.93 收窄：HOSA-1 逐页人工核对时抓到过三处整句丢失，全部是正文最后一行
    # 恰好落在旧的 7%/93% 边距线之外被直接过滤掉（真实坐标 y0=757/752/738，页高 793.5，
    # 旧 bot_frac=0.93 对应 y=738，卡得太死）。页眉页脚真正靠 dead（多页同位置重复文本）识别，
    # 不依赖这个百分比边距；这个参数只用来挡页面物理边缘的出血/裁切线一类东西，不该切掉正文。
    doc = fitz.open(path)
    BODY, dead = compute_body_and_dead(doc, top_frac, bot_frac)

    # 摸底行距：先跑一遍只收集「正文行到正文行」的纵向间距，取中位数当「正常单倍行距」的参照，
    # 再乘一个系数当「空行分段」的判定阈值——不能用固定字号倍数，不同论文的行距密度差异很大
    # （实测同一批材料里，紧凑排版的正文行距只有 0.7pt，段间空行间距 16.3pt，两者相差 20+ 倍，
    # 用统一的固定阈值要么在紧凑文档里判太松漏检，要么在宽松文档里判太紧误伤正常段内换行）。
    gaps = []
    for pno, pg in enumerate(doc):
        H, W = pg.rect.height, pg.rect.width
        got = page_columns(pg, H, W, BODY, dead, top_frac, bot_frac)
        if not got: continue
        starts, groups, colw = got
        for x in starts:
            prev = None
            for l in merge_rows(groups[x], BODY * 0.45):
                if BODY * 0.93 <= l["sz"] <= BODY * 1.22:  # 只用正文行统计，排除标题/脚注
                    if prev is not None: gaps.append(l["b"][1] - prev)
                    prev = l["b"][3]
                else:
                    prev = None
    gaps.sort()
    normal_gap = gaps[len(gaps) // 2] if gaps else BODY * 0.3
    PARA_GAP = max(normal_gap * 3, BODY * 0.3)

    blocks, notes, buf = [], [], []
    positions = []     # 与 blocks 一一对应，(页码, 栏首x, y0)，供图表按位置插入合并用
    buf_pos = [None]   # 当前正在累积的段落，第一行的 (页码, 栏首x, y0)
    page_starts = {}   # pno -> (starts, colw)，供合并图片时判断图片属于哪一栏
    heading_refs = []  # (index_in_blocks, pno, bbox) 供乱码检测+OCR 补救用
    last_bottom = {}   # 每栏上一个正文行的 y1，用于识别「空行分段」（不缩进、靠空行分段的论文，国际学生写作常见）
    last_line = {}     # 每栏上一个正文行的 (文本, x1)，用于识别「提前收尾+句末标点=换段」（既不缩进也不空行的论文）
    def flush():
        nonlocal buf
        if buf:
            blocks.append(["p", clean(join(buf))])
            positions.append(buf_pos[0])
            buf = []
            buf_pos[0] = None

    for pno, pg in enumerate(doc):
        H, W = pg.rect.height, pg.rect.width
        got = page_columns(pg, H, W, BODY, dead, top_frac, bot_frac)
        if not got: continue
        starts, groups, colw = got
        page_starts[pno] = (starts, colw)
        for col_idx, x in enumerate(starts):
            # 同一页内换栏（col_idx > 0）必须先清空上一栏残留的段落缓冲——栏与栏之间不存在
            # 段落延续关系，但 gap/indent 两个判据都是「跟上一行比」，新栏第一行在
            # last_bottom/last_line 里还没有本栏自己的记录，两个判据会双双不触发，
            # 于是上一栏最后一段被无声地跟这一栏第一段粘在一起。260925 用 AS0055 页 6
            # 实测踩过：左栏最后一句"...social stability."直接被接上了右栏第一句
            # "These findings mirror..."，两段风马牛不相及的内容拼成了一段，且没有任何
            # 报错或异常输出，是那种「看着流程跑完了、实际内容被悄悄破坏」的典型坑。
            #
            # 注意：只在 col_idx > 0（同一页内的第 2、3...栏）强制 flush，**不能对每页的
            # 第一栏也无脑强制 flush**——第一版修复图省事把 flush() 放在了 for 循环最外层，
            # 结果对单栏文档（只有一栏，col_idx 恒为 0）等于在每一页开头都强制断一次，
            # 把单栏论文里横跨页面边界、上一页最后一句没写完接到下一页开头接着写完的正常
            # 段落也拦腰斩断了（AS0779 回归测试实测抓到 4 处），比没修之前还差。跨页续接
            # 的判断应该继续交给下面的 gap/indent 逻辑处理，这里只管「同一页内确实换了栏」
            # 这一种情况。
            if col_idx > 0:
                flush()
            in_hanging_item = False  # 是否正处在「项目符号+悬挂缩进续行」的累积过程中，见下方说明
            for l in merge_rows(groups[x], BODY * 0.45):
                t, sz = l["t"], l["sz"]
                if sz > BODY * 1.22:
                    flush()
                    in_hanging_item = False
                    blocks.append(["h", clean(t), round(sz, 1)])
                    positions.append((pno, x, l["b"][1]))
                    heading_refs.append((len(blocks) - 1, pno, l["b"]))
                    continue
                if sz < BODY * 0.93:
                    notes.append(t); continue
                if is_centered(l["b"], W, colw) or looks_like_field(t):
                    flush()
                    in_hanging_item = False
                    blocks.append(["field", clean(t)])
                    positions.append((pno, x, l["b"][1]))
                    continue
                prev_t, prev_x1 = last_line.get(x, (None, None))
                prev_stripped = prev_t.rstrip() if prev_t else ""
                short_ended = (prev_stripped and prev_stripped[-1] in '.!?"”\'’」』）'
                               and (x + colw) - prev_x1 > BODY * 3)
                gap = l["b"][1] - last_bottom.get(x, l["b"][1])
                is_bullet_start = bool(BULLET_RE.match(t.strip()))
                hard_break = bool(short_ended or gap > PARA_GAP)     # 提前收尾/空行分段：真正的段落边界
                indent_break = l["b"][0] >= x + BODY * 1.2 and not in_hanging_item  # 首行缩进分段（非列表续行）
                if hard_break or is_bullet_start or indent_break:
                    flush()
                # 260925 补：项目符号列表常用「悬挂缩进」——符号行本身缩进较浅，换行后的续行
                # 反而缩进更深（对齐到符号后文字的起点），这跟普通段落「只有首行缩进、续行归零」
                # 正好相反。原先的「首行缩进=新段」判据不认这种版式，把每一行续行都当成新段落，
                # 一条列表项被拆成一堆只有一行的碎块。AS0055 实测三条列表项（Scenario 1/2/未来
                # 展望）全部被拆散。第一版修复把 is_bullet_start 和 short_ended/gap 写成互斥的
                # if/elif 链，结果符号行本身十有八九同时也满足 short_ended（上一段句末刚好是句号），
                # short_ended 分支抢先命中、is_bullet_start 分支被跳过，`in_hanging_item` 根本没被
                # 设成 True，等于没修——这也是一个真实踩过的坑：两个独立判据错误地写成了互斥关系。
                # 改法：flush 判断（hard_break / is_bullet_start / indent_break 三者只要有一个满足
                # 就 flush）和 in_hanging_item 状态更新彻底分开算，不共用同一条 if/elif。
                if is_bullet_start:
                    in_hanging_item = True        # 本行是新条目的符号行，后续缩进续行都算它的一部分
                elif hard_break:
                    in_hanging_item = False       # 真正的段落边界，不管之前是不是在列表里，都清空状态
                # 否则（普通续行，含列表悬挂缩进续行）：in_hanging_item 维持原值不变
                if buf_pos[0] is None: buf_pos[0] = (pno, x, l["b"][1])
                buf.append(t)
                last_bottom[x] = l["b"][3]
                last_line[x] = (t, l["b"][2])
    flush()

    if ocr_fix:
        for idx, pno, bbox in heading_refs:
            raw = blocks[idx][1]
            if not looks_glyph_broken(raw): continue
            fixed = ocr_region(doc, pno, bbox)
            if fixed: blocks[idx][1] = clean(fixed)

    # 过滤空块的同时保持 positions 跟 blocks 一一对应（否则后面按下标合并图片会错位）
    kept = [(b, p) for b, p in zip(blocks, positions) if b[1]]
    blocks = [b for b, p in kept]
    positions = [p for b, p in kept]

    if img_out_dir:
        all_lines = [lines_of(pg) for pg in doc]
        images = extract_images(doc, img_out_dir, all_lines, min_size=40)
    else:
        images = []
    if images:
        # 图片和文字块统一按 (页码, 栏首x, y0) 排序合并——图片本身不参与分栏检测，
        # 用它自己的 x0 套用跟文字行相同的「就近栏首」规则重新归位到正确的栏，
        # 不能直接拿图片原始 (pno, y0, x0) 跟文字块的新 (pno, x, y0) 混排（见上面第 6 条修复）
        def image_col_pos(raw_pos):
            pno, y0, x0 = raw_pos
            starts_colw = page_starts.get(pno)
            if not starts_colw or not starts_colw[0]:
                return (pno, x0, y0)
            starts, _ = starts_colw
            home = min(starts, key=lambda sx: abs(sx - x0))
            return (pno, home, y0)
        combined = list(zip(blocks, positions)) + [
            (["image", path], image_col_pos(pos)) for pos, path in images
        ]
        combined.sort(key=lambda bp: bp[1])
        blocks = [b for b, _ in combined]

    return {"body_size": BODY, "blocks": blocks, "notes": notes, "pages": len(doc)}

def tighten_rect(rect, page_rect, lines, pad=3, max_shift=40):
    """PPT/Canva 导出的 PDF 里，图片的 get_image_rects() 声明范围有时比肉眼可见的实际图片范围大
    （260924 实测：HOSA-1 第 8 页两张照片，声明的矩形顶部越过了上方正文最后一行、底部越过了页面
    边界，裁出来的图片顶部带了一截正文文字）。只收上下两边，且只信「离声明边界足够近」
    （<= max_shift pt）的文字行当围栏——试过四边都收 + 不限距离，结果在图片彼此紧邻的页面上
    找错围栏、把照片本体也切掉了，比不修还差。宁可留一点轻微渗入，人工核对/描述时肉眼过滤，
    也不能让裁剪框比实际内容还小。"""
    r = fitz.Rect(rect) & page_rect
    if r.is_empty: return r
    x_overlap = lambda l: l["b"][2] > r.x0 + 2 and l["b"][0] < r.x1 - 2
    above = [l["b"][3] for l in lines if x_overlap(l) and r.y0 < l["b"][3] and l["b"][3] - r.y0 < max_shift]
    if above: r.y0 = max(above) + pad
    below = [l["b"][1] for l in lines if x_overlap(l) and l["b"][1] < r.y1 and r.y1 - l["b"][1] < max_shift]
    if below: r.y1 = min(below) - pad
    return r

def extract_images(doc, out_dir, all_lines, min_size=40, scale=2, max_page_ratio=0.85):
    """抠出每页嵌入的图表/插图，过滤掉宽高 < min_size pt 的小图标/项目符号。
    用渲染导出（get_pixmap clip）而不是 extract_image 抠原始字节，保证拿到标准 RGB PNG；
    裁剪框先经过 tighten_rect() 用相邻文字轻微收紧上下边。同一页内如果两张图片声明的矩形
    大面积重叠（>70%），大概率是 PPT 导出留下的冗余背景/合成层，丢弃面积更大的那张，
    只保留更贴近实际内容的那张——但这个判断只看「重叠面积占比」，不做几何微调，
    避免像 tighten_rect 那样因为过度调整反而切掉真实内容。

    260925 补：还要过滤掉「铺满整页的装饰性背景纹理图」。HOSA-2 实测：Canva/Slides 导出的
    PDF 常把全页背景（斑驳纹理、渐变色块）也存成一个跟页面等大的图片 XObject，纯文字页
    因此被误判成"有一张图片"，实际那张图跟正文内容毫无关系。判据：图片声明的矩形面积占页面
    面积的比例超过 max_page_ratio（默认 85%）**且这一页还有其他实质文字内容**（说明这张
    整页图只是文字内容的背景）才当背景丢弃。**必须加"该页有没有其他文字"这个条件，不能只看
    面积比例**——实测踩过反例：封面页整页就是一张插画（标题和团队信息是画在图里的美术字，
    PDF 文字层这页是空的），面积比例同样接近或等于 100%，但这张图本身就是唯一、有意义的内容，
    不是背景，纯按面积比例过滤会把封面也一起误删。"""
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(doc.name))[0]
    out = []
    for pno, pg in enumerate(doc):
        lines = all_lines[pno]
        page_text_len = sum(len(l["t"]) for l in lines)
        page_area = pg.rect.width * pg.rect.height
        xrefs = [img[0] for img in pg.get_images(full=True)]
        seen, candidates = set(), []
        for xref in xrefs:
            for raw_rect in pg.get_image_rects(xref):
                if raw_rect.width < min_size or raw_rect.height < min_size: continue
                clipped = raw_rect & pg.rect
                is_full_page = page_area > 0 and (clipped.width * clipped.height) / page_area >= max_page_ratio
                if is_full_page and page_text_len >= 50:
                    continue  # 铺满整页 + 页面还有实质文字，才当背景丢弃；页面本身没文字（如封面）就保留
                key = (round(raw_rect.x0), round(raw_rect.y0), round(raw_rect.x1), round(raw_rect.y1))
                if key in seen: continue
                seen.add(key)
                rect = tighten_rect(raw_rect, pg.rect, lines)
                if rect.width < min_size or rect.height < min_size: continue
                candidates.append(rect)
        keep = [True] * len(candidates)
        for i in range(len(candidates)):
            for j in range(len(candidates)):
                if i == j or not keep[i] or not keep[j]: continue
                inter = candidates[i] & candidates[j]
                if inter.is_empty: continue
                ai, aj = candidates[i].width * candidates[i].height, candidates[j].width * candidates[j].height
                smaller = min(ai, aj)
                if smaller > 0 and (inter.width * inter.height) / smaller > 0.7:
                    keep[i if ai > aj else j] = False
        candidates = [r for r, k in zip(candidates, keep) if k]
        for idx, rect in enumerate(candidates, 1):
            fname = f"{stem}_p{pno:02d}_{idx:02d}.png"
            fpath = os.path.join(out_dir, fname)
            try:
                pix = pg.get_pixmap(clip=rect, matrix=fitz.Matrix(scale, scale))
                pix.save(fpath)
            except Exception:
                continue
            out.append(((pno, rect.y0, rect.x0), os.path.join(os.path.basename(out_dir), fname)))
    return out

if __name__ == "__main__":
    img_dir = sys.argv[3] if len(sys.argv) > 3 else None
    r = run(sys.argv[1], img_out_dir=img_dir)
    json.dump(r, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_img = sum(1 for b in r["blocks"] if b[0] == "image")
    print("正文字号 %.1f | 块 %d | 字 %d | 脚注行 %d | 图片 %d" % (
        r["body_size"], len(r["blocks"]),
        sum(len(b[1]) for b in r["blocks"] if b[0] != "image"), len(r["notes"]), n_img))
