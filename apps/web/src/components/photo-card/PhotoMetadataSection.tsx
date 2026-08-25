import { Aperture, Calendar, Camera, ImageIcon, MapPin, Ruler, Tag } from "lucide-react";
import type { Photo, PhotoDetail } from "@/api/types";
import { formatLocationAddress, formatLocationSummary } from "@/lib/utils";
import { InfoRow } from "./InfoRow";

interface PhotoMetadataSectionProps {
  photo: Photo;
  detail?: PhotoDetail;
}

function formatSize(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "未知日期";
  const d = new Date(iso);
  return d.toLocaleDateString("zh-CN", { year: "numeric", month: "short", day: "numeric" });
}

function formatExifDecimal(value: string | null, maximumFractionDigits = 2): string | null {
  if (!value) return null;

  const [numeratorText, denominatorText, ...rest] = value.split("/");
  const numerator = Number(numeratorText);
  const denominator = denominatorText == null ? 1 : Number(denominatorText);
  if (rest.length > 0 || !Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator === 0) {
    return value;
  }

  return (numerator / denominator).toLocaleString("zh-CN", {
    maximumFractionDigits,
    useGrouping: false,
  });
}

export function PhotoMetadataSection({ photo, detail }: PhotoMetadataSectionProps) {
  const locationSummary = formatLocationSummary(detail, { short: true });
  const locationAddress = formatLocationAddress(detail);

  return (
    <div className="space-y-3">
      <h3 className="text-caption-sm font-semibold uppercase tracking-wide text-mute">照片信息</h3>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-body-sm">
        <InfoRow icon={<Calendar className="w-3.5 h-3.5" />} label="拍摄时间" value={formatDate(photo.taken_at)} />
        <InfoRow
          icon={<Ruler className="w-3.5 h-3.5" />}
          label="尺寸"
          value={photo.width && photo.height ? `${photo.width} × ${photo.height}` : "—"}
        />
        <InfoRow icon={<Tag className="w-3.5 h-3.5" />} label="文件大小" value={formatSize(photo.file_size)} />
        <InfoRow
          icon={<ImageIcon className="w-3.5 h-3.5" />}
          label="格式"
          value={photo.mime_type?.replace("image/", "").toUpperCase() ?? "—"}
        />
      </div>

      {detail && (locationSummary || detail.gps_latitude != null || detail.camera_make || detail.aperture) && (
        <div className="space-y-3 pt-1 border-t border-hairline">
          {locationSummary && (
            <div className="rounded-md border border-emerald-200 bg-emerald-50/70 p-3">
              <div className="flex items-start gap-2">
                <span className="mt-0.5 text-emerald-700">
                  <MapPin className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <p className="text-caption-sm text-emerald-700">拍摄地点</p>
                  <p className="text-body-sm font-semibold text-emerald-950">{locationSummary}</p>
                  {locationAddress && locationAddress !== locationSummary && (
                    <p className="mt-1 break-words text-caption-sm text-emerald-800">{locationAddress}</p>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="space-y-2">
            <h3 className="text-caption-sm font-semibold uppercase tracking-wide text-mute">EXIF 信息</h3>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-body-sm">
            {detail.gps_latitude != null && detail.gps_longitude != null && (
              <InfoRow
                icon={<MapPin className="w-3.5 h-3.5" />}
                label="GPS"
                value={
                  <a
                    href={`https://maps.apple.com/?ll=${detail.gps_latitude},${detail.gps_longitude}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary underline underline-offset-2"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {detail.gps_latitude.toFixed(5)}, {detail.gps_longitude.toFixed(5)}
                  </a>
                }
              />
            )}
            {(detail.camera_make || detail.camera_model) && (
              <InfoRow
                icon={<Camera className="w-3.5 h-3.5" />}
                label="相机"
                value={[detail.camera_make, detail.camera_model].filter(Boolean).join(" ")}
              />
            )}
            {detail.lens_model && (
              <InfoRow
                icon={<Aperture className="w-3.5 h-3.5" />}
                label="镜头"
                value={detail.lens_model}
              />
            )}
            {(detail.aperture || detail.exposure_time || detail.iso) && (
              <InfoRow
                icon={<Aperture className="w-3.5 h-3.5" />}
                label="曝光"
                value={[
                  detail.aperture ? `f/${formatExifDecimal(detail.aperture)}` : null,
                  detail.exposure_time ? `${detail.exposure_time}s` : null,
                  detail.iso ? `ISO ${detail.iso}` : null,
                  detail.focal_length ? `${formatExifDecimal(detail.focal_length)}mm` : null,
                ].filter(Boolean).join("  ")}
              />
            )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
