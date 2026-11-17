import io, sys
APP = "/opt/books/app/web/static/app.js"
OLD = """        _status.textContent = _issue ? _issue
          : (_backend === 'libsql'
            ? '云端已接' : (_backend === 'local'
              ? '云端没接通——备份留不住，换设备拉不回' : '查一下云端…'));"""
NEW = """        /* R21（用户直报）：原文案「云端没接通——备份留不住，换设备拉不回」
         * 对本机库是错的——本机库就在服务器上，实测换一台全新浏览器登录
         * 能把生辰原样拉回（records 带 me$）。改成说实话，并点明唯一的
         * 真实风险（服务器清盘），不夸大也不隐瞒。 */
        _status.textContent = _issue ? _issue
          : (_backend === 'libsql'
            ? '云端已接' : (_backend === 'local'
              ? '账号存在服务器本机库——换设备登录能拉回生辰和数据；只有服务器清盘才会没'
              : '查一下云端…'));"""
with io.open(APP, "r", encoding="utf-8") as f:
    a = f.read()
if a.count(OLD) != 1:
    sys.exit("FAIL: anchor count=%d" % a.count(OLD))
if "原文案「云端没接通" in a:
    sys.exit("FAIL: 已打过")
a = a.replace(OLD, NEW, 1)
with io.open(APP, "w", encoding="utf-8") as f:
    f.write(a)
print("app.js: 后端状态文案改实话")
