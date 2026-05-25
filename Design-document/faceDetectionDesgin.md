# ai-photo-lib People / Face Recognition 设计与实施进度

> 更新时间：2026-05-25
> 状态：Phase 1 已基本落地，Phase 2 正在起步

## 1. 功能边界

本项目的人脸能力目标不是做通用身份识别，而是做本地照片库里的 People Recognition：

- 用户先命名人物并确认样本
- 系统再根据当前项目内的本地样本查找相似人脸
- 不自动识别真实身份
- 不重训练模型权重
- 所有数据严格按 `project_id` 隔离

当前技术方向仍然保持为：

- Face Service 负责 detection / crop / embedding
- PostgreSQL + pgvector 负责结构化存储与相似度检索
- Web People UI 负责人名管理、人工确认和纠错闭环
- MiniCPM-V 继续负责场景理解、caption、tags、OCR 辅助

## 2. 当前已完成进展

### 2.1 数据层基础已落地

已经完成项目级人脸相关表和迁移：

- `project_face_settings`
- `face_detections`
- `face_embeddings`
- `persons`
- `person_face_assignments`
- `person_prototypes`
- `face_negative_constraints`
- `person_cannot_links`

当前实现原则：

- 所有人脸相关表都冗余保存 `project_id`
- embedding 记录保存 `model_name` / `model_version` / `embedding_dim`
- 后续换模型时允许并存，避免静默覆盖旧向量

### 2.2 项目级 Face Settings 已可用

后端已经提供项目级配置 API：

- `GET /projects/{project_id}/face-settings`
- `PUT /projects/{project_id}/face-settings`
- `POST /projects/{project_id}/face-settings/reset`

前端已经在项目 AI 设置页提供面板，可配置：

- 启停人脸识别
- 自动归类开关
- 新人物是否必须人工确认
- face crop 是否落盘
- 阈值和质量门槛
- negative constraints / cannot-links 开关

### 2.3 单张照片 Face Scan 链路已打通

当前已经支持：

- `POST /projects/{project_id}/photos/{photo_id}/face-scan`
- 读取项目级 face settings
- 调用 Face Service provider
- 写入 `face_detections`
- 写入 `face_embeddings`
- 可选保存 face crop
- provider 不可用时返回明确错误

当前 provider 抽象已经存在，但真实 OpenCV 运行依赖仍需要本地环境提供：

- `cv2`
- `FACE_DETECTOR_MODEL_PATH`
- `FACE_EMBEDDING_MODEL_PATH`

### 2.4 Faces / People 只读 API 已可用

当前已提供：

- `GET /projects/{project_id}/faces`
- `GET /projects/{project_id}/faces/{face_id}`
- `GET /projects/{project_id}/faces/{face_id}/crop`
- `GET /projects/{project_id}/people`
- `GET /projects/{project_id}/people/{person_id}`

这批 API 主要用于：

- 调试检测结果
- 查看 embedding 与 crop
- 展示当前已有 `persons` 和 assignments

### 2.5 前端调试闭环已形成

当前前端已经具备一条最小闭环：

1. 在项目设置页开启人脸识别
2. 在照片详情页手动执行 `face scan`
3. 查看当前照片检测到的人脸与 crop
4. 打开 `/projects/:projectId/people` 查看人物列表和只读详情

已落地页面：

- 项目 AI 设置中的 Face Settings 面板
- 照片详情弹窗中的人脸识别区块
- `/projects/:projectId/people` 人物页

人物页当前能力：

- 展示人物列表
- 展示代表头像
- 展示样本数、已确认数、自动识别数、待确认数
- 展示关联人脸及状态、相似度、质量、bbox

## 3. 当前还没有完成的部分

虽然基础链路已经可用，但 People Recognition 还没有进入“越用越准”的状态。当前缺口主要有：

### 3.1 自动聚类与人物自动创建未完成

还没有真正落地：

- `face_cluster_project`
- 未知人脸聚类
- 自动生成 `人物 1 / 人物 2 / 人物 3`
- representative face 自动选择策略

这意味着：

- 当前 People 页只能展示数据库中已经存在的 `persons`
- 还不能靠扫描全库自动长出完整人物列表

### 3.2 人工纠错闭环未完成

还没有落地写操作 API：

- 人物重命名
- 确认属于某人
- 不是此人
- 移动到其他人物
- 设为代表头像
- 合并人物
- 拆分人物

因此当前人物页还是只读的，不能直接形成正样本和负样本沉淀。

### 3.3 Worker 化任务体系未完成

还没有接入正式 worker 任务：

- `face_scan_photo`
- `face_scan_project`
- `face_match_detection`
- `face_cluster_project`
- `face_rematch_unknown`
- `face_rebuild_person_prototypes`

当前主要还是同步调用单张照片扫描，用于开发和调试。

### 3.4 Search 集成未完成

目前还没有把人物能力接进搜索系统：

- search query parser 还不能解析人物名
- search service 还没有 `person_id` filter
- 还不支持多人共现
- 还不支持 `face_count` 条件

## 4. 当前可验收范围

截至当前版本，可以确认的能力是：

- 数据模型已经为 People 模块预留完整结构
- 所有新增 API 都是 project-scoped
- 单张照片的人脸检测与 embedding 入库链路已实现
- 照片详情页可手动触发人脸扫描并查看结果
- People 列表与详情页已经接上后端只读 API

当前不应误认为已经上线的能力：

- 自动人物聚类
- 人工确认闭环
- 批量 review queue
- 人物搜索
- merge / split / rematch

## 5. 下一步行动计划

推荐按下面顺序继续推进。

### P1：补齐人物写操作闭环

目标：让 People 页从“只读”进入“可人工纠错”。

优先实现：

- `PATCH /projects/{project_id}/people/{person_id}`：重命名人物
- `POST /projects/{project_id}/people/{person_id}/faces/{face_id}/confirm`
- `POST /projects/{project_id}/people/{person_id}/faces/{face_id}/reject`
- `POST /projects/{project_id}/people/{person_id}/faces/{face_id}/move`
- 代表头像设置接口

同时补齐：

- `human_confirmed` / `human_corrected` / `rejected` 状态流转
- `is_positive_sample` 更新
- `face_negative_constraints` 写入

### P2：补齐 prototype rebuild 与 matcher 基础

目标：让人工确认开始真正影响后续识别。

优先实现：

- `face_rebuild_person_prototypes`
- `person_prototypes` 重建逻辑
- 基于 confirmed samples 的最小 matcher
- `negative constraints` 过滤

这样做完后，新增照片的人脸识别结果就不再只是“扫出来”，而是开始对已命名人物做相似度匹配。

### P3：引入 review queue 和批量操作

目标：让中置信度结果进入可批量修正流程。

优先实现：

- `review_pending` 状态
- `/projects/{project_id}/people/review`
- 按人物分组的待确认列表
- 批量确认 / 批量排除 / 批量移动

### P4：全库扫描、聚类和未知人物管理

目标：让系统能从照片库中自动长出人物分组。

优先实现：

- `face_scan_project`
- `face_cluster_project`
- 自动创建系统人物
- unknown cluster 管理

### P5：搜索系统集成人物过滤

目标：把 People 模块接入核心搜索体验。

优先实现：

- query parser 识别人物名
- `person_id` 结构化过滤
- 多人共现搜索
- `face_count` 条件搜索

## 6. 当前建议的开发策略

建议近期不要同时并行推进太多块，而是优先保证“人工纠错闭环”先成立。

理由很简单：

- 没有确认 / 排除 / 移动，People 页就只是浏览页
- 没有 prototype rebuild，人工标注不能反哺识别
- 没有 negative constraints，误识别会反复出现

所以当前最值得优先投入的顺序是：

1. 人物写操作 API
2. prototype rebuild
3. matcher + rematch
4. review queue
5. search integration

## 7. 使用说明

当前版本要验证 People / Face 功能，建议按下面流程：

1. 在项目 AI 设置页开启“人脸识别配置”
2. 确保本地 Face provider 依赖和模型路径可用
3. 在照片详情页手动点击“扫描人脸”
4. 观察 faces 区块中的 bbox、crop、置信度和质量分
5. 打开 `/projects/{project_id}/people` 查看已有人物和关联样本

如果扫描成功但人物页为空，通常不是扫描失败，而是因为：

- 当前还没有自动聚类创建人物
- 数据库里还没有对应的 `persons` 记录

## 8. 一句话结论

当前 ai-photo-lib 的 People Recognition 已经具备“项目级配置 + 单张照片扫描 + face 入库 + 人物只读展示”的基础能力。

下一阶段的核心任务不是继续堆更多页面，而是优先补齐“人工确认 -> 样本沉淀 -> prototype rebuild -> 再匹配”的闭环。
