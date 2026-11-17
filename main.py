"""books 部署入口（通用公网部署 · S5）。

平台默认启动 `uvicorn main:app`；本文件把「小满的解忧铺」接进来。

- 路径引导：books/ 进 sys.path，web/__init__.py 自动再补 ROOT 与 src/；
- 公开态开关（docs/DEPLOY.md「多访客公开站必须开」）：
    BOOKS_PAIPAN_HISTORY_DISABLE=1  排盘台账关闭——否则所有访客的
        生辰互见互删（服务端无按用户隔离，见 STUDIO_WORKLOG S5）；
    BOOKS_WRITE_DISABLE=1           共享写面关闭（prefs/收藏/便签/
        import）——同理，无隔离即混池；
    BOOKS_EXTERNAL_DISABLE=1        RSS 外呼关闭；
    BOOKS_TRUST_XFF=1               TLS 反代后信任 X-Forwarded-Proto。
  全部 setdefault——部署方显式设置时以外层为准。想开放共享写面
  （接受访客数据混池）删掉对应 setdefault 即可。
- LLM：配置在 books/web/llm_config.json（gitignored，600 权限）；
  删掉该文件即回到纯确定性模式，应用自动降级（R230t：LLM 永远
  不是承重墙）。
"""

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_BOOKS = os.path.join(_APP_DIR, "books")

# docs/DEPLOY.md：TLS 反代后必须让应用信任 X-Forwarded-Proto/For。
os.environ.setdefault("BOOKS_TRUST_XFF", "1")

# 公开多访客态：排盘台账 + 共享写面 + RSS 外呼全关（无用户隔离）。
os.environ.setdefault("BOOKS_PAIPAN_HISTORY_DISABLE", "1")
os.environ.setdefault("BOOKS_WRITE_DISABLE", "1")
os.environ.setdefault("BOOKS_EXTERNAL_DISABLE", "1")

if _BOOKS not in sys.path:
    sys.path.insert(0, _BOOKS)

from web.app import app  # noqa: E402  （web/__init__.py 负责 ROOT + src/）
