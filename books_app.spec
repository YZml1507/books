# pyinstaller spec — 古籍智慧助手单文件打包
#
# 构建：.venv\Scripts\python.exe -m PyInstaller books_app.spec --noconfirm
# 产物：dist\books_app.exe（单文件，约 40-60MB）
#
# 设计：
#   * entry = web_launcher.py（无控制台窗口，--windowed）
#   * 内嵌 web/static/（前端单页，60K）
#   * data/ 不内嵌（392MB 太大）：exe 启动时从同目录 data/ 读，
#     找不到则降级（仅排盘无检索）。发行时 exe + data/ 一起分发。
#   * 运行时资源路径：PyInstaller 单文件解压到 sys._MEIPASS；
#     开发模式用 __file__ 推导的 ROOT。web_launcher.py 已处理两种模式。
#
# 依赖打包：
#   * fastapi + uvicorn（核心）
#   * numpy + sentence-transformers（bge 语义检索，可选）
#   * feedparser（外部资讯）
#   * 纯标准库模块（bazi/liuyao/huangli/qiming）自动包含

# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

a = Analysis(
    ['web_launcher.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        # 内嵌前端单页（小，必内嵌）
        ('web/static', 'web/static'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # web.app 自身（uvicorn 字符串导入 "web.app:app"）
        'web',
        'web.app',
        # guji 子模块（确保被打包）
        'guji.bazi',
        'guji.bazi_calc',
        'guji.bazi_lookup',
        'guji.liuyao',
        'guji.huangli',
        'guji.qiming',
        'guji.external',
        'guji.history',
        'guji.llm_reader',
        'guji.lunar',
        'guji.search',
        'guji.ingest',
        'guji.compare',
        'guji.knowledge',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除大型不需要的包（torch 496MB 是 exe 217MB 主因）
        'torch', 'torchvision', 'torchaudio',
        'sentence_transformers',
        'transformers', 'tokenizers', 'huggingface_hub', 'safetensors',
        'sklearn', 'scipy', 'scipy.libs',
        'pandas',
        'matplotlib',
        'PIL', 'pillow',
        'fitz', 'pymupdf',
        'markitdown',
        'playwright', 'pyee',
        'sympy', 'mpmath',
        'onnxruntime',
        'skimage',
        'pyarrow',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='books_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # UPX 压缩减小体积
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # 无控制台窗口（--windowed）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
