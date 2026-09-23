import fitz, sys
from collections import Counter

for path in sys.argv[1:]:
    doc = fitz.open(path)
    print(f"\n=== {path} ({len(doc)} pages) ===")
    total_lines = 0
    block_line_counts = Counter()
    empty_pages = 0
    for pno, pg in enumerate(doc):
        d = pg.get_text("dict")
        lines = [l for b in d["blocks"] if b["type"] == 0 for l in b["lines"]]
        total_lines += len(lines)
        if len(lines) == 0:
            empty_pages += 1
        for b in d["blocks"]:
            if b["type"] == 0:
                block_line_counts[len(b["lines"])] += 1
        if pno >= 2:
            continue  # only detail first 3 pages
        x0s = Counter(round(l["bbox"][0]) for l in lines)
        print(f"  page {pno}: rect={pg.rect}, lines={len(lines)}, x0众数={x0s.most_common(6)}")
    print(f"  总行数={total_lines}, 空白页数={empty_pages}/{len(doc)}, 块行数分布(前5)={block_line_counts.most_common(5)}")
