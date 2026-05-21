# ai-photo-lib High-Level Architecture Upgrade Design

> Version: vNext
> Scope: 系统命名收敛、服务层抽象、数据读写层、日志读写层、配置治理、任务体系与前后端架构边界

---

## 1. 设计背景

ai-photo-lib 已经从一个单目录照片扫描工具，逐步演进为一个支持多项目、多照片库、多 AI 配置、多 Prompt、多检索方式的智能照片管理系统。

当前系统已经具备：

* 项目级照片库管理
* 项目级照片扫描
* 项目级 AI 分析
* 项目级 Prompt 配置
* PostgreSQL + pgvector 向量检索
* keyword / vector / hybrid 搜索
* 文件夹树浏览
* 时间线浏览
* 原图下载
* 全局 Debug Mode / Debug Matrix

随着功能增加，现有代码开始出现架构膨胀：

* Router 承担过多业务逻辑
* Service 层边界不清晰
* 数据读写散落在 router、service、worker 中
* 日志配置、日志上下文、debug policy、runtime state 混在一起
* Worker 同时负责任务调度、业务处理、模型调用、结果写入
* 前端 API client 越来越重
* Deprecated global API 仍然存在，需要避免继续扩展

本设计目标是将系统升级为一个稳定的、项目隔离的、可观测的 AI Photo Platform。

---

## 2. 架构升级目标

本次升级不是简单增加几个 service 文件，而是建立清晰的系统边界。

目标架构需要满足：

1. 项目隔离明确
   所有照片、AI 分析、向量、标签、搜索、任务、日志、配置都必须以 `project_id` 为作用域。

2. 业务边界清晰
   Router、Application Service、Domain Policy、Repository、Infrastructure Adapter 各司其职。

3. 数据读写收敛
   所有 DB 查询和写入通过 Repository / Query Service 管理，避免重复 SQL 和遗漏 `project_id`。

4. 日志可观测
   运行日志、业务事件日志、Search Debug Trace、AI Job Trace、Scan Task Trace 分层管理。

5. 配置治理统一
   环境配置、全局运行配置、项目级配置、最终生效配置统一解析。

6. API 命名收敛
   所有新功能只走 `/projects/{project_id}/...` 路径。

7. 可渐进落地
   先拆边界，再抽服务，再迁移数据读写和日志，不做一次性大爆炸重构。

---

## 3. 核心架构原则

### 3.1 Project Isolation First

项目隔离是系统最高优先级原则。

所有业务数据必须显式绑定 `project_id`：

```text
photos
photo_ai_analysis
photo_embeddings
ai_jobs
project_prompt_templates
project_ai_settings
project_folders
search_debug_runs
task_runs
business_event_logs
```

所有业务 API 必须使用 project-scoped 形式：

```text
/projects/{project_id}/photos
/projects/{project_id}/folders
/projects/{project_id}/scan
/projects/{project_id}/ai
/projects/{project_id}/embeddings
/projects/{project_id}/search
/projects/{project_id}/tags
/projects/{project_id}/debug
```

旧 global API 只保留兼容，不继续扩展。

---

### 3.2 Router Thin Layer

Router 只负责 HTTP 层职责：

* 参数解析
* Depends 注入
* Request / Response schema 映射
* HTTPException 映射
* 调用 Application Service

Router 不应该直接承载：

* 多表查询
* 状态机流转
* 任务编排
* 文件系统扫描
* 模型调用
* 向量检索逻辑
* prompt 渲染
* debug trace 生成

---

### 3.3 Application Service Orchestration

Application Service 是业务用例入口，负责：

* 事务边界
* 多 repository 协作
* 业务流程编排
* 调用 domain policy
* 调用 infrastructure client
* 写业务事件日志
* 返回业务 DTO

典型 Application Service：

```text
ProjectAppService
PhotoAppService
ScanAppService
AIJobAppService
AIAnalysisAppService
EmbeddingAppService
SearchAppService
SettingsAppService
DebugAppService
```

---

### 3.4 Repository / Query Service Data Boundary

所有数据写入通过 Repository 完成。

所有复杂读模型通过 Query Service 完成。

Repository 偏写模型：

```text
ProjectRepository
PhotoRepository
FolderRepository
AIJobRepository
AIAnalysisRepository
EmbeddingRepository
PromptTemplateRepository
RuntimeSettingsRepository
```

Query Service 偏页面读取和聚合：

```text
PhotoQueryService
TimelineQueryService
TagQueryService
SearchQueryService
DashboardQueryService
DebugLogQueryService
```

---

### 3.5 Infrastructure Adapter Isolation

外部依赖必须通过 adapter 隔离：

```text
FileSystemReader
ImageMetadataReader
ThumbnailStore
VLMClient
EmbeddingClient
StructuredLogger
EventLogWriter
```

业务服务不直接依赖底层文件系统、HTTP client、pgvector SQL、Python logging 细节。

---

## 4. High-Level Target Architecture

```text
Frontend React
│
├── Project Shell
│   ├── Dashboard
│   ├── Photo Browser
│   ├── Folder Browser
│   ├── Timeline Browser
│   ├── Search Lab
│   ├── AI Jobs
│   ├── AI Settings
│   ├── Embedding Status
│   └── Debug Console
│
├── API Client Layer
│   ├── client.ts
│   ├── projects.ts
│   ├── photos.ts
│   ├── folders.ts
│   ├── scan.ts
│   ├── ai.ts
│   ├── embeddings.ts
│   ├── search.ts
│   ├── settings.ts
│   └── debug.ts
│
Backend FastAPI
│
├── Routers
│   ├── projects
│   ├── project_photos
│   ├── project_folders
│   ├── project_scan
│   ├── project_ai_jobs
│   ├── project_ai_settings
│   ├── project_prompt_templates
│   ├── project_embeddings
│   ├── project_search
│   ├── project_tags
│   └── project_debug
│
├── Application Services
│   ├── ProjectAppService
│   ├── PhotoAppService
│   ├── ScanAppService
│   ├── AIJobAppService
│   ├── AIAnalysisAppService
│   ├── EmbeddingAppService
│   ├── SearchAppService
│   ├── SettingsAppService
│   └── DebugAppService
│
├── Domain / Policy
│   ├── ProjectContext
│   ├── ProjectGuard
│   ├── ScanPolicy
│   ├── AIJobPolicy
│   ├── PromptPolicy
│   ├── EmbeddingPolicy
│   ├── SearchPolicy
│   └── DebugPolicy
│
├── Data Access
│   ├── UnitOfWork
│   ├── Repositories
│   └── Query Services
│
├── Infrastructure
│   ├── PostgreSQL / pgvector
│   ├── File System
│   ├── Thumbnail Generator
│   ├── VLM Client
│   ├── Embedding Client
│   ├── Runtime Settings Storage
│   └── Structured Logging
│
└── Worker
    └── Job Executor -> Application Services
```

---

## 5. Backend 模块设计

### 5.1 API Router 拆分

当前 project router 应拆为多个 project-scoped router：

```text
routers/projects.py
routers/project_photos.py
routers/project_folders.py
routers/project_scan.py
routers/project_ai_jobs.py
routers/project_ai_settings.py
routers/project_prompt_templates.py
routers/project_embeddings.py
routers/project_search.py
routers/project_tags.py
routers/project_debug.py
```

`projects.py` 只保留：

* list projects
* create project
* get project
* update project
* delete project
* project dashboard

其他能力按业务域拆出。

---

### 5.2 ProjectContext

引入统一上下文对象：

```text
ProjectContext
  project_id
  request_id
  task_id
  photo_id
  debug_mode
  effective_settings
```

所有 application service 显式接收 `ProjectContext`，禁止 service 内部隐式猜项目。

---

### 5.3 ProjectGuard

统一项目存在性和隔离校验：

```text
ProjectGuard
  require_active_project(project_id)
  require_project_photo(project_id, photo_id)
  require_project_folder(project_id, folder_id)
  require_project_prompt_template(project_id, template_id)
```

目标是替代散落在 router 内的 `_get_or_404()` 和临时查询。

---

### 5.4 UnitOfWork

引入 UnitOfWork 管理事务边界：

```text
UnitOfWork
  projects
  photos
  folders
  ai_jobs
  ai_analysis
  embeddings
  prompt_templates
  runtime_settings
  commit()
  rollback()
```

Application Service 使用 UnitOfWork，Router 不直接处理事务。

---

## 6. 数据读写层设计

### 6.1 Repository 层

Repository 负责实体读写，所有方法必须显式带 `project_id`。

示例职责：

```text
PhotoRepository
  get_project_photo(project_id, photo_id)
  upsert_scanned_photo(project_id, scanned_photo)
  update_thumbnail(project_id, photo_id, thumbnail_path)
  mark_ai_indexed(project_id, photo_id)

AIJobRepository
  enqueue_analysis_jobs(project_id, photo_ids)
  enqueue_embedding_jobs(project_id, photo_ids)
  claim_next_queued_job()
  mark_running(job_id)
  mark_success(job_id)
  mark_failed(job_id)

EmbeddingRepository
  get_by_project_photo(project_id, photo_id)
  upsert(project_id, photo_id, embedding_data)
  count_by_status(project_id)
```

---

### 6.2 Query Service 层

Query Service 负责页面聚合读取：

```text
PhotoQueryService
  list_project_photos()
  get_photo_detail()

TimelineQueryService
  get_monthly_counts()

TagQueryService
  get_tag_counts()

SearchQueryService
  keyword_candidates()
  vector_candidates()
  hydrate_results()

DashboardQueryService
  get_project_dashboard()

DebugLogQueryService
  list_system_events()
  get_search_debug_run()
```

Query Service 可以使用复杂 SQL，但必须封装在单独模块内，不进入 router。

---

## 7. 日志与 Debug 架构

### 7.1 日志分层

日志体系拆为两类：

1. Runtime Log
   使用 Python logging 输出到 stdout / container log。

2. Business Event Log
   写入数据库，供页面 Debug Console 查询。

---

### 7.2 logging 模块拆分

建议将现有日志逻辑拆成：

```text
infrastructure/logging/log_context.py
infrastructure/logging/sensitive_filter.py
infrastructure/logging/logging_setup.py
domain/debug_policy.py
infrastructure/logging/event_log_writer.py
```

职责分别为：

* `log_context.py`: request_id / project_id / task_id / photo_id 上下文
* `sensitive_filter.py`: token、DATABASE_URL、API key 脱敏
* `logging_setup.py`: logger group、formatter、handler、runtime level 应用
* `debug_policy.py`: OFF / BASIC / DEBUG / TRACE / CUSTOM 的行为派生
* `event_log_writer.py`: 写业务事件日志

---

### 7.3 Business Event Log

新增业务事件表：

```text
system_event_logs
  id
  project_id
  request_id
  task_id
  photo_id
  event_type
  level
  message
  payload_json
  source
  created_at
```

典型事件：

```text
project.created
scan.started
scan.completed
scan.failed
ai.job.created
ai.job.started
ai.job.completed
ai.job.failed
embedding.rebuild.started
embedding.failed
search.executed
search.vector_failed
settings.debug.updated
```

---

### 7.4 Search Debug Trace

Search debug 不应只靠普通日志。建议新增：

```text
search_debug_runs
  id
  project_id
  query
  mode
  normalized_query
  effective_config_json
  embedding_model
  embedding_dimension
  keyword_candidate_count
  vector_candidate_count
  merged_candidate_count
  total_duration_ms
  created_at

search_debug_items
  id
  run_id
  photo_id
  keyword_score
  vector_score
  rrf_score
  final_score
  match_source
  matched_tags
  explanation_json
```

DEBUG / TRACE 模式下，Search API 返回 `debug_run_id`，页面 Debug Panel 可查看完整检索链路。

---

## 8. 配置治理设计

### 8.1 三层配置模型

配置分为三层：

```text
EnvSettings
  部署级配置
  database_url
  default path
  default model endpoint
  default thumbnail path

GlobalRuntimeSettings
  运行时全局配置
  global debug config
  global search defaults
  global embedding defaults

ProjectEffectiveSettings
  项目最终生效配置
  global defaults + project overrides
```

---

### 8.2 ProjectSettingsResolver

新增统一解析器：

```text
ProjectSettingsResolver
  resolve(project_id) -> EffectiveProjectSettings
```

`EffectiveProjectSettings` 包含：

```text
library
ai
embedding
search
debug
```

所有 Scan、AI、Embedding、Search 都从 resolver 获取最终配置，不直接散落读取全局 settings。

---

### 8.3 配置变更原则

* 不允许在业务代码中新增隐式 hardcode
* 新配置必须进入 schema / migration / settings resolver
* Prompt、AI 参数、embedding 参数、search weight、debug matrix 均应可追踪
* 页面展示的是 effective config，而不只是 DB 原始字段

---

## 9. Search 架构设计

Search 应拆成以下组件：

```text
SearchAppService
SearchPolicy
KeywordSearchQuery
VectorSearchQuery
SearchResultHydrator
SearchDebugWriter
EmbeddingClient
```

Search 流程：

```text
1. 接收 query / mode / filters
2. 解析 ProjectContext
3. 读取 EffectiveProjectSettings
4. query normalization
5. keyword branch
6. vector branch
7. fallback policy
8. RRF / hybrid merge
9. hydrate photo result
10. 写 search debug trace
11. 返回 SearchResponse
```

Search Response 建议：

```json
{
  "query": "夜晚古建筑",
  "mode": "hybrid",
  "total": 12,
  "page": 1,
  "page_size": 50,
  "debug_run_id": 123,
  "items": []
}
```

---

## 10. Scan 架构设计

当前扫描逻辑应拆成：

```text
PhotoLibraryReader
ImageMetadataReader
FolderTreeService
ThumbnailService
ScanAppService
ScanRunRepository
```

职责：

```text
PhotoLibraryReader
  遍历照片源目录
  跳过 thumbnail 目录
  判断支持的图片后缀

ImageMetadataReader
  hash
  EXIF
  GPS
  image size

FolderTreeService
  ensure folder path
  recompute folder counts

ThumbnailService
  generate thumbnail

ScanAppService
  start scan
  run scan
  process file
  update scan state
  write event log
```

建议将 scan 状态从内存 dict 迁移为持久化：

```text
scan_runs
  id
  project_id
  status
  scanned
  inserted
  updated
  errors
  current_path
  started_at
  finished_at
  created_at
  updated_at
```

---

## 11. AI / Worker 架构设计

### 11.1 Worker 角色收敛

Worker 应定位为 Job Executor，不直接实现完整业务流程。

目标形态：

```text
Worker
  poll queued job
  claim job
  call AIJobAppService.process_job(job_id)
  sleep / shutdown
```

---

### 11.2 AIJobAppService

负责：

```text
enqueue_analysis_jobs
enqueue_reanalysis_jobs
enqueue_embedding_jobs
retry_failed_jobs
clear_failed_jobs
claim_next_job
process_job
process_analysis_job
process_embedding_job
```

---

### 11.3 AIAnalysisService

负责：

```text
resolve AI settings
resolve active prompt template
render prompt
call VLM client
parse JSON
validate schema
upsert analysis
emit event
```

---

### 11.4 EmbeddingAppService

负责：

```text
build embedding inputs
detect stale
enqueue rebuild jobs
upsert embeddings
count embedding status
emit event
```

---

## 12. 前端架构设计

### 12.1 API Client 拆分

当前 API client 应拆为：

```text
src/api/client.ts
src/api/types.ts
src/api/projects.ts
src/api/photos.ts
src/api/folders.ts
src/api/scan.ts
src/api/ai.ts
src/api/embeddings.ts
src/api/search.ts
src/api/settings.ts
src/api/debug.ts
```

主页面不再调用 deprecated global API。

---

### 12.2 Project Shell

前端页面建议以 Project Shell 组织：

```text
ProjectShell
  ProjectSelector
  ProjectNavigation
  ProjectContextProvider
  Outlet
```

项目级页面：

```text
DashboardPage
PhotoBrowserPage
FolderBrowserPage
SearchLabPage
AIJobsPage
AISettingsPage
EmbeddingStatusPage
ScanRunsPage
DebugConsolePage
```

---

## 13. 演进路线

### Phase 0: Safety Net

目标：保护现有行为。

任务：

* 增加 project isolation 测试
* 增加 search hybrid 测试
* 增加 debug settings roundtrip 测试
* 增加 AI job enqueue / retry 测试
* 增加 embedding stale 测试

---

### Phase 1: Router 拆分

目标：先拆 HTTP 边界，不改业务行为。

任务：

* 拆分 `projects.py`
* 保持原有 path / response_model / 行为不变
* `main.py` include 新 router
* Deprecated global router 不新增功能

---

### Phase 2: Repository / UnitOfWork

目标：收敛数据读写。

任务：

* 新增 repositories
* 新增 UnitOfWork
* Router / Service 中重复 DB 查询逐步迁移
* 所有 repository 方法显式要求 `project_id`

---

### Phase 3: Application Service

目标：收敛业务流程。

任务：

* 新增 PhotoAppService
* 新增 ScanAppService
* 新增 AIJobAppService
* 新增 EmbeddingAppService
* 新增 SearchAppService
* Worker 改为调用 application service

---

### Phase 4: Logging / Debug Read-Write Layer

目标：建立可观测系统。

任务：

* 拆分 logging 模块
* 新增 system_event_logs
* 新增 search_debug_runs / search_debug_items
* 新增 project debug API
* 页面增加 Debug Console

---

### Phase 5: Project Settings Resolver

目标：统一配置治理。

任务：

* 新增 EffectiveProjectSettings
* 新增 ProjectSettingsResolver
* Search / Embedding / AI / Scan 改为读取 effective config
* 页面展示 effective config snapshot

---

### Phase 6: Task Persistence

目标：任务状态持久化。

任务：

* 新增 scan_runs
* 新增 task_run_events
* Scan 状态从内存迁移到 DB
* AI / Embedding / Scan 页面统一任务展示

---

### Phase 7: Frontend API Refactor

目标：前端 API 和页面边界收敛。

任务：

* 拆分 `api.ts`
* 页面只使用 project-scoped API
* 移除主流程 deprecated fallback
* 增加统一错误反馈和 debug panel

---

## 14. 优先级建议

建议优先级：

```text
P0  Router 拆分
P0  ProjectGuard + Repository
P0  SearchService 拆分
P1  ScanService 拆分
P1  Worker 调用 AIJobAppService
P1  Logging / Search Debug Trace
P2  ProjectSettingsResolver
P2  Task Persistence
P2  Frontend API Client 拆分
```

优先做结构边界重构，再做行为升级。

---

## 15. Cursor 编程建议

```text
你正在 ai-photo-lib 仓库中做架构升级。请严格遵守：

1. 不要改变现有 API 行为，除非任务明确要求。
2. 不要新增 global API。
3. 所有新功能必须使用 /projects/{project_id}/...。
4. 所有业务查询必须显式带 project_id。
5. Router 只做 HTTP 层，不写复杂业务逻辑。
6. 第一阶段只拆 router，不改数据库模型，不改前端行为。
7. 从 apps/api/app/routers/projects.py 拆出：
   - project_photos.py
   - project_scan.py
   - project_ai_jobs.py
   - project_ai_settings.py
   - project_prompt_templates.py
   - project_embeddings.py
   - project_search.py
   - project_tags.py
8. 保持所有 URL path、response_model、函数行为不变。
9. 在 main.py include 新 router。
10. projects.py 只保留 Project CRUD。
11. 后续再新增 repositories 和 application services。
12. 不要在业务代码中新增 hardcode 配置。
13. DebugMode / DebugMatrix 语义必须保持兼容。
14. Worker 后续要改为调用 AIJobAppService.process_job(job_id)。
15. Search 后续要拆成 keyword query、vector query、search policy、result hydrator、debug writer。
16. 前端后续拆分 api.ts，但第一阶段不要改前端。
17. 每一步完成后运行后端测试和 TypeScript typecheck。
18. 保持小步提交、可回滚。
```

---

## 16. 总结

本次 high-level 架构升级的核心是建立清晰边界：

```text
Router
  -> Application Service
    -> Domain Policy
    -> Repository / Query Service
    -> Infrastructure Adapter
```

短期先解决：

* `projects.py` 过重
* 数据查询散落
* service 职责不清
* worker 承担过多业务逻辑
* debug 和日志体系不成层

中期建立：

* 日志读写层
* Search Debug Trace
* Project Effective Settings
* Repository / UnitOfWork

长期将 ai-photo-lib 收敛为一个稳定的、多项目隔离的、可观测的 AI Photo Platform。
