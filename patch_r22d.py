# -*- coding: utf-8 -*-
import io, sys
JS="/opt/books/app/web/static/app.js"; CSS="/opt/books/app/web/static/styles.css"
with io.open(JS,"r",encoding="utf-8") as f: a=f.read()
with io.open(CSS,"r",encoding="utf-8") as f: c=f.read()
def rep(s,tag,old,new,n=1):
    if s.count(old)!=n: sys.exit("FAIL[%s]: count=%d"%(tag,s.count(old)))
    if new in s: sys.exit("FAIL[%s]: 已打过"%tag)
    return s.replace(old,new,n)
# app.js：日卡档案行带头像
a=rep(a,"me-face",
"""  box.innerHTML = '<span class="daily-me-txt">' + esc(txt) + '</span>' +
    '<button type="button" class="daily-me-edit">改</button>';""",
"""  /* R22d：档案行带头像——me.av 随备份走，日常视图也看得见 */
  var _av = me.av ? String(me.av).replace(/[^a-z0-9.\\-_]/gi, '') : '';
  box.innerHTML = (_av ? '<img class="daily-me-face" src="/static/avatars/' +
      _av + '" alt="">' : '') +
    '<span class="daily-me-txt">' + esc(txt) + '</span>' +
    '<button type="button" class="daily-me-edit">改</button>';""")
# styles.css：头像样式
c=rep(c,"css-face",
""".acct-who-row .acct-who{overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap;}""",
""".acct-who-row .acct-who{overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap;}
/* R22d：日卡档案行头像 */
.daily-me-face{width:26px; height:26px; border-radius:50%; object-fit:cover;
  flex:0 0 auto; vertical-align:middle; margin-right:2px;
  background:var(--accent-soft); border:1px solid var(--border);}
.daily-me{align-items:center;}
.daily-me .daily-me-face{flex:0 0 auto;}""")
with io.open(JS,"w",encoding="utf-8") as f: f.write(a)
with io.open(CSS,"w",encoding="utf-8") as f: f.write(c)
print("R22d OK")
