import { UserRound } from "lucide-react";
import { api, type PersonSummary } from "@/api";
import { formatDateTime } from "./formatDateTime";

export function PersonCard({
  projectId,
  faceCropEnabled,
  person,
  selected,
  onSelect,
}: {
  projectId: number;
  faceCropEnabled: boolean;
  person: PersonSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={[
        "w-full text-left rounded-xl border p-4 transition-colors",
        selected
          ? "border-primary bg-primary/5 shadow-sm"
          : "border-hairline bg-canvas hover:bg-surface-card",
      ].join(" ")}
    >
      <div className="flex gap-3">
        <div className="w-16 h-16 rounded-lg overflow-hidden border border-hairline bg-surface-soft flex-shrink-0">
          {faceCropEnabled && person.representative_face_detection_id ? (
            <img
              src={api.projects.faceCropUrl(
                projectId,
                person.representative_face_detection_id,
                person.updated_at,
              )}
              alt={person.display_name}
              className="w-full h-full object-cover"
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-mute">
              <UserRound className="w-6 h-6" />
            </div>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-body-sm font-semibold text-ink truncate">
              {person.display_name}
            </h3>
            <span
              className={[
                "px-2 py-0.5 rounded-full text-caption-sm",
                person.is_named
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-secondary-bg text-mute",
              ].join(" ")}
            >
              {person.is_named ? "已命名" : "未命名"}
            </span>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-caption-sm text-mute">
            <span>样本 {person.sample_count}</span>
            <span>已确认 {person.confirmed_sample_count}</span>
            <span>自动识别 {person.auto_assigned_count}</span>
            <span>待确认 {person.review_pending_count}</span>
          </div>
          <p className="mt-2 text-caption-sm text-mute">
            最近更新 {formatDateTime(person.updated_at)}
          </p>
        </div>
      </div>
    </button>
  );
}
