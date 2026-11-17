#!/usr/bin/env python3
"""R4（StepFun Studio 自主优化·周期一）门页错误态好奇熊 + 壳内门浮层同款化。

服务器权威版原位补丁（本地 66a2456 与服务器 7e14bef 不同线，
严禁本地改动后整文件覆盖——版本漂移事故教训）。三处精确替换：
  1) app.py _GATE_HINT：错匙提示上方挂好奇熊（72px，与红字同级）。
  2) app.js 壳内门浮层：🌾 → gate-bear.jpg（R1 只换了服务端门页，
     R4921 浮层还挂 emoji，两边不同款——恢复同款同口径）。
  3) app.js _gateErr：错误时显示 #gateCurious 好奇熊。
锚点缺失即 AssertionError 退出，绝不静默跳过。
"""
import io, sys

APP_PY = "web/app.py"
APP_JS = "web/static/app.js"


def patch(path, pairs):
    with io.open(path, encoding="utf-8") as f:
        src = f.read()
    for old, new in pairs:
        assert src.count(old) == 1, f"{path}: 锚点命中 {src.count(old)} 次（应 1 次）: {old[:60]!r}"
        src = src.replace(old, new)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"OK {path} ({len(pairs)} 处)")


# 1) app.py：错匙提示 = 好奇熊 + 红字（原纯红字）
patch(APP_PY, [(
    '''    _GATE_HINT = ("<p style='color:#c0504a;font-size:13px;margin:10px 0 0'>"
                  "钥匙不对——再想想？</p>")''',
    '''    # R4（StepFun 自主优化）：错匙提示上方挂好奇熊——门页是第一面，
    # 敲错口令的用户看到一只歪头执钥匙的软熊比一行红字贴「解忧」定位。
    _GATE_HINT = ("<img src='/static/cream/gate-curious.jpg' alt='' width=72 "
                  "height=72 style='display:block;margin:12px auto 0;"
                  "border-radius:16px;box-shadow:0 3px 10px "
                  "rgba(120,80,40,.12)'>"
                  "<p style='color:#c0504a;font-size:13px;margin:8px 0 0'>"
                  "钥匙不对——再想想？</p>")''',
)])

# 2) app.js：壳内门浮层同款化 + 3) 错误态好奇熊
patch(APP_JS, [
    # 注释同步真实面貌（原写 🌾）
    (
        " * 口径（白卡+🌾+口令框+开门钮+错匙/限速提示）。只在 401 时挂：",
        " * 口径（白卡+门熊+口令框+开门钮+错匙/限速提示+好奇熊）。只在 401 时挂：",
    ),
    # 🌾 → 门熊（R1 服务端门页同款：120px 适配浮层窄卡）
    (
        '''    + '<div style="font-size:34px">🌾</div>'
''',
        '''    + '<img src="/static/cream/gate-bear.jpg" alt="小满" width=120 '
    + 'height=120 style="display:block;margin:0 auto 6px;border-radius:20px;'
    + 'box-shadow:0 4px 14px rgba(120,80,40,.14)">'
''',
    ),
    # 提示区尾部挂好奇熊（默认隐藏）
    (
        '''    + '<p id="gateHint" style="color:#c0504a;font-size:13px;margin:10px 0 0;'
    + 'display:none"></p></div>';''',
        '''    + '<p id="gateHint" style="color:#c0504a;font-size:13px;margin:10px 0 0;'
    + 'display:none"></p>'
    + '<img id="gateCurious" src="/static/cream/gate-curious.jpg" alt="" '
    + 'width=72 height=72 loading="lazy" decoding="async" '
    + 'style="display:none;width:72px;height:72px;margin:12px auto 0;'
    + 'border-radius:16px;box-shadow:0 3px 10px rgba(120,80,40,.12)"></div>';''',
    ),
    # 错误即亮熊
    (
        """  function _gateErr(t) {
    _hint.textContent = t;
    _hint.style.display = 'block';
  }""",
        """  function _gateErr(t) {
    _hint.textContent = t;
    _hint.style.display = 'block';
    var _cu = document.getElementById('gateCurious');   /* R4：错误态亮好奇熊 */
    if (_cu) _cu.style.display = 'block';
  }""",
    ),
])
print("R4 补丁完成")
