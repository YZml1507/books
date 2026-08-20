"""probe_scripts_importable.py — 审查轨自有工具不得被上游重构打死（R120a，D-141a）。

**为什么存在**：R178b 删掉了 `src/guji/llm_reader.py`。`scripts/ask_bazi.py`
的 `--llm` 分支 `from guji import llm_reader` 于是**必崩**——实测退出码 1、
`ImportError: cannot import name 'llm_reader' from 'guji'`。

这类缺陷有个讨厌的性质：它在**审查轨自己的领土**（`scripts/`）里，
优化轨没有义务发现它；而 13 道闸门只跑其中 9 个脚本，另外那些
（`ask.py` / `ask_bazi.py` / `research_thread.py` …）没有任何闸门覆盖，
可以坏很久没人知道。

**做法：纯静态 AST 分析，不执行任何被检模块。** 用 `ast.parse` 找出
`scripts/` 与 `probes/` 里所有对 `guji` 的引用——**包括写在函数体里的延迟
导入**——再逐个核对 `guji` 是否真的还有那个名字。

**为什么不真导入（本 probe 第一版的设计错误，实测踩过，见 D-141a）**：
第一版用 `importlib` + `exec_module` 做"导入级冒烟"，以为不调 `main()` 就
没有副作用。错了——模块级代码在 `exec_module` 时**就会执行**，而 `probes/`
里不少模块在模块级就跑查询、连数据库、打表格。实测整个 probe 跑到 600s
工具上限被杀，还顺带打了一屏无关输出。纯静态分析零副作用、秒级完成，
且**恰好**能抓到延迟导入（`ask_bazi.py` 那个 bug 就在函数体里，
真导入反而抓不到——因为那行代码只在 `--llm` 时才执行）。

**已知局限（诚实声明，不假装覆盖）**：静态分析只核对"名字还在不在"，
不核对函数**签名**是否变了（如参数增减）。签名级回归由各闸门自己的实测
覆盖，本 probe 不声称覆盖。

复现命令：
    C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe probes\\probe_scripts_importable.py
退出码：0 = 引用的上游符号都存在；1 = 有断裂。
"""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCAN_DIRS = ["scripts", "probes"]
# 已知历史遗留、与本闸门无关的文件（**不是** R178b 造成的）。
# 两者都带 UTF-8 BOM 导致 `ast.parse` 报 `invalid non-printable character
# U+FEFF`，自 initial commit（83d7604，2026-08-14）起就如此，与上游重构无关。
# 实测：probe_coverage.py 因 GBK 控制台编码崩、probe_show.py 缺命令行参数崩，
# 都属一次性勘查脚本而非闸门。**排除它们而不是"顺手修掉"**——本 probe 的职责
# 是抓"上游改动打断审查轨工具"，把无关的历史脏数据混进来会让它的失败含义模糊。
# 若哪天要清理，应当作独立任务，并在 TASK_LEDGER 记一条。
KNOWN_BAD = {"probe_coverage.py", "probe_show.py"}
# 这些是本 probe 自己或会起服务/长耗时的，只做静态检查不真导入
SKIP_IMPORT = {"probe_scripts_importable.py", "probe_ui_smoke.py"}


def guji_symbols() -> tuple[set[str], set[str]]:
    """返回 (guji 包的属性名集合, guji 子模块文件名集合)。"""
    import guji
    attrs = set(dir(guji))
    srcdir = os.path.join(ROOT, "src", "guji")
    mods = {f[:-3] for f in os.listdir(srcdir) if f.endswith(".py")}
    return attrs, mods


def static_guji_refs(path: str) -> list[tuple[int, str]]:
    """扫出文件里所有对 guji 子模块/符号的引用（含函数体内的延迟导入）。"""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except SyntaxError as exc:
        return [(getattr(exc, "lineno", 0) or 0, f"SYNTAX:{exc.msg}")]
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "guji":
                for a in node.names:
                    out.append((node.lineno, a.name))
            elif node.module.startswith("guji."):
                out.append((node.lineno, node.module.split(".", 1)[1]))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("guji."):
                    out.append((node.lineno, a.name.split(".", 1)[1]))
    return out


def main() -> int:
    attrs, mods = guji_symbols()
    print(f"guji 现有子模块 {len(mods)} 个、包级属性 {len(attrs)} 个")

    broken_static: list[str] = []
    broken_import: list[str] = []
    n_files = n_refs = 0

    for d in SCAN_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for fname in sorted(os.listdir(base)):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            if fname in KNOWN_BAD:
                continue
            path = os.path.join(base, fname)
            n_files += 1
            # ── 静态：引用的 guji 符号必须存在（覆盖延迟导入）──
            for lineno, name in static_guji_refs(path):
                if name.startswith("SYNTAX:"):
                    broken_static.append(f"{d}/{fname}:{lineno} {name}")
                    continue
                n_refs += 1
                root = name.split(".")[0]
                if root not in mods and root not in attrs:
                    broken_static.append(
                        f"{d}/{fname}:{lineno} 引用 guji.{name}"
                        f" —— guji 里已不存在这个名字")
    print(f"扫描 {n_files} 个模块、{n_refs} 处 guji 引用（纯静态，零副作用）")
    if broken_static:
        print(f"\n❌ 静态断裂（引用了 guji 里已不存在的名字，{len(broken_static)}）：")
        for b in broken_static:
            print(f"  {b}")
    if broken_static:
        print("\nprobe_scripts_importable FAIL: 审查轨工具引用了上游已删除的名字。"
              "这类缺陷不在 13 道闸门覆盖内（闸门只跑其中 9 个脚本），"
              "只有本 probe 能抓。")
        return 1
    print(f"\nprobe_scripts_importable PASS: {n_files} 个模块的 {n_refs} 处 "
          f"guji 引用全部有效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
