# -*- coding: utf-8 -*-
import io, sys
JS="/opt/books/app/web/static/app.js"
with io.open(JS,"r",encoding="utf-8") as f: a=f.read()
def rep(tag,old,new,n=1):
    global a
    c=a.count(old)
    if c!=n: sys.exit("FAIL[%s]: count=%d"%(tag,c))
    if new in a: sys.exit("FAIL[%s]: 已打过"%tag)
    a=a.replace(old,new,n)
# _bindGender 移到 if(c) 之前——注册时（未登录）也得能点
rep("bind-move",
"""      function _acctRender() {
        var c = _creds();
        if (c) {""",
"""      function _acctRender() {
        /* R22c：性别钮无条件绑——此前只挂在「已登录」分支里，注册时
         * （未登录）点「男生」没有监听器，_acctGender() 恒回 'f'，
         * 男生也被分到女生头像池。 */
        _bindGender();
        var c = _creds();
        if (c) {""")
rep("bind-drop",
"""          _who.textContent = c.n;
          _bindGender();
          _acctFace();""",
"""          _who.textContent = c.n;
          _acctFace();""")
with io.open(JS,"w",encoding="utf-8") as f: f.write(a)
print("R22c OK")
