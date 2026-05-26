# ai-photo-lib 功能收敛与架构落地方案

> 更新时间：2026-05-26
> 目标：把当前“功能已成型、边界开始膨胀”的项目收敛为稳定可迭代的平台形态

---

## 1. 当前判断

当前代码已经不再是“照片扫描工具”，而是一个具备以下能力的本地 AI Photo Platform：

- 多项目照片库与项目隔离
- 文件夹树 / 时间线 / 标签浏览
- AI 分析任务、失败重试、Prompt 模板、Embedding 配置
- `keyword + vector + metadata + people` 混合搜索
- People Recognition 的人工闭环
- 项目级批量 face scan 与 unknown clustering

当前主要问题不在“功能缺失”，而在“功能水位、文档真相、任务体系、代码边界”没有同步收敛。

---

## 2. 收敛目标

本轮收敛按四个目标推进：

1. 真相源收敛
   让 README、设计文档、运行说明与代码实现一致。

2. 任务体系收敛
   统一长任务的状态模型、执行入口、重试机制和观测口径。

3. 业务边界收敛
   把超大 router / page 拆回应用服务、查询服务和子面板。

4. 验证体系收敛
   让主路径具备稳定的回归验证，而不是只靠人工烟测。

---

## 3. 分阶段实施

### Phase 0：文档真相与默认值一致性

目标：

- 修正文档与代码水位错位
- 修正“启动行为”和“默认配置”的误导点
- 为后续拆分建立统一描述

执行项：

1. 更新 `README.md`
   - People 当前状态改为真实功能水位
   - 明确“API 启动做 schema self-check，不自动执行 migration”
   - 把已上线能力、待完成能力重新分栏

2. 更新 `Design-document/faceDetectionDesgin.md`
   - 从“只读阶段”修正为“人工纠错闭环已落地”
   - 标记 unknown clustering、people search、project face scan 已上线
   - 明确仍未完成的是全量 worker 化和匹配链路进一步工程化

3. 新增本方案文档
   - 作为当前收敛工作的主计划

4. 修复搜索默认值不一致
   - 收敛 `enable_semantic_tag_boost` 的默认值来源
   - 避免“有无 project row”导致行为漂移

交付物：

- `README.md`
- `Design-document/faceDetectionDesgin.md`
- `Design-document/convergence-roadmap.md`
- `apps/api/app/services/search/settings_resolver.py`
- 搜索回归测试补充

状态：

- 本轮已执行

### Phase 1：长任务体系统一

目标：

- 所有长任务统一进入持久化 job 模型
- 消除 API 进程内线程 + 内存状态带来的重启丢状态问题

范围：

- 照片库 `scan/start`
- `scan/reindex`
- `face-cluster-unknown`

建议方案：

1. 引入统一任务类型
   - `library_scan`
   - `library_reindex`
   - `face_cluster_unknown`

2. 建立统一任务表或扩展现有 `ai_jobs`
   - 如果继续复用 `ai_jobs`，建议更名为泛化任务表
   - 如果不更名，则新增 `task_runs` / `project_tasks`

3. 把以下入口改为“只负责入队”
   - `POST /projects/{project_id}/scan/start`
   - `POST /projects/{project_id}/scan/reindex`
   - `POST /projects/{project_id}/face-cluster-unknown`

4. Worker 统一执行
   - 统一状态：`queued / running / success / failed`
   - 统一重试和失败日志
   - 统一 API 查询状态与前端展示

5. 移除进程内状态
   - 删除 `_project_scan_states`
   - 删除 API router 中的 daemon thread

验收标准：

- API 重启后任务状态不丢
- 同一项目任务可观测、可重试、可追踪
- `scan` / `reindex` / `face cluster` 与 `ai analyze` 使用同一任务心智模型

状态：

- 待执行

### Phase 2：People 业务边界拆分

目标：

- 降低 `project_people.py` 的复杂度
- 把“状态机 + 计数刷新 + prototype rebuild + negative constraint”集中到服务层

建议拆分：

- `PeopleQueryService`
  - list/detail/review list
- `PeopleCommandService`
  - rename/create/delete
  - confirm/reject/move
  - merge/split
  - set representative
- `PeopleReviewService`
  - batch confirm/reject/move
  - request_id/operator/retry policy
- `PeopleLearningService`
  - counter refresh
  - prototype rebuild
  - negative constraint maintenance

收敛原则：

- Router 只做参数校验和 HTTP 映射
- 事务边界在 command/review service
- 读写路径分离

状态：

- 待执行

### Phase 3：前端信息架构与页面拆分

目标：

- 让任务页只承担“任务执行与状态查看”
- 让设置页承担“配置编辑”
- 降低千行页面的维护压力

执行项：

1. 收敛入口
   - `TasksPage` 保留执行类入口
   - `ProjectAISettingsPage` 保留配置类入口
   - 避免双入口长期并存

2. 页面拆分
   - `PeoplePage.tsx` 拆为列表、详情、批量操作、分裂操作子组件
   - `ProjectAISettingsPanel.tsx` 拆为
     - model settings
     - prompt template settings
     - embedding settings
     - face settings
     - search settings

3. 把 mutation / query 逻辑下沉到 hooks

状态：

- 待执行

### Phase 4：测试与发布验证补齐

目标：

- 补齐前端主路径测试
- 固化高风险行为回归

优先补的链路：

1. People
   - rename
   - confirm/reject/move
   - merge/split
   - review batch actions

2. Search
   - people-only query
   - people + semantic mixed query
   - metadata-only query
   - settings reset/default consistency

3. Tasks
   - AI job retry
   - face scan batch enqueue
   - long task state rendering

状态：

- 待执行

---

## 4. 本轮已执行内容

本轮先落地 Phase 0：

- 更新项目级收敛路线文档
- 更新 README 到当前真实功能水位
- 更新 People 设计文档到当前真实功能水位
- 修复搜索默认值不一致问题
- 补充一条默认值一致性回归测试

---

## 5. 推荐下一步顺序

建议按下面顺序继续做，不要并行摊大：

1. Phase 1：统一长任务框架
2. Phase 2：拆 People 后端边界
3. Phase 3：拆 People / AI Settings 前端页面
4. Phase 4：补前端主路径测试
