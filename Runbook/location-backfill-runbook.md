# 批量回填地点运维说明

适用场景：

- 历史照片已有 GPS，经纬度已入库，但还没有 `city` / `district` / `formatted_address`
- 之前 `LOCATION_RESOLVER_PROVIDER=none`，现在准备开启地点搜索
- 更换 reverse geocode provider 后，准备按项目批量补齐地点字段

## 前置条件

1. 数据库 schema 已升级到包含地点字段和缓存表的版本
2. API 进程读取的是最新 `.env`
3. 目标照片已具备 `gps_latitude` 和 `gps_longitude`

## 推荐 provider 策略

- 开发验证、小批量补数：`nominatim`
- 长期、大批量、稳定 SLA：后续切换到自建或商业地理编码服务

当前代码已支持：

- 关闭 provider 时安全跳过地点反查
- 把反查结果缓存到 `photo_location_cache`
- 通过 `missing_location` 只补未解析地点的照片

## 操作步骤

### 1. 执行数据库迁移

```bash
./scripts/init-db.sh
```

### 2. 修改 `.env`

```env
LOCATION_RESOLVER_PROVIDER=nominatim
LOCATION_RESOLVER_ENDPOINT=https://nominatim.openstreetmap.org/reverse
LOCATION_RESOLVER_TIMEOUT_SECONDS=8
LOCATION_RESOLVER_USER_AGENT=ai-photo-lib/1.0
LOCATION_CACHE_ROUNDING_DECIMALS=4
```

建议：

- `LOCATION_CACHE_ROUNDING_DECIMALS=4` 先不要改大，优先提高缓存命中率
- `LOCATION_RESOLVER_USER_AGENT` 建议带上你的服务标识，避免公共服务拒绝请求

### 3. 重启 API

```bash
./scripts/svc.sh restart api
```

### 4. 触发“只补地点”的 reindex

```bash
curl -X POST "http://127.0.0.1:8000/projects/1/scan/reindex?scope=missing_location"
```

如果你的 API 不是本地监听，请把 `127.0.0.1:8000` 换成对应地址。

### 5. 查看进度

```bash
curl "http://127.0.0.1:8000/projects/1/scan/status"
```

返回里重点关注：

- `running`
- `scanned`
- `updated`
- `errors`
- `message`

### 6. 需要全量重跑时

```bash
curl -X POST "http://127.0.0.1:8000/projects/1/scan/reindex?scope=all"
```

`scope=all` 会重新抽 EXIF 并尝试重新反查地点，适合：

- 更换 provider
- 调整缓存精度
- 需要刷新历史地点字段

## 推荐操作顺序

首次上线地点搜索时，建议这样做：

1. 先选一个小项目验证 `missing_location`
2. 确认搜索 `2024年5月 杭州` 这类 query 能命中
3. 再按项目分批回填全部历史照片

## 注意事项

- Nominatim 属于公共服务，不适合高并发暴力补数
- 如果项目照片很多，建议分批执行，不要多个大项目同时回填
- provider 关闭时，搜索仍可用时间和 GPS 是否存在等过滤，只是不能直接按地点名检索
- `photo_location_cache` 会缓存近似坐标的反查结果，相同地点附近照片不会每张都重复请求

## 故障排查

### 1. 触发了 reindex，但 `updated=0`

优先检查：

- `.env` 是否真的启用了 `LOCATION_RESOLVER_PROVIDER`
- 目标照片是否已经有 GPS
- 该批照片是否已经有 `location_resolved_at`

### 2. `errors` 持续增加

优先检查：

- API 日志里是否有 reverse geocode 超时或限流
- provider endpoint 是否可访问
- `LOCATION_RESOLVER_TIMEOUT_SECONDS` 是否过低

### 3. 搜索仍搜不到地点词

优先检查：

- 对应照片的 `city` / `district` / `formatted_address` 是否已写入
- 查询是否属于纯地点词或“年月 + 地点词”模式
- API 是否已重启到最新代码
