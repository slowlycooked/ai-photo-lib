

## 1. 背景与当前状态

ai-photo-lib 当前已经完成了若干关键基础能力：

1. **后端开始项目级 API 迁移**
   - 已新增或开始使用 `/projects/{project_id}/search`。
   - 已新增或开始使用 `/projects/{project_id}/tags`。
   - 旧的 global `ai / scan / search / tags` router 已标记 deprecated。
   - 前端部分 hook 已改为 project-scoped API。

2. **数据库已升级到 PostgreSQL + pgvector**
   - `photo_embeddings` 已从 placeholder 升级为真实向量结构。
   - 已引入 caption / tag / OCR 三类 embedding 字段。
   - Search 已开始支持 hybrid 检索。

3. **AI 分析能力已经可用，但需要稳定化**
   - 本地模型服务通过 OpenAI-compatible `/v1/chat/completions` 方式调用。
   - AI 输出曾出现非纯 JSON、包含解释文本、解析失败等问题。
   - Prompt 需要改为项目级可配置。

4. **近期高优先级需求**
   - embedding stale 判断。
   - embedding rebuild 去重。
   - search debug 能力。
   - 页面侧向量搜索测试。
   - 全局 / 项目级 Debug 模式。
   - AI Prompt 页面配置。
   - 扫描任务重跑 / 重扫。
   - 文件夹树状浏览模式。
   - 时间线浏览。
   - 原始图片下载。

因此，后续开发不应该继续做零散补丁，而应该围绕统一架构主链路推进：

```text
Project
  -> Settings
  -> Photo Library
  -> Scan Jobs
  -> AI Analysis
  -> Embeddings
  -> Search
  -> Debug
  -> Browser UX
```

---

## 2. 产品定位

ai-photo-lib 应被设计为一个 **多项目照片智能管理平台**，而不是单目录照片扫描工具。

一个项目可以代表一个独立照片语义域，例如：

- 建筑照片库
- 日常生活照片库
- 家庭相册库
- 户外旅行照片库
- 商业素材库
- 商品图库
- 设计参考图库

不同项目之间必须独立管理：

- 照片源路径
- AI Prompt
- AI 模型参数
- 标签体系
- EXIF / OCR / 语义字段
- 向量索引
- 搜索配置
- 扫描任务
- Debug 日志
- 页面筛选状态
- 统计数据

---

## 3. 核心架构原则

### 3.1 Project Isolation 是最高优先级

所有业务数据必须以 `project_id` 为作用域。

任何返回照片、标签、搜索结果、AI 分析结果、向量结果、扫描任务、统计数据、Debug Trace 的 API，都必须显式携带或推导当前项目上下文。

禁止新增以下类型的 global API：

```text
GET /photos
GET /search?q=xxx
GET /tags
GET /scan/jobs
GET /ai/analysis
```

所有新 API 必须采用 project-scoped 形式：

```text
GET /projects/{project_id}/photos
GET /projects/{project_id}/search
GET /projects/{project_id}/tags
GET /projects/{project_id}/scan/jobs
GET /projects/{project_id}/ai/analysis
GET /projects/{project_id}/embeddings
```

后端查询必须始终带：

```sql
WHERE project_id = :project_id
```

所有唯一约束必须是项目级唯一：

```sql
UNIQUE(project_id, photo_id)
UNIQUE(project_id, file_path_relative)
UNIQUE(project_id, tag_name)
UNIQUE(project_id, folder_path_relative)
```

---

### 3.2 配置驱动，禁止 hardcode

所有运行参数必须来自配置文件、环境变量或项目级数据库配置。

禁止 hardcode：

- AI base URL
- AI model name
- Prompt
- response schema
- embedding model
- embedding dimension
- vector topK
- hybrid search weight
- timeout
- retry count
- debug level
- media root path
- thumbnail path
- scan batch size
- API path fallback

新增配置项前必须检查现有配置体系，不能在 coding 时随意创造局部常量。

---

### 3.3 旧 global API 只保留兼容，不继续扩展

旧 router 可以保留 deprecated 行为，但不允许继续承载新功能。

原则：

- 新功能只放到 project router。
- deprecated router 中增加 warning log。
- deprecated router 不增加新参数。
- deprecated router 不作为前端默认调用路径。
- 前端 hook 不允许 fallback 到 deprecated API。

---

### 3.4 Search 必须可解释

语义搜索和 hybrid search 不能是黑盒。

Debug 开启时，页面和日志必须能看到：

- 用户输入 query。
- query normalization 结果。
- search mode。
- keyword branch 参数。
- vector branch 参数。
- query embedding 是否生成成功。
- vector dimension。
- vector distance / similarity。
- keyword score。
- semantic score。
- hybrid score。
- rerank 过程。
- 命中的 photo id。
- 命中的 caption / tags / OCR / path / EXIF。
- 每张图排序原因。
- 耗时拆分。

---

### 3.5 AI 输出必须可审计、可恢复

图片分析模型必须被当成“不稳定 JSON 生产者”。

必须具备：

- Prompt 强约束。
- raw output 保存。
- JSON 清洗。
- JSON parse fallback。
- schema validate。
- error 结构化保存。
- 页面查看失败原因。
- 支持失败重试。
- 支持选中照片重扫。
- 支持全量重扫。

---

## 4. 总体架构

```text
Frontend React
│
├── Project Shell
│   ├── Project Dashboard
│   ├── Photo Browser
│   │   ├── Grid View
│   │   ├── Folder Tree Filter
│   │   ├── Timeline Filter
│   │   └── Tag Filter
│   ├── Search Lab
│   │   ├── Keyword Search
│   │   ├── Semantic Search
│   │   ├── Hybrid Search
│   │   └── Debug Panel
│   ├── AI Settings
│   │   ├── Provider Config
│   │   ├── Prompt Config
│   │   ├── Response Schema
│   │   └── Test Analyze
│   ├── Scan Jobs
│   │   ├── Library Scan
│   │   ├── AI Rescan
│   │   ├── Embedding Rebuild
│   │   └── Job Detail
│   └── Debug Console
│
Backend FastAPI
│
├── Routers
│   ├── projects
│   ├── project_photos
│   ├── project_scan
│   ├── project_ai
│   ├── project_search
│   ├── project_tags
│   ├── project_embeddings
│   ├── project_settings
│   └── project_debug
│
├── Domain Services
│   ├── ProjectService
│   ├── ProjectSettingsService
│   ├── PhotoLibraryService
│   ├── FolderTreeService
│   ├── TimelineService
│   ├── ScanService
│   ├── AIAnalysisService
│   ├── EmbeddingService
│   ├── SearchService
│   ├── TagService
│   └── DebugTraceService
│
├── Infrastructure
│   ├── PostgreSQL
│   ├── pgvector
│   ├── File System Reader
│   ├── Thumbnail Generator
│   ├── AI Model HTTP Client
│   ├── Embedding Client
│   └── Structured Logger
│
└── Migration
    └── Alembic
```

---

## 5. Backend Design

### 5.1 Router 分层

推荐 router 命名方式：

```text
/api/projects
/api/projects/{project_id}/photos
/api/projects/{project_id}/scan
/api/projects/{project_id}/ai
/api/projects/{project_id}/search
/api/projects/{project_id}/tags
/api/projects/{project_id}/embeddings
/api/projects/{project_id}/settings
/api/projects/{project_id}/debug
```

禁止新功能继续放入：

```text
/api/search
/api/tags
/api/scan
/api/ai
```

旧 router 仅做 deprecated compatibility。

---

### 5.2 ProjectService

#### 职责

- 创建项目。
- 更新项目基础信息。
- 删除或归档项目。
- 获取项目列表。
- 获取项目 dashboard。
- 校验 project 是否存在。
- 提供统一 project guard。

#### API

```text
GET    /projects
POST   /projects
GET    /projects/{project_id}
PATCH  /projects/{project_id}
DELETE /projects/{project_id}
GET    /projects/{project_id}/dashboard
```

#### Dashboard 返回字段

```json
{
  "project_id": 1,
  "photo_count": 12000,
  "analyzed_photo_count": 10000,
  "embedding_ready_count": 9200,
  "embedding_stale_count": 300,
  "embedding_failed_count": 20,
  "failed_analysis_count": 120,
  "scan_job_count": 42,
  "last_scan_at": "2026-05-20T10:00:00Z",
  "last_ai_analyze_at": "2026-05-20T11:00:00Z",
  "last_embedding_rebuild_at": "2026-05-20T12:00:00Z",
  "tag_count": 340,
  "folder_count": 96,
  "date_range": {
    "min_taken_at": "2018-01-01T00:00:00Z",
    "max_taken_at": "2026-05-01T00:00:00Z"
  }
}
```

---

### 5.3 ProjectSettingsService

项目配置应拆成多个 logical section，而不是所有字段塞进一个不可控 JSON。

#### 页面结构

```text
Project Settings
├── Basic
├── Photo Library
├── AI Analyze
├── Embedding
├── Search
├── Debug
└── Advanced
```

#### 聚合 API

```text
GET   /projects/{project_id}/settings
PATCH /projects/{project_id}/settings
```

#### 内部配置模块

```text
project_library_settings
project_ai_settings
project_embedding_settings
project_search_settings
project_debug_settings
```

#### 设计要求

1. 项目配置可以 override 全局默认配置。
2. API 返回的是“当前有效配置”，即 global default + project override 的合并结果。
3. 页面保存时只更新用户显式修改的字段。
4. Debug 开启时，需要输出 effective config snapshot。
5. Prompt 修改后不自动重扫历史照片。

---

### 5.4 PhotoLibraryService

#### 职责

- 管理项目图片源目录。
- 扫描文件系统。
- 保存相对路径。
- 保存文件元数据。
- 构建文件夹树。
- 生成缩略图。
- 提供原图下载。
- 检查文件是否移动、删除或更新。

#### Photo 关键字段

```text
photos
├── id
├── project_id
├── file_path_relative
├── folder_path_relative
├── filename
├── extension
├── file_size
├── file_mtime
├── content_hash
├── width
├── height
├── taken_at
├── camera_make
├── camera_model
├── lens_model
├── gps_latitude
├── gps_longitude
├── thumbnail_path
├── scan_status
├── created_at
└── updated_at
```

#### 路径设计

后端可以存储容器内绝对路径，但 API 不应该默认暴露宿主机真实路径。

前端展示使用：

```text
file_path_relative
folder_path_relative
filename
```

原图下载必须通过后端 project-scoped API：

```text
GET /projects/{project_id}/photos/{photo_id}/download
```

下载 API 必须校验：

1. photo 属于 project。
2. 文件存在。
3. 文件路径仍在项目 library root 下。
4. 不允许通过 path traversal 访问任意文件。

---

### 5.5 FolderTreeService

文件夹浏览是并行过滤器，不替代搜索。

#### 数据来源

扫描照片时保存：

```text
file_path_relative
folder_path_relative
filename
```

#### API

```text
GET /projects/{project_id}/folders/tree
GET /projects/{project_id}/photos?folder_path=xxx&include_children=true
```

#### Folder Node 返回结构

```json
{
  "path": "2025/travel/japan",
  "name": "japan",
  "photo_count": 123,
  "children_count": 4,
  "children": []
}
```

#### 查询规则

- `include_children=false`：只返回当前目录直属照片。
- `include_children=true`：返回当前目录及所有子目录照片。
- folder filter 可以与 tag/date/search query 组合使用。

---

### 5.6 TimelineService

Timeline 是照片浏览体验的一部分。

#### 时间来源优先级

```text
EXIF taken_at
  -> file_mtime
  -> scan created_at
```

#### API

```text
GET /projects/{project_id}/timeline
GET /projects/{project_id}/photos?date_from=xxx&date_to=xxx
```

#### Timeline 返回示例

```json
{
  "buckets": [
    {
      "year": 2026,
      "month": 5,
      "count": 320
    },
    {
      "year": 2026,
      "month": 4,
      "count": 210
    }
  ]
}
```

---

## 6. Scan Job Design

### 6.1 Job 类型

扫描任务需要从“按钮触发函数”升级为“可观察、可重跑、可恢复的 job”。

建议 job 类型：

```text
library_scan
metadata_refresh
thumbnail_rebuild
ai_analyze_missing
ai_rescan_selected
ai_rescan_failed
ai_rescan_all
embedding_build_missing
embedding_rebuild_stale
embedding_rebuild_selected
embedding_rebuild_all
```

---

### 6.2 scan_jobs 表

```text
scan_jobs
├── id
├── project_id
├── job_type
├── status
├── total_count
├── success_count
├── failed_count
├── skipped_count
├── created_at
├── started_at
├── finished_at
├── created_by
├── config_snapshot
├── error_message
└── updated_at
```

`status` 枚举：

```text
pending
running
completed
failed
cancelled
partial_success
```

---

### 6.3 scan_job_items 表

```text
scan_job_items
├── id
├── project_id
├── job_id
├── photo_id
├── item_type
├── status
├── step
├── retry_count
├── error_message
├── started_at
├── finished_at
└── updated_at
```

`status` 枚举：

```text
pending
running
success
failed
skipped
```

---

### 6.4 重扫策略

| 操作 | 行为 |
|---|---|
| Library Scan | 扫描新文件，更新文件元数据 |
| Metadata Refresh | 重新读取 EXIF / 文件属性 |
| AI Analyze Missing | 只分析没有 AI 分析结果的照片 |
| AI Rescan Selected | 重新分析选中照片 |
| AI Rescan Failed | 只重跑 AI 失败照片 |
| AI Rescan All | 清理或覆盖已有 AI 分析并全量重跑 |
| Embedding Build Missing | 只生成缺失 embedding |
| Embedding Rebuild Stale | 只重建 stale embedding |
| Embedding Rebuild Selected | 重建选中照片 embedding |
| Embedding Rebuild All | 全量重建 embedding |

---

### 6.5 Job Detail 页面

Job Detail 必须展示：

- job 类型。
- 当前状态。
- 总数。
- 成功数。
- 失败数。
- 跳过数。
- 开始时间。
- 结束时间。
- 配置快照。
- 失败 item 列表。
- 每个失败 item 的 error。
- 可操作按钮：retry failed / cancel / rebuild stale。

---

## 7. AI Analysis Design

### 7.1 AI 配置模型

```text
project_ai_settings
├── id
├── project_id
├── provider
├── base_url
├── model_name
├── prompt_template
├── response_schema
├── temperature
├── max_tokens
├── timeout_seconds
├── retry_count
├── prompt_version
├── enabled
├── created_at
└── updated_at
```

#### provider 示例

```text
llama_cpp_openai_compatible
openai_compatible
custom_http
```

当前本地模型服务可以继续视为 OpenAI-compatible chat completion provider。

---

### 7.2 AI 调用流程

```text
photo file
  -> load project AI settings
  -> build prompt
  -> call model HTTP endpoint
  -> receive raw output
  -> save raw output
  -> clean output
  -> parse JSON
  -> validate response schema
  -> normalize tags
  -> save photo_ai_analysis
  -> mark embedding stale
```

---

### 7.3 photo_ai_analysis 表

```text
photo_ai_analysis
├── id
├── project_id
├── photo_id
├── caption
├── scene_tags
├── object_tags
├── activity_tags
├── people_count
├── ocr_text
├── location_clues
├── quality_tags
├── search_keywords
├── raw_output
├── parsed_json
├── confidence
├── analysis_status
├── analysis_error
├── model_name
├── prompt_version
├── analysis_version
├── analyzed_at
├── created_at
└── updated_at
```

`analysis_status` 枚举：

```text
pending
success
failed
parse_failed
schema_failed
skipped
```

---

### 7.4 JSON 解析要求

AI 输出必须经过以下步骤：

1. 保存 raw output。
2. 去除 markdown code fence。
3. 提取第一个合法 JSON object。
4. JSON parse。
5. schema validate。
6. 字段默认值补齐。
7. 类型标准化。
8. 保存 parsed_json。

解析失败时必须记录：

```text
project_id
photo_id
job_id
model_name
prompt_version
raw_output
error_message
duration_ms
```

---

### 7.5 Prompt 管理

Prompt 是项目级配置，不允许写死在代码中。

Prompt 修改后：

1. 新照片使用新 Prompt。
2. 历史照片不会自动重扫。
3. 页面提示用户可以选择：
   - 只影响后续扫描。
   - 重扫失败照片。
   - 重扫选中照片。
   - 全量重扫。

---

## 8. Embedding Design

### 8.1 photo_embeddings 表

```text
photo_embeddings
├── id
├── project_id
├── photo_id
├── embedding_model
├── embedding_dimension
├── caption_embedding
├── tag_embedding
├── ocr_embedding
├── caption_text_hash
├── tag_text_hash
├── ocr_text_hash
├── analysis_version
├── prompt_version
├── embedding_status
├── embedding_error
├── embedded_at
├── created_at
└── updated_at
```

建议唯一约束：

```sql
UNIQUE(project_id, photo_id, embedding_model)
```

如果未来允许多个模型并存，可以增加：

```text
is_active
```

---

### 8.2 embedding_status 枚举

```text
missing
pending
success
failed
stale
skipped
```

---

### 8.3 Stale 判断

Embedding 是否 stale 不能只看向量是否存在。

至少需要比较：

```text
caption_text_hash
tag_text_hash
ocr_text_hash
embedding_model
embedding_dimension
analysis_version
prompt_version
```

判断规则：

```text
embedding 不存在
  -> stale / missing

AI analysis 文本变化
  -> stale

embedding_model 变化
  -> stale

embedding_dimension 变化
  -> stale

prompt_version 变化且项目设置要求重建语义索引
  -> stale

embedding_status = failed 且允许 retry
  -> rebuild candidate
```

---

### 8.4 Rebuild 去重

同一项目、同一照片、同一 embedding model，不应重复进入同一个 active rebuild job。

去重维度：

```text
project_id
photo_id
embedding_model
job_type
active_status
```

active status 包括：

```text
pending
running
```

---

### 8.5 Embedding Build 流程

```text
load photo_ai_analysis
  -> build caption text
  -> build tag text
  -> build OCR text
  -> hash each text
  -> compare existing embedding state
  -> skip if fresh
  -> call embedding model
  -> validate dimension
  -> upsert photo_embeddings
  -> update status
```

---

## 9. Search Design

### 9.1 搜索模式

SearchService 必须统一支持：

```text
keyword
semantic
hybrid
auto
```

前端 Search Page 提供：

```text
Search Mode
├── Auto
├── Keyword Only
├── Semantic Only
└── Hybrid
```

---

### 9.2 Search API

```text
GET /projects/{project_id}/search
```

Query 参数建议：

```text
q
mode
limit
offset
tags
folder_path
include_children
date_from
date_to
has_ai_analysis
has_embedding
debug
```

返回结构：

```json
{
  "items": [],
  "total": 100,
  "limit": 50,
  "offset": 0,
  "debug": null
}
```

Debug 关闭时，`debug` 应为空或不存在。

---

### 9.3 Keyword Branch

Keyword branch 负责传统关键词匹配。

匹配字段：

```text
filename
file_path_relative
folder_path_relative
caption
scene_tags
object_tags
activity_tags
quality_tags
search_keywords
ocr_text
location_clues
EXIF camera fields
```

输入：

```text
project_id
query
filters
limit
```

输出：

```text
photo_id
keyword_score
matched_fields
```

---

### 9.4 Vector Branch

Vector branch 负责语义匹配。

向量来源：

```text
caption_embedding
tag_embedding
ocr_embedding
```

输入：

```text
project_id
query_embedding
embedding_model
top_k
filters
```

输出：

```text
photo_id
caption_similarity
tag_similarity
ocr_similarity
semantic_score
```

语义分数建议：

```text
semantic_score =
  caption_similarity * caption_vector_weight +
  tag_similarity * tag_vector_weight +
  ocr_similarity * ocr_vector_weight
```

---

### 9.5 Hybrid Merge / Rerank

Hybrid search 由三段组成：

```text
keyword branch
  + vector branch
  -> merge
  -> rerank
```

最终分数建议：

```text
final_score =
  keyword_score * keyword_weight +
  semantic_score * semantic_weight +
  exact_tag_boost +
  folder_boost +
  recency_boost
```

所有 weight 应来自项目配置。

---

### 9.6 Search 配置

```text
project_search_settings
├── id
├── project_id
├── default_search_mode
├── keyword_weight
├── semantic_weight
├── caption_vector_weight
├── tag_vector_weight
├── ocr_vector_weight
├── top_k
├── min_similarity
├── enable_recency_boost
├── enable_exact_tag_boost
├── debug_enabled
├── created_at
└── updated_at
```

---

## 10. Search Debug Design

### 10.1 Debug Response

Debug 开启时，Search API 返回：

```json
{
  "debug": {
    "request_id": "uuid",
    "project_id": 1,
    "input_query": "有猫的家庭照片",
    "normalized_query": "猫 家庭 照片",
    "search_mode": "hybrid",
    "effective_config": {},
    "keyword_branch": {
      "matched_count": 12,
      "duration_ms": 24
    },
    "vector_branch": {
      "embedding_model": "xxx",
      "query_embedding_dimension": 1024,
      "matched_count": 50,
      "duration_ms": 120
    },
    "merge_branch": {
      "before_merge_count": 62,
      "after_merge_count": 50,
      "duration_ms": 8
    },
    "results_debug": [
      {
        "photo_id": 123,
        "keyword_score": 0.62,
        "semantic_score": 0.84,
        "caption_similarity": 0.81,
        "tag_similarity": 0.88,
        "ocr_similarity": 0.1,
        "final_score": 0.78,
        "matched_fields": ["caption", "object_tags"],
        "reason": "caption and tag vectors strongly matched query"
      }
    ],
    "total_duration_ms": 160
  }
}
```

---

### 10.2 Debug Trace 持久化

可选表：

```text
search_debug_traces
├── id
├── project_id
├── request_id
├── query
├── search_mode
├── effective_config
├── debug_payload
├── duration_ms
├── created_at
└── expires_at
```

Debug trace 默认可配置过期时间，避免数据库无限增长。

---

### 10.3 Debug 安全原则

不能暴露：

- 密钥。
- token。
- 完整环境变量。
- 宿主机敏感绝对路径。
- 用户不应该看到的容器内部路径。

Debug 可以暴露：

- project_id。
- photo_id。
- query。
- score。
- branch duration。
- sanitized SQL summary。
- model name。
- embedding dimension。

---

## 11. Frontend Design

### 11.1 URL 结构

推荐：

```text
/projects
/projects/:projectId
/projects/:projectId/photos
/projects/:projectId/search
/projects/:projectId/tags
/projects/:projectId/scan
/projects/:projectId/scan/:jobId
/projects/:projectId/settings/basic
/projects/:projectId/settings/library
/projects/:projectId/settings/ai
/projects/:projectId/settings/embedding
/projects/:projectId/settings/search
/projects/:projectId/settings/debug
```

---

### 11.2 Frontend Hook 规则

推荐 hook：

```text
useCurrentProject()
useProjectSettings(projectId)
useProjectPhotos(projectId)
useProjectSearch(projectId)
useProjectTags(projectId)
useProjectScanJobs(projectId)
useProjectAISettings(projectId)
useProjectEmbeddingStatus(projectId)
```

规则：

1. 没有 `projectId` 时不要请求业务 API。
2. 不允许 fallback 到 global API。
3. API error 必须在页面上可见。
4. mutation 必须有 loading / success / error 状态。

---

### 11.3 Project Dashboard

Dashboard 展示：

- 照片总数。
- 已 AI 分析数量。
- AI 失败数量。
- embedding ready 数量。
- embedding stale 数量。
- 最近扫描时间。
- 最近 AI 分析时间。
- 最近 embedding rebuild 时间。
- 标签数量。
- 文件夹数量。
- 时间范围。

---

### 11.4 Photo Browser

页面结构：

```text
Photo Browser
├── Left Sidebar
│   ├── Folder Tree
│   ├── Tag Filter
│   └── Date Filter
├── Main Toolbar
│   ├── Sort
│   ├── View Mode
│   ├── Selected Actions
│   └── Download
└── Photo Grid
```

能力：

- 文件夹筛选。
- 标签筛选。
- 日期筛选。
- AI 状态筛选。
- embedding 状态筛选。
- 选中照片重扫。
- 选中照片 rebuild embedding。
- 原图下载。

---

### 11.5 Search Lab

Search Page 不只是搜索框，而是搜索实验台。

页面结构：

```text
Search Lab
├── Query Input
├── Search Mode Selector
├── Filters
│   ├── Tags
│   ├── Folder
│   ├── Date Range
│   ├── Has AI Analysis
│   └── Has Embedding
├── Result Grid
└── Debug Panel
```

Debug Panel 仅在 Debug 开启时显示。

每个结果卡片在 Debug 模式下显示：

- final score。
- keyword score。
- semantic score。
- caption similarity。
- tag similarity。
- OCR similarity。
- matched fields。
- ranking reason。

---

### 11.6 AI Settings Page

页面结构：

```text
AI Settings
├── Provider Config
│   ├── provider
│   ├── base_url
│   ├── model_name
│   ├── timeout
│   └── retry
├── Prompt Editor
│   ├── prompt_template
│   ├── response_schema
│   └── prompt_version
├── Test Analyze
│   ├── select photo
│   ├── run test
│   ├── raw output
│   ├── parsed JSON
│   └── validation result
└── Actions
    ├── Save
    ├── Reset
    └── Rescan Options
```

保存 Prompt 后页面提示：

```text
Prompt 已更新。已有 AI 分析不会自动变化。
你可以选择：
- 只影响后续扫描
- 重扫失败照片
- 重扫选中照片
- 全量重扫
```

---

### 11.7 Scan Jobs Page

页面结构：

```text
Scan Jobs
├── New Job Actions
│   ├── Scan Library
│   ├── Analyze Missing
│   ├── Rescan Failed
│   ├── Rebuild Missing Embeddings
│   └── Rebuild Stale Embeddings
├── Job List
└── Job Detail
```

按钮必须有明确反馈：

```text
idle
loading
success
warning
error
```

禁止点击后无任何页面反馈。

---

## 12. Error Handling Design

### 12.1 API Error Response

统一错误结构：

```json
{
  "error": {
    "code": "AI_JSON_PARSE_FAILED",
    "message": "Cannot parse model output as JSON",
    "details": {},
    "request_id": "uuid"
  }
}
```

### 12.2 常见错误码

```text
PROJECT_NOT_FOUND
PHOTO_NOT_FOUND
SCAN_JOB_NOT_FOUND
AI_PROVIDER_UNAVAILABLE
AI_TIMEOUT
AI_JSON_PARSE_FAILED
AI_SCHEMA_VALIDATION_FAILED
EMBEDDING_DIMENSION_MISMATCH
EMBEDDING_BUILD_FAILED
SEARCH_EMBEDDING_FAILED
INVALID_PROJECT_SETTINGS
FILE_NOT_FOUND
FILE_ACCESS_DENIED
MIGRATION_REQUIRED
```

---

## 13. Logging Design

日志必须结构化，至少包含：

```text
request_id
project_id
photo_id
job_id
operation
status
duration_ms
error_code
error_message
```

Search debug 和 backend log 通过 `request_id` 关联。

Job item 和日志通过 `job_id + photo_id` 关联。

---

## 14. Database Migration Discipline

当前项目已经出现过模型字段与数据库字段不一致的问题，例如代码查询 `photo_embeddings.id`，但数据库表中没有该列。

后续必须严格遵守：

1. SQLAlchemy model 修改必须配套 Alembic migration。
2. Alembic migration 必须可从当前数据库升级。
3. 不允许只改 model 不改 migration。
4. 不允许只改 migration 不改 model。
5. pgvector dimension 必须和配置一致。
6. embedding model / dimension 变更通过 stale + rebuild 机制处理，不能直接破坏旧数据。
7. migration 需要考虑已有数据 backfill。
8. 关键表必须包含 `created_at / updated_at`。
9. 启动阶段可以增加 schema sanity check。

---

## 15. Security and Safety

### 15.1 文件访问安全

下载或读取原图时必须校验：

- photo 属于当前 project。
- 文件路径位于项目 library root 内。
- 禁止 `../` path traversal。
- 不暴露宿主机敏感绝对路径。

### 15.2 Debug 安全

Debug 不能返回：

- 密钥。
- token。
- 完整环境变量。
- 数据库连接串。
- 用户密码。
- 宿主机敏感路径。

### 15.3 Project 数据隔离

任何 API 都不能因为 filter、join、search、tag aggregation 导致跨项目数据泄露。

特别注意：

- tags aggregation。
- photo_ai_analysis join photos。
- embeddings join photos。
- scan job item 查询。
- folder tree aggregation。
- timeline aggregation。

---

## 16. Execution Plan

### Phase 1：Project Settings + Debug 基础

目标：把后续所有功能的地基打稳。

任务：

1. 完成 project settings 聚合 API。
2. AI 配置进入项目设置页。
3. Search 配置进入项目设置页。
4. Debug 配置进入项目设置页。
5. 所有操作按钮增加 loading / success / warning / error 状态。
6. Search API 支持 debug payload。
7. Search 页面展示 Debug Panel。

验收：

- 无 projectId 时不请求业务 API。
- Debug 关闭时 response 无 debug payload。
- Debug 开启时 search 页面能看到完整输入输出。
- 修改 AI Prompt 后不会误触发全量重扫。

---

### Phase 2：Scan / Rescan / Rebuild 稳定化

目标：让扫描、重扫、embedding rebuild 可控、可观察、可恢复。

任务：

1. 新增 job 类型。
2. 增加 job detail 页面。
3. 实现 rescan failed / selected / all。
4. 实现 embedding missing / stale / selected / all rebuild。
5. 实现 stale 判断。
6. 实现 rebuild 去重。

验收：

- 同一个项目内不会重复创建相同 rebuild item。
- 一个 photo 的 embedding 状态可解释。
- job 失败后可以看到具体 photo 和 error。
- 重跑不会污染其他项目。

---

### Phase 3：Search Lab 完整化

目标：让 keyword / semantic / hybrid 可测试、可调参。

任务：

1. Search mode selector。
2. Search debug panel。
3. 每个结果展示 score breakdown。
4. 页面支持向量搜索测试场景。
5. 支持 folder / tag / date filter 与搜索组合。
6. Search API 支持 request_id。

验收：

- 输入“有猫的家庭照片”，能看到 semantic branch 命中原因。
- 输入“塔楼 夜景”，能看到 keyword 和 vector 各自贡献。
- 输入文件夹过滤时，只返回该项目该文件夹下照片。
- Debug 日志和页面 request_id 对得上。

---

### Phase 4：Folder Tree + Timeline Browser

目标：补齐用户自然浏览体验。

任务：

1. 扫描时保存 folder path。
2. 构建 folder tree API。
3. 前端左侧 folder tree。
4. 支持 include children。
5. 增加右侧 timeline。
6. 支持时间范围过滤。
7. 支持原图下载。

验收：

- 文件夹树和照片库真实目录一致。
- 点击文件夹不会影响 search 的语义逻辑，只作为过滤器。
- 时间线拖动后结果正确刷新。
- 下载原图不暴露宿主机绝对路径。

---

## 17. Cursor AI Coding Instruction

以下内容可直接给 Cursor / AI coding agent 作为开发指令。

---

### Cursor Instruction

你正在开发 `ai-photo-lib`。这是一个多项目照片 AI 管理系统，不是单照片库工具。后续所有改动必须遵守以下架构约束。

#### 1. Project Isolation

所有业务数据和 API 必须以 `project_id` 为作用域。

禁止新增 global API。

禁止任何跨项目查询。

所有查询 photos、tags、AI analysis、embeddings、scan jobs、search results、debug traces 时必须显式过滤：

```sql
project_id = current_project_id
```

所有唯一约束必须是项目级唯一，例如：

```sql
UNIQUE(project_id, photo_id)
UNIQUE(project_id, file_path_relative)
UNIQUE(project_id, tag_name)
```

旧的 global routers 只允许保留 deprecated 兼容，不允许继续扩展。

---

#### 2. Configuration Discipline

所有运行参数必须来自配置文件、环境变量或项目级 settings。

禁止 hardcode：

```text
AI base URL
model name
prompt
embedding model
embedding dimension
search weight
topK
timeout
retry count
debug level
file path
thumbnail path
```

新增配置项前，先检查是否已有配置。不要随意创建新配置字段。

---

#### 3. AI Settings

AI Prompt 必须是项目级配置。

实现或修改 AI analyze 时，必须从 project settings 中读取：

```text
provider
base_url
model_name
prompt_template
response_schema
temperature
max_tokens
timeout_seconds
retry_count
prompt_version
```

AI 输出必须保存 raw output、parse result 和 error 信息。

JSON parse 失败时不能静默失败，必须记录：

```text
project_id
photo_id
job_id
raw_output
error_message
duration_ms
```

---

#### 4. Embedding Rules

`photo_embeddings` 是真实向量表，必须和 Alembic migration 保持一致。

修改 SQLAlchemy model 时必须同步 migration。

Embedding stale 判断至少基于：

```text
caption_text_hash
tag_text_hash
ocr_text_hash
embedding_model
embedding_dimension
analysis_version
prompt_version
```

不要重复 rebuild 同一 photo 的同一 embedding model。

所有 embedding 查询必须带 project_id。

---

#### 5. Search Rules

SearchService 必须支持：

```text
keyword
semantic
hybrid
auto
```

Hybrid search 应拆分为：

```text
keyword branch
vector branch
merge/rerank branch
```

Debug 开启时，API response 需要返回：

```text
input_query
normalized_query
effective_config
keyword_score
semantic_score
caption_similarity
tag_similarity
ocr_similarity
final_score
matched_fields
duration_ms
request_id
```

Debug 关闭时，不要返回 debug payload。

---

#### 6. Frontend Rules

前端所有业务页面必须在 project context 下运行。

推荐 URL：

```text
/projects/:projectId/photos
/projects/:projectId/search
/projects/:projectId/tags
/projects/:projectId/scan
/projects/:projectId/settings/ai
/projects/:projectId/settings/search
/projects/:projectId/settings/debug
```

Hook 不允许 fallback 到 global API。

按钮必须有明确状态：

```text
idle
loading
success
warning
error
```

不能出现点击按钮后页面无反馈。

---

#### 7. Folder Tree

文件夹浏览是并行过滤器，不替代搜索。

扫描时必须保存：

```text
file_path_relative
folder_path_relative
filename
```

Folder tree API 必须 project-scoped：

```text
GET /projects/{project_id}/folders/tree
```

选择 folder 后，只作为 filters 传入 photo/search API。

---

#### 8. Migration Safety

任何数据库结构变化都必须：

1. 修改 SQLAlchemy model。
2. 新增 Alembic migration。
3. 确认 migration 可从当前数据库升级。
4. 确认 downgrade 或兼容策略。
5. 确认 pgvector dimension 与配置一致。
6. 确认不会破坏已有项目数据。

特别注意不要再次出现 model 中有 `id`，但数据库表中没有 `id` 的情况。

---

#### 9. Implementation Priority

按以下顺序开发：

```text
1. Project settings 聚合 API 和页面
2. Debug 开关和 Search Debug Panel
3. Embedding stale 判断
4. Rebuild 去重
5. Scan Job Detail 和 Rescan
6. Folder Tree Browser
7. Timeline Browser
8. 原图下载
```

每完成一个阶段，必须保证：

```text
Python compile pass
Alembic migration pass
TypeScript build pass
project isolation test pass
existing search flow not broken
```

---

## 18. Final Summary

后续 ai-photo-lib 的核心演进方向是：

```text
从“能扫照片、能打标签、能搜”
升级为
“多项目隔离、Prompt 可配置、AI 输出可审计、向量检索可调试、扫描任务可恢复、浏览体验完整”的照片 AI 管理系统。
```

最重要的工程原则是：

1. 一切围绕 `project_id` 隔离。
2. 一切运行参数配置化。
3. 一切 AI 输出可审计。
4. 一切向量搜索可解释。
5. 一切数据库变更必须有 migration。
6. 一切页面操作必须有明确反馈。

