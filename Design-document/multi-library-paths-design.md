# 多图片库路径（1 项目 : N 路径）设计

日期：2026-10-21 · 状态：已实施（expand 阶段） · 关联：`apps/api`、`apps/web`、`apps/mobile-web`

## 1. 目标与现状

一个图片库（Project）当前只允许一个 `projects.photo_library_path`（NOT NULL Text）。
目标：一个图片库可挂载多个图片路径（1:N），扫描/浏览/清理/隔离全部按"任一根路径"解析。

单根假设的读点（全部迁移）：

| 读点 | 用途 | 迁移方式 |
|---|---|---|
| `services/scanner.py` | 扫描根 | 遍历全部根，逐根计算 relative_base_path |
| `routers/project_scan.py` ×2 | 扫描前置校验 | 校验全部根 |
| `routers/projects.py` readiness | 就绪检查 | 校验全部根并聚合错误 |
| `services/project_photo_asset_service.py` ×3 | 文件所有权检查 | 任一根匹配即通过 |
| `services/photo_quarantine_service.py` ×2 | 隔离/删除路径校验 | 任一根匹配 |
| `services/photo_cleanup.py` | 相对路径回退计算 | 优先存量 relative_path，回退按匹配根计算 |
| `services/project_app_service.py` | CRUD + legacy 修复 | 经由新服务同步 |

## 2. 数据模型（expand-contract 第 1 阶段：expand）

新表 `project_library_paths`（Alembic 041）：

```sql
CREATE TABLE project_library_paths (
  id          BIGINT PRIMARY KEY AUTOINCREMENT,
  project_id  BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  path        TEXT NOT NULL,
  position    INTEGER NOT NULL DEFAULT 0,   -- 0 = 主路径
  created_at  TIMESTAMP NOT NULL DEFAULT now(),
  updated_at  TIMESTAMP NOT NULL DEFAULT now(),
  CONSTRAINT uq_project_library_paths_project_path UNIQUE (project_id, path)
);
CREATE INDEX ix_project_library_paths_project_id ON project_library_paths (project_id);
CREATE INDEX ix_project_library_paths_project_position ON project_library_paths (project_id, position);
-- 回填：INSERT ... SELECT id, photo_library_path, 0 FROM projects WHERE photo_library_path <> ''
```

**决策**：`projects.photo_library_path` 保留为非规范化主路径（= position 0），由服务层保持同步。
- 理由：老客户端/脚本/前端只读该字段不破坏；NOT NULL 约束不动，回滚安全。
- 被否备选：直接删列改 join——爆炸半径大（所有读点+测试），留给 contract 阶段。

## 3. API 契约（向后兼容）

- `ProjectCreate`：`photo_library_path: str`（旧）或 `photo_library_paths: list[str]`（新），二选一必填；
  同时提供时要求 `photo_library_paths[0] == photo_library_path`，否则 422。
- `ProjectUpdate`：`photo_library_paths` 提供 → 全量替换；仅 `photo_library_path` → 只替换主路径（保序保留其余）。
- `ProjectResponse`：新增 `photo_library_paths: list[str]`（恒非空，首元素=主路径）；`photo_library_path` 保留。
- 路径校验规则不变：strip、去尾 `/`、必须绝对路径、`normpath == 原值`（禁 `..`）；列表按序去重、空项 422。

## 4. 运行时语义

- **扫描**：逐根 `rglob`；嵌套根（如 `/a` 与 `/a/b`）自动去重保外层；部分根缺失 → 跳过并告警，
  全部缺失 → 中止（维持原行为）。
- **清理保护（数据安全）**：任一根不可用时跳过 `cleanup_missing_project_photos`，
  防止 NAS 离线时误删该根下全部 DB 记录。扫描结果标记 `done_with_errors`。
- **所有权检查**：文件落在任一配置根内即合法（缩略图/原图/预览/隔离）。
- **NAS 删除清单**：manifest 新增 `library_path` 字段（增量、向后兼容），NAS 侧脚本可据此解析源根。
- **自愈回退**：`get_project_library_paths` 读子表为空时回退 `[photo_library_path]`（只读，不写库）。

## 5. 迁移与回滚

1. 041 建表 + 回填（幂等：新表无冲突行；重跑由 alembic version 控制）。
2. 代码同步写子表与主路径列；启动时 `startup_schema_service` 校验新表存在。
3. 回滚：`alembic downgrade 040_face_rematch_concurrency_3`（drop 表，数据无损——主路径列仍在）+ `git revert`。
4. Contract 阶段（后续，不在本次）：全部客户端迁移到 list 后删 `projects.photo_library_path` 列。

## 6. 可观测性

- 扫描日志记录每根的 discovered 计数与 missing 根列表；跳过清理时 `recent_errors` 追加可行动信息。
- readiness 对每个无效路径给出独立错误消息（分号聚合）。
