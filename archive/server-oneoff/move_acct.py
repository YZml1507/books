import io, sys
IDX = "/opt/books/app/web/static/index.html"
APP = "/opt/books/app/web/static/app.js"
with io.open(IDX, "r", encoding="utf-8") as f: s = f.read()
# 1) 从 .daily-top 摘出
BTN = """      <button type="button" class="daily-acct" id="dailyAcct"
              title="登录 / 注册——填好生辰，礼物直接拆">🔐 账号</button>
"""
if s.count(BTN) != 1:
    sys.exit("FAIL: daily-top 里的钮 count=%d" % s.count(BTN))
s = s.replace(BTN, "", 1)
# 2) 挂到品牌行（在日卡之外：封面遮不到、inert 管不到）
OLD_B = """      <div class="brand-tagline">今天也要好好生活呀 ✨</div>
    </div>
  </div>"""
NEW_B = """      <div class="brand-tagline">今天也要好好生活呀 ✨</div>
    </div>
    <!-- R20（用户直报）：账号入口前置到品牌行——原先只埋在「排盘历史」
         视图里。放在日卡之外是硬要求：日卡封面没拆时整张卡被 inert +
         封面层物理遮挡，放里面新用户反而点不到（实测 click 报
         "element is inert" / "intercepts pointer events"）。 -->
    <button type="button" class="daily-acct" id="dailyAcct"
            title="登录 / 注册——填好生辰，礼物直接拆">🔐 账号</button>
  </div>"""
if s.count(OLD_B) != 1:
    sys.exit("FAIL: brand anchor count=%d" % s.count(OLD_B))
s = s.replace(OLD_B, NEW_B, 1)
with io.open(IDX, "w", encoding="utf-8") as f: f.write(s)
print("index.html: 钮已移到品牌行")

with io.open(APP, "r", encoding="utf-8") as f: a = f.read()
# 3) 回 inert 豁免（钮已不在卡内，豁免成了死代码）
EX = """        if (c !== _cov && !c.hasAttribute('inert') &&
            !(c.classList && c.classList.contains('daily-top')))
          c.setAttribute('inert', '');"""
if a.count(EX) != 1:
    sys.exit("FAIL: inert 豁免 count=%d" % a.count(EX))
a = a.replace(EX, """        if (c !== _cov && !c.hasAttribute('inert')) c.setAttribute('inert', '');""", 1)
with io.open(APP, "w", encoding="utf-8") as f: f.write(a)
print("app.js: inert 豁免已回退（死代码清理）")
