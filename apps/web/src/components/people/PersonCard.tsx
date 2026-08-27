import { UserRound } from "lucide-react";
import { api, type PersonSummary } from "@/api";
import { formatDateTime } from "./formatDateTime";

export function PersonCard({
  projectId,
  faceCropEnabled,
  person,
  selected,
  checked = false,
  showCheckbox = false,
  actionBusy = false,
  onSelect,
  onToggleChecked,
  onArchive,
  onDelete,
}: {
  projectId: number;
  faceCropEnabled: boolean;
  person: PersonSummary;
  selected: boolean;
  checked?: boolean;
  showCheckbox?: boolean;
  actionBusy?: boolean;
  onSelect: () => void;
  onToggleChecked?: (checked: boolean) => void;
  onArchive?: () => void;
  onDelete?: () => void;
}) {
  return (
    <article
      className={[
        "relative w-full overflow-hidden rounded-lg border p-3 transition-colors [content-visibility:auto] [contain-intrinsic-size:112px]",
        selected
          ? "border-primary bg-primary/5 shadow-sm ring-2 ring-primary/10"
          : "border-hairline bg-canvas hover:bg-surface-card",
      ].join(" ")}
    >
      <div className="flex items-start gap-2">
        {showCheckbox && (
          <label
            className="grid h-11 w-11 shrink-0 cursor-pointer place-items-center rounded-md hover:bg-surface-soft"
            onClick={(e) => e.stopPropagation()}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => onToggleChecked?.(e.target.checked)}
              className="h-5 w-5 rounded border-hairline text-primary focus:ring-focus-outer"
              aria-label={`选择人物 ${person.display_name}`}
            />
          </label>
        )}
        <button type="button" onClick={onSelect} aria-pressed={selected} className="min-w-0 flex-1 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer">
          <div className="flex gap-3">
          <div className="h-14 w-14 flex-shrink-0 overflow-hidden rounded-full border border-hairline bg-surface-soft">
            {faceCropEnabled && person.representative_face_detection_id ? (
              <img
                src={api.projectFaces.cropUrl(
                  projectId,
                  person.representative_face_detection_id,
                  person.updated_at,
                )}
                alt={person.display_name}
                loading="lazy"
                decoding="async"
                className="h-full w-full object-cover"
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                }}
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-mute">
                <UserRound className="h-6 w-6" aria-hidden="true" />
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              <h3 className="min-w-0 flex-1 truncate text-body-sm font-semibold text-ink">
                {person.display_name}
              </h3>
              <span
                className={[
                  "shrink-0 rounded-full px-2 py-0.5 text-caption-sm font-medium",
                  person.is_named
                    ? "bg-success/10 text-success"
                    : "bg-secondary-bg text-secondary",
                ].join(" ")}
              >
                {person.is_named ? "已命名" : "未命名"}
              </span>
            </div>
            {person.name_tags && person.name_tags.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {person.name_tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-caption-sm text-mute">
              <span>样本 <strong className="font-medium tabular-nums text-secondary">{person.sample_count}</strong></span>
              <span>已确认 <strong className="font-medium tabular-nums text-secondary">{person.confirmed_sample_count}</strong></span>
              {person.review_pending_count > 0 && <span className="rounded-full bg-warning/10 px-2 py-0.5 font-medium text-secondary">待确认 {person.review_pending_count}</span>}
            </div>
            <p className="mt-1.5 truncate text-caption-sm text-mute">
              更新 {formatDateTime(person.updated_at)}
            </p>
          </div>
          </div>
        </button>
      </div>

      {selected && (onArchive || onDelete) && (
        <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-hairline pt-2">
          {onArchive && (
            <button
              type="button"
              disabled={actionBusy}
              aria-label={`将 ${person.display_name} 加入 archive`}
              onClick={onArchive}
              className="min-h-9 rounded-md border border-hairline px-2.5 text-caption-sm text-mute hover:bg-surface-soft hover:text-ink disabled:cursor-not-allowed disabled:opacity-60"
            >
              加入 archive
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              disabled={actionBusy}
              aria-label={`删除人物 ${person.display_name}`}
              onClick={onDelete}
              className="min-h-9 rounded-md border border-danger/30 px-2.5 text-caption-sm text-danger hover:bg-danger/10 disabled:cursor-not-allowed disabled:opacity-60"
            >
              删除人物
            </button>
          )}
        </div>
      )}
    </article>
  );
}
