# R2357（R113-P0-2）：部署载体——把启动命令钉进仓库。
# 构建期生成 corpus.db（~10s），运行期零额外构建。
#
# 公网部署务必按「数据姿态」二选一并写进平台 env：
#   BOOKS_PAIPAN_HISTORY_DISABLE=1  排盘台账（生辰自动记盘）整体关闭——
#                                   多访客公开站必须开，否则生日互见互删
#   BOOKS_WRITE_DISABLE=1           共享 knowledge.db 写面整体拒绝
#                                   （prefs/favorites/threads/import/delete）
#   BOOKS_EXTERNAL_DISABLE=1        关掉 RSS 外呼面（无代理环境必开）
#   BOOKS_ALLOWED_HOSTS=your.domain TrustedHost 白名单（有正式域名后开）
#   BOOKS_CORS_ORIGINS=https://…    分体部署（落地页+API 分离）时开
# 平台健康检查路径必须配 /api/health——闸下 / 恒 403，配错即永久
# unhealthy（R2400 R137 实测提醒）。
# 与 CI/.python-version 同钉——漂移过一次就不测第二次
# （注意：Docker 不允许指令行尾挂 # 注释——行内注释只认行首）
FROM python:3.10-slim
WORKDIR /app
ENV PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple \
    PIP_EXTRA_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple https://mirrors.bfsu.edu.cn/pypi/web/simple" \
    PIP_FIND_LINKS=https://mirrors.aliyun.com/pytorch-wheels/cpu/
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt
COPY . .
RUN python scripts/check_quality.py && python scripts/build_index.py
EXPOSE 7860
# 默认 7860 = HF Spaces app_port 缺省值；Railway/Render/Fly 注入 PORT 即用其值。
# R2400（R137-P2-3）：sh -c 下 dash 不 exec → uvicorn 是子进程收不到
# SIGTERM，容器停机等 kill 超时。exec 让 uvicorn 顶 PID1 优雅停机。
CMD ["sh", "-c", "exec uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips '*' --no-access-log --workers 1"]
