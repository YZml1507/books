"""probe_banned_copy.py — 用户可见文案禁词静态闸门（R3256 / UX-COPY-PLAN §禁词表）。

**要防的错**：文案层反复出现的「内部腔/离谱词」上屏——「落点」
「承载」「两头凑」「大声念三遍」这类词用户实测感到生硬出戏。
`check_warm_voice.py` 拦的是运行时输出（吉凶断言/现实指令），
本 probe 拦的是**源码里的用户可见字符串**——词在代码里就红，
不用等服务渲染出来。

扫描口径（只扫用户可见面，注释/字段名不算违规）：
  - Python 文件（voice.py / dream.py / llm_polish.py / services.py）：
    `tokenize` 抽出 STRING token——docstring 与 f-string 文案都覆盖，
    行内注释天然豁免（注释不是 STRING token）。
  - 前端 JS（app.js + app_*.js 懒加载块）：正则抽 `'…'`/`"…"`/`…`
    三种引号/模板字面量。
  - index.html：剥掉 `<!-- -->` 后扫全文——标签属性（alt/title）
    与可见文本都在面内。

阳性对照（宪法第四条 U-08，不许永远返回 0）：
    `probe_banned_copy.py --self-check` 往临时副本里注入
    「有落点」必须被抓到；抓不到退出 2（闸门自身失灵）。

退出码：0 = 零命中；1 = 存在禁词（明细逐条打印）；2 = probe 无法判定。
"""
from __future__ import annotations

import io
import os
import re
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 禁词表锚 `docs/UX-COPY-PLAN.md` §二「禁词/别扭词清单（审计基线）」。
# 加词规则：词必须是「用户可见但不该出现」的文案腔；出现在注释里不违规。
BANNED = (
    "不藏",       # 「缺的那角不藏」式内部口径直译
    "念三遍", "大声念",  # 起名旧文案的仪式指令（实测离谱）
    "落点",       # 「盘里有落点」内部词裸奔——改「有着落/留位置」
    "硬凑",       # 「不硬凑」自证腔——改「不乱猜/不替你编」
    "派发",       # 「派发好运」运营腔
    "承载",       # 「由它承载」开发腔
    "两头凑",     # 解梦 trad 旧句尾
    "供你复验",   # 「供你复验」写给审查员不是写给用户
)

PY_FILES = [
    "src/guji/voice.py",
    "src/guji/dream.py",
    "src/guji/llm_polish.py",
    "web/services.py",
    "web/selftest.py",   # 自测里的期望串若写禁词，等于把禁词钉成基线
]
STATIC = os.path.join(ROOT, "web", "static")
JS_FILES = ["app.js"] + sorted(
    f for f in os.listdir(STATIC)
    if f.startswith("app_") and f.endswith(".js"))
HTML_FILES = ["web/static/index.html"]

_JS_STR = re.compile(
    r"'((?:\\.|[^'\\\n])*)'|\"((?:\\.|[^\"\\\n])*)\"|`([^`]*)`",
    re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _py_strings(path: str):
    """tokenize 抽 STRING token 的 (lineno, text)。注释与标识符豁免。"""
    out = []
    with open(path, "rb") as f:
        for tok in tokenize.tokenize(f.readline):
            if tok.type == tokenize.STRING:
                out.append((tok.start[0], tok.string))
    return out


def _js_strings(path: str):
    """引号/模板字面量正则抽取（行内注释不剥——`//` 出现在字符串里
    的概率远低于注释里躺禁词的概率，宁严勿漏；命中注释串的误报
    用 --self-check 复核手感）。"""
    out = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            for m in _JS_STR.finditer(line):
                s = m.group(1) or m.group(2) or m.group(3) or ""
                if s:
                    out.append((i, s))
    return out


def _html_lines(path: str):
    with open(path, encoding="utf-8") as f:
        text = _HTML_COMMENT.sub("", f.read())
    return [(i, l) for i, l in enumerate(text.splitlines(), 1)]


def scan(root: str = ROOT) -> list[tuple[str, int, str, str]]:
    """→ [(file, lineno, word, snippet)]"""
    hits = []
    for rel in PY_FILES:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            continue
        for ln, s in _py_strings(p):
            for w in BANNED:
                if w in s:
                    hits.append((rel, ln, w, s[:60]))
    for rel in JS_FILES:
        p = os.path.join(STATIC, rel)
        if not os.path.exists(p):
            continue
        for ln, s in _js_strings(p):
            for w in BANNED:
                if w in s:
                    hits.append((f"web/static/{rel}", ln, w, s[:60]))
    for rel in HTML_FILES:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            continue
        for ln, line in _html_lines(p):
            for w in BANNED:
                if w in line:
                    hits.append((rel, ln, w, line.strip()[:60]))
    return hits


def _self_check() -> int:
    """阳性对照：临时字符串文件注入禁词必须命中；不命中 = 闸门失灵。"""
    import tempfile
    src = 'x = "这件事在你盘里有落点，供你复验"\n'
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "t.py")
        with open(p, "w", encoding="utf-8") as f:
            f.write(src)
        hits = [(w) for _, s in _py_strings(p) for w in BANNED if w in s]
    if set(hits) >= {"落点", "供你复验"}:
        print("self-check PASS（注入禁词被抓到）")
        return 0
    print("self-check FAIL：注入禁词没被抓到，闸门失灵")
    return 2


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(_self_check())
    hits = scan()
    for f, ln, w, snip in hits:
        print(f"HIT {f}:{ln} 禁词「{w}」→ {snip!r}")
    if hits:
        print(f"FAIL：{len(hits)} 处禁词命中（口径见 probe docstring）")
        sys.exit(1)
    print(f"PASS：0 命中（扫 {len(PY_FILES)} py + "
          f"{len(JS_FILES)} js + {len(HTML_FILES)} html，"
          f"禁词 {len(BANNED)} 个）")
    sys.exit(0)
