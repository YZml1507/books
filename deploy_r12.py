import io, sys, os, subprocess

SRV = "root@116.205.229.222"
APP = "/opt/books/app"
FONT = "/workspace/downloads/r12-font/lxgwwenkai-home.woff2"
BLOCK = io.open("/workspace/downloads/r12-font/r12_fontface.css", encoding="utf-8").read()

def ssh(cmd):
    r = subprocess.run(["ssh", "-i", os.path.expanduser("~/.ssh/id_ed25519"),
                        "-o", "ConnectTimeout=15", SRV, cmd],
                       capture_output=True)
    if r.returncode != 0:
        print("SSH FAIL:", r.stderr.decode("utf-8","replace")[:500]); sys.exit(1)
    return r.stdout.decode("utf-8", "replace")

# 1. 上传字体
r = subprocess.run(["scp", "-i", os.path.expanduser("~/.ssh/id_ed25519"), "-o", "ConnectTimeout=15",
                    FONT, "%s:%s/web/static/fonts/lxgw/lxgwwenkai-home.woff2" % (SRV, APP)],
                   capture_output=True)
if r.returncode != 0:
    print("SCP FAIL:", r.stderr.decode("utf-8","replace")[:500]); sys.exit(1)
print("1. 字体已上传")

# 2. 备份 + 追加 @font-face 到 lxgw.css 末尾
css_path = "%s/web/static/fonts/lxgw.css" % APP
before = ssh("wc -c %s && md5sum %s" % (css_path, css_path)).strip()
print("2. 当前 lxgw.css:", before)
ssh("cp %s %s.bak-r12" % (css_path, css_path))
# 用 python 在服务器上精确追加（幂等：已有 R12 标记则跳过）
check = ssh("grep -c 'R12 首页 curated 字体' %s || true" % css_path).strip()
print("   R12 标记出现次数:", check)
if check == "0":
    io.open("/tmp/r12_block.css", "w", encoding="utf-8").write("\n" + BLOCK)
    subprocess.run(["scp", "-i", os.path.expanduser("~/.ssh/id_ed25519"), "-o", "ConnectTimeout=15",
                    "/tmp/r12_block.css", "%s:/tmp/r12_block.css" % SRV], check=True)
    ssh("cat /tmp/r12_block.css >> %s && rm /tmp/r12_block.css" % css_path)
    print("   已追加")
else:
    print("   已存在，跳过追加")

# 3. 校验
after = ssh("tail -c 400 %s && echo '---' && wc -c %s" % (css_path, css_path)).strip()
print("3. 追加后 lxgw.css 尾部:\n", after[-300:])
# 语法自检：face 数应从 50 变 51，括号配平
n = ssh("grep -c '@font-face' %s" % css_path).strip()
print("   @font-face 总数:", n)
