import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Photo } from "@/api";
import { queryKeys } from "@/api/queryKeys";

interface UsePhotoDetailModalDataOptions {
  photo: Photo;
  onClose: () => void;
  onDeleted?: (photoId: number) => void;
}

export function usePhotoDetailModalData({
  photo,
  onClose,
  onDeleted,
}: UsePhotoDetailModalDataOptions) {
  const [faceMessage, setFaceMessage] = useState<string | null>(null);
  const [deleteOriginal, setDeleteOriginal] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const projectId = photo.project_id;
  const queryClient = useQueryClient();

  const { data: detail } = useQuery({
    queryKey: queryKeys.projectPhotoDetail(projectId, photo.id),
    queryFn: () => api.projects.photo(projectId, photo.id),
    enabled: projectId != null,
    staleTime: 30_000,
  });

  const { data: aiData, isLoading: aiLoading } = useQuery({
    queryKey: queryKeys.projectPhotoAi(projectId, photo.id),
    queryFn: () => api.projects.photoAI(projectId, photo.id),
    enabled: projectId != null,
    retry: false,
  });

  const {
    data: facesData,
    isLoading: facesLoading,
    error: facesError,
    refetch: refreshFaces,
  } = useQuery({
    queryKey: queryKeys.projectFaces(projectId, photo.id),
    queryFn: () => api.projects.faces(projectId, 1, 50, photo.id),
    enabled: projectId != null,
    staleTime: 10_000,
  });

  const faceScanMutation = useMutation({
    mutationFn: () => api.projects.scanPhotoFaces(projectId, photo.id),
    onSuccess: (result) => {
      let detail = "";
      if (result.message && result.message !== "Face scan completed") {
        detail = `；${result.message}`;
      } else if (result.review_pending === 0 && result.auto_assigned === 0 && result.faces_detected > 0) {
        detail = "；未产生待审核，可能是后端未重启到最新版本，或缺少 persons/person_face_assignments 表（请执行 alembic upgrade head）";
      }
      setFaceMessage(
        `已扫描 ${result.faces_detected} 张脸，新增待审核 ${result.review_pending} 条，自动归入 ${result.auto_assigned} 条${detail}`,
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.projectFaces(projectId, photo.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projectPhotoDetail(projectId, photo.id) });
      queryClient.invalidateQueries({ queryKey: ["project-review-page", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-people", projectId] });
    },
    onError: (error: Error) => {
      setFaceMessage(error.message);
    },
  });

  const deletePhotoMutation = useMutation({
    mutationFn: () => api.projects.deletePhotoRecord(projectId, photo.id, deleteOriginal),
    onSuccess: () => {
      setDeleteMessage(deleteOriginal ? "已删除库记录、缩略图和本地原图" : "已删除库记录和缩略图");
      queryClient.invalidateQueries({ queryKey: queryKeys.photosBase(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.timeline(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tags(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projectPhotoDetail(projectId, photo.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projectPhotoAi(projectId, photo.id) });
      queryClient.invalidateQueries({ queryKey: ["search"] });
      onDeleted?.(photo.id);
      onClose();
    },
    onError: (error: Error) => {
      setDeleteMessage(`删除失败：${error.message}`);
    },
  });

  function handleDeleteRecord() {
    const actionText = deleteOriginal ? "删除库记录、缩略图并尝试删除本地原图" : "仅删除库记录和缩略图";
    if (!window.confirm(`确认${actionText}吗？`)) {
      return;
    }
    deletePhotoMutation.mutate();
  }

  return {
    aiData,
    aiLoading,
    deleteMessage,
    deleteOriginal,
    deletePhotoMutation,
    detail,
    faceMessage,
    faceScanMutation,
    facesData,
    facesError,
    facesLoading,
    handleDeleteRecord,
    projectId,
    refreshFaces,
    setDeleteOriginal,
  };
}
