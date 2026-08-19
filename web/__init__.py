"""web — 网页层包（应用工厂 + 分层：schemas / services / routers / deps）。

本文件唯一职责：**导入路径引导**。`web` 无论被谁导入，都要保证
项目根与 `src/` 在 `sys.path` 上，否则 `from guji import ...` 失败。

两种导入方式都必须成立（宪法第一条：断言必须可复验）：
    .\\.venv\\Scripts\\python.exe -m uvicorn web.app:app   # 包导入
    .\\.venv\\Scripts\\python.exe web\\selftest.py         # 直接跑脚本
后者由 selftest.py 自己先把项目根塞进 sys.path 再 `import web`。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
