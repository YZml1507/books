# -*- coding: utf-8 -*-
import io, sys
CSS="/opt/books/app/web/static/styles.css"
with io.open(CSS,"r",encoding="utf-8") as f: c=f.read()
OLD="""/* R3358：轻账号（昵称+口令码，不要邮箱/手机）——注册/登录后"""
if c.count(OLD)!=1: sys.exit("FAIL count=%d"%c.count(OLD))
if ".acct-empty" in c: sys.exit("FAIL 已打过")
NEW="""/* R24（用户要求）：账号/个人信息独立成 #view-account 后，未登录态
   的空态提示——别让用户点进一个空白视图。 */
.acct-empty{ margin:14px 2px 2px; padding:14px 16px; font-size:13px;
  line-height:1.7; color:var(--secondary); background:var(--card);
  border:1px dashed var(--border); border-radius:14px; text-align:center; }
""" + OLD
with io.open(CSS,"w",encoding="utf-8") as f: f.write(c.replace(OLD,NEW,1))
print("css OK")
