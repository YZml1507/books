"""web/deps.py — 路径解析与资源句柄（web 层的基础设施边界）。

从原 app.py 顶部抽出，职责单一：算出 ROOT / INDEX / DB 路径，并提供
Corpus / KnowledgeBase 的上下文管理器，让路由不再各自写 try/finally。

原 app.py 里每个端点都重复 `c = Corpus(...); try: ... finally: c.close()`
——那是 20 多处同款样板，漏一次就泄漏连接。这里收成一处。
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager


def _resolve_root() -> str:
    """项目根：开发期为 web/ 的父目录；PyInstaller frozen 期另算。

    PyInstaller 单文件模式：__file__ 在 _MEIPASS 临时解压目录，exe 在 dist/。
    data/ 在项目根（dist/ 的父目录），不是 exe 同目录——frozen 期需向上一级
    找含 data/index 的项目根；找不到则退回 exe 同目录（用户需自带 data/）。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        parent = os.path.dirname(exe_dir)
        root = parent if os.path.isdir(os.path.join(parent, "data", "index")) else exe_dir
    return root


ROOT = _resolve_root()

for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 静态前端：frozen 时 spec 把 web/static 内嵌进 _MEIPASS，必须优先用它
# ——按"exe + data/ 单独分发"模型，exe 旁没有 web/ 目录，若从 ROOT 找首页
# 会 404/500。开发期 _MEIPASS 不存在，走项目根。
# 注意 _MEIPASS 缺省不能给 ""：join("", ...) 得到相对路径，恰好被 cwd 命中。
_MEIPASS = getattr(sys, "_MEIPASS", None)
_STATIC_CANDIDATES = (
    [os.path.join(_MEIPASS, "web", "static", "index.html")] if _MEIPASS else []
) + [os.path.join(ROOT, "web", "static", "index.html")]
INDEX = next((p for p in _STATIC_CANDIDATES if os.path.exists(p)),
             _STATIC_CANDIDATES[-1])
STATIC_DIR = os.path.dirname(INDEX)

CORPUS_DB = os.path.join(ROOT, "data", "index", "corpus.db")
KNOWLEDGE_DB = os.path.join(ROOT, "data", "index", "knowledge.db")
CORPUS_MANIFEST = os.path.join(ROOT, "data", "catalog", "corpus_manifest.json")
RAW_DIR = os.path.join(ROOT, "data", "raw")

# 五种地址体系的 label（scheme -> 地址形式说明），供前端 addr 视图提示
SCHEME_LABELS = {
    "zhouyi": "卦·爻（周易系，addr1=卦號 1-64，addr2=爻位）",
    "bcv": "卷:章:節（圣经系，addr_name=卷名）",
    "yilin": "卦·林（焦氏易林，addr1=本卦，addr2=之卦）",
    "booksec": "BOOK:節（Herodotus/Plato/Iliad，addr1=卷）",
    "play": "剧目:幕場（Shakespeare，addr1=剧目序号 1-44，addr2='ACT <roman> SCENE <roman>'）",
    "euclid": "BOOK:proposition（几何原本，addr1=卷，addr2=命题）",
    # R230a-33（R14-P3-1）：键用小写真值 'none'（此前字面 'None' 会让
    # scheme='None' 字符串通过校验后恒零命中）。none = DB 里 scheme IS NULL。
    "none": "无正典地址（页锚点）",
}


@contextmanager
def corpus():
    """语料库句柄（只读检索），退出必关。"""
    from guji.search import Corpus
    c = Corpus(CORPUS_DB)
    try:
        yield c
    finally:
        c.close()


@contextmanager
def knowledge():
    """知识库句柄（研究线程 / 偏好 / 收藏），退出必关。"""
    from guji.knowledge import KnowledgeBase
    kb = KnowledgeBase(KNOWLEDGE_DB)
    try:
        yield kb
    finally:
        kb.close()
