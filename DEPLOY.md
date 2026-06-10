# ai-photo-lib 部署与升级指南（macOS / Windows x86）

本文档是独立部署说明，覆盖以下场景：

- `git clone` 拉取代码
- 配置文件更新（基于 `.env.example`）
- 本地化构建与启动
- 支持 `macOS` 与 `Windows x86`（Intel/AMD 64 位）
- 后续版本升级与回滚建议

> 说明：当前仓库的服务编排脚本（如 `scripts/svc.sh`、`scripts/bootstrap-macos.sh`）主要面向 macOS。Windows 使用“手动启动流程”。

---

## 1. 部署前准备

### 1.1 通用依赖

- Git（用于克隆与升级）
- Python 3.11
- Node.js 20 + npm
- PostgreSQL 17（需安装 pgvector 扩展）

### 1.2 可选依赖（AI 本地模型）

- llama-server（用于视觉模型与 embedding，本地 OpenAI 兼容接口）
- 对应 GGUF 模型文件

如果暂时不跑本地模型，可先只完成 API/Web/DB 部署，再按需接入模型服务。

---

## 2. 代码拉取（git clone）

在目标机器执行：

```bash
git clone https://github.com/<your-org>/ai-photo-lib.git
cd ai-photo-lib
```

如果你已经有仓库，只需后续走“升级更新”章节。

---

## 3. 配置文件更新

### 3.1 创建本机配置

```bash
cp .env.example .env
```

### 3.2 只修改已有配置项（不要新增自定义键）

请在 `.env` 中按机器实际情况更新这些已有项：

- 路径相关：`PHOTO_LIBRARY_PATH`、`THUMBNAIL_PATH`、`POSTGRES_DATA_DIR`
- 数据库相关：`POSTGRES_BIN_DIR`、`POSTGRES_USER`、`POSTGRES_DB`、`POSTGRES_PASSWORD`、`POSTGRES_PORT`、`DATABASE_URL`
- API/Web：`API_HOST`、`API_PORT`、`WEB_HOST`、`WEB_PORT`、`WEB_MODE`
- 鉴权：`AUTH_USERNAME`、`AUTH_PASSWORD`、`AUTH_SESSION_SECRET`
- AI（如启用）：`OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_VISION_MODEL`、`EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`

### 3.3 配置原则

- 必需配置缺失时，系统会显式失败；不要依赖硬编码默认值。
- 建议所有路径使用绝对路径。
- 不要在代码中写死端口、模型地址、项目 ID 或 Prompt。

---

## 4. macOS 本地化构建与启动（推荐）

### 4.1 安装系统依赖

```bash
brew install python@3.11 node@20 postgresql@17 pgvector
```

如需本地模型服务：

```bash
brew install llama.cpp
```

### 4.2 一键安装项目依赖

在仓库根目录执行：

```bash
./scripts/bootstrap-macos.sh
```

该脚本会：

- 创建 `apps/api/.venv`
- 安装 `apps/api/requirements.txt`
- 安装 `apps/web` 的 npm 依赖

### 4.3 初始化数据库

```bash
./scripts/svc.sh start postgres
./scripts/init-db.sh
./scripts/db-schema.sh check
./scripts/db-schema.sh verify
```

### 4.4 启动服务

开发常用（postgres + api + web）：

```bash
./scripts/dev-up.sh
```

完整启动（含 worker/ai/embed，取决于 `.env` 配置）：

```bash
./scripts/svc.sh start
```

仅启动手机端前端：

```bash
./scripts/svc.sh start mobile-web
```

常用运维命令：

```bash
./scripts/svc.sh status
./scripts/svc.sh logs api
./scripts/svc.sh restart api
./scripts/svc.sh stop
```

---

## 5. Windows x86 本地化构建与启动（手动流程）

> 建议使用 PowerShell 7 或 Windows PowerShell。以下命令使用 PowerShell 语法。

### 5.1 安装系统依赖

- 安装 Git for Windows
- 安装 Python 3.11 x64（勾选 Add Python to PATH）
- 安装 Node.js 20 LTS
- 安装 PostgreSQL 17（并安装 pgvector 扩展）

### 5.2 拉取代码并创建配置

```powershell
git clone https://github.com/<your-org>/ai-photo-lib.git
cd ai-photo-lib
Copy-Item .env.example .env
```

编辑 `.env`，重点确认 Windows 路径和数据库连接：

- `PHOTO_LIBRARY_PATH`
- `THUMBNAIL_PATH`
- `POSTGRES_DATA_DIR`
- `DATABASE_URL`
- `API_HOST/API_PORT`
- `WEB_HOST/WEB_PORT`

### 5.3 安装后端依赖

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5.4 安装前端依赖与构建

```powershell
cd ../web
npm install
npm run build
```

### 5.5 执行数据库迁移

```powershell
cd ../api
.\.venv\Scripts\python -m alembic upgrade head
```

### 5.6 启动 API / Worker / Web

打开 3 个 PowerShell 窗口：

窗口 A（API）：

```powershell
cd <repo>\apps\api
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

窗口 B（Worker）：

```powershell
cd <repo>\apps\worker
..\api\.venv\Scripts\python main.py
```

窗口 C（Web 预览）：

```powershell
cd <repo>\apps\web
npm run preview -- --host 0.0.0.0 --port 8088
```

如果你是开发调试，也可以把窗口 C 改成：

```powershell
npm run dev -- --host 0.0.0.0 --port 8088
```

---

## 6. 本地化构建产物说明

- 前端构建产物目录：`apps/web/dist`
- 手机端前端构建产物目录：`apps/mobile-web/dist`
- 后端为 Python 运行时，不需要单独打包二进制
- Worker 与 API 共享 `apps/api` 代码与依赖环境

### 6.1 手机端切换建议

推荐生产部署使用同域路径：

- 桌面端：`/`
- 手机端：`/m/`
- API：`/api/`

这样可以复用同源 Cookie session，并启用桌面端的“移动端自动跳转 `/m`”能力。

说明：桌面端会在移动浏览器下探测 `/m/` 是否可用；仅在可用时才自动跳转，不会影响独立端口开发模式。

推荐目录落位：

- `apps/web/dist` -> Nginx 根目录（例如 `/usr/share/nginx/html`）
- `apps/mobile-web/dist` -> Nginx 子目录（例如 `/usr/share/nginx/html/m`）

示例 Nginx 配置（同域 `/` + `/m/` + `/api/`）：

```nginx
server {
	listen 80;
	server_name _;
	root /usr/share/nginx/html;
	index index.html;

	location /api/ {
		proxy_pass http://api:8000/;
		proxy_set_header Host $host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		proxy_read_timeout 120s;
	}

	location /m/ {
		try_files $uri $uri/ /m/index.html;
	}

	location / {
		try_files $uri $uri/ /index.html;
	}
}
```

发布后建议做冒烟验证：

```bash
# 1) 桌面端
curl -I http://<host>/

# 2) 手机端入口
curl -I http://<host>/m/

# 3) API
curl http://<host>/api/health
```

手机浏览器自动切换验证：

1. 在手机访问 `http://<host>/photos`，应自动进入 `/m/photos`。
2. 访问 `http://<host>/photos?desktop=1`，应保持桌面端并记住偏好。
3. 访问 `http://<host>/photos?mobile=1`，应清除偏好并恢复自动跳转。

### 6.2 一键发布桌面+手机前端（单机）

仓库已提供脚本：`scripts/publish-web.sh`

示例：

```bash
./scripts/publish-web.sh \
	--desktop-dir /usr/share/nginx/html \
	--mobile-dir /usr/share/nginx/html/m
```

脚本行为：

1. 构建 `apps/web` 与 `apps/mobile-web`
2. 同步 `apps/web/dist` 到 `--desktop-dir`
3. 同步 `apps/mobile-web/dist` 到 `--mobile-dir`
4. 同步时会删除目标目录中已不存在于 dist 的旧文件（`rsync --delete`）

常用选项：

- `--dry-run`：仅打印计划动作，不写入文件
- `--no-build`：跳过构建，仅同步已有 dist 产物

建议在升级前后执行基础检查：

```bash
# macOS
./scripts/svc.sh status
```

```powershell
# Windows（示例）
Invoke-WebRequest http://127.0.0.1:8000/health
```

---

## 7. 升级更新流程（macOS / Windows 通用）

### 7.1 升级前备份

至少备份：

- `.env`
- PostgreSQL 数据库（逻辑备份或数据目录快照）
- 关键业务目录（照片目录、缩略图目录）

### 7.2 拉取新版本代码

```bash
git fetch --all --tags
git checkout <release-tag-or-branch>
git pull --ff-only
```

### 7.3 对齐配置文件

1. 对比新版本 `.env.example` 与你当前 `.env`。
2. 仅补充“新版本已定义”的配置项。
3. 不要自行新增未定义配置键。

推荐使用差异对比工具（如 `git diff` / VS Code Compare）逐项确认。

### 7.4 升级依赖

macOS：

```bash
./scripts/bootstrap-macos.sh
```

Windows：

```powershell
cd apps/api
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd ../web
npm install
npm run build
```

### 7.5 执行数据库迁移

macOS：

```bash
./scripts/init-db.sh
./scripts/db-schema.sh check
```

Windows：

```powershell
cd apps/api
.\.venv\Scripts\python -m alembic upgrade head
```

### 7.6 重启服务并验证

- 重启 API / Worker / Web
- 检查健康接口和关键页面
- 验证项目隔离与核心链路（扫描、搜索、任务）

---

## 8. 回滚建议

若升级失败，按以下顺序回滚：

1. 停止服务（API/Worker/Web）
2. 切回上一稳定代码版本（tag/commit）
3. 恢复 `.env` 到升级前备份
4. 还原数据库备份（如果迁移已破坏兼容）
5. 启动服务并验证健康接口

> 数据库回滚必须与备份策略配套执行；不要在未备份情况下直接做不可逆迁移。

---

## 9. 常见问题

### 9.1 API 启动时报配置缺失

这是预期保护行为。请补齐 `.env` 必填项，不要在代码中写默认值绕过。

### 9.2 Windows 启动 worker 失败，提示依赖找不到

通常是没有使用 `apps/api/.venv` 的 Python。请确认 worker 使用的是：

- `..\api\.venv\Scripts\python main.py`

### 9.3 前端可以打开但请求失败

优先检查：

- `API_HOST/API_PORT` 是否正确
- CORS 配置是否包含 Web 访问地址
- API 进程日志是否有启动自检错误

---

## 10. 推荐发布节奏

- 日常开发：按功能分支迭代，尽量小步提交
- 预发布：先在本地完整跑一次“升级流程 + 健康检查”
- 正式发布：固定 tag，保留 `.env` 与数据库备份
