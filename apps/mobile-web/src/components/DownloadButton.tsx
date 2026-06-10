import { api } from "@/api";

export function DownloadButton({
  projectId,
  photoId,
}: {
  projectId: number;
  photoId: number;
}) {
  return (
    <a
      className="inline-flex h-11 items-center justify-center rounded-xl bg-mobileAccent px-4 text-sm font-semibold text-white active:bg-mobileAccentPressed"
      href={api.photos.originalUrl(projectId, photoId)}
      download
    >
      下载 / 打开原图
    </a>
  );
}
