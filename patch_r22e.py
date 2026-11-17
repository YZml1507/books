# -*- coding: utf-8 -*-
import io, sys
JS="/opt/books/app/web/static/app.js"
with io.open(JS,"r",encoding="utf-8") as f: a=f.read()
def rep(tag,old,new,n=1):
    global a
    if a.count(old)!=n: sys.exit("FAIL[%s]: count=%d"%(tag,a.count(old)))
    if new in a: sys.exit("FAIL[%s]: 已打过"%tag)
    a=a.replace(old,new,n)
rep("ritual-label",
"""        _dr.textContent = _rdone ? '✅ 今日宜 · 已打卡' : '✅ 做完了';""",
"""        /* R22e（用户直报「已做完是什么意思，我都不知道要做什么」）：
         * 可点态也点名是「宜试试」那件事——原来只写「做完了」，
         * 人不晓得在给什么盖戳。 */
        _dr.textContent = _rdone ? '✅ 宜试试 · 已打卡' : '✅ 宜试试 · 打卡';""")
with io.open(JS,"w",encoding="utf-8") as f: f.write(a)
print("R22e OK")
