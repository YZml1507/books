# -*- coding: utf-8 -*-
import io, sys
HTML="/opt/books/app/web/static/index.html"
JS="/opt/books/app/web/static/app.js"
with io.open(HTML,"r",encoding="utf-8") as f: h=f.read()
O1 = """        <!-- R3414：排盘历史小锁——同设备他人借用时防窥。可选功能：
             不设锁一切照旧；设了锁进历史页要输口令码才看（口令哈希
             存本机，本标签页解锁一次即可）。跟账号体系无关——不登录
             也能锁。 -->
        <button id="historyLockBtn" type="button" class="ghost">🔒 加个锁</button>
"""
if h.count(O1)!=1: sys.exit("FAIL O1=%d"%h.count(O1))
h=h.replace(O1, """        <!-- R26（用户裁决「排盘历史里面的加个锁其实是不需要的」）：
             锁钮已撤。历史改按登录账户归属（见 D-931），账号本身就是
             边界——同一个账户名下只看自己的记录，不需要再加一道本机锁。 -->
""", 1)
O2 = """      <!-- R3414：锁态面板——设锁/开锁/撤锁三态共用（JS 切文案）。
           锁着时整个历史区只露这个面板。 -->
      <div id="historyLockPanel" class="ph-lock" hidden>
        <div class="ph-lock-title" id="historyLockTitle">🔒 排盘历史上了锁</div>
        <input id="historyLockInput" type="password" inputmode="numeric"
               maxlength="6" autocomplete="off" placeholder="输入 6 位口令码">
        <button id="historyLockGo" type="button" class="ghost">开锁</button>
        <div class="ph-lock-tip" id="historyLockTip">口令码只存在这台设备上，忘了可以「忘掉我的数据」重设。</div>
      </div>
"""
if h.count(O2)!=1: sys.exit("FAIL O2=%d"%h.count(O2))
h=h.replace(O2,"",1)
with io.open(HTML,"w",encoding="utf-8") as f: f.write(h); print("html OK")

with io.open(JS,"r",encoding="utf-8") as f: a=f.read()
# 一次性清理：历史遗留的 histLock 会让老用户卡在锁面板（钮已撤，没法再设/撤）
O3 = """  function _phLocked() {"""
N3 = """  /* R26（用户裁决撤锁）：锁钮与锁面板已从 DOM 撤掉，但老用户本机
   * 可能还留着 histLock——不清理的话他们会卡在锁面板且再也找不到入口。
   * 这里做一次性清理，清完 _phLocked() 恒 false，后面整套锁逻辑自然空转。 */
  try { localStorage.removeItem('histLock'); } catch (eL) {}
  try { sessionStorage.removeItem('histUnlocked'); } catch (eU) {}
  function _phLocked() {"""
if a.count(O3)!=1: sys.exit("FAIL O3=%d"%a.count(O3))
a=a.replace(O3,N3,1)
with io.open(JS,"w",encoding="utf-8") as f: f.write(a); print("app.js OK")
