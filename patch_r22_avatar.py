# -*- coding: utf-8 -*-
import io, sys
IDX="/opt/books/app/web/static/index.html"
CSS="/opt/books/app/web/static/styles.css"
JS ="/opt/books/app/web/static/app.js"
def rd(p):
    with io.open(p,"r",encoding="utf-8") as f: return f.read()
def wr(p,s):
    with io.open(p,"w",encoding="utf-8") as f: f.write(s)
def rep(tag, s, old, new, n=1):
    c = s.count(old)
    if c != n: sys.exit("FAIL[%s]: anchor count=%d (预期 %d)" % (tag, c, n))
    if new in s: sys.exit("FAIL[%s]: 已打过" % tag)
    return s.replace(old, new, n)

# ---------- 1. index.html：注册表单加「性别」 ----------
idx = rd(IDX)
G_OLD = """            <button id="acctRegister" type="button" class="ghost">注册</button>"""
G_NEW = """            <div class="acct-gender">
              <span class="acct-birth-lab">你是</span>
              <div class="acct-gender-row" role="group" aria-label="性别">
                <button type="button" class="acct-gender-btn is-on" id="acctGF" data-g="f" aria-pressed="true">女生</button>
                <button type="button" class="acct-gender-btn" id="acctGM" data-g="m" aria-pressed="false">男生</button>
              </div>
              <span class="acct-gender-note">小满会按这个给你分一张头像，随机不重样</span>
            </div>
            <button id="acctRegister" type="button" class="ghost">注册</button>"""
idx = rep("idx-gender", idx, G_OLD, G_NEW)

# ---------- 2. index.html：登录页那句「忘了就是没了」改口 ----------
T_OLD = """<div class="acct-tip">口令码没有找回渠道，忘了就是没了——记个牢的。注册即同步一份备份到云端。</div>"""
T_NEW = """<div class="acct-tip">口令码记个牢的就好。注册即同步一份备份到云端——换设备登录同名账号，生辰和数据都给你拉回来。</div>"""
idx = rep("idx-tip", idx, T_OLD, T_NEW)
wr(IDX, idx)

# ---------- 3. styles.css ----------
css = rd(CSS)
C_OLD = """.ck-quest-btn{font-size:12px; padding:3px 12px; border-radius:999px;
  border:1px solid var(--accent-ink); background:transparent;
  color:var(--accent-ink); cursor:pointer; min-height:var(--tap);}
.ck-quest-btn:active{background:var(--accent-ink); color:#fff;}"""
C_NEW = """.ck-quest-btn{font-size:12px; padding:3px 12px; border-radius:999px;
  border:1px dashed var(--border); background:var(--card);
  color:var(--accent-ink); cursor:pointer; min-height:var(--tap);
  transition:background .16s ease, border-color .16s ease;}
.ck-quest-btn:hover{background:var(--accent-soft); border-color:var(--accent-ink);}
.ck-quest-btn:active{background:var(--accent-soft); color:var(--accent-ink);}"""
css = rep("css-questbtn", css, C_OLD, C_NEW)
# dday-set 与 quest-btn 同族柔化
D_OLD = """.ck-quest{display:flex; align-items:center; gap:8px; flex-wrap:wrap;
  font-size:12px; color:var(--muted); margin:6px 0 2px;
  padding:6px 10px; border-radius:10px;
  background:var(--accent-soft); border:1px dashed var(--border);}"""
D_NEW = D_OLD + """
/* R22（用户直报「定一个 → 很突兀」）：与 ck-quest-btn 同族柔化——
原 2px 实线深色描边在奶油底上太硬，改虚线软框 + 悬停柔光。 */
.ck-dday .dday-set{font-size:12px; padding:3px 12px; border-radius:999px;
  border:1px dashed var(--border); background:var(--card);
  color:var(--accent-ink); cursor:pointer; min-height:var(--tap);
  transition:background .16s ease, border-color .16s ease;}
.ck-dday .dday-set:hover{background:var(--accent-soft);
  border-color:var(--accent-ink);}
/* R22：账号头像（注册按性别随机分一张，随备份走） */
.acct-face{width:44px; height:44px; border-radius:50%; object-fit:cover;
  vertical-align:middle; margin-right:8px; background:var(--accent-soft);
  border:1px solid var(--border); flex:0 0 auto;}
.acct-who-row{display:flex; align-items:center; gap:2px; min-width:0;}
.acct-who-row .acct-who{overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap;}
/* R22：性别二选一——软分段，不用 radio 的硬点 */
.acct-gender{margin:2px 0 8px;}
.acct-gender-row{display:flex; gap:8px; margin-top:5px;}
.acct-gender-btn{flex:1; font-size:13px; padding:8px 0; border-radius:12px;
  border:1px dashed var(--border); background:var(--card);
  color:var(--muted); cursor:pointer; min-height:var(--tap);
  transition:background .16s ease, border-color .16s ease, color .16s ease;}
.acct-gender-btn.is-on{border-style:solid; border-color:var(--accent-ink);
  background:var(--accent-soft); color:var(--accent-ink); font-weight:600;}
.acct-gender-note{display:block; font-size:11px; color:var(--muted);
  margin-top:5px; line-height:1.5;}"""
css = rep("css-dday", css, D_OLD, D_NEW)
wr(CSS, css)
print("index.html + styles.css OK")
