# -*- coding: utf-8 -*-
"""学生论文/多栏 PDF 后处理：标点规范化、西文断词、未完句合并、标题识别

fork 自 lecture-notes skill 的 text-normalize.py，补了一步 PUA_RE 兜底清理
（行内嵌入图片留下的对象替换符/私有区图标字符），跟 pdf-extract-columns.py 的
clean() 重复一次，防止绕过抽取脚本直接喂旧 JSON 时漏清。
"""
import json, re, sys

CN = lambda t: any("一" <= c <= "鿿" for c in t)
END = "。！？；：」』》）.!?"
PUA_RE = re.compile("[" + chr(0xFFFC) + chr(0xE000) + "-" + chr(0xF8FF) + "]")

def quotes(t):
    t = re.sub(r'“([^“”]{0,400})”',
               lambda m: ('「%s」' if CN(m.group(1)) else '"%s"') % m.group(1), t)
    t = re.sub(r'"([^"]{1,400})"',
               lambda m: '「%s」' % m.group(1) if CN(m.group(1)) else m.group(0), t)
    t = re.sub(r'‘([^‘’]{0,200})’',
               lambda m: ('『%s』' if CN(m.group(1)) else "'%s'") % m.group(1), t)
    return t

def punct(t):
    # 中文语境的半角标点转全角
    for h, f in ((":", "："), (";", "；"), ("?", "？"), ("!", "！")):
        t = re.sub(r'(?<=[一-鿿」』》）])\s*\%s\s*' % h, f, t)
        t = re.sub(r'\s*\%s\s*(?=[一-鿿「『《（])' % h, f, t)

    # 括号内含中文 → 全角
    def par(m):
        s = m.group(1).strip()
        return "（%s）" % s if CN(s) else "(%s)" % s
    t = re.sub(r'\(\s*([^()]{0,120}?)\s*\)', par, t)
    t = re.sub(r'（[ \t]+', '（', t); t = re.sub(r'[ \t]+）', '）', t)
    t = re.sub(r'）[ \t]+(?=[一-鿿])', '）', t)
    t = re.sub(r'(?<=[一-鿿])[ \t]+（', '（', t)
    if CN(t):                      # 中文语境：半角逗号转全角，半角括号内的西文除外
        keep = []
        def _hide(m):
            keep.append(m.group(0)); return "\x00%d\x00" % (len(keep) - 1)
        t = re.sub(r'\([^()一-鿿]{0,150}\)', _hide, t)
        t = re.sub(r'\s*,\s*', '，', t)
        for i, v in enumerate(keep): t = t.replace("\x00%d\x00" % i, v)
    t = re.sub(r'&(?=[A-Za-z])', '& ', t)
    t = re.sub(r'\s+&', ' &', t)
    t = re.sub(r'([一-鿿])[ \t]+([一-鿿])', r'\1\2', t)   # 中文之间不留半角空格（全角空格是分隔符，保留）
    t = re.sub(r'[ \t]{2,}', ' ', t)
    return t.strip()

def dehyphen(t):
    # 西文换行连字符（行末 - 接小写）
    return re.sub(r'([A-Za-z]{2,})-([a-z]{2,})',
                  lambda m: m.group(1) + m.group(2)
                  if (m.group(1) + m.group(2)).lower() in HY else m.group(0), t)
HY = {"schuler", "hillman", "administrative", "management", "organizational", "performance",
      "consequences", "comprehensiveness", "communication", "psychology", "companies",
      "institutional", "selection", "successions", "employee", "relations", "behavior"}

HEAD = [
    (re.compile(r'^[一二三四五六七八九十]+、\s*\S{2,20}$'), "h"),
    (re.compile(r'^（[一二三四五六七八九十]+）\s*\S{2,20}$'), "h2"),
    (re.compile(r'^\d+[、.．]\s*\S{2,24}$'), "h3"),
]

def merge_heads(blocks, BODY):
    """大字号的标题/导语/拉引文在版面上是逐行排的，按字号把连续的行并回一块。
    图片块（如标题背景图刚好卡在两行标题中间）要透明跳过，不能打断合并——
    否则「标题第一行 + 图片 + 标题第二行」会被拆成三个块，图片还插在标题中间。"""
    out = []
    last_h_idx = None
    for b in blocks:
        k, t = b[0], b[1]
        sz = b[2] if len(b) > 2 else None
        if k == "image":
            out.append([k, t, None])
            continue
        if k == "h" and sz and last_h_idx is not None and out[last_h_idx][2] == sz:
            prev_t = out[last_h_idx][1]
            join = "" if re.search(r"[一-鿿，。、；：]$", prev_t) or t[:1] in "，。、；：" else ""
            out[last_h_idx][1] = prev_t + join + t
        else:
            out.append([k, t, sz])
            last_h_idx = len(out) - 1 if k == "h" else None
    hs = [b[2] for b in out if b[0] == "h" and b[2]]
    top = max(hs) if hs else None
    res = []
    for k, t, sz in out:
        if k != "h" or not sz: res.append((k, t)); continue
        if sz == top and top >= BODY * 1.8: res.append(("title", t))
        elif sz >= BODY * 1.5:
            res.append(("lead" if len(t) < 120 else "q", t))
        else:
            res.append(("h" if len(t) <= 22 else "q", t))
    return res

def finalize(blocks, keep_h=True):
    out = []
    for k, t in blocks:
        # image：块内容是图片文件的相对路径，不是正文，不能套用任何文本清洗/标点规则
        if k == "image": out.append((k, t)); continue
        t = PUA_RE.sub('', t)
        t = dehyphen(t); t = punct(t); t = quotes(t)
        if not t or t in ("*", "**"): continue
        # field：抽取阶段识别出的居中字段行/表单行，本来就不以句末标点收尾，
        # 不能套用下面「未完句合并」的逻辑，否则会被当成被截断的段落重新粘回去
        if k in ("h", "title", "lead", "q", "field"): out.append((k, t)); continue
        hit = next((kk for rx, kk in HEAD if rx.match(t)), None)
        out.append((hit or "p", t))
    # 拉引文/导语若插在被切断的段落中间，先移到该段之后
    i = 0
    while i + 2 < len(out):
        a, mid, b = out[i], out[i + 1], out[i + 2]
        if a[0] == "p" and b[0] == "p" and mid[0] in ("lead", "q") \
           and len(a[1]) > 12 and a[1][-1] not in END:
            out[i + 1], out[i + 2] = b, mid
        i += 1
    # 未完句合并：上一段没有收尾标点，说明是被版面切断的。图片块（如插在段落中间的图表）
    # 透明跳过，不能打断——否则一句话被图片劈成两段，合并规则找不到「上一段」而失效。
    merged = []
    last_p_idx = None
    for k, t in out:
        if k == "image":
            merged.append((k, t))
            continue
        if last_p_idx is not None and k == "p" and merged[last_p_idx][0] == "p" \
           and len(merged[last_p_idx][1]) > 12 and merged[last_p_idx][1][-1] not in END:
            prev = merged[last_p_idx][1]
            sep = " " if (re.search(r'[A-Za-z0-9]$', prev) and re.match(r'^[A-Za-z(]', t)) else ""
            merged[last_p_idx] = ("p", prev + sep + t)
        else:
            merged.append((k, t))
            last_p_idx = len(merged) - 1 if k == "p" else None
    return merged


META_MARK = re.compile(r'(内容提要|摘\s*要|关键词|中图分类号|文献标志码|文章编号|Abstract)')

def split_meta(blocks):
    out = []
    for k, t in blocks:
        if k != "p" or not META_MARK.search(t):
            out.append((k, t)); continue
        parts, last = [], 0
        for m in META_MARK.finditer(t):
            if m.start() > last: parts.append(t[last:m.start()].strip())
            last = m.start()
        parts.append(t[last:].strip())
        for x in parts:
            if not x: continue
            if re.match(r'^(中图分类号|文献标志码|文章编号)', x): continue   # 刊务元数据，网页不需要
            out.append(("meta" if META_MARK.match(x) else "p", x))
    return out

def apply_fixes(blocks, fixes):
    out = []
    for k, t in blocks:
        for a, b in fixes: t = t.replace(a, b)
        if t.strip(): out.append((k, t.strip()))
    return out

if __name__ == "__main__":
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    FIXES = json.load(open(sys.argv[3], encoding="utf-8")) if len(sys.argv) > 3 else []
    d["blocks"] = apply_fixes(split_meta(finalize(merge_heads(d["blocks"], d["body_size"]))), FIXES)
    json.dump(d, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    b = d["blocks"]
    print("块 %d | 字 %d | 弯引号 %d | 标题 %d/%d/%d" % (
        len(b), sum(len(v) for _, v in b),
        sum(v.count("“") + v.count("”") for _, v in b),
        sum(1 for k, _ in b if k == "h"), sum(1 for k, _ in b if k == "h2"),
        sum(1 for k, _ in b if k == "h3")))
