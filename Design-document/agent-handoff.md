# ai-photo-lib Agent Handoff

> 更新时间：2026-10-20  
> 交接基线：`13e9c6b`（`Add video thumbnailing and sampled-frame VLM analysis`）  
> 状态：仓库包含大量未提交工作；本文把“已提交基线”和“当前工作区状态”分开描述。
> 当前仓库路径：`/Users/martinclaw/Projects/ai-photo-lib`

## 1. 交接摘要

ai-photo-lib 是 Martin 的私有本地 AI Photo Platform，不是通用云服务。它的目标是把 NAS 上的原片库变成可扫描、可理解、可搜索、可人工纠错、可安全清理的多项目照片系统，同时坚持原片安全和本地数据主权。

系统当前主线已经成型：

- PostgreSQL + pgvector 保存项目、照片、AI 分析、embedding、People、任务与调试数据。
- FastAPI 提供项目级 API，React/Vite 提供管理端，Mobile Web 提供只读浏览端。
- Python Worker 统一领取并执行 `ProjectTask` 与 `AIJob`。
- 本地 llama.cpp / Ollama 承担视觉理解、embedding 和 query planning。
- People Recognition 已形成“检测 / embedding / 聚类 / 匹配 / 人工确认 / 负样本学习 / rematch”的闭环。
- Search 已形成 LLM planner + 规则兜底 + metadata / keyword / vector / people 多路召回与融合。
- 原片删除采用应用写 JSONL 清单、NAS 后台脚本移入回收目录的两段式边界。

最重要的安全边界：

1. 应用进程不直接移动或删除照片原片。
2. 缩略图必须保留在 NAS：`/Users/martinclaw/nas/ai-photo-data/thumbs`。
3. 生产运行模式是 Martin 交互 iTerm2 会话中的 `scripts/svc.sh`；不要恢复 launchd，也不要创建 recovery job。
4. 未经 Martin 对“精确服务 + 精确动作”的批准，不得 start / stop / restart / recover / 改执行上下文。
5. 未经批准不得改变存储路径、目录语义、数据库路径、挂载点或运行时路径。
6. 自动聚类和 rematch 不得覆盖 `human_confirmed` / `human_corrected` 归属。
7. 所有新业务数据和 API 必须以 `project_id` 隔离。

## 2. 业务目标

### 2.1 核心用户价值

- **本地优先**：照片、向量、任务和配置主要留在 Martin 控制的 Mac / NAS / 本地模型环境内。
- **多项目隔离**：不同照片库、家庭成员或用途可以作为独立项目管理，避免查询和 AI 数据串库。
- **自然语言找图**：支持中文自然语言、时间 / 地点 / 相机 / 人物 / 语义组合查询。
- **人物闭环**：不是自动识别真实身份，而是通过人工命名、确认、排除、移动、合并和拆分持续改进项目内匹配。
- **安全清理**：疑似删除、敏感内容、重复片进入人工复核；应用只记录意图，NAS 脚本负责移动原片。
- **可运维**：任务可查询、暂停、取消、重试并保留失败明细；系统健康检查覆盖 DB、migration、路径、模型和认证。

### 2.2 主要场景

1. 新项目接入后扫描照片库，抽取 EXIF、尺寸、哈希、视频采样帧，生成缩略图。
2. Worker 调用视觉模型输出 caption、tags、OCR 等结构化分析。
3. Embedding 服务为照片和文本建立向量索引。
4. 用户在桌面端浏览照片、时间线、文件夹、标签和搜索结果。
5. 用户在 People 页面处理自动候选、复核队列、误识别和负样本。
6. 用户用手机端快速浏览、搜索和下载授权项目内的照片。
7. 待删除审核页筛选敏感 / 成人 / 重复内容，并只提交清单给 NAS 后台处理。

### 2.3 非目标

- 不做通用身份识别或跨项目人脸身份库。
- 不重训练底层模型权重。
- 不默认支持 Docker 运行；Docker 仅历史兼容参考。
- 不把原始照片、模型权重、数据库数据、日志或缓存放进 Git。
- 不把管理能力复制到 Mobile Web；Mobile Web 保持只读浏览。
- 不把 launchd 作为运行方案。

## 3. 当前仓库与运行状态

### 3.1 Git 基线与未提交工作

交接开始时的快照：

- 仓库当前位于 `/Users/martinclaw/Projects/ai-photo-lib`；`/Users/martinclaw/ai-photo-lib` 已不再是 Git 仓库。
- 当前分支：`main`，与 `origin/main` 同步到 `13e9c6b`。
- 已跟踪文件：65 个文件修改，约 `+1817 / -273`。
- 未跟踪文件：
  - `ignored.db`：0 字节，来源不明，不要提交；继续接手时先确认是否可删除。
  - `scripts/deleteMartinLib.sh`：NAS 原片回收批处理 wrapper，未提交。

未提交工作主要主题：

| 主题 | 相关区域 | 交接判断 |
|---|---|---|
| People 负样本学习 | `people_learning_service.py`、相关 schema / query / tests | 已有较完整测试补充；真实照片效果仍需人工复核评估。 |
| 项目任务失败明细与控制 | `project_task_*`、Tasks UI、测试 | 方向正确；提交前需跑任务相关回归。 |
| 查询规划与搜索回归 | `query_planner/mapper.py`、planner tests | 需要跑 Search / planner 主链路测试。 |
| 隔离审核与清理 | quarantine、photo cleanup、Web 审核页 | 需要重点验证 API 语义和 UI 状态。 |
| NAS 原片回收安全强化 | `nas-trash-deleted-photos.py`、`deleteMartinLib.sh` | 有 dry-run / validate / apply、hash 和同文件系统约束；生产执行必须 Martin 批准。 |
| 文档状态修正 | `faceDetectionDesgin.md` | 仍有部分章节落后于当前任务体系，需要后续统一。 |

不要把这些未提交改动当成已经发布或已经全量验证的能力。接手后第一步是读取 `git diff`、确认改动归属，再决定拆分提交或继续修复。

### 3.2 运行拓扑

| 服务 | 角色 | 默认端口 | 说明 |
|---|---|---:|---|
| PostgreSQL | 元数据、任务、pgvector | 5432 | 本地进程；数据目录由 `.env` 决定，不进 Git。 |
| API | FastAPI | 8000 | 项目级 API、认证、健康检查、schema self-check。 |
| Web | React + Vite | 8088 | 管理端：照片、搜索、标签、任务、People、设置。 |
| Mobile Web | React + Vite | 8090 | 手机端只读浏览、搜索、原图下载。 |
| Worker | Python 后台进程 | - | 统一处理 `ProjectTask` 与 `AIJob`。 |
| Vision llama-server | MiniCPM-V 等 | 8082 | 视觉分析；可切换 Ollama。 |
| Embedding llama-server | Qwen embedding 等 | 8083 | 照片 / 文本向量。 |
| Query planner llama-server | Qwen planner 等 | 8084 | 自然语言查询规划。 |

机器角色：

- MacBook Air M4：开发机，可按需运行较小组件。
- Mac mini M4：长期运行机，运行 PostgreSQL、API、Web、Worker 和模型服务。
- 两台机器使用同一套代码与脚本，实际差异由各自 `.env` 表达。

### 3.3 目录职责

```text
apps/api/          FastAPI、SQLAlchemy models、Alembic、services、backend tests
apps/web/          管理端 React/Vite/TypeScript
apps/mobile-web/   手机端 React/Vite/TypeScript
apps/worker/       后台 Worker 入口
scripts/           macOS native 启动、DB、发布预检、NAS 辅助脚本
Design-document/   架构、领域设计、收敛路线与本文
Runbook/           发布、回填、扫描故障处理
```

文档事实源：

| 信息类型 | 事实源 |
|---|---|
| 当前能力与运行入口 | `README.md` |
| 项目工作规则 | `AGENTS.md` |
| 架构与领域设计 | `Design-document/` |
| 运维步骤 | `Runbook/` |
| 代码级当前行为 | 代码与测试 |
| 本交接快照 | 本文件 |

## 4. 架构设计

### 4.1 总体分层

目标分层是：

```text
React Web / Mobile Web
  -> typed API client / hooks
FastAPI project-scoped routers
  -> application services / query services
  -> domain policies
  -> repositories / SQLAlchemy models
  -> PostgreSQL + pgvector
Worker
  -> TaskClaimService
  -> ProjectTaskAppService / AIJobAppService
  -> project task handlers / AI pipelines
Infrastructure adapters
  -> FileSystemReader / ThumbnailStore / VLMClient / EmbeddingClient / structured logging
```

这是目标态与当前态混合的架构。当前代码已经落地大量 service / repository / query service，但仍有若干 router 直接查库、超大 service、Worker 编排集中和前端大页面问题。

### 4.2 项目隔离原则

- 项目、照片、文件夹、AI 分析、embedding、People、任务、prompt、搜索设置和调试记录都必须绑定 `project_id`。
- 新 API 只使用 `/projects/{project_id}/...`。
- Worker 任务必须携带并严格使用 `project_id`。
- 跨项目用户 / 成员 / 权限管理与业务数据隔离是两层问题，不能用成员关系替代 SQL scope。
- 项目隔离相关测试是发布门禁，不允许为了局部功能放松。

### 4.3 任务体系

任务体系已经从单一路径演进为双队列统一领取：

- `ProjectTask`：项目级长任务，例如 library scan / reindex、face scan、unknown clustering、face rematch、prototype rebuild 等。
- `AIJob`：照片级 AI 分析任务。

核心链路：

1. API 或调度器只负责入队并返回任务状态。
2. Worker 通过 `TaskClaimService.claim_next()` 按创建时间在两类队列中领取最早任务。
3. `ProjectTaskAppService.process_task()` 处理 pause / cancel / running / failure / success 状态。
4. `project_task_handlers.py` 将任务类型映射到具体业务服务。
5. 任务保留进度、阶段、错误、失败照片明细和 result payload。
6. Stuck task 依据任务类型策略恢复，lease 过期后可重新认领。

任务中心支持：

- 项目级状态查询
- 暂停 / 恢复 / 取消
- 失败重试
- 子任务或照片级失败明细
- 进度流与历史记录展示

后续新增长任务时应优先扩展 `ProjectTask`，不要新增一次性内存状态或独立任务机制。

### 4.4 扫描与素材处理

扫描入口位于 `apps/api/app/services/scanner.py`，由项目任务驱动。

关键规则：

- 使用项目自己的 `photo_library_path` 和 `thumbnail_path`。
- 照片库路径不存在时 fail-fast。
- `thumbnail_path` 为空或不可写时 fail-fast。
- 不回退到全局默认路径，不运行时悄悄改写项目配置。
- 扫描排除缩略图目录和隔离目录，避免生成物被再次当作原片。
- 文件准备并发执行，数据库写入分批提交；单文件失败尽量不拖垮整批。
- 支持图片元数据、内容哈希、地点反查和视频缩略图 / 采样帧分析。

缩略图是生成物，但生产存储位置是 NAS：`/Users/martinclaw/nas/ai-photo-data/thumbs`。`.env.example` 中的示例路径只用于示例，不能推断为生产例外。

### 4.5 AI 分析与模型

视觉分析：

- `AIJob` 按项目与照片入队。
- Worker 调用 `vlm_client.py`，兼容本地 llama-server / OpenAI-compatible endpoint / Ollama 配置。
- 输出 caption、tags、OCR 等 prompt 约束的结构化 JSON。
- Prompt 支持项目模板、测试图片、解析结果和本地历史回看。
- 视频分析使用采样帧，避免把完整视频作为单一输入。

Embedding：

- 独立 embedding server。
- 记录模型名、版本和维度；换模型时旧向量允许并存并按维度 / 模型隔离。
- 支持项目级状态检查、按范围重建与任务入队。

配置要求：

- 模型路径、endpoint、维度和并发度来自 `.env` / 项目设置。
- 缺关键配置应显式失败，不做隐藏默认。
- 27B 视觉模型建议 `AI_WORKER_CONCURRENCY=1`。

### 4.6 People / Face Recognition

领域目标是“项目内 People Recognition”，不是身份识别：

```text
scan photo
  -> face detection
  -> face crop / embedding
  -> unknown clustering
  -> named-person matching
  -> auto assigned / review pending
  -> human confirm / reject / move / merge / split
  -> prototype rebuild + negative constraints
  -> person rematch / unknown rematch
```

数据模型包含：

- `project_face_settings`
- `face_detections`
- `face_embeddings`
- `persons`
- `person_face_assignments`
- `person_prototypes`
- `face_negative_constraints`
- `person_cannot_links`

学习规则：

- 正样本只来自人工确认 / 纠正且满足质量门槛的人脸。
- 排除、移动、拆分可形成负样本或 cannot-link。
- 负样本泛化要求同项目、同模型、同版本、同维度且质量达标。
- 自动拒绝结果不作为负样本。
- 重新确认可撤销对应负约束并重建正样本特征。
- 自动匹配跳过人工确认 / 人工纠正的人脸，避免覆盖人工结果。

UI 主路径：

1. 项目 AI 设置开启 Face Recognition。
2. 照片详情页手动 scan，或任务中心批量 face scan。
3. `/projects/:projectId/people` 管理人物、样本、代表头像、合并和拆分。
4. `/projects/:projectId/people/review` 处理待确认队列。
5. 搜索页通过人物、合照、单人照、待确认和未命名人物过滤。

遗留重点不是“能不能用”，而是评估、自动化策略和代码拆分。

### 4.7 Search

Search 是多阶段 pipeline：

1. Query planner 优先使用 LLM 输出结构化 plan；模型不可用或配置关闭时使用规则 fallback。
2. 解析 intent、semantic residual、exact terms、metadata filters、people 约束和 mode。
3. 并行或按阶段执行 metadata、keyword、vector、concept、people recall。
4. People / metadata 约束先收缩候选集，再叠加语义证据。
5. RRF / fusion 合并候选，再由 evidence policy 过滤弱结果。
6. Hydration 输出页面模型、debug trace 和 explain 信息。

重要边界：

- 查询 planner 有版本化 contract；v2 主链路不要随意降回 v1 语义。
- metadata-only、people-only、people + semantic、时间 + 地点等路径都有回归测试。
- Debug trace 不得泄露密钥或无控制地输出 raw model payload。
- 搜索设置默认值必须避免“有无项目配置 row”导致行为漂移。

### 4.8 原片删除与隔离审核

删除链路是显式的两段式：

```text
Web 审核动作
  -> API 更新应用内状态
  -> append pending-original-trash.jsonl
  -> NAS 后台脚本验证清单
  -> NAS 后台脚本移动原片到 NAS recycle
  -> 清单归档或保留 processing 文件
```

应用侧边界：

- 普通删除和 quarantine review 共用 manifest 边界。
- 应用不移动、不删除原片。
- 敏感 / 成人内容只强制复核，不因“内容敏感”自动批准删除。
- 重复片按项目内容哈希比较，同内容最早记录作为参照。
- 旧 `move` / `MOVE` 兼容语义也是“提交删除”，不是 API 进程移动。

NAS 侧当前未提交强化：

- `nas-trash-deleted-photos.py` 增加严格 manifest 校验、SHA-256、文件指纹、符号链接检查、路径逃逸检查、同文件系统检查、destination 保留和断点恢复语义。
- `deleteMartinLib.sh` 默认 dry-run；`APPLY=1` 才会执行，成功清单默认 archive。
- wrapper 目前固定项目映射 `3 -> Chang`、`4 -> Martin` 和 NAS 路径，后续需要配置化或明确保留为 Martin 专用脚本。

任何 `APPLY=1`、成功清单删除、NAS 文件移动、批处理恢复都属于高风险操作，必须 Martin 明确批准。

### 4.9 Web 与 Mobile Web

管理端 `apps/web`：

- Photos、Search、Tags、Tasks、People、People Review、Settings、AI settings、登录。
- API client 和 typed hooks 是主路径，不要在组件里新增 ad hoc fetch。
- Tasks 页是执行与状态中心；配置编辑留在 Settings / AI settings。
- 旧 `/scan` 仅 redirect。

Mobile Web `apps/mobile-web`：

- 登录 / 登出、项目切换、照片流、搜索、详情预览、原图下载。
- 不包含管理、People 管理、任务、AI 配置。
- 桌面端可探测同域 `/m/` 并自动切换手机页面；`?desktop=1` / `?mobile=1` 提供偏好覆盖。

### 4.10 认证、健康与配置

- 使用 session cookie 登录；关键 auth 配置缺失时应阻断登录和受保护路由，而不是静默放行。
- `/health` 用于存活检查。
- `/health/system` 输出 DB、pgvector、Alembic / migration、路径、模型、auth 等状态；只输出状态和提示，不泄露密钥。
- `svc.sh start api` / `restart api` 会先执行 Alembic migration。
- 直接 `uvicorn app.main:app` 只做 schema self-check，不自动升级数据库。
- `.env` 是机器私有配置，不提交；`.env.example` 只保留占位值。

## 5. 关键设计决策

| 决策 | 原因 | 接手时注意 |
|---|---|---|
| macOS native 而非 Docker 默认 | Mac mini / llama / NAS 挂载与本地模型路径更直接。 | 不要把 Docker 当发布路径。 |
| `svc.sh` 是批准运行模式 | 项目已明确从 launchd 回退。 | 不新增 LaunchAgent / recovery job。 |
| `ProjectTask` 统一长任务 | API 重启后状态不丢，可暂停 / 取消 / 追踪失败。 | 新长任务不要回到内存线程。 |
| `project_id` 显式隔离 | 防止照片、embedding、People 和任务串库。 | 新 query / task 必须带 scope。 |
| 原片只由 NAS 脚本变更 | 降低应用错误直接破坏不可替代照片的风险。 | 不要在 API service 中新增删除 / move 原片逻辑。 |
| 人工标注受保护 | 自动重跑不能覆盖用户纠错。 | rematch 必须跳过 human-confirmed / corrected。 |
| LLM planner + 规则 fallback | 保留自然语言能力，同时保证可降级。 | fallback 语义要和 debug trace 一致。 |
| 模型信息随 embedding 保存 | 换模型时避免维度 / 语义混用。 | 相似度计算必须检查模型契约。 |
| 迁移与 schema self-check 分离 | 防止直接启动服务时误解 migration 状态。 | schema drift 应修 migration，不应弱化检查。 |

## 6. 遗留项与优先级

### P0：先处理当前工作区

1. 逐块 review 当前 65 个已跟踪文件改动，确认没有半完成重构。
2. 检查 `ignored.db` 来源；它不应进入 Git。
3. 给 `scripts/deleteMartinLib.sh` 明确归属：Martin 专用工具或配置化通用工具。
4. 在不重启服务、不改生产数据的前提下运行目标测试与 `git diff --check`。
5. 与 Martin 确认未提交工作的拆分 / 提交策略。

### P1：验证与收口

1. 运行任务、People learning、quarantine cleanup、query planner 的目标 pytest。
2. 运行 Web 相关 Vitest、typecheck、build。
3. 发布前运行 `./scripts/release-preflight.sh`。
4. 通过后再考虑提交；不要先提交再靠生产验证。

### P2：架构收敛

1. 拆分超大 search service：query parsing、filter policy、recall、fusion、hydration、debug trace。
2. 拆分 People mutation / review / learning 边界，router 只保留 HTTP 映射。
3. 收敛 router 里的直接 DB 读写，优先 `project_faces.py`、prompt、embeddings、photos、projects。
4. 拆分 `SettingsPage`、`TasksPage`、`PeoplePage`、search grid 和 photo card 等大前端文件。
5. 清理 legacy endpoint 和 legacy `/scan` redirect，先定义 sunset 版本。

### P3：产品与质量补齐

1. People：真实照片误认 / 漏认评估集，自动 rematch 触发策略与范围控制。
2. Unknown cluster：生命周期管理、命名策略、质量评估和复核体验。
3. Tasks：按类型筛选、批量操作、告警联动。
4. Search：planner v2 评测集、缓存指标、debug trace 权限和可读性。
5. Cleanup：NAS wrapper 配置化、审计报表、恢复演练和清单归档策略。
6. 文档：`convergence-roadmap.md` 与 `faceDetectionDesgin.md` 的任务状态仍落后于代码，需要按当前 `ProjectTask` 体系重写。

## 7. 接手指令与审批边界

### 7.1 必读

1. `AGENTS.md`：当前项目硬约束。
2. `AGENT.md`：工程约定与测试入口。
3. `README.md`：当前能力、运行模型和已知边界。
4. `Runbook/README.md` 与 `Runbook/release-checklist.md`。
5. 本文和 `Design-document/architect-design.md`。

### 7.2 常用验证命令

只在这些命令不改变运行服务状态时执行：

```bash
# 后端
cd apps/api
../../.venv/bin/python -m pytest -q

# 前端
cd apps/web
npm test
npm run typecheck
npm run build

# 发布预检
./scripts/release-preflight.sh

# Git 基本检查
git diff --check
```

如果测试脚本内部会启动 / 重启项目服务，先向 Martin 说明精确影响并等待批准。

### 7.3 运行服务诊断规则

收到“服务不可用”类报告时，先只读诊断：

1. `./scripts/svc.sh status`
2. `ps` / `pgrep` 查看真实进程、父进程和 coalition。
3. 检查 `.run/*.pid`。
4. 检查端口 owner。
5. 检查 Mac mini 上进程用户、环境、NAS 挂载可见性和 macOS privacy 权限。
6. 检查是否残留 submitted launchd job 或 recovery job。
7. 读取相关 logs。

诊断结论必须说明实际执行上下文；`svc.sh status` 成功或 pid 存在不等于证明服务在批准模式下运行。

## 8. Open Questions / Unknowns

| 编号 | 问题 | 影响 | 建议 |
|---|---|---|---|
| U-01 | 当前未提交改动是否已经过本机全量验证？ | 可能提交半成品。 | 先跑目标测试和 preflight。 |
| U-02 | `ignored.db` 为什么存在？ | 污染工作区，可能被误提交。 | 查明来源后删除或明确忽略。 |
| U-03 | `deleteMartinLib.sh` 是否长期保留 Martin 专用硬编码？ | 影响可维护性和跨机器复用。 | 做 ADR 或配置化。 |
| U-04 | People 负样本策略的真实照片阈值是否已评估？ | 影响误认 / 漏认。 | 建立项目内评测集。 |
| U-05 | 自动 face rematch 的触发频率与范围策略？ | 影响算力和复核队列质量。 | 先定策略，再扩大自动化。 |
| U-06 | 旧设计文档哪些章节仍是目标态？ | 容易误导下一个 agent。 | 以代码 + 测试为准，重写状态。 |
| U-07 | 当前生产 Mac mini 是否有残留 launchd / recovery 状态？ | 影响运行模式判断。 | 只读审计后再报告。 |
| U-08 | 仓库路径为何在 2026-10-20 交接过程中变为 `/Users/martinclaw/Projects/ai-photo-lib`？ | 影响脚本、IDE、索引和运行入口的路径假设。 | 向 Martin 确认迁移批准记录；不要继续使用旧根目录。 |

## 9. 交接完成定义

下一个 agent 可以认为交接完成，当其能回答：

1. 系统的业务目标、非目标和安全边界是什么。
2. API、Web、Worker、DB、模型、NAS 之间的数据流是什么。
3. `ProjectTask` 和 `AIJob` 如何入队、领取、执行、恢复和展示失败。
4. 原片删除为什么必须经过 JSONL + NAS 脚本边界。
5. 当前工作区哪些文件是未提交状态，验证缺口在哪里。
6. 哪些服务 / 路径 / 数据操作必须先获得 Martin 的精确批准。
