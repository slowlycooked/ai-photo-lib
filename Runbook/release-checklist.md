# 发布前 Checklist（Week 4）

## 1. 能力成熟度分层一致性

| 能力 | 成熟度 | 发布说明 |
|------|--------|----------|
| Face clustering | 稳定 | 聚类任务已纳入项目级队列、状态跟踪与 Review Pending 主链路。 |
| Face rematch unknown | 稳定 | 未知人脸重匹配已纳入项目级队列，并保留人工确认结果。 |
| Search face filters | 稳定 | 合照、单人照、待确认和未命名人物筛选已接入搜索主链路。 |
| Task controls | 稳定 | 任务中心已支持项目级暂停、取消与失败明细查看。 |
| System health check | 稳定 | `/health/system` 与设置页“运行状态”可用于部署检查和排错。 |
| Prompt 测试 | 稳定 | Prompt 测试支持项目模板、测试图片、解析结果与本地历史回看。 |
| Embedding rebuild | 稳定 | 已支持项目级状态检查、按范围重建与任务入队。 |

发布要求：文档与页面标记必须一致，禁止“文档实验、页面无标记”。

## 2. 工程质量守门

- 重复逻辑继续下沉：People learning/policy 与任务编排不得新增硬编码状态枚举。
- 新增改动不回填大 router/大 page，优先复用已有抽象。
- 圈复杂度守门：关键服务函数复杂度不得突破测试阈值。

## 3. 隔离与配置审计

- 所有新增/改动接口必须有 project_id 作用域校验。
- 无新增硬编码运行参数。
- 无未经确认的新配置项。
- 配置缺失必须显式失败。
- worker 任务处理必须携带并严格使用 project_id。
- 新增系统健康检查项必须避免泄露密钥，只返回状态和可操作提示。

## 4. 产品化主链路验收

- Tasks：项目级 scan / face scan / unknown clustering / unknown rematch 可入队、可查询状态，并支持暂停、取消与失败明细查看。
- People：人工确认/排除/移动后 prototype rebuild 保持有效；unknown rematch 不覆盖人工确认结果。
- Search：人脸筛选入口可用，结果返回 `face_count`，普通搜索在缺少人脸表时可降级。
- Settings：运行状态页能展示 DB、migration、路径、模型配置、auth 配置等检查结果。

## 5. 一键预检命令

发布前请在仓库根目录执行：

```bash
./scripts/release-preflight.sh
```

该命令会依次执行：

- 后端发布审计 + 项目隔离 / People / Face / Search / 任务主链路回归
- 前端成熟度渲染、Tasks、Settings、失败任务组件回归
- TypeScript typecheck
- 前端 build
