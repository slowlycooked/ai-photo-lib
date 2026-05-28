# Scanner Fail-Fast 运维 Runbook

## 背景

扫描链路已从“默认项目路径/缩略图目录自动 fallback”收敛为“显式失败”。

触发条件：

- 项目 `photo_library_path` 不存在
- 项目 `thumbnail_path` 为空
- 项目 `thumbnail_path` 不可写

失败时会直接返回错误状态，不再尝试回退到全局配置路径，也不会在运行时悄悄改写项目配置。

## 常见症状

`/projects/{project_id}/scan/status` 中可能出现：

- `Directory not found: ...`
- `Missing required project thumbnail_path`
- `Thumbnail path is not writable: ...`

## 处理步骤

1. 检查项目配置

```bash
curl "http://127.0.0.1:8000/projects"
```

确认目标项目的 `photo_library_path` 与 `thumbnail_path`。

2. 校验路径存在性与权限

```bash
ls -ld /your/photo/library
ls -ld /your/thumbnail/path
```

3. 修复后重试扫描

```bash
curl -X POST "http://127.0.0.1:8000/projects/<project_id>/scan/start"
```

4. 查看进度

```bash
curl "http://127.0.0.1:8000/projects/<project_id>/scan/status"
```

## 推荐实践

- 始终为每个项目显式配置 `photo_library_path` 与 `thumbnail_path`
- 不依赖默认项目语义做路径兜底
- 上线前执行 `./scripts/release-preflight.sh`，并关注 scanner 相关错误日志
