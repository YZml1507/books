# -*- coding: utf-8 -*-
import io, sys
CSS="/opt/books/app/web/static/styles.css"
with io.open(CSS,"r",encoding="utf-8") as f: c=f.read()
OLD = """.daily-acct:hover{background:var(--accent-soft); border-color:var(--accent-ink);}
.daily-acct.is-on{color:var(--primary-ink);}"""
NEW = """.daily-acct:hover{background:var(--accent-soft); border-color:var(--accent-ink);}
.daily-acct.is-on{color:var(--primary-ink);}
/* R26（用户原话「右上角用户名旁边为什么加个锁而不是加一个头像」）：
   头像替代 🔓 开锁表情——用户名旁边该是一张脸。 */
.daily-acct{display:inline-flex; align-items:center; gap:7px;}
.daily-acct-face{width:26px; height:26px; border-radius:50%; object-fit:cover;
  flex:0 0 auto; border:1.5px solid var(--border);
  box-shadow:0 2px 8px rgba(184,134,11,.18);}
.daily-acct-name{font-weight:600;}"""
if c.count(OLD)!=1: sys.exit("FAIL count=%d"%c.count(OLD))
if "用户名旁边该是一张脸" in c: sys.exit("FAIL 已打过")
c=c.replace(OLD,NEW,1)
with io.open(CSS,"w",encoding="utf-8") as f: f.write(c)
print("css OK")
