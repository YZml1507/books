#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R20-1：「✉️ 写给未来的自己」去下划线 + 空盒排版（CYCLE5_PLAN 任务二）

现役锚点（styles.css:4308-4316，md5 302434d2945ba4fe60b77686188dd117）：
    /* R12：打卡区唯一裸文本行……补 ck-quest 同族软卡底归队；下划线/文案不动。 */
    .fl-entry{display:flex; align-items:center; gap:10px;
      margin:8px 0 2px; padding:8px 12px; flex-wrap:wrap;
      background:var(--accent-soft); border:1px dashed var(--border);
      border-radius:10px;}
    .fl-write{background:none; border:0; padding:0; font-size:12.5px;
      color:var(--primary-ink); cursor:pointer; text-decoration:underline;
      text-underline-offset:3px;}

病灶（CYCLE5_PLAN §2.1）：
  · 下划线是 R12 刻意留的（注释白纸黑字「下划线/文案不动」），用户本轮
    直接判它难看并点名「先去掉」→ 删 text-decoration。
  · .fl-entry 实测高 82px，盒内只有一个 44px 按钮（.fl-pend 恒空 h=0），
    上下各空 ~29/9px →「悬在大空盒左上角」。虚线软卡底改 quiet 行，
    与 .checkin-q 同族，高度随内容收缩。
可点性补偿：主色 --primary-ink 不动 + 行 hover 柔光（替代下划线语义）。
零功能删除：.fl-pend 待送达计数、fl-modal 写信弹层、未来信渲染链全不碰。
"""
import io, sys

CSS = "/opt/books/app/web/static/styles.css"

OLD = """/* R12：打卡区唯一裸文本行——上邻周信卡、下接小功课/旺运/
 * 要紧日子全是卡面，独它一缕带下划线纯文本（用户报「整体格式
 * 有点问题」）。补 ck-quest 同族软卡底归队；下划线/文案不动。 */
.fl-entry{display:flex; align-items:center; gap:10px;
  margin:8px 0 2px; padding:8px 12px; flex-wrap:wrap;
  background:var(--accent-soft); border:1px dashed var(--border);
  border-radius:10px;}
.fl-write{background:none; border:0; padding:0; font-size:12.5px;
  color:var(--primary-ink); cursor:pointer; text-decoration:underline;
  text-underline-offset:3px;}"""

NEW = """/* R20（用户直报）：「✉️ 写给未来的自己」带下划线、且悬在 82px 空软卡里
 * （盒内只有一个 44px 按钮，.fl-pend 恒空，上下各空 ~29/9px）——
 * 用户判「排版有问题」并点名「一就是先去掉」。R12 当轮注释写着
 * 「下划线/文案不动」，那是当时取舍；本轮按用户裁决改：
 *   ① 删 text-decoration/underline-offset——可点性交给主色
 *      --primary-ink + 行 hover 柔光补偿，不再靠下划线；
 *   ② 虚线软卡底改 quiet 行（与 .checkin-q 同族），高度随内容收缩，
 *      空盒观感消除；.fl-pend 待送达计数保留，写信链路零改动。 */
.fl-entry{display:flex; align-items:center; gap:10px;
  margin:6px 0 2px; padding:5px 6px; flex-wrap:wrap;
  background:none; border:0; border-radius:8px;
  transition:background .15s;}
.fl-entry:hover{background:var(--accent-soft);}
.fl-write{background:none; border:0; padding:0; font-size:12.5px;
  color:var(--primary-ink); cursor:pointer;}"""


def main():
    with io.open(CSS, "r", encoding="utf-8") as f:
        s = f.read()
    n = s.count(OLD)
    if n != 1:
        sys.exit("FAIL: anchor count=%d（预期 1）——现役内容已变，先重查再打" % n)
    if "R20（用户直报）" in s:
        sys.exit("FAIL: 已打过 R20-1（重复打补丁自检命中）")
    s = s.replace(OLD, NEW, 1)
    with io.open(CSS, "w", encoding="utf-8") as f:
        f.write(s)
    # 打后自检：新块在、旧声明干净
    for probe in (".fl-write{background:none; border:0; padding:0; font-size:12.5px;",
                  ".fl-entry:hover{background:var(--accent-soft);}"):
        if s.count(probe) != 1:
            sys.exit("FAIL: 打后自检未命中 %r" % probe)
    if "text-decoration:underline" in s.split(".fl-write{")[1].split("}")[0]:
        sys.exit("FAIL: .fl-write 仍带下划线")
    print("styles.css PATCHED (R20-1 去下划线 + quiet 行)")


if __name__ == "__main__":
    main()
