import io, re
html = io.open("web/static/index.html", encoding="utf-8").read()
sw = io.open("web/static/sw.js", encoding="utf-8").read()
vers = sorted(set(re.findall(r"/static/[\w./-]+\?v=([\w]+)", html)))
print("index.html ?v= 取值:", vers[:6])
print("sw.js CACHE 名:", re.findall(r"books-shell-[\w]+", sw)[:2])
print("sw.js 预缓存 styles.css:", re.findall(r"/static/styles\.css[^\"'\s]*", sw)[:2])
print("index.html styles.css link:", re.findall(r'href="(/static/styles\.css[^"]*)"', html)[:2])
mism = [v for v in vers if v not in sw]
print("index 有而 sw 没有的版本串:", mism if mism else "无（一致）")
