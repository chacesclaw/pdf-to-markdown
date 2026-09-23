"""检测一张复合图片内部是否是规则网格（如 Google Slides 网格视图截图），
是的话按网格线切成单张缩略图，不是的话原样返回。
判定方法：找背景色的行/列条带（gutter），把内容行/列分组成网格。
"""
import sys, os
from PIL import Image
import numpy as np

def detect_grid(img_path, out_dir, bg_tol=12, min_cells=4):
    img = Image.open(img_path).convert("RGB")
    arr = np.array(img)
    H, W, _ = arr.shape

    # 背景色：取四个角的众数颜色，Slides 网格视图背景通常是浅灰/白
    corners = [arr[0,0], arr[0,-1], arr[-1,0], arr[-1,-1]]
    bg = np.median(corners, axis=0)

    def is_bg_row(y):
        row = arr[y]
        diff = np.abs(row.astype(int) - bg.astype(int)).sum(axis=1)
        return (diff < bg_tol).mean() > 0.92

    def is_bg_col(x):
        col = arr[:, x]
        diff = np.abs(col.astype(int) - bg.astype(int)).sum(axis=1)
        return (diff < bg_tol).mean() > 0.92

    def content_bands(n, is_bg_fn, min_gap=3, min_band=15):
        bg_flags = [is_bg_fn(i) for i in range(n)]
        bands, start = [], None
        for i, f in enumerate(bg_flags):
            if not f and start is None:
                start = i
            elif f and start is not None:
                if i - start >= min_band:
                    bands.append((start, i))
                start = None
        if start is not None and n - start >= min_band:
            bands.append((start, n))
        return bands

    row_bands = content_bands(H, is_bg_row)
    col_bands = content_bands(W, is_bg_col)

    n_rows, n_cols = len(row_bands), len(col_bands)
    if n_rows * n_cols < min_cells or n_rows < 1 or n_cols < 2:
        return None  # 不是网格，或格子太少不值得拆

    # 校验：格子尺寸要大致一致（真实网格的判据），允许 25% 误差
    row_heights = [b - a for a, b in row_bands]
    col_widths = [b - a for a, b in col_bands]
    if max(row_heights) > min(row_heights) * 1.25 or max(col_widths) > min(col_widths) * 1.25:
        return None

    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(img_path))[0]
    cells = []
    idx = 0
    for ri, (y0, y1) in enumerate(row_bands):
        for ci, (x0, x1) in enumerate(col_bands):
            idx += 1
            cell = img.crop((x0, y0, x1, y1))
            fname = f"{stem}_cell{idx:02d}.png"
            fpath = os.path.join(out_dir, fname)
            cell.save(fpath)
            cells.append((ri, ci, fpath))
    return {"rows": n_rows, "cols": n_cols, "cells": cells}

def split_evenly(img_path, out_dir, rows, cols):
    """自动检测失败时的兜底：内容紧贴格子边界、没有干净背景间隔时（比如图表+表格拼接图），
    自动找边界不可靠，改成按行列数强制等分裁切。切出来的边界不会跟真实格子线像素对齐，
    但足够看清每格内容，人工核对/描述用途够用，不追求像素级精确。"""
    img = Image.open(img_path).convert("RGB")
    W, H = img.size
    cw, ch = W / cols, H / rows
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(img_path))[0]
    cells, idx = [], 0
    for ri in range(rows):
        for ci in range(cols):
            idx += 1
            box = (round(ci*cw), round(ri*ch), round((ci+1)*cw), round((ri+1)*ch))
            cell = img.crop(box)
            fname = f"{stem}_cell{idx:02d}.png"
            fpath = os.path.join(out_dir, fname)
            cell.save(fpath)
            cells.append((ri, ci, fpath))
    return {"rows": rows, "cols": cols, "cells": cells}

if __name__ == "__main__":
    img_path, out_dir = sys.argv[1], sys.argv[2]
    if len(sys.argv) > 4:
        # 手动指定行列数强制等分：python grid_split.py 图片 输出目录 行数 列数
        rows, cols = int(sys.argv[3]), int(sys.argv[4])
        r = split_evenly(img_path, out_dir, rows, cols)
        print(f"EVEN-SPLIT {r['rows']}x{r['cols']}, {len(r['cells'])} cells")
    else:
        r = detect_grid(img_path, out_dir)
        if r is None:
            print("NOT_A_GRID（试试加行列数参数强制等分，如: python grid_split.py 图片 输出目录 2 6）")
        else:
            print(f"GRID {r['rows']}x{r['cols']}, {len(r['cells'])} cells")
    if r:
        for ri, ci, fpath in r["cells"]:
            print(f"  row{ri} col{ci}: {fpath}")
