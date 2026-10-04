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
# R3316（审-P2）：PyPI 源按构建区切换——海外平台（Render/HF/GH runner）
# 拉国内镜像超时（CI 490444b 同款教训），缺省走官方源；境内本机
# build 想提速再 `--build-arg PIP_CN_MIRROR=1`。torch find-links
# 一并去——requirements-runtime 根本没有 torch 依赖，死配置。
ARG PIP_CN_MIRROR=0
ENV PIP_INDEX_URL=https://pypi.org/simple
COPY requirements-runtime.txt .
RUN if [ "$PIP_CN_MIRROR" = "1" ]; then \
      export PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple \
        PIP_EXTRA_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple"; \
    fi && \
    pip install --no-cache-dir -r requirements-runtime.txt
COPY . .
RUN python scripts/check_quality.py && python scripts/build_index.py
EXPOSE 7860
# 默认 7860 = HF Spaces app_port 缺省值；Railway/Render/Fly 注入 PORT 即用其值。
# R2400（R137-P2-3）：sh -c 下 dash 不 exec → uvicorn 是子进程收不到
# SIGTERM，容器停机等 kill 超时。exec 让 uvicorn 顶 PID1 优雅停机。
# R3341（审-低）：容器级健康检查——/api/health 免闸。平台自配探活
# 的会覆盖本条；本地 docker run 也能 docker ps 看 healthy 态。
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
  CMD ["sh", "-c", "exec python -c \"import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','7860')+'/api/health',timeout=4)\""]
CMD ["sh", "-c", "exec uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips '*' --no-access-log --workers 1"]
