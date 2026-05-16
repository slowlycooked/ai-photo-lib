# AI Photo Library — Synology NAS 部署指南

> 目标平台：Synology DS916+（Pentium N3710，CPU only）  
> 镜像在开发机构建，打包后传到 NAS 运行。

---

## 前置条件

- 开发机已安装 Docker（含 `buildx`）
- 群晖已安装 Docker 套件并开启 SSH
- 已下载模型文件：
  - `MiniCPM-V-4_6-Q4_K_M.gguf`
  - `mmproj-model-f16.gguf`

---

## Step 1 — 在开发机构建所有镜像

在项目根目录依次执行。

### 1.1 API 镜像

```bash
docker buildx build \
  --builder desktop-linux \
  --platform linux/amd64 \
  -f apps/api/Dockerfile \
  -t ai-photo-lib-api:ds916 \
  --load \
  apps/api
```

### 1.2 Web 镜像

```bash
docker buildx build \
  --builder desktop-linux \
  --platform linux/amd64 \
  -f apps/web/Dockerfile \
  -t ai-photo-lib-web:ds916 \
  --load \
  apps/web
```

### 1.3 Worker 镜像

> build context 必须是项目根目录（`.`），Dockerfile 里需要同时复制 `apps/api/` 和 `apps/worker/`。

```bash
docker buildx build \
  --builder desktop-linux \
  --platform linux/amd64 \
  -f apps/worker/Dockerfile \
  -t ai-photo-lib-worker:ds916 \
  --load \
  .
```

### 1.4 llama-server 镜像

> 编译 llama.cpp，耗时约 10–20 分钟。

```bash
docker buildx build \
  --builder desktop-linux \
  --platform linux/amd64 \
  -f Dockerfile.llama \
  -t ai-photo-lib-llama:ds916-cpu \
  --load \
  .
```

---

## Step 2 — 导出镜像

```bash
docker save \
  ai-photo-lib-api:ds916 \
  ai-photo-lib-web:ds916 \
  ai-photo-lib-worker:ds916 \
  ai-photo-lib-llama:ds916-cpu \
  -o ai-photo-lib-ds916-images.tar

gzip ai-photo-lib-ds916-images.tar
```

---

## Step 3 — 在群晖创建目录和配置

SSH 到群晖（替换实际 IP）：

```bash
ssh admin@192.168.1.50
```

创建目录结构：

```bash
mkdir -p /volume1/docker/ai-photo-lib/models
mkdir -p /volume1/docker/ai-photo-lib/postgres
mkdir -p /volume1/docker/ai-photo-lib/redis
mkdir -p /volume1/docker/ai-photo-lib/thumbs
```

创建 `.env` 文件（`/volume1/docker/ai-photo-lib/.env`）：

```env
PHOTO_LIBRARY_PATH=/volume1/photo
DATA_DIR=/volume1/docker/ai-photo-lib
MODEL_DIR=/volume1/docker/ai-photo-lib/models

POSTGRES_PASSWORD=请换成强密码

POSTGRES_HOST_PORT=15432
REDIS_HOST_PORT=16379
WEB_PORT=18088

OPENAI_API_KEY=sk-local
OPENAI_MODEL=MiniCPM-V-4.6
OPENAI_VISION_MODEL=MiniCPM-V-4.6

LLAMA_HOST_PORT=18082
LLAMA_CTX=2048
LLAMA_THREADS=4

THUMBNAIL_SIZE=512
AI_WORKER_CONCURRENCY=1
AI_MAX_RETRIES=3
```

> 从 `LLAMA_CTX=2048` 起步；稳定后可改为 `4096`。

---

## Step 4 — 上传文件到群晖

在开发机上执行（替换实际 IP）：

```bash
NAS=admin@192.168.1.50
DEST=/volume1/docker/ai-photo-lib

scp ai-photo-lib-ds916-images.tar.gz  $NAS:$DEST/
scp docker-compose.yml                $NAS:$DEST/docker-compose.yml
```

同时上传模型文件（首次部署）：

```bash
scp MiniCPM-V-4_6-Q4_K_M.gguf  $NAS:$DEST/models/
scp mmproj-model-f16.gguf        $NAS:$DEST/models/
```

---

## Step 5 — 在群晖导入镜像并启动

SSH 到群晖，进入部署目录：

```bash
cd /volume1/docker/ai-photo-lib
```

导入镜像：

```bash
gunzip ai-photo-lib-ds916-images.tar.gz
docker load -i ai-photo-lib-ds916-images.tar
```

确认镜像已就绪：

```bash
docker images | grep ai-photo-lib
```

启动所有服务：

```bash
docker compose up -d
```

---

## Step 6 — 初始化数据库

等待 `postgres` 健康检查通过（约 10 秒）后执行：

```bash
docker exec ai-photo-lib-api alembic upgrade head
```

> 后续版本升级时同样执行此命令。

---

## Step 7 — 验证

### 检查服务状态

```bash
docker compose ps
```

所有服务应为 `running`，`ai-photo-lib-llama` 在加载模型期间（约 1–2 分钟）可能显示 `starting`，属正常现象。

### 验证 llama-server

```bash
curl http://127.0.0.1:18082/v1/models
```

### 验证 API

```bash
curl http://127.0.0.1:8000/health
```

### 打开 Web UI

浏览器访问 `http://192.168.1.50:18088`

---

## 日常运维

查看日志：

```bash
docker logs -f ai-photo-lib-llama
docker logs -f ai-photo-lib-api
docker logs -f ai-photo-lib-worker
```

重启单个服务：

```bash
docker compose restart worker
```

停止所有服务：

```bash
docker compose down
```

---

## 版本升级流程

1. 在开发机重新构建受影响的镜像（Step 1）
2. 导出镜像（Step 2）
3. 上传到群晖（Step 4，只传镜像，不需要重传模型）
4. 在群晖停止服务、导入新镜像、启动：

```bash
cd /volume1/docker/ai-photo-lib
docker compose down
docker load -i ai-photo-lib-ds916-images.tar
docker compose up -d
docker exec ai-photo-lib-api alembic upgrade head
```

---

## 架构说明

```text
浏览器  →  web (nginx:80)  →  api (uvicorn:8000)  →  postgres
                                                    →  redis
worker  →  llama (llama-server:8082)
         ←  postgres (轮询 ai_jobs)
```

**AI 图片传递路径**（`worker` → `llama`）：
- worker 生成 `file://subdir/photo.jpg`（相对路径）
- llama-server 用 `--media-path /photos` 解析为 `/photos/subdir/photo.jpg`
- 两个容器都挂载同一个宿主机目录到 `/photos`

---

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| worker 报 `ModuleNotFoundError: No module named 'app'` | 容器内 API 路径不对 | 确认 `apps/worker/Dockerfile` 的 WORKDIR 是 `/app/apps/worker` 并重新构建 |
| api 容器启动后立即退出 | `apps/api/Dockerfile` CMD 不正确 | 确认 CMD 是 `uvicorn app.main:app ...` 并重新构建 |
| llama 容器 `Illegal instruction` | 编译时开了 native 优化 | 确认 `Dockerfile.llama` 中是 `-DGGML_NATIVE=OFF` |
| llama healthcheck 长时间 `starting` | 模型加载慢，属正常 | 等待，可跟 `docker logs -f ai-photo-lib-llama` |
| worker 无法连接 llama | `OPENAI_BASE_URL` 错误 | 群晖用 `http://llama:8082/v1`（由 compose 文件设置，勿改 .env）|
| web 显示 API 错误 | API 或 DB 未就绪 | `docker compose ps` 确认所有服务 healthy，执行 Step 6 迁移 |
