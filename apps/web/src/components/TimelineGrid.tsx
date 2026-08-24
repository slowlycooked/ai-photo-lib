import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, ImageOff } from "lucide-react";
import { usePhotos } from "@/hooks/usePhotos";
import { useInfiniteScrollSentinel } from "@/hooks/useInfiniteScrollSentinel";
import { MasonryGrid } from "./MasonryGrid";
import { PhotoCard } from "./PhotoCard";
import { TimelineRail } from "./TimelineRail";
import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";
import type { Photo, FolderScope } from "@/api";
import { useAuth } from "@/contexts/AuthContext";
import { canManageProjects } from "@/lib/permissions";

interface TimelineGridProps {
  projectId?: number | null;
  folderId?: number | null;
  folderScope?: FolderScope;
}

function formatGroupLabel(key: string): string {
  if (key === "unknown") return "未知日期";
  const [year, month] = key.split("-");
  const d = new Date(Number(year), Number(month) - 1);
  return d.toLocaleDateString("zh-CN", { year: "numeric", month: "long" });
}

function groupPhotosByMonth(photos: Photo[]): Map<string, Photo[]> {
  const groups = new Map<string, Photo[]>();
  for (const photo of photos) {
    const raw = photo.taken_at ?? photo.created_at;
    let key = "unknown";
    if (raw) {
      const d = new Date(raw);
      if (!isNaN(d.getTime())) {
        key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      }
    }
    const bucket = groups.get(key) ?? [];
    bucket.push(photo);
    groups.set(key, bucket);
  }
  return new Map(
    [...groups.entries()].sort(([a], [b]) => {
      if (a === "unknown") return 1;
      if (b === "unknown") return -1;
      return b.localeCompare(a);
    })
  );
}

export function TimelineGrid({ projectId, folderId, folderScope = "subtree" }: TimelineGridProps) {
  const auth = useAuth();
  const canDeletePhoto = canManageProjects(auth.session);
  const [dateFrom, setDateFrom] = useState<string | null>(null);
  const [dateTo, setDateTo] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [selectedPhotoIds, setSelectedPhotoIds] = useState<number[]>([]);
  const [deleteOriginalInBatch, setDeleteOriginalInBatch] = useState(true);
  const [batchMessage, setBatchMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, isError } =
    usePhotos({ projectId, dateFrom, dateTo, folderId, folderScope });

  const sentinelRef = useInfiniteScrollSentinel<HTMLDivElement>({
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    requireScrollDown: true,
  });

  const allPhotos = useMemo(() => {
    const loaded = data?.pages.flatMap((p) => p.items) ?? [];
    const uniqueById = new Map<number, Photo>();
    for (const photo of loaded) {
      if (!uniqueById.has(photo.id)) {
        uniqueById.set(photo.id, photo);
      }
    }
    return Array.from(uniqueById.values());
  }, [data]);
  const total = data?.pages[0]?.total ?? 0;
  const isInitialLoading = isLoading && allPhotos.length === 0;
  const priorityPhotoIds = useMemo(
    () => new Set(allPhotos.slice(0, 8).map((photo) => photo.id)),
    [allPhotos],
  );

  useEffect(() => {
    setSelectedPhotoIds([]);
    setBatchMessage(null);
  }, [projectId, folderId, folderScope, dateFrom, dateTo]);

  const batchDeleteMutation = useMutation({
    mutationFn: () => {
      if (projectId == null) {
        throw new Error("未选择项目");
      }
      return api.projectPhotos.batchDeleteRecords(projectId, {
        photo_ids: selectedPhotoIds,
        delete_original: deleteOriginalInBatch,
      });
    },
    onSuccess: (result) => {
      setSelectedPhotoIds([]);
      setBatchMessage(
        `批量删除完成：删除 ${result.deleted_count} 张，写入 NAS 清单 ${result.queued_original_for_trash_count} 张，未命中 ${result.not_found_photo_ids.length} 张。`,
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.photosBase(projectId ?? null) });
      queryClient.invalidateQueries({ queryKey: queryKeys.timeline(projectId ?? null) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tags(projectId ?? null) });
      queryClient.invalidateQueries({ queryKey: ["search"] });
    },
    onError: (error: Error) => {
      setBatchMessage(`批量删除失败：${error.message}`);
    },
  });

  const selectedCount = selectedPhotoIds.length;
  const allLoadedIds = allPhotos.map((photo) => photo.id);
  const allLoadedSelected = allLoadedIds.length > 0 && allLoadedIds.every((id) => selectedPhotoIds.includes(id));

  const togglePhotoSelection = (photoId: number, checked: boolean) => {
    setBatchMessage(null);
    setSelectedPhotoIds((prev) => {
      if (checked) {
        if (prev.includes(photoId)) {
          return prev;
        }
        return [...prev, photoId];
      }
      return prev.filter((id) => id !== photoId);
    });
  };

  const toggleSelectByPhotoIds = (photoIds: number[]) => {
    if (photoIds.length === 0) {
      return;
    }
    setBatchMessage(null);
    setSelectedPhotoIds((prev) => {
      const allSelected = photoIds.every((id) => prev.includes(id));
      if (allSelected) {
        return prev.filter((id) => !photoIds.includes(id));
      }
      const merged = new Set(prev);
      for (const id of photoIds) {
        merged.add(id);
      }
      return Array.from(merged);
    });
  };

  const toggleSelectAllLoaded = () => {
    setBatchMessage(null);
    if (allLoadedSelected) {
      setSelectedPhotoIds((prev) => prev.filter((id) => !allLoadedIds.includes(id)));
      return;
    }
    setSelectedPhotoIds((prev) => {
      const merged = new Set(prev);
      for (const id of allLoadedIds) {
        merged.add(id);
      }
      return Array.from(merged);
    });
  };

  const clearSelected = () => {
    setBatchMessage(null);
    setSelectedPhotoIds([]);
  };

  const handleBatchDelete = () => {
    if (!canDeletePhoto) {
      return;
    }
    if (selectedCount === 0 || batchDeleteMutation.isPending) {
      return;
    }
    const actionText = deleteOriginalInBatch
      ? `删除 ${selectedCount} 张照片的库记录和缩略图，并把原图写入 NAS 垃圾箱清单`
      : `删除 ${selectedCount} 张照片的库记录和缩略图`;
    if (!window.confirm(`确认${actionText}吗？此操作不可恢复。`)) {
      return;
    }
    batchDeleteMutation.mutate();
  };

  const handleMonthSelect = (key: string, from: string, to: string) => {
    if (activeKey === key) {
      // Clicking same month → clear filter
      setActiveKey(null);
      setDateFrom(null);
      setDateTo(null);
    } else {
      setActiveKey(key);
      setDateFrom(from);
      setDateTo(to);
    }
  };

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3 text-mute">
        <ImageOff className="w-8 h-8" />
        <p className="text-body-sm">无法连接 API，请确认后端服务已启动</p>
      </div>
    );
  }

  if (!isLoading && allPhotos.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4 text-mute">
        <div className="w-20 h-20 rounded-full bg-secondary-bg flex items-center justify-center">
          <ImageOff className="w-9 h-9 text-stone" />
        </div>
        <div className="text-center">
          <p className="text-heading-md font-semibold text-ink">还没有照片</p>
          <p className="text-body-sm text-mute mt-1">点击上方「重新扫描」或先启动扫描导入照片</p>
        </div>
      </div>
    );
  }

  const groups = groupPhotosByMonth(allPhotos);

  return (
    <div className="flex gap-4">
      {/* Photo grid */}
      <div className="flex-1 min-w-0 space-y-8">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-body-sm text-mute">
            共 <span className="font-semibold text-ink">{total.toLocaleString()}</span> 张照片
          </p>
          {canDeletePhoto && (
            <button
              type="button"
              onClick={toggleSelectAllLoaded}
              className="text-caption-sm text-primary hover:text-primary-pressed"
            >
              {allLoadedSelected ? "取消当前页全选" : "勾选当前页全部"}
            </button>
          )}
          {canDeletePhoto && selectedCount > 0 && (
            <button
              type="button"
              onClick={clearSelected}
              className="text-caption-sm text-primary hover:text-primary-pressed"
            >
              清空已选（{selectedCount}）
            </button>
          )}
          {activeKey && (
            <button
              onClick={() => {
                setActiveKey(null);
                setDateFrom(null);
                setDateTo(null);
              }}
              className="text-caption-sm text-primary hover:text-primary-pressed"
            >
              × 清除月份筛选
            </button>
          )}
        </div>

        {canDeletePhoto && selectedCount > 0 && (
          <div className="fixed left-4 top-24 z-30 w-[min(24rem,calc(100vw-2rem))] rounded-md border border-danger/30 bg-danger/10 p-3 shadow-lg backdrop-blur-sm">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-body-sm text-ink">已勾选 {selectedCount} 张</span>
              <label className="flex items-center gap-2 text-caption-sm text-ink">
                <input
                  type="checkbox"
                  checked={deleteOriginalInBatch}
                  onChange={(e) => setDeleteOriginalInBatch(e.target.checked)}
                  className="h-4 w-4"
                />
                写入 NAS 垃圾箱清单
              </label>
              <button
                type="button"
                onClick={handleBatchDelete}
                disabled={selectedCount === 0 || batchDeleteMutation.isPending}
                className="inline-flex items-center gap-2 rounded-md border border-danger/40 px-3 py-1.5 text-body-sm text-danger hover:bg-danger/10 disabled:opacity-60"
              >
                {batchDeleteMutation.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                批量删除已选
              </button>
            </div>
          </div>
        )}

        {batchMessage && <p className="text-caption-sm text-mute">{batchMessage}</p>}

        {isInitialLoading && (
          <div className="flex items-center justify-center gap-2 py-10 text-mute">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-body-sm">正在加载首批照片…</span>
          </div>
        )}

        {[...groups.entries()].map(([key, photos]) => (
          <section key={key}>
            {(() => {
              const groupPhotoIds = photos.map((photo) => photo.id);
              const groupAllSelected =
                groupPhotoIds.length > 0 && groupPhotoIds.every((id) => selectedPhotoIds.includes(id));

              return (
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  {canDeletePhoto ? (
                    <button
                      type="button"
                      onClick={() => toggleSelectByPhotoIds(groupPhotoIds)}
                      className="text-heading-md font-semibold text-ink hover:text-primary-pressed"
                      title={groupAllSelected ? "取消该日期全选" : "全选该日期"}
                    >
                      {formatGroupLabel(key)}
                      <span className="ml-2 text-body-sm font-normal text-mute">
                        {photos.length} 张
                      </span>
                      <span className="ml-2 text-caption-sm text-primary">
                        {groupAllSelected ? "取消全选" : "全选"}
                      </span>
                    </button>
                  ) : (
                    <p className="text-heading-md font-semibold text-ink">
                      {formatGroupLabel(key)}
                      <span className="ml-2 text-body-sm font-normal text-mute">
                        {photos.length} 张
                      </span>
                    </p>
                  )}
                </div>
              );
            })()}
            <MasonryGrid
              items={photos}
              getKey={(photo) => photo.id}
              getItemHeight={(photo) => (photo.width && photo.height ? photo.height / photo.width : 3 / 4)}
              renderItem={(photo) => (
                <PhotoCard
                  photo={photo}
                  priority={priorityPhotoIds.has(photo.id)}
                  selectMode={canDeletePhoto}
                  selected={selectedPhotoIds.includes(photo.id)}
                  onToggleSelect={togglePhotoSelection}
                  onDeleted={(photoId) => {
                    setSelectedPhotoIds((prev) => prev.filter((id) => id !== photoId));
                  }}
                />
              )}
            />
          </section>
        ))}

        <div ref={sentinelRef} className="h-4" />

        {isFetchingNextPage && (
          <div className="flex justify-center py-6">
            <Loader2 className="w-5 h-5 animate-spin text-mute" />
          </div>
        )}
      </div>

      {/* Right-side timeline rail */}
      <TimelineRail
        projectId={projectId}
        folderId={folderId}
        folderScope={folderScope}
        activeKey={activeKey}
        onSelect={handleMonthSelect}
      />
    </div>
  );
}
