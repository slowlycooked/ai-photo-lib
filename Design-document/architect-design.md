**私有化、NAS 本地运行的“AI Photo Library”**。但架构上要注意一点：**MiniCPM-V 4.6 负责图片理解与标签生成，不直接负责搜索引擎本身**。搜索能力应该由 **结构化标签 + OCR 文本 + Caption 描述 + 向量索引 + 全文索引** 共同完成。

MiniCPM-V 4.6 当前定位就是轻量端侧多模态模型，支持单图、多图、视频理解，并适配 llama.cpp、Ollama、vLLM、SGLang 等部署框架，也有 GGUF、AWQ、GPTQ 等量化版本，适合在 NAS / 本地机器上做私有化图片分析。([Hugging Face][1]) GGUF 量化版（Q4_K_M）模型体积约 2–3 GB，比较适合先做 NAS 本地验证。

**本项目选用 llama-server（llama.cpp）而非 Ollama 作为 AI 运行时。** 原因：
- 暴露标准 OpenAI 兼容 API（`/v1/chat/completions`），Worker 调用方式与 OpenAI SDK 完全一致；
- 支持 `--media-path` 参数，Worker 可直接传 `file://相对路径` 引用本地图片，无需 base64 编码，减少内存拷贝；
- 资源占用比 Ollama 更轻，适合 NAS 常驻；
- Docker Compose 中 worker 通过 `host.docker.internal:8082` 访问宿主机上的 llama-server。

---

# 1. 总体架构建议

建议做成 **离线索引 + 在线搜索** 架构。

```mermaid
flowchart LR
    A[Synology Photo Folder<br>/volume1/photo] --> B[File Scanner<br>文件扫描器]
    B --> C[Metadata Extractor<br>EXIF/Hash/缩略图]
    C --> D[Job Queue<br>Redis / BullMQ / Celery]
    D --> E[AI Worker<br>MiniCPM-V 4.6 图片理解]
    E --> F[Tag & Caption Parser<br>结构化标签解析]
    F --> G[(PostgreSQL<br>照片元数据)]
    F --> H[(Vector DB<br>pgvector / Qdrant)]
    F --> I[(Full-text Index<br>Meilisearch / OpenSearch)]

    J[Web UI / Mobile Web] --> K[API Gateway]
    K --> G
    K --> H
    K --> I
    K --> L[Thumbnail Service]
    L --> M[Thumbnail Cache]
```

核心原则：

| 模块                       | 作用                            |
| ------------------------ | ----------------------------- |
| 文件扫描器                    | 监听 / 扫描群晖照片目录，发现新增、修改、删除      |
| 元数据处理                    | 读取 EXIF、拍摄时间、GPS、相机型号、文件 hash |
| 缩略图服务                    | 生成 WebP / AVIF 缩略图，避免前端直接加载原图 |
| AI Worker                | 调用 MiniCPM-V 4.6 识别图片内容       |
| 标签解析器                    | 把模型输出转成稳定 JSON                |
| PostgreSQL               | 存照片、相册、标签、任务状态                |
| pgvector / Qdrant        | 做语义搜索                         |
| Meilisearch / OpenSearch | 做关键词、OCR、标签全文搜索               |
| Web UI                   | 照片浏览、智能搜索、标签管理、任务状态           |

---

# 2. 推荐技术栈

## NAS 上的容器组合

Docker Compose 适合这个项目，因为它可以用一个 YAML 文件定义多个服务、网络和卷，统一启动整套应用。([Docker Documentation][3]) 群晖 DSM 7 的 Container Manager 可以管理容器网络，例如 bridge 或 host 网络模式。([知识中心][4])

建议服务拆分如下：

```yaml
services:
  web:
    image: smart-photo-web
    ports:
      - "8088:80"

  api:
    image: smart-photo-api
    environment:
      DATABASE_URL: postgres://photo:photo@postgres:5432/photo
      REDIS_URL: redis://redis:6379
    volumes:
      - /volume1/photo:/photos:ro
      - /volume1/docker/smart-photo/thumbs:/app/thumbs

  worker:
    image: smart-photo-worker
    environment:
      DATABASE_URL: postgres://photo:photo@postgres:5432/photo
      REDIS_URL: redis://redis:6379
      # llama-server 运行在宿主机，通过 host.docker.internal 访问
      OPENAI_API_KEY: sk-local
      OPENAI_BASE_URL: http://host.docker.internal:8082/v1
      OPENAI_MODEL: MiniCPM-V-4.6
      OPENAI_VISION_MODEL: MiniCPM-V-4.6
      PHOTO_LIBRARY_PATH: /photos
    volumes:
      - /volume1/photo:/photos:ro
      - /volume1/docker/smart-photo/thumbs:/app/thumbs

  # llama-server 建议直接运行在宿主机（NAS）上，而非容器内，
  # 以便利用 --media-path 高效读取照片文件（file:// URL 方式）。
  # 启动命令示例（在宿主机执行）：
  #   llama-server \
  #     --model /volume1/docker/smart-photo/models/MiniCPM-V-4.6-Q4_K_M.gguf \
  #     --mmproj /volume1/docker/smart-photo/models/mmproj.gguf \
  #     --port 8082 \
  #     --media-path /volume1/photo/
  #
  # 如果必须容器化，可以用以下配置：
  # llama-server:
  #   image: ghcr.io/ggerganov/llama.cpp:server
  #   command: >
  #     --model /models/MiniCPM-V-4.6-Q4_K_M.gguf
  #     --mmproj /models/mmproj.gguf
  #     --port 8082
  #     --media-path /photos/
  #   volumes:
  #     - /volume1/docker/smart-photo/models:/models
  #     - /volume1/photo:/photos:ro
  #   ports:
  #     - "8082:8082"

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: photo
      POSTGRES_USER: photo
      POSTGRES_PASSWORD: photo
    volumes:
      - /volume1/docker/smart-photo/postgres:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - /volume1/docker/smart-photo/redis:/data
```

原始照片目录建议用 **bind mount 只读挂载**，例如 `/volume1/photo:/photos:ro`。应用自己的数据库、缩略图、模型、索引文件放到 `/volume1/docker/smart-photo/` 下。Docker 官方文档也建议：容器生成的数据适合用 volume 持久化；如果容器和宿主机都需要直接访问文件目录，则更适合用 bind mount。([Docker Documentation][5])

---

# 3. MiniCPM-V 4.6 在系统里的职责

MiniCPM-V 4.6 不应该直接承担“搜索引擎”的角色，而应该作为 **图片语义理解引擎**。

对每张照片，AI Worker 调用 MiniCPM-V 4.6 后生成这样的结构化结果：

```json
{
  "caption": "一张在山顶拍摄的风景照片，画面中有蓝天、云海、远处山脉和几名徒步者。",
  "scene": ["山地", "户外", "自然风光", "徒步"],
  "objects": ["山", "云", "天空", "背包", "登山杖"],
  "activities": ["徒步", "爬山", "旅行"],
  "people_count": 3,
  "text_ocr": [],
  "location_clues": ["山顶", "自然景区"],
  "quality_tags": ["清晰", "白天", "横图"],
  "search_keywords": [
    "山顶",
    "徒步",
    "爬山",
    "户外",
    "云海",
    "旅行",
    "自然风光"
  ],
  "confidence": 0.86
}
```

标签体系建议分层：

| 标签层级   | 示例               | 用途      |
| ------ | ---------------- | ------- |
| 场景标签   | 海边、山地、城市、办公室、餐厅  | 快速分类    |
| 对象标签   | 狗、汽车、电脑、蛋糕、篮球    | 精确过滤    |
| 活动标签   | 爬山、聚餐、会议、运动、旅行   | 场景搜索    |
| OCR 文本 | 发票、招牌、PPT、菜单文字   | 搜图片里的文字 |
| 质量标签   | 模糊、夜景、自拍、截图      | 清理照片    |
| 时间地点   | EXIF 时间、GPS、地点推断 | 时间线和地图  |
| 人物信息   | 人脸聚类 ID，不直接识别姓名  | 私有相册管理  |

---

# 4. 搜索架构：不要只靠一种搜索

智能照片搜索建议做 **Hybrid Search**。

## 搜索链路

用户输入：

> “找去年在山上拍的有云海的照片”

系统拆解为：

```json
{
  "semantic_query": "山上 云海 徒步 自然风光",
  "time_filter": "last_year",
  "tags": ["山地", "云海", "户外"],
  "sort": "relevance"
}
```

然后并行查询：

```mermaid
flowchart TD
    A[用户搜索 Query] --> B[Query Parser]
    B --> C[全文搜索<br>标签/OCR/Caption]
    B --> D[向量搜索<br>语义相似度]
    B --> E[结构化过滤<br>时间/地点/相册/人物]
    C --> F[结果融合 RRF]
    D --> F
    E --> F
    F --> G[排序与去重]
    G --> H[返回照片墙]
```

## 三类索引

| 索引类型  | 推荐组件                     | 存什么                             | 解决什么问题 |
| ----- | ------------------------ | ------------------------------- | ------ |
| 结构化索引 | PostgreSQL               | 时间、路径、EXIF、标签、任务状态              | 精准筛选   |
| 全文索引  | Meilisearch / OpenSearch | caption、OCR、标签、文件名              | 关键词搜索  |
| 向量索引  | pgvector / Qdrant        | caption embedding、OCR embedding | 语义搜索   |

向量模型可以用：

| 模型                  | 用法                                      |
| ------------------- | --------------------------------------- |
| `bge-small-zh-v1.5` | 中文搜索够用，资源占用低                            |
| `bge-m3`            | 中英文混合、长文本更强                             |
| CLIP / SigLIP       | 图片相似图搜索                                 |
| MiniCPM-V 4.6       | 图片理解、标签、caption、OCR，不建议直接当 embedding 模型 |

---

# 5. 数据库核心表设计

## photos 表

```sql
CREATE TABLE photos (
  id BIGSERIAL PRIMARY KEY,
  file_path TEXT UNIQUE NOT NULL,
  file_name TEXT,
  file_hash TEXT,
  file_size BIGINT,
  mime_type TEXT,
  width INT,
  height INT,
  taken_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now(),
  exif JSONB,
  gps_lat DOUBLE PRECISION,
  gps_lng DOUBLE PRECISION,
  thumbnail_path TEXT,
  status TEXT DEFAULT 'pending'
);
```

## photo_ai_analysis 表

```sql
CREATE TABLE photo_ai_analysis (
  id BIGSERIAL PRIMARY KEY,
  photo_id BIGINT REFERENCES photos(id),
  model_name TEXT,
  model_version TEXT,
  caption TEXT,
  ocr_text TEXT,
  scene_tags TEXT[],
  object_tags TEXT[],
  activity_tags TEXT[],
  quality_tags TEXT[],
  people_count INT,
  raw_result JSONB,
  confidence FLOAT,
  created_at TIMESTAMP DEFAULT now()
);
```

## photo_embeddings 表

```sql
CREATE TABLE photo_embeddings (
  photo_id BIGINT PRIMARY KEY REFERENCES photos(id),
  caption_embedding vector(1024),
  ocr_embedding vector(1024),
  tag_embedding vector(1024),
  updated_at TIMESTAMP DEFAULT now()
);
```

## jobs 表

```sql
CREATE TABLE jobs (
  id BIGSERIAL PRIMARY KEY,
  photo_id BIGINT REFERENCES photos(id),
  job_type TEXT,
  status TEXT DEFAULT 'queued',
  retry_count INT DEFAULT 0,
  error_message TEXT,
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT now()
);
```

---

# 6. 图片处理流水线

每张照片进入系统后，走下面流程：

```mermaid
sequenceDiagram
    participant Scanner as File Scanner
    participant DB as PostgreSQL
    participant Queue as Redis Queue
    participant Worker as AI Worker
    participant Model as MiniCPM-V 4.6
    participant Index as Search Index

    Scanner->>DB: upsert photo metadata
    Scanner->>Queue: enqueue analyze_photo
    Worker->>DB: get pending photo
    Worker->>Worker: generate thumbnail / resize image
    Worker->>Model: send image + structured prompt
    Model-->>Worker: caption + tags + OCR JSON
    Worker->>DB: save ai_analysis
    Worker->>Index: update full-text index
    Worker->>Index: update vector index
    Worker->>DB: mark photo indexed
```

关键点：

1. **原图不传给前端直接加载**
   前端只加载缩略图，点击后再读取原图或大图。

2. **AI 识别使用压缩图**
   不要直接把 20MB 原图丢给模型。先缩放到 1024px / 1280px 长边，节省 NAS CPU 和内存。

3. **任务可断点续跑**
   群晖重启、容器重启后，任务状态还能恢复。

4. **任务低优先级运行**
   建议默认夜间跑，比如 01:00 - 07:00，避免影响 NAS 正常文件服务。

---

# 7. MiniCPM-V Prompt 设计

AI Worker 调用 MiniCPM-V 时，不要让它自由发挥，要强制输出 JSON。

示例 Prompt：

```text
你是一个本地照片库的图片理解模型。请分析这张图片，并只输出合法 JSON，不要输出 Markdown。

要求：
1. 用中文生成一句自然语言 caption。
2. 提取适合照片搜索的标签。
3. 识别场景、物体、活动、人物数量、OCR文字。
4. 不要推断具体人物身份。
5. 不要编造地点；如果无法确定，只输出视觉线索。
6. 标签要简短，适合作为搜索关键词。
7. 输出字段必须完整。

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

---

# 8. NAS 性能设计

群晖 NAS 通常不是 GPU 服务器，所以架构必须控制资源。

## 推荐配置策略

| NAS 类型                    | 建议方案                                          |
| ------------------------- | --------------------------------------------- |
| Intel / AMD x86 NAS，无 GPU | Ollama / llama.cpp + MiniCPM-V 4.6 量化版，低并发离线跑 |
| 高配 x86 NAS + 外接 GPU 不现实   | 不建议依赖 GPU，除非是独立小主机                            |
| ARM NAS                   | 谨慎，模型兼容性和性能会受限                                |
| NAS + 局域网 GPU 主机          | 最优方案：NAS 存储，GPU 主机跑模型服务                       |
| NAS 只做相册服务                | Worker 可配置为远程模型 endpoint                      |

## 三种部署模式

### 模式 A：纯群晖本地

```mermaid
flowchart LR
    NAS[Synology NAS] --> WEB[Web/API]
    NAS --> DB[Postgres/Redis/Meili]
    NAS --> MODEL[Ollama MiniCPM-V 4.6]
```

优点：隐私最好，部署简单。
缺点：首次索引几万张照片会很慢。

适合：家庭相册、低频搜索、夜间后台处理。

---

### 模式 B：群晖 + 局域网 AI 小主机

```mermaid
flowchart LR
    NAS[Synology NAS<br>照片/DB/Web] --> GPU[Mac mini / NUC / GPU Server<br>MiniCPM-V Service]
```

优点：性能明显更好。
缺点：多一台机器。

适合：照片很多、想要较快索引、未来还想接视频理解。

---

### 模式 C：群晖只存储，AI 服务可切换

```mermaid
flowchart LR
    NAS[Synology NAS] --> API[Smart Photo API]
    API --> Local[Local MiniCPM-V]
    API --> Remote[Remote OpenAI-compatible Endpoint]
```

优点：模型服务可插拔。
缺点：如果用外部模型，隐私要重新评估。

适合：产品化、后续支持多模型。

---

# 9. 前端产品形态

建议前端不要只做“照片墙”，而是做几个核心页面。

## 页面一：照片时间线

功能：

* 按年 / 月 / 日浏览
* 懒加载缩略图
* 原图预览
* EXIF 展示
* AI 标签展示
* 手动修正标签

## 页面二：智能搜索

搜索示例：

```text
找有篮球的照片
找去年爬山的照片
找带发票文字的图片
找孩子在海边玩的照片
找所有截图里的订单号
找模糊照片
找夜景照片
找包含英文菜单的照片
```

搜索结果支持：

* 时间过滤
* 地点过滤
* 标签过滤
* 人物聚类过滤
* 横图 / 竖图 / 截图过滤
* 相似图片搜索

## 页面三：AI 任务中心

需要展示：

| 指标     | 说明                           |
| ------ | ---------------------------- |
| 已扫描照片数 | 文件总量                         |
| 待识别数量  | 等待 MiniCPM-V 分析              |
| 识别成功数量 | 已完成 AI 标签                    |
| 失败数量   | 可重试                          |
| 当前速度   | 张 / 小时                       |
| 当前模型   | MiniCPM-V 4.6 q5 / q8        |
| 队列状态   | running / paused / scheduled |

## 页面四：标签管理

支持：

* 标签合并：`爬山` + `徒步` 合并
* 标签禁用：屏蔽低质量标签
* 标签别名：`小孩` = `儿童` = `孩子`
* 用户纠错：人工改过的标签优先级更高

---

# 10. 搜索排序逻辑

最终搜索结果不要只按向量相似度排。建议使用打分融合：

```text
final_score =
  0.40 * vector_score
+ 0.25 * fulltext_score
+ 0.15 * tag_match_score
+ 0.10 * time_score
+ 0.05 * quality_score
+ 0.05 * user_feedback_score
```

例如用户搜：

> “爬山 云海”

排序优先级：

1. caption 里明确出现“爬山、云海”
2. AI 标签里有“山地、徒步、云海”
3. 向量语义接近“户外登山自然风光”
4. 拍摄地点或 GPS 接近山区
5. 用户曾经收藏 / 打过标签的照片优先

---

# 11. MVP 版本范围

第一版不要做太大，建议控制成 4 个核心能力。

## MVP v0.1

| 功能                                    | 是否必须 |
| ------------------------------------- | ---- |
| 扫描群晖指定照片目录                            | 必须   |
| 生成缩略图                                 | 必须   |
| MiniCPM-V 4.6 生成 caption / tags / OCR | 必须   |
| 按标签和 caption 搜索                       | 必须   |
| Web 照片墙                               | 必须   |
| AI 任务队列                               | 必须   |
| 向量搜索                                  | 建议   |
| 人脸识别                                  | 暂缓   |
| 地图相册                                  | 暂缓   |
| 视频理解                                  | 暂缓   |
| 多用户权限                                 | 暂缓   |

MVP 的目标不是替代 Synology Photos，而是先证明：

> “我能在 NAS 本地对照片做 AI 理解，并用自然语言搜到照片。”

---

# 12. 关键技术风险

| 风险      | 说明                             | 解决方案                                   |
| ------- | ------------------------------ | -------------------------------------- |
| NAS 推理慢 | CPU 跑多模态模型速度有限                 | 后台异步、夜间任务、缩略图输入、并发 1                   |
| 模型标签不稳定 | 同类照片输出标签不一致                    | 固定 JSON Schema + 标签归一化                 |
| 搜索误召回   | 语义搜索会搜出不相关图片                   | hybrid search + 标签过滤                   |
| 中文搜索效果差 | 英文 embedding 或 tokenizer 不适合中文 | 使用中文 embedding，如 bge-small-zh / bge-m3 |
| OCR 不完整 | VLM OCR 不是专业 OCR               | 重要场景可接 PaddleOCR / RapidOCR            |
| 文件变动复杂  | 照片移动、改名、删除                     | hash + inode/path 双重追踪                 |
| 首次索引很久  | 几万张照片可能跑数天                     | 可暂停、可恢复、增量扫描                           |
| 隐私风险    | 家庭照片敏感                         | 全本地、不上传、目录只读                           |

---

# 13. 推荐最终架构版本

我建议你采用这个版本：

```text
Frontend: React / Next.js
Backend: FastAPI 或 NestJS
Queue: Redis + Celery / BullMQ
Database: PostgreSQL + pgvector
Full-text: Meilisearch
Model Runtime: Ollama + MiniCPM-V 4.6 q5_K_M
Thumbnail: Sharp / Pillow
Image Metadata: exiftool
Deployment: Docker Compose on Synology Container Manager
Storage:
  - /volume1/photo                  原始照片，只读挂载
  - /volume1/docker/smart-photo/db  数据库
  - /volume1/docker/smart-photo/thumbs 缩略图
  - /volume1/docker/smart-photo/index 搜索索引
  - /volume1/docker/smart-photo/models 模型缓存
```

最小可行链路：

```text
照片目录扫描
→ 生成缩略图
→ MiniCPM-V 4.6 识别
→ 存 caption/tags/OCR
→ 生成 embedding
→ 写入 pgvector + Meilisearch
→ 前端自然语言搜索
```

---

# 14. 一句话架构结论

这个系统应该设计成：

> **以群晖 NAS 为私有照片存储中心，以 Docker Compose 编排 Web/API/DB/Queue/AI Worker/Ollama，以 MiniCPM-V 4.6 做离线图片理解，以 PostgreSQL + pgvector + Meilisearch 做混合智能搜索的本地 AI 照片库。**
