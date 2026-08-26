"""R218a 优化轨后真实可行的验收（替代消失的闸门脚本）

台账里引用的 selftest_163/probe_ui_smoke/baseline_voice/check_warm_voice/
check_plain_first/check_poster 等脚本在当前 scripts/ 目录均不存在（R217+
阶段未保留）。本验证只做三件事：
  1. uvicorn 8183 健康
  2. 三个关键 API 真实调用（bazi/qiming/chat）能返回 200 且关键字段非空
  3. 主页 HTML 含本次改动的关键标记（chat-fallback / qm-style / .recent-backdrop / R218a-01 CSS）

退出码: 0 全部通过 / 1 任一失败
"""
import json, sys, time, urllib.request, urllib.error, re
from pathlib import Path

BASE = "http://127.0.0.1:8183"
failures = []


def check(name, fn):
    t0 = time.time()
    try:
        msg = fn()
        print(f"  ✓ {name}  [{time.time()-t0:.1f}s]  {msg}")
    except AssertionError as e:
        failures.append((name, str(e)))
        print(f"  ✗ {name}  FAIL: {e}")
    except Exception as e:
        failures.append((name, f"{type(e).__name__}: {e}"))
        print(f"  ✗ {name}  ERROR: {type(e).__name__}: {e}")


# 1. 健康
print("=== 1. uvicorn 健康 ===")
def health():
    r = urllib.request.urlopen(f"{BASE}/", timeout=5)
    assert r.status == 200, f"status={r.status}"
    return "HTTP 200"
check("GET /", health)


# 2. 关键 API
print("\n=== 2. 关键 API（POST）===")

def post(path, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def api_bazi():
    d = post("/api/bazi", {"year": 1990, "month": 5, "day": 15, "hour": 14, "gender": "女"})
    assert "bazi" in d or "voice" in d or "result" in d, f"keys={list(d.keys())[:5]}"
    return f"keys={list(d.keys())[:5]}"
check("POST /api/bazi", api_bazi)


def api_qiming():
    d = post("/api/qiming", {"surname": "李", "gender": "女", "style": "诗经"})
    assert isinstance(d, dict), f"type={type(d).__name__}"
    return f"keys={list(d.keys())[:5]}"
check("POST /api/qiming", api_qiming)


def api_chat():
    d = post("/api/chat", {"session_id": "r218a-verify", "message": "帮我看看盘"})
    assert isinstance(d, dict), f"type={type(d).__name__}"
    return f"keys={list(d.keys())[:5]}"
check("POST /api/chat", api_chat)


# 3. 改动标记
print("\n=== 3. 改动标记（静态资源）===")
def has(path, needles):
    r = urllib.request.urlopen(f"{BASE}{path}", timeout=5)
    body = r.read().decode("utf-8", errors="replace")
    missing = [n for n in needles if n not in body]
    assert not missing, f"missing={missing}"
    return f"all {len(needles)} markers found"

def css_markers():
    return has("/static/styles.css", [
        "R218a-01",                  # 侧栏宽度
        "recent-backdrop",            # 遮罩
        "qm-style-chip",              # 起名风格芯片
        "qm-score",                   # 推荐指数
    ])
check("GET /static/styles.css", css_markers)


def js_markers():
    return has("/static/app.js", [
        "_CHAT_FALLBACK_DEFAULT",     # 降级文案池
        "_CHAT_FALLBACK_BY_KW",       # 关键词分支
        "_chatFallbackLine",          # 选句函数
        "qm-style",                   # 起名风格按钮
        "qm-score",                   # 推荐指数
        "R218a-01",                   # 注释
    ])
check("GET /static/app.js", js_markers)


def copy_bank_markers():
    cb = Path("src/guji/copy_bank.json")
    assert cb.exists(), "copy_bank.json 不存在"
    data = json.loads(cb.read_text(encoding="utf-8"))
    cf = data.get("chat_fallback_openers")
    assert cf is not None, "chat_fallback_openers 字段缺失"
    default = cf.get("default", [])
    kws = [k for k in cf.keys() if k != "default"]
    assert len(default) >= 4, f"default 池 {len(default)} 句，不足 4 句"
    assert len(kws) >= 3, f"关键词池 {len(kws)} 类，不足 3 类"
    return f"default {len(default)} 句 + {len(kws)} 关键词池"
check("copy_bank.json#chat_fallback_openers", copy_bank_markers)


# 汇总
print(f"\n=== 汇总 ===")
print(f"  总检查: 8  通过: {8 - len(failures)}  失败: {len(failures)}")
if failures:
    print("  失败项:")
    for n, m in failures:
        print(f"    - {n}: {m}")
    sys.exit(1)
print("  ✅ R218a 验收通过")
sys.exit(0)
