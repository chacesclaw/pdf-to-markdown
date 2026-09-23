# -*- coding: utf-8 -*-
"""双栏（及以上）论文核对工具：按「栏 1 全文、栏 2 全文……」的真实阅读顺序打印每一页的分栏
结果，供人工整理 Markdown 正文时逐块核对着写，不能凭肉眼扫读一份按 y 坐标排序的原始转储去猜
（§6.10 记录过的真实事故：AS0055 双栏页面手抄整理时把左右两栏内容拼成了一段，还漏掉了一整句
和三条项目符号要点）。

直接复用 pdf-extract-columns.py 里的 `compute_body_and_dead()` / `page_columns()` 模块级函数，
跟实际抽取管线用的是同一份实现，不会出现"诊断脚本和真实抽取逻辑悄悄跑偏"的问题。

用法：
    ./venv/bin/python scripts/verify-columns.py <PDF路径> [起始页(1起) [结束页]]

输出格式：
    =====PAGE N: k column(s) at x=[...] =====
      --col 1 x=... --
        y=... '这一行的文字...'
      --col 2 x=... --
        y=... '这一行的文字...'

k==1 就是单栏，k>=2 就是双栏（或更多栏）。每一栏内部已经按 y 从上到下排好，两栏之间按
「栏 1 全文、栏 2 全文」的顺序打印，就是最终应该写进 Markdown 正文的真实阅读顺序。
"""
import sys
import importlib.util
import os

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("pec", os.path.join(_here, "pdf-extract-columns.py"))
pec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pec)

import fitz

def main():
    if len(sys.argv) < 2:
        print("用法: verify-columns.py <PDF路径> [起始页(1起) [结束页]]")
        sys.exit(1)
    path = sys.argv[1]
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    end = int(sys.argv[3]) if len(sys.argv) > 3 else None

    doc = fitz.open(path)
    BODY, dead = pec.compute_body_and_dead(doc)
    end = end or len(doc)

    for pno in range(start - 1, min(end, len(doc))):
        pg = doc[pno]
        H, W = pg.rect.height, pg.rect.width
        got = pec.page_columns(pg, H, W, BODY, dead)
        if not got:
            print(f"=====PAGE {pno + 1}: no columns=====")
            continue
        starts, groups, colw = got
        print(f"=====PAGE {pno + 1}: {len(starts)} column(s) at x={starts}=====")
        for ci, x in enumerate(starts):
            print(f"  --col {ci + 1} x={x}--")
            for l in pec.merge_rows(groups[x], BODY * 0.45):
                y = round(l["b"][1])
                print(f"    y={y} {l['t'][:100]!r}")

if __name__ == "__main__":
    main()
