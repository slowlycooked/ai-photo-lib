# ai-photo-lib 当前代码匹配版架构设计

> 基于上传仓库 `ai-photo-lib-main.zip` 的当前代码整理。本文档描述“当前实现应该如何被理解和运行”，同时列出与最初方案不一致但需要在后续统一的地方。

---

## 1. 当前实现状态

当前仓库已经不是单纯 v0.1，而是接近 **v0.4 MVP**：

| 阶段 | 当前状态 | 说明 |
|---|---:|---|
| v0.1 照片扫描与缩略图 | 已实现 | 扫描目录、读取 EXIF、生成 WebP 缩略图、照片墙浏览 |
| v0.2 AI 打标签 | 已实现主体 | DB 任务表轮询、Worker 调用 OpenAI-compatible 视觉模型、解析 JSON、入库 |
| v0.3 智能搜索 | 已实现轻量版 | PostgreSQL ILIKE + 标签数组匹配 + Python 打分；pgvector 仅预留表 |
| v0.4 UI 优化 | 已实现主体 | `/photos`、`/search`、`/tags`、`/tasks`、`/settings` 页面 |
| v0.5 群晖完整部署 | 部分实现 | Docker Compose 已有 Postgres/Redis/API/Web/Worker；llama-server 当前建议宿主机运行 |

当前系统应被定义为：

> 一个基于 FastAPI + React + PostgreSQL 的私有本地照片库。照片扫描、缩略图、AI 标签和中文关键词搜索已经形成闭环；AI Runtime 使用 **llama-server / OpenAI-compatible API**，不再使用 Ollama。

---

## 2. 当前运行时拓扑

### 2.1 本地 macOS 开发拓扑

当前 `scripts/svc.sh` 的实际设计是：

```text
macOS Host
  ├─ llama-server，本地进程，由 scripts/svc.sh start ai 可选启动
  │    └─ http://127.0.0.1:8082/v1
  │
  ├─ FastAPI，本地 uvicorn 进程
  │    └─ http://127.0.0.1:8000
  │
  ├─ Worker，本地 Python 进程
  │    └─ 轮询 PostgreSQL ai_jobs 表
  │
  ├─ Web，本地 Vite dev server
  │    └─ http://127.0.0.1:5173 或 WEB_PORT
  │
  ├─ PostgreSQL，Docker Compose service
  └─ Redis，Docker Compose service
```

默认一键启动顺序：

```text
postgres → redis → ai(llama-server) → api → worker → web
```

注意：`svc.sh` 里的 help 文案仍然只写了 `postgres / redis / api / web`，但实际已经支持 `ai` 和 `worker`。

### 2.2 Docker Compose 拓扑

当前 `docker-compose.yml` 包含：

```text
postgres
redis
api
web
worker
```

当前 **没有** 独立的 `llama-srv` 容器服务。Worker 默认通过：

```env
OPENAI_BASE_URL=http://host.docker.internal:8082/v1
```

访问宿主机上的 llama-server。

因此当前 Docker 部署形态应理解为：

```text
Docker Network
  ├─ postgres
  ├─ redis
  ├─ api
  ├─ worker
  └─ web/nginx

Host Machine
  └─ llama-server :8082
```

---

## 3. AI Runtime 设计：llama-server + OpenAI-compatible API

### 3.1 当前代码中的命名

虽然当前文件名仍是：

```text
apps/api/app/services/vlm_client.py
```

但它实际上已经不是 Ollama Client，而是一个 **OpenAI-compatible VLM Client**。

当前使用的环境变量是：

```env
OPENAI_API_KEY=sk-local
OPENAI_BASE_URL=http://127.0.0.1:8082/v1
OPENAI_MODEL=MiniCPM-V-4.6
OPENAI_VISION_MODEL=MiniCPM-V-4.6
```

`svc.sh` 里用于启动 llama-server 的变量是：

```env
LLAMA_SERVER=/path/to/llama-server
LLAMA_MODEL=/path/to/MiniCPM-V-4.6-Q4_K_M.gguf
LLAMA_MMPROJ=/path/to/mmproj-model-f16.gguf
LLAMA_PORT=8082
LLAMA_CTX=8192
LLAMA_MEDIA_PATH=${PHOTO_LIBRARY_PATH}
```

建议后续把 `vlm_client.py` 改名为 `vlm_client.py`，已完成。

### 3.2 图片传输方式

当前 Worker 调用模型时没有使用 base64，而是使用 llama-server 的 `--media-path` 能力。

流程如下：

```text
photo.file_path
  ↓
计算相对 PHOTO_LIBRARY_PATH 的相对路径
  ↓
构造 file://relative/path.jpg
  ↓
POST /v1/chat/completions
  ↓
llama-server 根据 --media-path 读取原图
```

例如：

```text
PHOTO_LIBRARY_PATH=/Users/martin/Pictures
原图=/Users/martin/Pictures/trip/a.jpg
发送给模型=file://trip/a.jpg
llama-server --media-path /Users/martin/Pictures
```

这个设计的好处：

1. 不需要把图片 base64 编码进 HTTP 请求；
2. Worker 内存占用更低；
3. 大图分析时网络和序列化开销更小；
4. 适合本地 NAS 文件系统。

约束：

1. llama-server 必须能访问同一份照片目录；
2. `--media-path` 必须与 `PHOTO_LIBRARY_PATH` 指向同一个照片库根目录；
3. Docker Worker 内看到的是 `/photos`，但 llama-server 若在宿主机运行，需要通过相对路径映射到宿主机照片目录。

### 3.3 llama-server 推荐启动方式

本地 macOS：

```bash
llama-server \
  -m /path/to/MiniCPM-V-4.6-Q4_K_M.gguf \
  --mmproj /path/to/mmproj-model-f16.gguf \
  --host 127.0.0.1 \
  --port 8082 \
  --ctx-size 8192 \
  --media-path /path/to/photo/library
```

如果使用当前 `scripts/svc.sh`，推荐在 `.env` 中配置：

```env
LLAMA_SERVER=/Users/yourname/Workspace/llama.cpp/build/bin/llama-server
LLAMA_MODEL=/Users/yourname/models/MiniCPM-V-4.6-Q4_K_M.gguf
LLAMA_MMPROJ=/Users/yourname/models/mmproj-model-f16.gguf
LLAMA_PORT=8082
LLAMA_CTX=8192
PHOTO_LIBRARY_PATH=/Users/yourname/Pictures
LLAMA_MEDIA_PATH=/Users/yourname/Pictures

OPENAI_API_KEY=sk-local
OPENAI_BASE_URL=http://127.0.0.1:8082/v1
OPENAI_MODEL=MiniCPM-V-4.6
OPENAI_VISION_MODEL=MiniCPM-V-4.6
```

验证：

```bash
curl http://127.0.0.1:8082/v1/models \
  -H "Authorization: Bearer sk-local"
```

---

## 4. 当前后端架构

### 4.1 FastAPI 应用

入口：

```text
apps/api/app/main.py
```

当前注册的 router：

```text
/health
/photos
/scan
/ai
/search
/tags
/settings
```

版本号目前为：

```text
FastAPI app version = 0.4.0
/health version = 0.4.0
```

版本号已统一。

### 4.2 API 路由

| 路由 | 作用 |
|---|---|
| `GET /health` | 服务健康检查 |
| `POST /scan/start` | 启动后台扫描线程 |
| `GET /scan/status` | 返回扫描状态 |
| `GET /photos` | 分页获取照片列表 |
| `GET /photos/{photo_id}` | 获取照片详情 |
| `GET /photos/{photo_id}/thumbnail` | 返回 WebP 缩略图 |
| `GET /photos/{photo_id}/ai` | 返回照片最新 AI 分析结果 |
| `POST /ai/analyze/start` | 给尚未分析的照片创建 AI 任务 |
| `GET /ai/status` | 返回 AI 任务数量统计 |
| `GET /ai/jobs` | 分页查看 AI 任务 |
| `POST /ai/jobs/retry-failed` | 重试未超过最大次数的失败任务 |
| `GET /search?q=...` | 中文关键词搜索 |
| `GET /tags` | 聚合标签及出现次数 |
| `GET /settings` | 返回只读环境配置 |

前端访问时统一走 `/api` 前缀：

```text
Web /api/photos → nginx 或 Vite proxy → API /photos
```

---

## 5. 数据库设计

当前已实现三组表。

### 5.1 photos

用途：存储原始照片文件元数据和缩略图路径。

关键字段：

```text
id
file_path
file_name
file_hash
file_size
mime_type
width
height
taken_at
exif
thumbnail_path
status
created_at
updated_at
deleted_at
```

已建索引：

```text
ix_photos_status
ix_photos_taken_at
ix_photos_file_hash
```

当前扫描策略：

1. 按 `PHOTO_LIBRARY_PATH` 递归扫描；
2. 支持 `.jpg`, `.jpeg`, `.png`, `.webp`, `.heic`；
3. 读取文件大小、MIME、图片宽高、EXIF；
4. 使用 SHA256 计算文件 hash；
5. 内容未变化则跳过；
6. 生成 WebP 缩略图；
7. 不修改原图。

### 5.2 photo_ai_analysis

用途：存每张照片的 AI 结构化分析结果。

关键字段：

```text
photo_id
model_name
model_version
caption
ocr_text
scene_tags
object_tags
activity_tags
quality_tags
location_clues
search_keywords
people_count
confidence
raw_result
created_at
updated_at
```

当前 Worker 行为是：

```text
同一 photo_id 重新分析时：删除旧 analysis → 插入新 analysis
```

当前 `model_name` 写入：

```text
settings.openai_vision_model
```

当前 `model_version` 为：

```text
None
```

建议后续把 provider、base_url、runtime、模型 GGUF 文件名放入 `raw_result` 或新增字段。

### 5.3 ai_jobs

用途：AI 分析任务队列。

当前任务队列不是 Redis，而是 **PostgreSQL 表轮询**。

状态：

```text
queued
running
success
failed
skipped，预留但当前逻辑未使用
```

关键字段：

```text
photo_id
job_type
status
retry_count
error_message
started_at
finished_at
created_at
updated_at
```

Worker 每次取一个 `queued` 任务，使用：

```sql
FOR UPDATE SKIP LOCKED
```

所以未来可以扩展多 Worker 并发，但当前 `AI_WORKER_CONCURRENCY` 没有真正驱动多进程或多线程。

### 5.4 photo_embeddings

当前只是预留表。

字段：

```text
photo_id
caption_embedding TEXT
tag_embedding TEXT
ocr_embedding TEXT
updated_at
```

注意：当前并没有真正启用 pgvector 类型，embedding 也没有实现。

---

## 6. AI 打标签流程

当前实际流程：

```text
用户点击“开始分析”
  ↓
POST /ai/analyze/start
  ↓
API 查询尚未分析、且没有 queued/running job 的 photos
  ↓
为每张照片插入 ai_jobs(status=queued)
  ↓
Worker 轮询 ai_jobs
  ↓
将任务置为 running
  ↓
读取 photo.file_path
  ↓
优先分析原图；若原图不存在才回退 thumbnail_path
  ↓
OpenAI-compatible POST /v1/chat/completions
  ↓
解析 choices[0].message.content
  ↓
parse_model_json_output 修复 JSON
  ↓
写入 photo_ai_analysis
  ↓
photos.status = ai_indexed
  ↓
ai_jobs.status = success
```

失败重试逻辑：

```text
异常 → retry_count + 1
  ├─ retry_count < AI_MAX_RETRIES → status=queued
  └─ retry_count >= AI_MAX_RETRIES → status=failed
```

注意：当前 `_pick_image_path()` 优先使用原图，缩略图只是 fallback。这个与最初“优先缩略图以节省性能”的设计不同。由于当前 llama-server 使用 `file://` 直接读文件，优先原图是可接受的，但在 NAS 上可能导致处理变慢。后续可以增加 `AI_IMAGE_SOURCE=original|thumbnail|resized`。

---

## 7. AI Prompt 与 JSON Schema

当前 Prompt 要求 MiniCPM-V 输出中文 JSON，并禁止英文标签。

目标字段：

```json
{
  "caption": "中文描述",
  "scene_tags": [],
  "object_tags": [],
  "activity_tags": [],
  "people_count": 0,
  "ocr_text": [],
  "location_clues": [],
  "quality_tags": [],
  "search_keywords": [],
  "confidence": 0.0
}
```

当前 JSON parser 设计应继续保留：

1. 直接 `json.loads`；
2. 去掉 Markdown code fence；
3. 截取第一个 `{` 到最后一个 `}`；
4. 缺失字段补默认值；
5. 字段类型归一化。

---

## 8. 搜索设计

当前搜索是 **轻量关键词 Hybrid Search**，还不是向量搜索。

查询入口：

```text
GET /search?q=关键词&page=1&page_size=50
```

当前匹配字段：

```text
photo_ai_analysis.caption
photo_ai_analysis.ocr_text
photo_ai_analysis.scene_tags
photo_ai_analysis.object_tags
photo_ai_analysis.activity_tags
photo_ai_analysis.search_keywords
photo_ai_analysis.quality_tags
photo_ai_analysis.location_clues
photos.file_name
```

当前打分权重：

| 字段 | 权重 |
|---|---:|
| OCR | 5 |
| scene_tags | 4 |
| object_tags | 4 |
| activity_tags | 4 |
| search_keywords | 4 |
| caption | 3 |
| quality_tags | 2 |
| location_clues | 2 |
| file_name | 1 |

当前限制：

1. 仅按空格切词，不支持中文分词；
2. 候选最多 2000 条；
3. 分数在 Python 中计算；
4. 不支持语义向量；
5. 不支持时间语义解析，如“去年”“上个月”。

建议下一步：

```text
v0.5-search：加入 PostgreSQL 全文索引 / trigram / pgvector
v0.6-query：加入中文 query parser，解析时间、地点、活动
```

---

## 9. 前端架构

当前前端是：

```text
React 18 + Vite + TypeScript + Tailwind CSS + React Query + React Router
```

实际页面：

```text
/photos     照片时间线 + 扫描面板 + AI 面板
/search     搜索结果页
/tags       标签聚合页
/tasks      扫描 / AI 任务中心
/settings   只读配置页
```

API Client：

```text
apps/web/src/lib/api.ts
```

所有前端 API 请求使用：

```text
const BASE = "/api"
```

开发环境由 Vite proxy 转发：

```text
/api/* → http://localhost:${API_PORT}/*
```

生产容器由 nginx 转发：

```text
/api/* → http://api:8000/*
```

---

## 10. Docker 与群晖部署设计

### 10.1 当前 docker-compose 事实

当前 Compose 适合运行：

```text
postgres
redis
api
web
worker
```

当前不包含 llama-server 容器，原因是设计上倾向让 llama-server 运行在宿主机：

1. 更容易直接访问照片目录；
2. `--media-path` 与宿主机文件系统更直接；
3. 避免容器内 Metal/GPU/CPU 特性不一致；
4. NAS 上更容易调试模型路径。

### 10.2 群晖推荐部署

群晖上推荐：

```text
/volume1/photo                         原始照片，只读给应用
/volume1/docker/ai-photo-lib/postgres  PostgreSQL 数据
/volume1/docker/ai-photo-lib/redis     Redis 数据
/volume1/docker/ai-photo-lib/thumbs    缩略图
/volume1/docker/ai-photo-lib/models    GGUF 模型文件
```

`.env`：

```env
PHOTO_LIBRARY_PATH=/volume1/photo
DATA_DIR=/volume1/docker/ai-photo-lib
POSTGRES_PASSWORD=your_secure_password
WEB_PORT=8088

OPENAI_API_KEY=sk-local
OPENAI_BASE_URL=http://host.docker.internal:8082/v1
OPENAI_MODEL=MiniCPM-V-4.6
OPENAI_VISION_MODEL=MiniCPM-V-4.6
```

宿主机启动 llama-server：

```bash
llama-server \
  -m /volume1/docker/ai-photo-lib/models/MiniCPM-V-4.6-Q4_K_M.gguf \
  --mmproj /volume1/docker/ai-photo-lib/models/mmproj-model-f16.gguf \
  --host 0.0.0.0 \
  --port 8082 \
  --ctx-size 8192 \
  --media-path /volume1/photo
```

如果群晖 Docker 无法访问 `host.docker.internal`，需要改用宿主机局域网 IP：

```env
OPENAI_BASE_URL=http://群晖IP:8082/v1
```

---

## 11. 当前代码与设计不一致点

这些不是阻塞问题，但建议纳入下一轮修正。

| 问题 | 当前状态 | 建议 |
|---|---|---|
| AI client 文件名 | `vlm_client.py`，调用 OpenAI-compatible API | 已完成 |
| Worker docstring | 仍写 “calls Ollama MiniCPM-V” | 改成 “calls llama-server/OpenAI-compatible VLM” |
| 环境变量命名 | 使用 `OPENAI_*` 表示本地 llama-server | 可以保留；若想更清晰可新增 `VLM_*` 并兼容 `OPENAI_*` |
| Redis 用途 | Compose 有 Redis，但 AI Worker 当前未用 Redis 队列 | 文档改成“Redis 预留/缓存/后续队列”，或真正迁到 RQ/Celery |
| docker-compose | 无 llama-server service | 文档写明 llama-server 宿主机运行；或新增 profile 可选容器化 |
| API 版本 | app 是 `0.4.0`，health 是 `0.1.0` | 统一版本来源 |
| AI 并发 | `AI_WORKER_CONCURRENCY` 存在但未实际使用 | 后续实现多 worker 或删除配置 |
| 搜索 | `photo_embeddings` 已建表但未启用 pgvector | 文档明确是 placeholder |
| 停止顺序 | `do_stop` 没有包含 `ai` | 把 `ai` 加入停止顺序，避免 `svc.sh stop` 漏停 |
| README 功能 | 标题仍写 v0.1，但实际已到 v0.4 | 更新 README 功能列表 |

---

## 12. 下一阶段建议

### P0：先做一致性修正

1. `vlm_client.py`（已完成重命名）；
2. Worker 注释和 README 全部改为 llama-server；
3. `svc.sh help` 增加 `ai`、`worker`；
4. `do_stop` 停止顺序加入 `ai`；
5. 统一 `/health` 版本号；
6. README 的 “功能 v0.1” 改为 “当前功能”。

### P1：增强 llama-server 健康检查

新增 API：

```text
GET /ai/runtime
```

返回：

```json
{
  "provider": "llama-server",
  "base_url": "http://127.0.0.1:8082/v1",
  "model": "MiniCPM-V-4.6",
  "online": true,
  "models": []
}
```

### P2：搜索增强

1. PostgreSQL trigram / GIN 索引；
2. 中文分词或 query rewrite；
3. pgvector 真正启用；
4. caption/tag/OCR embedding；
5. 结果融合 RRF。

### P3：AI 输入图策略

新增配置：

```env
AI_IMAGE_SOURCE=original
AI_IMAGE_MAX_EDGE=1280
AI_IMAGE_USE_FILE_URL=true
```

支持三种模式：

```text
original：当前模式，file:// 原图
thumbnail：传缩略图，速度快但 OCR 差
resized：生成专用分析图，质量和速度折中
```

---

## 13. 当前匹配版一句话架构结论

`ai-photo-lib` 当前实现应定义为：

> 一个运行在本地或群晖 NAS 上的私有 AI 照片库：FastAPI 负责扫描、任务和搜索 API，React/Vite 负责照片墙与任务 UI，PostgreSQL 存储照片元数据、AI 标签和任务状态，Worker 通过 OpenAI-compatible API 调用宿主机 llama-server 上的 MiniCPM-V 4.6，并使用 `--media-path + file://相对路径` 进行本地图片识别，最终通过 caption、OCR 和标签实现中文关键词搜索。
