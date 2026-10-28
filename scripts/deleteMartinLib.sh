#!/bin/sh

set -eu
umask 077

DATA_ROOT="/volume1/ai-photo-data"
MANIFEST="$DATA_ROOT/pending-original-trash.jsonl"
TRASH_SCRIPT="$DATA_ROOT/nas-trash-deleted-photos.py"
TRASH_ROOT="/volume1/photo/#recycle"

# 默认仅预演：
#   sh deleteMartinLib.sh
#
# 实际执行并归档成功清单：
#   APPLY=1 sh deleteMartinLib.sh
#
# 实际执行并删除成功清单：
#   APPLY=1 MANIFEST_SUCCESS_ACTION=delete sh deleteMartinLib.sh
APPLY="${APPLY:-0}"
MANIFEST_SUCCESS_ACTION="${MANIFEST_SUCCESS_ACTION:-archive}"

LOCK_DIR="$DATA_ROOT/.original-trash.lock"
LOCK_OWNED=0
TMP_DIR=""
PROCESSING_MANIFEST=""

log() {
    printf '%s\n' "$*"
}

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

cleanup() {
    if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
        rm -rf -- "$TMP_DIR"
    fi
    if [ "$LOCK_OWNED" = "1" ]; then
        rmdir "$LOCK_DIR" 2>/dev/null || true
    fi
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

case "$APPLY" in
    0|1) ;;
    *) fail "APPLY 只能是 0 或 1" ;;
esac

case "$MANIFEST_SUCCESS_ACTION" in
    archive|delete) ;;
    *) fail "MANIFEST_SUCCESS_ACTION 只能是 archive 或 delete" ;;
esac

[ -d "$DATA_ROOT" ] || fail "数据目录不存在: $DATA_ROOT"
[ -f "$TRASH_SCRIPT" ] || fail "Python 脚本不存在: $TRASH_SCRIPT"
[ ! -L "$TRASH_SCRIPT" ] || fail "拒绝运行符号链接脚本: $TRASH_SCRIPT"

if mkdir "$LOCK_DIR" 2>/dev/null; then
    LOCK_OWNED=1
else
    fail "已有删除批处理正在运行，或锁目录未清理: $LOCK_DIR"
fi

STALE_PROCESSING=""
for candidate in "$DATA_ROOT"/pending-original-trash.processing-*.jsonl; do
    [ -e "$candidate" ] || continue
    if [ -n "$STALE_PROCESSING" ]; then
        fail "发现多个未完成清单，请先人工检查: $STALE_PROCESSING 和 $candidate"
    fi
    STALE_PROCESSING="$candidate"
done

TMP_DIR="$(mktemp -d "$DATA_ROOT/.trash-batch.XXXXXX")"
STAMP="$(date +%Y%m%d%H%M%S)-$$"

if [ -n "$STALE_PROCESSING" ]; then
    [ -f "$STALE_PROCESSING" ] || fail "未完成清单不是普通文件: $STALE_PROCESSING"
    [ ! -L "$STALE_PROCESSING" ] || fail "拒绝处理符号链接清单: $STALE_PROCESSING"
    [ -s "$STALE_PROCESSING" ] || fail "未完成清单为空: $STALE_PROCESSING"
    INPUT_MANIFEST="$STALE_PROCESSING"
    if [ "$APPLY" = "1" ]; then
        PROCESSING_MANIFEST="$STALE_PROCESSING"
        log "执行模式：APPLY，续跑未完成清单: $PROCESSING_MANIFEST"
    else
        log "执行模式：DRY RUN，检查未完成清单: $STALE_PROCESSING"
    fi
    if [ -s "$MANIFEST" ]; then
        log "提示：新的待处理清单将保留到下一批: $MANIFEST"
    fi
else
    [ -f "$MANIFEST" ] || {
        log "没有待处理清单: $MANIFEST"
        exit 0
    }
    [ ! -L "$MANIFEST" ] || fail "拒绝处理符号链接清单: $MANIFEST"
    [ -s "$MANIFEST" ] || {
        log "待处理清单为空: $MANIFEST"
        exit 0
    }

    if [ "$APPLY" = "1" ]; then
        PROCESSING_MANIFEST="$DATA_ROOT/pending-original-trash.processing-$STAMP.jsonl"
        [ ! -e "$PROCESSING_MANIFEST" ] || \
            fail "处理清单名称已存在: $PROCESSING_MANIFEST"
        mv "$MANIFEST" "$PROCESSING_MANIFEST"
        INPUT_MANIFEST="$PROCESSING_MANIFEST"
        log "执行模式：APPLY"
    else
        INPUT_MANIFEST="$MANIFEST"
        log "执行模式：DRY RUN，不移动文件，不处理清单"
    fi
fi

# 先完整解析清单，并按固定项目映射拆分；任何错误都会在移动前终止。
python3 - "$INPUT_MANIFEST" "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
output_dir = Path(sys.argv[2])
projects = {3: "Chang", 4: "Martin"}
entries = []
errors = []

with manifest.open("r", encoding="utf-8") as fh:
    for line_number, raw_line in enumerate(fh, start=1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc}")
            continue
        if not isinstance(entry, dict):
            errors.append(f"line {line_number}: entry 不是 JSON object")
            continue
        project_id = entry.get("project_id")
        project_name = projects.get(project_id)
        if project_name is None:
            errors.append(f"line {line_number}: 未配置 project_id={project_id!r}")
            continue
        if entry.get("project_name") != project_name:
            errors.append(f"line {line_number}: project_name 与 project_id 不匹配")
            continue
        entries.append((project_id, entry))

if errors:
    print("清单拆分失败，本次不会移动照片：", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    raise SystemExit(2)
if not entries:
    print("清单没有有效条目", file=sys.stderr)
    raise SystemExit(2)

handles = {}
try:
    for project_id, entry in entries:
        handle = handles.get(project_id)
        if handle is None:
            handle = (output_dir / f"project-{project_id}.jsonl").open(
                "x", encoding="utf-8"
            )
            handles[project_id] = handle
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
finally:
    for handle in handles.values():
        handle.close()

print(f"清单拆分通过，共 {len(entries)} 张")
PY

run_worker() {
    WORKER_MODE="$1"
    PROJECT_ID="$2"
    PROJECT_NAME="$3"
    SOURCE_ROOT="$4"
    PROJECT_MANIFEST="$TMP_DIR/project-$PROJECT_ID.jsonl"
    OUTPUT_FILE="$TMP_DIR/project-$PROJECT_ID-$WORKER_MODE.out"

    if [ ! -s "$PROJECT_MANIFEST" ]; then
        return 0
    fi

    set -- python3 "$TRASH_SCRIPT" \
        --source-root "$SOURCE_ROOT" \
        --trash-root "$TRASH_ROOT/$PROJECT_NAME" \
        --expected-project-id "$PROJECT_ID" \
        --expected-project-name "$PROJECT_NAME" \
        "$PROJECT_MANIFEST"

    case "$WORKER_MODE" in
        validate) set -- "$@" --validate-only ;;
        apply) set -- "$@" --apply ;;
        dry-run) ;;
        *) fail "未知 worker mode: $WORKER_MODE" ;;
    esac

    if ! "$@" >"$OUTPUT_FILE" 2>&1; then
        cat "$OUTPUT_FILE" >&2
        fail "$PROJECT_NAME 的 $WORKER_MODE 阶段失败；processing 清单将保留"
    fi
    cat "$OUTPUT_FILE"
}

if [ "$APPLY" = "1" ]; then
    # 必须先验证所有项目，再开始移动任何项目。
    run_worker validate 3 "Chang" "/volume1/photo/Chang"
    run_worker validate 4 "Martin" "/volume1/photo/Martin"

    run_worker apply 3 "Chang" "/volume1/photo/Chang"
    run_worker apply 4 "Martin" "/volume1/photo/Martin"

    case "$MANIFEST_SUCCESS_ACTION" in
        archive)
            ARCHIVE="$DATA_ROOT/complete-$STAMP.jsonl"
            [ ! -e "$ARCHIVE" ] || fail "归档已存在: $ARCHIVE"
            mv "$PROCESSING_MANIFEST" "$ARCHIVE"
            PROCESSING_MANIFEST=""
            log "全部处理完成；清单已重命名: $ARCHIVE"
            ;;
        delete)
            rm -f -- "$PROCESSING_MANIFEST"
            PROCESSING_MANIFEST=""
            log "全部处理完成；清单已删除"
            ;;
    esac
else
    run_worker dry-run 3 "Chang" "/volume1/photo/Chang"
    run_worker dry-run 4 "Martin" "/volume1/photo/Martin"
    log "预演完成，没有移动照片，也没有处理 JSONL"
    log "实际执行并归档清单：APPLY=1 sh $0"
    log "实际执行并删除清单：APPLY=1 MANIFEST_SUCCESS_ACTION=delete sh $0"
fi
