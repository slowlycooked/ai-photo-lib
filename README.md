# AI Photo Library

私有化本地 AI 照片库，运行于群晖 NAS / Docker 环境。所有 AI 分析均在本地完成，照片不会上传至任何外部服务。

## 功能（当前实现状态，v0.4）

**照片管理**
- 扫描本地照片目录（jpg / jpeg / png / webp / heic）
- 自动生成 WebP 缩略图（长边 512px）
- 读取 EXIF 元数据（拍摄时间、相机型号等）
- 照片时间线（按年月分组）
- 无限滚动分页

**AI 打标签**
- Worker 轮询 PostgreSQL `ai_jobs` 表，调用 llama-server `/v1/chat/completions`
- 解析 JSON 结果，入库：内容描述、场景标签、物体标签、OCR 文字、中文关键词
- 失败任务支持重试（可配置最大重试次数）

**智能搜索**
- 中文关键词搜索（PostgreSQL ILIKE + 标签数组 + 内容评分）

**多页面 UI**
- `/photos` — 照片时间线
- `/search` — 关键词搜索
- `/tags` — 标签浏览（分类展示，点击跳搜索）
- `/tasks` — 任务中心（扫描 + AI 状态 + 失败任务重试）
- `/settings` — 设置页（只读显示环境配置）

## 技术栈

| 模块 | 技术 |
|------|------|
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| Backend | FastAPI + Python 3.11 |
| Database | PostgreSQL 16 + pgvector（v0.3 起用向量搜索） |
| Queue | Redis（v0.2 起用于 Worker 任务队列） |
| Image | Pillow + exifread |
| AI Runtime | **llama-server（llama.cpp）**，提供 OpenAI 兼容 API（`/v1/chat/completions`） |
| Vision Model | MiniCPM-V 4.6（GGUF 量化版，约 2–3 GB） |
| Deployment | Docker Compose |

> **为什么选 llama-server 而非 Ollama？**
>
> llama-server（llama.cpp 内置 HTTP 服务）暴露标准 OpenAI 兼容 API，支持 `--media-path` 参数，
> 允许 Worker 直接用 `file://相对路径` 传图，无需 base64 编码，对本地大文件更高效。
> 同时资源占用比 Ollama 更轻，适合在 NAS 上常驻运行。

---

## AI 运行时配置（llama-server）

### 启动 llama-server

```bash
llama-server \
  --model /path/to/MiniCPM-V-4.6-Q4_K_M.gguf \
  --mmproj /path/to/mmproj.gguf \
  --port 8082 \
  --media-path /path/to/your/photos/ \
  --n-gpu-layers 99  # 有 GPU 时加速，无 GPU 时去掉此行
```

> `--media-path` 必须与 `PHOTO_LIBRARY_PATH` 指向同一目录，这样 Worker 发送的
> `file://subdir/photo.jpg` 才能被 llama-server 正确解析。

### 环境变量

在根目录 `.env` 中配置：

```env
# AI 模型接口（OpenAI 兼容，指向本地 llama-server）
OPENAI_API_KEY=sk-local
OPENAI_BASE_URL=http://127.0.0.1:8082/v1          # 本地开发
# OPENAI_BASE_URL=http://host.docker.internal:8082/v1  # Docker 内访问宿主机
OPENAI_MODEL=MiniCPM-V-4.6
OPENAI_VISION_MODEL=MiniCPM-V-4.6
```

---

## 本地开发启动

### 前置条件

- Python 3.11+（API 虚拟环境已在 `apps/api/.venv` 中创建）
- Node.js 20+
- Docker Desktop（用于运行 Postgres + Redis）

### 1. 配置环境变量

编辑根目录 `.env`，将 `PHOTO_LIBRARY_PATH` 改为你本地的照片目录：

```env
PHOTO_LIBRARY_PATH=/Users/yourname/Pictures
```

### 2. 一键启动全部服务

```bash
./scripts/svc.sh start
```

启动顺序：PostgreSQL → Redis → 数据库迁移（`alembic upgrade head`）→ API → Web Dev Server。

### 3. 常用操作命令

```bash
# 查看所有服务状态
./scripts/svc.sh status

# 停止所有服务
./scripts/svc.sh stop

# 重启单个服务（如修改了后端代码后）
./scripts/svc.sh restart api

# 实时查看日志
./scripts/svc.sh logs api
./scripts/svc.sh logs web

# 只启动 / 停止指定服务
./scripts/svc.sh start postgres redis
./scripts/svc.sh stop web
```

**可管理的服务名：** `postgres` `redis` `ai` `api` `worker` `web`

> `ai` 对应宿主机上的 llama-server；`worker` 轮询 `ai_jobs` 表并通过 `OPENAI_BASE_URL` 调用 `/v1/chat/completions`。

### 4. 服务地址

| 服务 | 地址 |
|------|------|
| Web UI | http://localhost:8088 |
| API 文档 | http://localhost:8000/docs |
| PostgreSQL | localhost:5433 |
| Redis | localhost:6380 |

> 端口可在根目录 `.env` 中修改（`POSTGRES_HOST_PORT` / `REDIS_HOST_PORT` / `WEB_PORT`）。

---

## 开发调试：清理数据

> ⚠️ 以下操作**不可恢复**，仅用于开发阶段重置测试数据。

```bash
# 重置数据库 + 清空 Redis（默认，有确认提示）
./scripts/reset-dev.sh

# 只重置数据库（alembic downgrade → upgrade）
./scripts/reset-dev.sh --db-only

# 只清空 Redis
./scripts/reset-dev.sh --redis-only

# 同时删除缩略图目录
./scripts/reset-dev.sh --thumbs

# 组合使用，跳过确认（适合脚本调用）
./scripts/reset-dev.sh --thumbs --yes
```

清理完成后重新扫描：

```bash
./scripts/svc.sh restart api
```

---

## Docker 完整部署（开发环境）

```bash
# 构建并启动所有服务
docker compose up --build

# 后台运行
docker compose up --build -d
```

打开：http://localhost:8088

---

## 群晖 NAS 部署步骤

### 1. 创建目录结构

在群晖 SSH 或 File Station 中创建：

```
/volume1/docker/ai-photo-lib/
/volume1/docker/ai-photo-lib/postgres/
/volume1/docker/ai-photo-lib/thumbs/
/volume1/docker/ai-photo-lib/redis/
```

### 2. 上传配置文件

将以下文件上传到群晖：
- `docker-compose.yml`
- `.env`（从 `.env.example` 复制修改）

`.env` 关键配置：

```env
PHOTO_LIBRARY_PATH=/volume1/photo
DATA_DIR=/volume1/docker/ai-photo-lib
POSTGRES_PASSWORD=your_secure_password
WEB_PORT=8088
```

### 3. 在 Container Manager 启动

进入 DSM → Container Manager → 项目 → 新增 → 选择 docker-compose.yml

或通过 SSH：

```bash
cd /volume1/docker/ai-photo-lib
docker compose up -d
```

### 4. 打开 Web UI

```
http://群晖IP:8088
```

---

## 目录挂载说明

| 宿主机路径 | 容器路径 | 权限 | 说明 |
|-----------|---------|------|------|
| `PHOTO_LIBRARY_PATH` | `/photos` | **只读** | 原始照片，应用不会修改 |
| `DATA_DIR/postgres` | `/var/lib/postgresql/data` | 读写 | 数据库文件 |
| `DATA_DIR/thumbs` | `/data/thumbs` | 读写 | 缩略图缓存 |
| `DATA_DIR/redis` | `/data` | 读写 | Redis 持久化 |

> ⚠️ 原始照片目录始终以只读方式挂载，系统不会修改、移动或删除你的照片。

---

## 常见问题

### 照片不显示？

1. 确认 `PHOTO_LIBRARY_PATH` 配置正确且目录存在
2. 检查 API 日志：`docker compose logs api`
3. 确认支持的格式：`.jpg` `.jpeg` `.png` `.webp` `.heic`

### 重新扫描照片

点击 UI 中的「重新扫描」按钮，或调用 API：

```bash
curl -X POST http://localhost:8000/scan/start
```

已存在且内容未变（hash 一致）的照片会自动跳过。

### 重置数据库 / Redis

```bash
# 开发环境专用清理脚本（保留 Docker volume，只清空数据）
./scripts/reset-dev.sh

# 核弹级别：彻底删除 volume 重建
docker compose down -v
docker compose up -d postgres
./scripts/svc.sh start api
```

### 缩略图在哪里？

缩略图存放在 `DATA_DIR/thumbs/` 目录下，按文件 hash 分桶存储，WebP 格式，长边 512px。

### 如何重新生成缩略图？

删除 `DATA_DIR/thumbs/` 目录后重新扫描即可。

---

## 安全说明

- 原始照片只读挂载，应用无写入权限
- PostgreSQL 和 Redis 默认只监听 127.0.0.1（不暴露到公网）
- Web 服务默认端口 8088，建议在群晖防火墙中限制为局域网访问
- 所有 AI 分析在本地完成，无任何数据上传

---

## 开发路线图

| 版本 | 功能 |
|------|------|
| **v0.1** ✅ | 照片扫描、缩略图、照片墙 |
| **v0.2** ✅ | MiniCPM-V 4.6 AI 打标签（caption / tags / OCR）|
| v0.3 | 中文智能搜索（全文 + 向量） |
| v0.4 | UI 优化（时间线、标签页、任务中心）|
| v0.5 | 完整 Docker 群晖部署支持 |

---

## v0.2：AI 打标签使用说明

### 前置条件

1. 安装并启动 [Ollama](https://ollama.com)（或使用 Docker Compose 中的 ollama 服务）
2. 拉取 MiniCPM-V 4.6 模型：

```bash
ollama pull openbmb/minicpm-v4.6
```

### 启动所有服务

```bash
docker compose up -d
```

### 验证 AI 接口

```bash
# 查看当前任务状态
curl http://localhost:8000/ai/status

# 预期输出：
# {"queued":0,"running":0,"success":0,"failed":0,"total":0}
```

### 使用流程

1. 先完成照片扫描（点击页面「重新扫描」或调用 `POST /scan/start`）
2. 确认照片墙有图片
3. 确保 Ollama 已拉取 `openbmb/minicpm-v4.6` 模型
4. 在页面「AI 图片分析」区域点击**「开始分析」**按钮，或手动调用：
   ```bash
   curl -X POST http://localhost:8000/ai/analyze/start
   ```
5. Worker 容器会自动循环处理队列中的任务
6. 任务完成后，点击照片缩略图，在详情弹窗中可看到 AI caption 和标签

### 手动启动 Worker（开发环境）

```bash
cd apps/worker
DATABASE_URL=postgresql+psycopg://photo:photo@localhost:5432/photo \
OLLAMA_BASE_URL=http://localhost:11434 \
python main.py
```

Worker 支持 `Ctrl+C` 优雅退出；重启后会继续处理未完成（queued）的任务。

### 重试失败任务

```bash
curl -X POST http://localhost:8000/ai/jobs/retry-failed
```

或在页面点击「重试失败」按钮。

### 新增 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/ai/analyze/start` | 为未分析照片创建任务 |
| `GET` | `/ai/status` | 查看任务队列统计 |
| `GET` | `/ai/jobs` | 列出任务（支持 status 过滤）|
| `POST` | `/ai/jobs/retry-failed` | 重试失败任务 |
| `GET` | `/photos/{id}/ai` | 获取单张照片的 AI 分析结果 |

