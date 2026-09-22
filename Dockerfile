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
FROM python:3.10-slim   # 与 CI/.python-version 同钉——漂移过一次就不测第二次
WORKDIR /app
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt
COPY . .
RUN python scripts/check_quality.py && python scripts/build_index.py
EXPOSE 7860
# 默认 7860 = HF Spaces app_port 缺省值；Railway/Render/Fly 注入 PORT 即用其值。
CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips '*' --no-access-log --workers 1"]
