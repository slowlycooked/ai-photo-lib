import { useState } from "react";
import { Calendar, ImageIcon, MapPin, ZoomIn } from "lucide-react";
import type { SearchResultItem } from "@/api/types";
import { formatLocationAddress, formatLocationSummary } from "@/lib/utils";

interface SearchCardProps {
  item: SearchResultItem;
  debug?: boolean;
  onPreview?: (item: SearchResultItem) => void;
}

export function SearchCard({ item, debug, onPreview }: SearchCardProps) {
  const [loaded, setLoaded] = useState(false);
  const locationSummary = formatLocationSummary(item, { short: true });
  const locationAddress = formatLocationAddress(item);
  const takenAtLabel = item.taken_at
    ? new Date(item.taken_at).toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : null;

  return (
    <div className="break-inside-avoid mb-3">
      <div className="bg-canvas rounded-md overflow-hidden border border-hairline hover:shadow-md transition-shadow">
        <div
          className="relative bg-surface-card cursor-zoom-in group"
          onClick={() => onPreview?.(item)}
          role="button"
          aria-label={`预览 ${item.file_name}`}
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && onPreview?.(item)}
        >
          {!loaded && (
            <div className="flex items-center justify-center h-32">
              <ImageIcon className="w-8 h-8 text-stone" />
            </div>
          )}
          <img
            src={item.thumbnail_url}
            alt={item.file_name}
            className="w-full object-cover"
            style={{ opacity: loaded ? 1 : 0, transition: "opacity 0.2s" }}
            onLoad={() => setLoaded(true)}
          />
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
            <ZoomIn className="w-6 h-6 text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow" />
          </div>
        </div>

        <div className="p-3 space-y-2">
          {item.caption && <p className="text-body-sm text-ink line-clamp-2">{item.caption}</p>}

          {(locationSummary || takenAtLabel) && (
            <div className="flex flex-wrap gap-1.5">
              {locationSummary && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-800">
                  <MapPin className="h-3.5 w-3.5" />
                  <span className="max-w-[180px] truncate" title={locationAddress ?? locationSummary}>
                    {locationSummary}
                  </span>
                </span>
              )}
              {takenAtLabel && (
                <span className="inline-flex items-center gap-1 rounded-full bg-surface-card px-2.5 py-1 text-[11px] font-medium text-mute">
                  <Calendar className="h-3.5 w-3.5" />
                  {takenAtLabel}
                </span>
              )}
            </div>
          )}

          {item.matched_tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {item.matched_tags.slice(0, 6).map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-caption-md font-medium"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}

          <p className="text-caption-sm text-ash truncate">{item.file_name}</p>
          {item.face_count != null && item.face_count > 0 && (
            <p className="text-caption-sm text-mute">人脸 {item.face_count}</p>
          )}

          {debug && (
            <div className="text-[10px] font-mono text-muted-foreground space-y-0.5 border-t border-dashed border-border pt-1">
              {(item.taken_at || item.camera_make || item.camera_model || item.iso != null || item.gps_latitude != null) && (
                <div className="text-[9px] text-teal-700 dark:text-teal-300 space-y-0">
                  {item.taken_at && <div>📅 {new Date(item.taken_at).toLocaleDateString("zh-CN")}</div>}
                  {locationSummary && <div>📍 {locationSummary}</div>}
                  {(item.camera_make || item.camera_model) && (
                    <div>📷 {[item.camera_make, item.camera_model].filter(Boolean).join(" ")}</div>
                  )}
                  {item.iso != null && <div>ISO {item.iso}</div>}
                  {item.gps_latitude != null && <div>📍 GPS</div>}
                </div>
              )}
              {item.match_source?.includes("metadata") && (
                <div className="text-teal-600 dark:text-teal-400 font-semibold">metadata match</div>
              )}
              {(item.rrf_score != null || item.vector_score != null) && (
                <>
                  {item.rrf_score != null && <div>rrf: {item.rrf_score.toFixed(5)}</div>}
                  {item.keyword_score != null && <div>kw: {item.keyword_score.toFixed(4)}</div>}
                  {item.vector_score != null && <div>vec: {item.vector_score.toFixed(4)}</div>}
                  {item.field_scores && (
                    <div>
                      {Object.entries(item.field_scores)
                        .map(([k, v]) => `${k}:${(v as number).toFixed(3)}`)
                        .join(" ")}
                    </div>
                  )}
                </>
              )}
              {item.explain?.keyword && (
                <div className="text-[9px] text-blue-600 dark:text-blue-400">
                  kw_rank:{item.explain.keyword.rank ?? "?"}{" "}
                  fields:{Object.keys(item.explain.keyword.matched_fields ?? {}).join(",")}
                </div>
              )}
              {item.explain?.vector && (
                <div className="text-[9px] text-purple-600 dark:text-purple-400">
                  vec_rank:{item.explain.vector.rank ?? "?"}{" "}
                  {Object.entries(item.explain.vector.field_scores ?? {})
                    .map(([k, v]) => `${k}:${(v as number).toFixed(3)}`)
                    .join(" ")}
                </div>
              )}
              {item.match_source && (
                <div className="text-[9px] text-stone">{item.match_source.join(" ")}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
