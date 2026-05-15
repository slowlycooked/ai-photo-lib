下面是一份可以直接复制到 **Cursor** 里的分阶段实现 Prompt。它会引导 Cursor 从零搭建一个可在群晖 NAS 上运行的本地智能照片库项目，项目名建议用 `ai-photo-lib`。

---

# Cursor Prompt：构建本地智能照片库 ai-photo-lib

你是一个资深全栈工程师，请帮我从零实现一个可以运行在群晖 NAS / Docker 环境里的本地智能照片库系统，项目名为 `ai-photo-lib`。

目标是构建一个私有化照片管理工具，支持：

1. 扫描本地照片目录；
2. 生成缩略图；
3. 使用 MiniCPM-V 4.6 对图片进行识别、描述、OCR 和自动打标签；
4. 支持中文自然语言智能搜索；
5. 支持 Docker Compose 在群晖 NAS 上部署；
6. 原始照片目录只读挂载，系统不得修改用户照片。

请按以下版本阶段逐步实现：

* v0.1 扫描照片
* v0.2 AI 打标签
* v0.3 智能搜索
* v0.4 UI 优化
* v0.5 Docker 群晖部署

技术栈请使用：

* Frontend: React + Vite + TypeScript
* Backend: FastAPI + Python 3.11
* Database: PostgreSQL
* Vector Search: pgvector
* Queue: Redis + RQ 或 Celery
* AI Runtime: llama-server (llama.cpp)，提供 OpenAI 兼容 API
* Vision Model: `MiniCPM-V-4.6`（GGUF 量化版）
* Image Processing: Pillow
* EXIF: exifread 或 piexif
* Deployment: Docker Compose

项目结构如下：

```text
ai-photo-lib/
  apps/
    web/
    api/
    worker/
  packages/
    shared/
  docker/
  scripts/
  docker-compose.yml
  .env.example
  README.md
```

---

# 总体架构要求

系统采用“离线索引 + 在线搜索”的架构。

照片处理流程：

```text
扫描照片目录
→ 读取文件元数据
→ 计算文件 hash
→ 写入数据库
→ 生成缩略图
→ 创建 AI 识别任务
→ Worker 调用 MiniCPM-V 4.6
→ 解析 caption / tags / OCR
→ 写入数据库
→ 更新搜索索引
→ 前端搜索和浏览
```

重要约束：

1. 原始照片目录必须只读挂载；
2. 不允许修改、移动、删除原始照片；
3. 所有 AI 分析结果、缩略图、索引都存放在应用目录；
4. 首次扫描和 AI 分析必须支持断点续跑；
5. Worker 必须支持失败重试；
6. MiniCPM-V 输出必须被解析为结构化 JSON；
7. 中文搜索优先；
8. 不做人脸身份识别，最多只记录 `people_count`；
9. 先实现 MVP，不要引入复杂权限、多用户、移动 App。

---

# v0.1：照片扫描与缩略图

请先实现 v0.1。

## 目标

实现一个可以扫描指定照片目录的后端服务，并把照片元数据写入 PostgreSQL。

## 后端 API

实现 FastAPI 服务，提供以下接口：

```http
GET /health
POST /scan/start
GET /scan/status
GET /photos
GET /photos/{photo_id}
GET /photos/{photo_id}/thumbnail
```

## 数据库表

请创建 Alembic migration，包含以下表：

```sql
photos
```

字段：

```text
id BIGSERIAL PRIMARY KEY
file_path TEXT UNIQUE NOT NULL
file_name TEXT NOT NULL
file_hash TEXT
file_size BIGINT
mime_type TEXT
width INT
height INT
taken_at TIMESTAMP NULL
exif JSONB
thumbnail_path TEXT
status TEXT DEFAULT 'pending'
created_at TIMESTAMP DEFAULT now()
updated_at TIMESTAMP DEFAULT now()
deleted_at TIMESTAMP NULL
```

## 扫描逻辑

实现照片扫描器：

* 扫描环境变量 `PHOTO_LIBRARY_PATH` 指定的目录；
* 支持 `.jpg`, `.jpeg`, `.png`, `.webp`, `.heic`；
* 递归扫描子目录；
* 读取文件大小、文件名、路径；
* 使用 SHA256 或 xxhash 生成文件 hash；
* 使用 Pillow 获取图片宽高；
* 尝试读取 EXIF 拍摄时间；
* 已存在文件不重复插入；
* 文件变动时更新元数据；
* 生成缩略图，保存到 `THUMBNAIL_PATH`；
* 缩略图建议 WebP 格式，长边 512px；
* 扫描过程要有状态统计。

## 前端 UI

实现一个最简单照片墙：

```text
顶部：标题 ai-photo-lib
按钮：开始扫描
区域：扫描状态
区域：照片网格
```

照片网格要求：

* 懒加载；
* 每张图显示缩略图；
* 点击照片显示基础信息；
* 支持分页或 infinite scroll。

## 验收标准

v0.1 完成后，我应该可以：

1. 启动 PostgreSQL、API、Web；
2. 配置本地照片目录；
3. 点击“开始扫描”；
4. 看到照片缩略图；
5. API 能返回照片元数据；
6. 应用不会修改原始照片。

---

# v0.2：MiniCPM-V 4.6 AI 打标签

在 v0.1 的基础上实现 v0.2。

## 目标

实现后台 Worker，调用本地 **llama-server**（llama.cpp OpenAI 兼容接口）运行 MiniCPM-V 4.6，对照片进行图片理解、OCR 和标签生成。

## 新增数据库表

创建：

```sql
photo_ai_analysis
ai_jobs
```

`photo_ai_analysis` 字段：

```text
id BIGSERIAL PRIMARY KEY
photo_id BIGINT REFERENCES photos(id)
model_name TEXT
model_version TEXT
caption TEXT
ocr_text TEXT
scene_tags TEXT[]
object_tags TEXT[]
activity_tags TEXT[]
quality_tags TEXT[]
location_clues TEXT[]
search_keywords TEXT[]
people_count INT
confidence FLOAT
raw_result JSONB
created_at TIMESTAMP DEFAULT now()
updated_at TIMESTAMP DEFAULT now()
```

`ai_jobs` 字段：

```text
id BIGSERIAL PRIMARY KEY
photo_id BIGINT REFERENCES photos(id)
job_type TEXT
status TEXT DEFAULT 'queued'
retry_count INT DEFAULT 0
error_message TEXT NULL
started_at TIMESTAMP NULL
finished_at TIMESTAMP NULL
created_at TIMESTAMP DEFAULT now()
updated_at TIMESTAMP DEFAULT now()
```

## AI Worker

实现一个独立 worker 服务：

```text
apps/worker/
```

Worker 职责：

1. 从数据库或 Redis 队列读取待分析照片；
2. 使用缩略图或压缩后的图片作为模型输入；
3. 调用 Ollama API；
4. 要求 MiniCPM-V 4.6 输出 JSON；
5. 解析 JSON；
6. 写入 `photo_ai_analysis`；
7. 更新 `photos.status = indexed`；
8. 失败时记录错误；
9. 支持最多 3 次重试；
10. 并发数默认 1，避免压垮 NAS。

## llama-server 调用（OpenAI 兼容）

使用环境变量：

```env
OPENAI_API_KEY=sk-local
OPENAI_BASE_URL=http://127.0.0.1:8082/v1          # 本地开发
# OPENAI_BASE_URL=http://host.docker.internal:8082/v1  # Docker 容器内
OPENAI_VISION_MODEL=MiniCPM-V-4.6
```

调用 `/v1/chat/completions`，图片通过 `file://` 相对路径传递（需 llama-server 启动时配置 `--media-path` 指向照片目录）：

```json
{
  "model": "MiniCPM-V-4.6",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "请分析这张图片，并只输出合法 JSON。" },
        { "type": "image_url", "image_url": { "url": "file://subdir/photo.jpg" } }
      ]
    }
  ],
  "stream": false
}
```

> **注意**：`file://` URL 中的路径是相对于 `--media-path` 的相对路径，**不是**标准的 `file:///absolute/path` URI。
> Worker 需要将原始图片路径相对化，例如：
> ```python
> rel = Path(image_path).resolve().relative_to(Path(settings.photo_library_path).resolve())
> file_url = f"file://{rel.as_posix()}"  # → file://subdir/photo.jpg
> ```

## llama-server 启动（NAS / 宿主机）

```bash
llama-server \
  --model /path/to/MiniCPM-V-4.6-Q4_K_M.gguf \
  --mmproj /path/to/mmproj.gguf \
  --port 8082 \
  --media-path /path/to/photos/    # 与 PHOTO_LIBRARY_PATH 相同
```

## Prompt

使用以下系统 Prompt：

```text
你是一个本地照片库的图片理解模型。请分析这张图片，并只输出合法 JSON，不要输出 Markdown，不要输出解释。

要求：
1. 用中文生成一句自然语言 caption。
2. 提取适合照片搜索的标签。
3. 识别场景、物体、活动、人物数量、OCR文字。
4. 不要推断具体人物身份。
5. 不要编造地点；如果无法确定，只输出视觉线索。
6. 标签要简短，适合作为搜索关键词。
7. 输出字段必须完整。
8. 如果无法判断，请输出空数组或较低 confidence。

JSON Schema:
{
  "caption": string,
  "scene_tags": string[],
  "object_tags": string[],
  "activity_tags": string[],
  "people_count": number,
  "ocr_text": string[],
  "location_clues": string[],
  "quality_tags": string[],
  "search_keywords": string[],
  "confidence": number
}
```

## JSON 修复机制

MiniCPM-V 可能输出不合法 JSON，请实现一个稳健解析器：

1. 尝试直接 `json.loads`；
2. 如果失败，截取第一个 `{` 到最后一个 `}`；
3. 再失败则记录 raw output；
4. 任务标记为 failed；
5. 不要让 worker 崩溃。

## 后端 API 新增

```http
POST /ai/analyze/start
GET /ai/jobs
GET /ai/status
GET /photos/{photo_id}/ai
```

## 前端 UI 新增

照片详情里显示：

* caption；
* scene tags；
* object tags；
* activity tags；
* OCR；
* people count；
* confidence；
* AI 状态。

增加一个 AI 任务页面：

```text
待处理数量
处理中数量
成功数量
失败数量
按钮：开始 AI 分析
按钮：暂停 AI 分析
按钮：重试失败任务
```

## 验收标准

v0.2 完成后，我应该可以：

1. 启动 Ollama；
2. 拉取 `openbmb/minicpm-v4.6`；
3. 点击开始 AI 分析；
4. 后台逐张图片打标签；
5. 前端可以看到每张照片的 caption 和标签；
6. Worker 重启后可以继续处理未完成任务。

---

# v0.3：智能搜索

在 v0.2 基础上实现 v0.3。

## 目标

实现中文智能搜索，支持通过自然语言搜索照片。

搜索示例：

```text
爬山的照片
有篮球的照片
夜景照片
带菜单文字的照片
去年在海边玩的照片
有云海的照片
模糊照片
截图里的订单号
```

## 搜索策略

先实现轻量版 hybrid search：

1. PostgreSQL ILIKE 搜索；
2. 标签数组匹配；
3. OCR 文本匹配；
4. caption 匹配；
5. 后续再接 pgvector。

## API

新增：

```http
GET /search?q=爬山
```

返回：

```json
{
  "query": "爬山",
  "total": 123,
  "items": [
    {
      "photo_id": 1,
      "thumbnail_url": "/photos/1/thumbnail",
      "caption": "...",
      "matched_tags": ["爬山", "户外"],
      "score": 0.87
    }
  ]
}
```

## 搜索打分

先实现简单打分：

```text
caption 命中：+3
scene_tags 命中：+4
object_tags 命中：+4
activity_tags 命中：+4
ocr_text 命中：+5
search_keywords 命中：+4
file_name 命中：+1
```

结果按 score 降序排列。

## pgvector 扩展

请预留 embedding 架构。

新增表：

```sql
photo_embeddings
```

字段：

```text
photo_id BIGINT PRIMARY KEY REFERENCES photos(id)
caption_embedding vector
tag_embedding vector
ocr_embedding vector
updated_at TIMESTAMP DEFAULT now()
```

暂时可以不实现真正 embedding，但代码结构要预留：

```text
apps/api/services/search_service.py
apps/api/services/embedding_service.py
```

`embedding_service.py` 先提供 mock 或 TODO 接口：

```python
def embed_text(text: str) -> list[float]:
    raise NotImplementedError
```

## 前端 UI

新增搜索页面：

```text
顶部搜索框
搜索建议
搜索结果照片墙
结果数量
命中原因展示
```

每张搜索结果显示：

* 缩略图；
* caption；
* 命中标签；
* score；
* 拍摄时间。

## 验收标准

v0.3 完成后，我应该可以：

1. 搜索中文关键词；
2. 搜到 caption、标签、OCR 中相关的照片；
3. 搜索速度对几千张照片可接受；
4. 搜索结果能显示命中原因；
5. 未来可以无痛扩展到 pgvector。

---

# v0.4：UI 优化与照片库体验

在 v0.3 基础上实现 v0.4。

## 目标

把前端从简单 Demo 优化为可用的照片库界面。

## 页面结构

实现以下页面：

```text
/photos       照片时间线
/search       智能搜索
/tags         标签浏览
/tasks        AI 任务中心
/settings     设置
```

## UI 要求

使用 React + TypeScript。

建议使用：

* Tailwind CSS；
* shadcn/ui；
* lucide-react；
* React Query；
* Zustand。

## 照片时间线

功能：

1. 按拍摄日期分组；
2. 无拍摄日期的照片按文件修改时间分组；
3. 支持瀑布流或网格；
4. 图片懒加载；
5. 点击打开照片详情 Modal；
6. 详情页显示 EXIF 和 AI 分析结果。

## 标签页面

功能：

1. 展示所有标签；
2. 标签按出现次数排序；
3. 点击标签进入搜索结果；
4. 标签分类显示：

   * scene tags
   * object tags
   * activity tags
   * quality tags
   * search keywords

## 任务中心

功能：

1. 显示扫描状态；
2. 显示 AI 分析状态；
3. 显示失败任务；
4. 支持重试失败任务；
5. 支持暂停 / 恢复 AI Worker；
6. 显示处理速度，例如每小时处理多少张。

## 设置页面

配置项：

```text
照片目录路径
缩略图目录路径
Ollama Base URL
Ollama Model
AI 分析并发数
是否自动扫描
是否自动 AI 分析
夜间任务时间段
```

设置可以先写入数据库或 `.env`，MVP 阶段可以只读展示环境变量。

## 前端 API Client

请封装 API client：

```text
apps/web/src/lib/api.ts
```

不要在组件里直接散落 fetch。

## 错误处理

前端需要处理：

* API 不可用；
* 图片加载失败；
* AI 分析失败；
* 无搜索结果；
* 无照片；
* Ollama 未连接。

## 验收标准

v0.4 完成后，我应该可以把它当作一个基本照片库使用：

1. 浏览照片；
2. 查看 AI 标签；
3. 搜索照片；
4. 查看任务状态；
5. 重试失败任务；
6. 配置页面能看到当前系统配置。

---

# v0.5：Docker 与群晖部署

在 v0.4 基础上实现 v0.5。

## 目标

提供完整 Docker Compose，让系统可以在群晖 DSM Container Manager 中运行。

## Docker 服务

实现：

```yaml
services:
  web:
  api:
  worker:
  postgres:
  redis:
  ollama:
```

可选：

```yaml
  meilisearch:
```

## docker-compose.yml 要求

需要支持以下 volume：

```text
/volume1/photo:/photos:ro
/volume1/docker/ai-photo-lib/postgres:/var/lib/postgresql/data
/volume1/docker/ai-photo-lib/thumbs:/data/thumbs
/volume1/docker/ai-photo-lib/ollama:/root/.ollama
/volume1/docker/ai-photo-lib/redis:/data
```

端口：

```text
web: 8088
api: 8000
ollama: 11434
postgres: 5432
redis: 6379
```

## .env.example

生成：

```env
PHOTO_LIBRARY_PATH=/photos
THUMBNAIL_PATH=/data/thumbs

DATABASE_URL=postgresql+psycopg://photo:photo@postgres:5432/photo
REDIS_URL=redis://redis:6379/0

OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=openbmb/minicpm-v4.6

API_HOST=0.0.0.0
API_PORT=8000

WEB_PORT=8088

AI_WORKER_CONCURRENCY=1
AI_MAX_RETRIES=3
THUMBNAIL_SIZE=512
```

## 初始化脚本

提供脚本：

```bash
scripts/init-db.sh
scripts/pull-model.sh
scripts/dev-up.sh
scripts/prod-up.sh
```

`pull-model.sh` 内容应调用：

```bash
ollama pull openbmb/minicpm-v4.6
```

## README

README 需要包含：

1. 项目介绍；
2. 功能说明；
3. 本地开发启动；
4. 群晖部署步骤；
5. Ollama 模型拉取；
6. 目录挂载说明；
7. 常见问题；
8. 如何重置数据库；
9. 如何重新扫描；
10. 如何重跑 AI 标签。

## 群晖部署说明

README 中请写清楚：

```text
1. 在群晖上创建目录：
   /volume1/docker/ai-photo-lib
   /volume1/docker/ai-photo-lib/postgres
   /volume1/docker/ai-photo-lib/thumbs
   /volume1/docker/ai-photo-lib/ollama
   /volume1/docker/ai-photo-lib/redis

2. 确认照片目录：
   /volume1/photo

3. 上传 docker-compose.yml 和 .env

4. 在 Container Manager 中创建项目

5. 启动服务

6. 进入 ollama 容器拉模型：
   ollama pull openbmb/minicpm-v4.6

7. 打开：
   http://群晖IP:8088
```

## 安全要求

1. `/photos` 必须只读；
2. 不要暴露 PostgreSQL 到公网；
3. 不要暴露 Ollama 到公网；
4. 默认只监听局域网；
5. 不要上传照片到任何外部服务；
6. README 明确声明所有 AI 分析在本地运行。

## 验收标准

v0.5 完成后，我应该可以：

1. 在群晖上通过 Docker Compose 启动完整系统；
2. 打开 Web UI；
3. 扫描 `/volume1/photo`；
4. 生成缩略图；
5. 调用本地 Ollama MiniCPM-V 4.6 打标签；
6. 用中文搜索照片；
7. 重启容器后数据不丢失。

---

# 代码质量要求

请遵守以下要求：

1. 每个阶段完成后都保持项目可运行；
2. 不要一次性写巨大文件；
3. 后端按 service / router / model / schema 分层；
4. 前端按 page / component / lib / hook 分层；
5. 数据库 migration 清晰；
6. 所有环境变量有默认值或文档说明；
7. API 返回结构统一；
8. 错误日志清晰；
9. Worker 不能因为单张坏图崩溃；
10. 图片路径不要直接暴露宿主机完整路径给前端；
11. 写必要的单元测试；
12. README 要能让普通开发者照着跑起来。

---

# 推荐实现顺序

请严格按下面顺序实现：

```text
1. 初始化 monorepo 项目结构
2. 实现 docker-compose 基础服务：postgres、redis、api、web
3. 实现数据库连接和 migration
4. 实现 photos 表
5. 实现照片扫描器
6. 实现缩略图生成
7. 实现照片列表 API
8. 实现基础照片墙 UI
9. 实现 ai_jobs 和 photo_ai_analysis 表
10. 实现 Ollama client
11. 实现 MiniCPM-V JSON Prompt
12. 实现 Worker 打标签
13. 实现 AI 状态 API
14. 实现照片详情页 AI 标签展示
15. 实现搜索 API
16. 实现搜索页面
17. 优化 UI
18. 完善 Docker Compose
19. 完善 README
20. 最后做一次端到端检查


