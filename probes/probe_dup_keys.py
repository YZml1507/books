#!/usr/bin/env python3
"""probe_dup_keys — dict 字面量重复键静态闸（AST 全扫）。

R2576：R2574 实测抓到「购物」重复键——dict 字面量同键后写静默覆盖
先写，差点把「购物→出行」既有口径改成纳财。这类缺陷肉眼/测试都难抓，
AST 全扫一次到位、常驻防回归。

判据：仓内所有 .py 的 ast.Dict 常量键零重复。
用法：python3 probes/probe_dup_keys.py（离线、<1s）。
"""
import ast
import os
import sys
import warnings

warnings.filterwarnings("ignore")   # 存量文件的 escape SyntaxWarning 与本闸无关

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKIP = (".git", "node_modules", "__pycache__", ".venv", "dist", "build")


def main() -> int:
    bad = []
    # 与 CI ruff 闸同口径的代码面：src/web/probes/scripts + 根目录散文件。
    candidates = [os.path.join(ROOT, d) for d in ("src", "web", "probes", "scripts")]
    candidates += [os.path.join(ROOT, f) for f in os.listdir(ROOT)
                   if f.endswith(".py")]
    files_iter = []
    for c in candidates:
        if os.path.isfile(c):
            files_iter.append(c)
            continue
        for root, dirs, files in os.walk(c):
            dirs[:] = [d for d in dirs if d not in _SKIP]
            for f in files:
                if f.endswith(".py"):
                    files_iter.append(os.path.join(root, f))
    for path in files_iter:
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            seen: set = set()
            for k in node.keys:
                if isinstance(k, ast.Constant):
                    if k.value in seen:
                        bad.append(
                            f"{os.path.relpath(path, ROOT)}:{node.lineno}"
                            f" dup key {k.value!r}")
                    seen.add(k.value)
    if bad:
        for b in bad[:20]:
            print("FAIL", b)
        return 1
    print("PASS probe_dup_keys  dict 字面量零重复键（AST 全扫）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
