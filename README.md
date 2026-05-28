# AI Photo Library

本仓库现在以 macOS native 部署为主，不再把 Docker 作为默认运行方式。

推荐的使用模型：

- MacBook Air M4：开发机，跑 `web + api`，按需跑 `worker / llama`
- Mac mini M4：运行机，长期运行 `postgres + api + web + worker + llama`

两台机器共用同一套代码入口：

- 启动脚本：`./scripts/svc.sh`
- 初始化脚本：`./scripts/bootstrap-macos.sh`
- 配置方式：每台机器各自维护一份 `.env`

## People Recognition 当前状态

People Recognition 已经从“只读调试阶段”进入“人工纠错闭环已成型、工程收敛仍在继续”的阶段。

当前已经完成：

- 项目级人脸数据模型与 Alembic migration：
  - `face_detections`
  - `face_embeddings`
  - `persons`
  - `person_face_assignments`
  - `person_prototypes`
  - `face_negative_constraints`
  - `person_cannot_links`
- 项目级人脸配置 API 与前端配置面板
- 单张照片手动 `face scan` 链路
- 项目级批量 `face scan` 任务入队与状态查询；批量扫描和失败重试统一通过 `ProjectTask`
- unknown face clustering / 自动创建未命名人物
- unknown face rematch：基于已重建 prototype 异步重匹配未知人脸，生成 auto-assigned / review-pending
- `faces` / `people` 读写 API
- 人工确认 / 排除 / 移动 / 合并 / 拆分 / 代表头像设置
- 待确认队列与批量操作
- 搜索页的人物过滤、多人共现搜索，以及合照/单人照/待确认/未命名人物筛选
- 照片详情页的人脸调试区块
- `/projects/:projectId/people` 人物页与 `/projects/:projectId/people/review` 复核页

当前还没有完成：

- 任务中心的暂停 / 取消 / 子任务错误照片明细查看
- 人脸重匹配的自动触发策略与更细粒度范围控制
- People 模块后端与前端的大文件拆分收敛
- 前端 People / Search / Tasks 主路径自动化测试补齐

如果你想了解更完整的设计边界、当前进度和下一步实施计划，请看：

- [Design-document/faceDetectionDesgin.md](Design-document/faceDetectionDesgin.md)

## 第 4 周发布分层：能力成熟度标记

以下能力在 UI 与文档统一使用三档成熟度：`稳定` / `实验` / `待收敛`。

| 能力 | 成熟度 | 发布说明 |
|------|--------|----------|
| Face clustering | 稳定 | 聚类任务已纳入项目级队列、状态跟踪与 Review Pending 主链路。 |
| Face rematch unknown | 稳定 | 未知人脸重匹配已纳入项目级队列，并保留人工确认结果。 |
| Search face filters | 稳定 | 合照、单人照、待确认和未命名人物筛选已接入搜索主链路。 |
| System health check | 稳定 | `/health/system` 与设置页“运行状态”可用于部署检查和排错。 |
| Prompt 测试 | 稳定 | Prompt 测试支持项目模板、测试图片、解析结果与本地历史回看。 |
| Embedding rebuild | 稳定 | 已支持项目级状态检查、按范围重建与任务入队。 |

发布前检查清单见：[Design-document/release-checklist.md](Design-document/release-checklist.md)。

发布前一键预检命令：

```bash
./scripts/release-preflight.sh
```

该预检会覆盖后端发布审计、项目隔离、任务/People/Search 主链路、前端关键页面测试、TypeScript typecheck 和前端 build。

## 架构

| 服务 | 角色 | 默认端口 | 运行方式 |
|------|------|----------|----------|
| PostgreSQL | 元数据、任务、向量索引 | `5432` | 本地进程 |
| API | FastAPI 后端 | `8000` | `uvicorn` |
| Web | React 前端 | `8088` | `vite dev` 或 `vite preview` |
| Worker | AI 任务处理 | - | Python 进程 |
| llama-server | 视觉模型服务 | `8082` | 本地进程 |
| llama embedding | 向量模型服务 | `8083` | 本地进程 |

## 设计原则

- 代码库不绑定机器角色。开发机和运行机都用同一套脚本，只通过 `.env` 切换。
- 所有状态目录都由环境变量决定，不把本机绝对路径写死在代码里。
- Mac mini 可以随时替换为第二台机器，只要复制仓库、数据目录和对应 `.env` 即可。
- API 启动时执行 schema self-check，尽早暴露 migration 缺失或 schema drift。

## 目录与配置建议

建议把代码和运行数据分开：

- 代码仓库：`~/Workspace/ai-photo-lib`
- 照片目录：`/Volumes/Photos/...` 或 `~/Pictures/...`
- 模型目录：`/Volumes/Models/...` 或 `~/Models/...`
- PostgreSQL 数据目录：单独放在 `POSTGRES_DATA_DIR`
- 缩略图目录：单独放在 `THUMBNAIL_PATH`

关键点：

- `.env` 不要在两台机器之间直接复用，路径和暴露地址通常不同。
- API 启动会检查 `.env` 中的受管配置键（如 `OPENAI_*`、`EMBEDDING_*`、`PHOTO_*`、`THUMBNAIL_*` 等）；若出现未知键会直接启动失败。非 API 受管范围（如 `WEB_*`）不在该失败策略内。
- `PHOTO_LIBRARY_PATH`、`THUMBNAIL_PATH`、`POSTGRES_DATA_DIR` 都建议写绝对路径。
- 如果未来切到第二台 Mac mini，只要新机器重新准备这些目录并填写新的 `.env` 即可。
- `LOCATION_RESOLVER_PROVIDER=none` 表示只保存 GPS，不做地点名反查；需要地点搜索时再开启 provider。

## 1. 开发机：MacBook Air M4

### 安装依赖

先安装系统依赖：

```bash
brew install python@3.11 node@20 postgresql@17 pgvector
```

如果要本机跑 AI：

```bash
brew install llama.cpp
```

### 配置 `.env`

从示例文件开始：

```bash
cp .env.example .env
```

开发机建议值：

```env
DEPLOY_PROFILE=dev
API_HOST=127.0.0.1
API_RELOAD=0
WEB_HOST=127.0.0.1
WEB_MODE=dev
AUTH_USERNAME=admin
AUTH_PASSWORD=换成你自己的强密码
AUTH_SESSION_SECRET=换成一段随机长字符串
AUTH_SESSION_TIMEOUT_MINUTES=30
```

`AUTH_ENABLED=1` 时，除 `/health` 和 `/auth/*` 外的 API 都需要登录 session。Session 通过 HttpOnly cookie 保存，超过 `AUTH_SESSION_TIMEOUT_MINUTES` 没有有效请求后会过期并回到登录页。

### 初始化

```bash
./scripts/bootstrap-macos.sh
```

### 数据库初始化、升级与状态检查

推荐在仓库根目录按下面顺序执行：

```bash
# 1) 确保 PostgreSQL 已启动
./scripts/svc.sh start postgres

# 2) 初始化/升级数据库到最新 migration
./scripts/init-db.sh

# 3) 检查 migration 状态（是否有 pending）
./scripts/db-schema.sh check

# 4) 深度校验关键表/字段/约束
./scripts/db-schema.sh verify
```

常用补充命令：

```bash
# 一键做检查 + 深度校验（不执行 upgrade）
./scripts/db-schema.sh all

# 服务运行状态检查
./scripts/svc.sh status
```

说明：

- `init-db.sh` 仅执行 `alembic upgrade head`。
- `db-schema.sh upgrade` 与 `init-db.sh` 作用等价，二选一即可。
- 如果出现 `alembic_version` 多行异常，可执行 `./scripts/db-schema.sh fix-version` 后再 `upgrade`。
- API 启动不会自动执行 migration；如果数据库未升级到最新版本，启动时会直接报 schema self-check 错误。

### 启动开发服务

只启动开发核心链路：

```bash
./scripts/dev-up.sh
```

完整启动：

```bash
./scripts/svc.sh start
```

常用命令：

```bash
./scripts/svc.sh status
./scripts/svc.sh logs api
./scripts/svc.sh restart api
./scripts/reset-dev.sh --thumbs --yes
```

开发机默认行为：

- API 默认以稳定模式运行；需要热重载时可手动设 `API_RELOAD=1`
- Web 使用 `vite dev`
- PostgreSQL 使用本地数据目录
- 如果未配置 `LLAMA_MODEL`，`ai` / `embed` 服务会被跳过

## 2. 运行机：Mac mini M4

### 建议定位

Mac mini 作为常驻运行机，职责是：

- 持久运行 Postgres
- 提供 API / Web
- 跑 Worker
- 挂载本地模型和照片目录

### 运行机 `.env` 建议

```env
DEPLOY_PROFILE=runtime
API_HOST=0.0.0.0
API_RELOAD=0
WEB_HOST=0.0.0.0
WEB_MODE=preview
WEB_PORT=8088
```

另外建议把以下目录放在稳定磁盘位置：

```env
PHOTO_LIBRARY_PATH=/Volumes/PhotoLibrary
THUMBNAIL_PATH=/Users/Shared/ai-photo-lib/thumbs
POSTGRES_DATA_DIR=/Users/Shared/ai-photo-lib/postgres
LLAMA_MODEL=/Users/Shared/models/vision.gguf
LLAMA_MMPROJ=/Users/Shared/models/mmproj.gguf
EMBED_MODEL=/Users/Shared/models/embed.gguf
```

### 初始化与启动

```bash
./scripts/bootstrap-macos.sh
DEPLOY_PROFILE=runtime ./scripts/svc.sh start
```

或直接在 `.env` 里写 `DEPLOY_PROFILE=runtime` 后运行：

```bash
./scripts/svc.sh start
```

运行机默认行为：

- API 不开 reload
- Web 先 build，再用 `vite preview`
- 服务适合长期驻留

## 3. MacBook -> Mac mini 的开发部署流程

推荐采用 Git 拉取式部署：

### MacBook 开发机

```bash
git commit -am "..."
git push
```

### Mac mini 运行机

```bash
git pull
./scripts/bootstrap-macos.sh
./scripts/svc.sh restart api web worker
```

如果这次改动涉及数据库 migration：

- 不需要手动额外执行 `alembic upgrade`
- `start api` / `restart api` 时会自动跑 migration

如果你想在部署前手动确认 migration：

```bash
./scripts/init-db.sh
```

如果改动涉及前端依赖：

- `bootstrap-macos.sh` 会重新执行 `npm install`
- `WEB_MODE=preview` 时，`start web` 会自动重新 build

## 4. 将来迁移到第二台 Mac mini

迁移步骤建议如下：

1. 在新 Mac mini 安装 Homebrew、Python、Node、PostgreSQL、llama.cpp
2. 拉取同一个仓库
3. 准备新的 `.env`
4. 迁移或重建以下目录：
   - `PHOTO_LIBRARY_PATH`
   - `THUMBNAIL_PATH`
   - `POSTGRES_DATA_DIR`
   - 模型目录
5. 运行 `./scripts/bootstrap-macos.sh`
6. 运行 `./scripts/svc.sh start`

这套设计里，机器切换只依赖路径和数据，不依赖 Docker volume，也不依赖固定的宿主机目录结构。

## 5. 服务管理命令

```bash
./scripts/svc.sh start
./scripts/svc.sh stop
./scripts/svc.sh restart api
./scripts/svc.sh restart web
./scripts/svc.sh status
./scripts/svc.sh logs postgres
./scripts/svc.sh logs api
./scripts/svc.sh logs web
```

可管理服务名：

```text
postgres ai embed api worker web
```

## 6. 注意事项

- `POSTGRES_BIN_DIR` 默认可指向 `/opt/homebrew/bin`
- `DATABASE_URL` 要与 `POSTGRES_PORT`、`POSTGRES_USER`、`POSTGRES_DB` 保持一致
- `LLAMA_MEDIA_PATH` 建议与 `PHOTO_LIBRARY_PATH` 指向同一照片根目录
- `OPENAI_BASE_URL`、`EMBEDDING_BASE_URL` 默认都走本机 `127.0.0.1`
- 运行机如果要被局域网访问，请把 `API_HOST`、`WEB_HOST` 设为 `0.0.0.0`

## 7. 地点搜索与 reverse geocode

当前后端已经支持两层地点能力：

- 第一层：扫描 EXIF 时提取 `gps_latitude/gps_longitude`
- 第二层：可选地把坐标反查成 `country_name/admin1/city/district/formatted_address`

推荐配置策略：

- 默认保持 `LOCATION_RESOLVER_PROVIDER=none`
  适合纯离线或首次导库，扫描稳定、无外部依赖
- 需要“2024年5月 杭州”这类地点词检索时，再开启 `nominatim`

示例配置：

```env
LOCATION_RESOLVER_PROVIDER=nominatim
LOCATION_RESOLVER_ENDPOINT=https://nominatim.openstreetmap.org/reverse
LOCATION_RESOLVER_TIMEOUT_SECONDS=8
LOCATION_RESOLVER_USER_AGENT=ai-photo-lib/1.0
LOCATION_CACHE_ROUNDING_DECIMALS=4
```

说明：

- `LOCATION_CACHE_ROUNDING_DECIMALS=4` 会把相近坐标归并到缓存，减少重复 reverse geocode 请求
- provider 关闭时不会报错，只是不会填充地点名字段
- 当前实现已经内置地点缓存表 `photo_location_cache`

## 8. 批量回填地点运维说明

适用场景：

- 旧照片已经有 GPS，但新增地点字段还没填
- 之前 `LOCATION_RESOLVER_PROVIDER=none`，后来想补地点名
- 更换 reverse geocode provider 后，需要重新补齐地点

推荐操作顺序：

1. 确认数据库 migration 已经完成

```bash
./scripts/init-db.sh
```

2. 在 `.env` 中开启 reverse geocode provider

```env
LOCATION_RESOLVER_PROVIDER=nominatim
```

3. 重启 API，让新配置生效

```bash
./scripts/svc.sh restart api
```

4. 对目标项目触发“只补地点”的 reindex

```bash
curl -X POST "http://127.0.0.1:8000/projects/1/scan/reindex?scope=missing_location"
```

5. 查看进度

```bash
curl "http://127.0.0.1:8000/projects/1/scan/status"
```

6. 如果需要全量重跑元数据和地点，可使用：

```bash
curl -X POST "http://127.0.0.1:8000/projects/1/scan/reindex?scope=all"
```

建议：

- 首次开启 provider 时，优先用 `missing_location`
- 如果照片很多，建议分项目分批执行
- Nominatim 属于公共服务，批量回填时应控制节奏，避免高并发频繁重试
- 如果后续切到商业地理服务，优先保留当前“扫描写入 + 缓存表复用”的结构，不需要改搜索层

更详细的操作步骤见：

- `Design-document/location-backfill-runbook.md`
- `Design-document/scanner-failfast-runbook.md`

## 9. 当前保留的 Docker 文件

仓库中仍保留旧的 `docker-compose.yml` 与 `Dockerfile`，用于历史兼容和参考。

当前默认维护路径是：

- macOS native 启动脚本
- macOS native `.env` 配置
- MacBook 开发机 / Mac mini 运行机 双机协作流程
