# AI Photo Library

本仓库现在以 macOS native 部署为主，不再把 Docker 作为默认运行方式。

推荐的使用模型：

- MacBook Air M4：开发机，跑 `web + api`，按需跑 `worker / llama`
- Mac mini M4：运行机，长期运行 `postgres + api + web + worker + llama`

两台机器共用同一套代码入口：

- 启动脚本：`./scripts/svc.sh`
- 初始化脚本：`./scripts/bootstrap-macos.sh`
- 配置方式：每台机器各自维护一份 `.env`

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
- API 启动时自动跑 Alembic migration，降低部署切换成本。

## 目录与配置建议

建议把代码和运行数据分开：

- 代码仓库：`~/Workspace/ai-photo-lib`
- 照片目录：`/Volumes/Photos/...` 或 `~/Pictures/...`
- 模型目录：`/Volumes/Models/...` 或 `~/Models/...`
- PostgreSQL 数据目录：单独放在 `POSTGRES_DATA_DIR`
- 缩略图目录：单独放在 `THUMBNAIL_PATH`

关键点：

- `.env` 不要在两台机器之间直接复用，路径和暴露地址通常不同。
- `PHOTO_LIBRARY_PATH`、`THUMBNAIL_PATH`、`POSTGRES_DATA_DIR` 都建议写绝对路径。
- 如果未来切到第二台 Mac mini，只要新机器重新准备这些目录并填写新的 `.env` 即可。

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
```

### 初始化

```bash
./scripts/bootstrap-macos.sh
```

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

## 7. 当前保留的 Docker 文件

仓库中仍保留旧的 `docker-compose.yml` 与 `Dockerfile`，用于历史兼容和参考。

当前默认维护路径是：

- macOS native 启动脚本
- macOS native `.env` 配置
- MacBook 开发机 / Mac mini 运行机 双机协作流程
