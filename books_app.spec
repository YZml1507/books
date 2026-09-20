# pyinstaller spec — 古籍智慧助手单文件打包
#
# 构建：.venv\Scripts\python.exe -m PyInstaller books_app.spec --noconfirm
# 产物：dist\books_app.exe（单文件）
#
# 设计：
#   * entry = web_launcher.py（无控制台窗口，--windowed）
#   * 内嵌 web/static/（前端单页，60K）
#   * data/ 不内嵌（392MB 太大）：exe 启动时从同目录 data/ 读，
#     找不到则降级（仅排盘无检索）。发行时 exe + data/ 一起分发。
#   * 注意（R230c 勘正——原 R18a 注释与 deps.py 实际行为相反）：frozen
#     下 _STATIC_CANDIDATES 优先 _MEIPASS 内嵌副本（本 spec datas 已嵌
#     web/static）——exe 单文件即可渲染首页；exe 旁的 web/static 存在时
#     会被覆盖使用（便于不打包子迭代前端）。data/ 仍需 exe 旁分发。
#   * 运行时资源路径：PyInstaller 单文件解压到 sys._MEIPASS；
#     开发模式用 __file__ 推导的 ROOT。web_launcher.py 已处理两种模式。
#
# 依赖打包：
#   * fastapi + uvicorn（核心）
#   * feedparser（外部资讯）
#   * 纯标准库模块（bazi/liuyao/huangli/qiming）自动包含
#   * 不打包：numpy 之外的 ML 栈（torch/sentence-transformers 等，见
#     excludes）——bge 语义检索在 exe 里不可用，bazi_lookup 为函数内
#     懒加载，降级为仅 FTS 检索，不崩溃。

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
        # R229x：起名典故库 + daily/warm 文案库——不进 exe 时
        # classical_names 静默 0 候选、copy_bank 静默回退旧表。
        ('src/guji/classical_names.json', 'src/guji'),
        ('src/guji/copy_bank.json', 'src/guji'),
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
        # R229s：'guji.llm_reader' 已删——模块随 R178b LLM 层移除下线，
        # spec 残留引用会让 PyInstaller Analysis 直接报 hidden import 缺失。
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
