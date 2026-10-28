import { useState } from "react";
import type { QueryObserverResult, UseMutationResult } from "@tanstack/react-query";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, RefreshCw, ScanFace, Tag, UserRound, X } from "lucide-react";
import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";
import type { FaceDetection, FaceDetectionListResponse, FaceScanResponse } from "@/api/types";

interface PhotoFacesSectionProps {
  projectId: number;
  photoId: number;
  facesData?: FaceDetectionListResponse;
  facesLoading: boolean;
  facesError: unknown;
  faceMessage: string | null;
  faceScanMutation: UseMutationResult<FaceScanResponse, Error, void>;
  refreshFaces: () => Promise<QueryObserverResult<FaceDetectionListResponse, Error>> | void;
}

interface FaceAssignmentChipProps {
  face: FaceDetection;
}

function FaceAssignmentChip({ face }: FaceAssignmentChipProps) {
  const name = face.assignment_person_name;
  if (!face.assignment_person_id || !name) {
    return (
      <span className="px-2 py-0.5 rounded-full bg-secondary-bg text-caption-sm text-mute">
        未标记人物
      </span>
    );
  }
  if (
    face.assignment_status === "human_confirmed" ||
    face.assignment_status === "human_corrected"
  ) {
    return (
      <span className="px-2 py-0.5 rounded-full bg-green-100 text-caption-sm text-green-800">
        已确认 · {name}
      </span>
    );
  }
  if (face.assignment_status === "auto_assigned") {
    return (
      <span className="px-2 py-0.5 rounded-full bg-blue-100 text-caption-sm text-blue-800">
        自动归类 · {name}
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded-full bg-amber-100 text-caption-sm text-amber-800">
      待审核 · {name}
    </span>
  );
}

interface FacePersonTaggerProps {
  projectId: number;
  faceId: number;
  onDone: () => void;
  onCancel: () => void;
}

function FacePersonTagger({ projectId, faceId, onDone, onCancel }: FacePersonTaggerProps) {
  const queryClient = useQueryClient();
  const [searchText, setSearchText] = useState("");
  const [newPersonName, setNewPersonName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const personsQuery = useQuery({
    queryKey: queryKeys.projectPeople(projectId, false),
    queryFn: ({ signal }) =>
      api.projectPeople.list(
        projectId,
        false,
        50,
        searchText ? { q: searchText } : undefined,
        signal,
      ),
  });

  const invalidatePeopleQueries = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.projectPeople(projectId) }),
      queryClient.invalidateQueries({ queryKey: ["project-review-page", projectId] }),
    ]);
  };

  const confirmMutation = useMutation({
    mutationFn: (personId: number) => api.projectPeople.confirmFace(projectId, personId, faceId),
    onSuccess: async () => {
      await invalidatePeopleQueries();
      onDone();
    },
    onError: (err: Error) => setError(err.message),
  });

  const createAndTagMutation = useMutation({
    mutationFn: async (displayName: string) => {
      const created = await api.projectPeople.create(projectId, {
        display_name: displayName,
        is_named: true,
      });
      return api.projectPeople.confirmFace(projectId, created.person.id, faceId);
    },
    onSuccess: async () => {
      await invalidatePeopleQueries();
      onDone();
    },
    onError: (err: Error) => setError(err.message),
  });

  const busy = confirmMutation.isPending || createAndTagMutation.isPending;

  return (
    <div className="mt-2 rounded-md border border-hairline bg-canvas p-2 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-caption-sm font-medium text-ink">选择人物</span>
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex items-center gap-1 text-caption-sm text-mute hover:text-ink"
        >
          <X className="w-3 h-3" />
          关闭
        </button>
      </div>
      <input
        type="text"
        value={searchText}
        onChange={(event) => setSearchText(event.target.value)}
        placeholder="搜索人物名称…"
        className="w-full px-2 py-1.5 rounded-md border border-hairline text-body-sm text-ink bg-canvas focus:outline-none focus:ring-1 focus:ring-primary"
      />
      <div className="max-h-40 overflow-y-auto space-y-1">
        {personsQuery.isLoading && (
          <p className="text-caption-sm text-mute flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 animate-spin" />
            加载人物中…
          </p>
        )}
        {personsQuery.error && (
          <p className="text-caption-sm text-danger">{(personsQuery.error as Error).message}</p>
        )}
        {personsQuery.data?.items.length === 0 && (
          <p className="text-caption-sm text-mute">没有匹配的人物，可在下方新建。</p>
        )}
        {personsQuery.data?.items.map((person) => (
          <button
            key={person.id}
            type="button"
            onClick={() => confirmMutation.mutate(person.id)}
            disabled={busy}
            className="w-full flex items-center justify-between px-2 py-1.5 rounded-md border border-hairline text-left text-body-sm text-ink hover:bg-surface-soft disabled:opacity-60"
          >
            <span className="truncate">{person.display_name}</span>
            <span className="text-caption-sm text-mute flex-shrink-0 ml-2">
              {person.sample_count} 张
            </span>
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2 border-t border-hairline pt-2">
        <input
          type="text"
          value={newPersonName}
          onChange={(event) => setNewPersonName(event.target.value)}
          placeholder="新人物名称"
          className="min-w-0 flex-1 px-2 py-1.5 rounded-md border border-hairline text-body-sm text-ink bg-canvas focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <button
          type="button"
          onClick={() => createAndTagMutation.mutate(newPersonName.trim())}
          disabled={busy || !newPersonName.trim()}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-primary text-white text-caption-sm hover:bg-primary-pressed disabled:opacity-60 flex-shrink-0"
        >
          {createAndTagMutation.isPending ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Plus className="w-3 h-3" />
          )}
          新建并标记
        </button>
      </div>
      {busy && (
        <p className="text-caption-sm text-mute flex items-center gap-1.5">
          <Loader2 className="w-3 h-3 animate-spin" />
          正在更新人物归属…
        </p>
      )}
      {error && <p className="text-caption-sm text-danger break-all">{error}</p>}
    </div>
  );
}

export function PhotoFacesSection({
  projectId,
  photoId,
  facesData,
  facesLoading,
  facesError,
  faceMessage,
  faceScanMutation,
  refreshFaces,
}: PhotoFacesSectionProps) {
  const [taggerFaceId, setTaggerFaceId] = useState<number | null>(null);
  const [tagMessage, setTagMessage] = useState<{ faceId: number; text: string } | null>(null);

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <UserRound className="w-4 h-4 text-primary" />
          <span className="text-body-sm font-semibold text-ink">人脸识别</span>
          {facesLoading && <Loader2 className="w-3.5 h-3.5 animate-spin text-mute" />}
        </div>
        <button
          type="button"
          onClick={() => faceScanMutation.mutate()}
          disabled={faceScanMutation.isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card disabled:opacity-60"
        >
          {faceScanMutation.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <ScanFace className="w-3.5 h-3.5" />
          )}
          手动扫描
        </button>
      </div>

      {faceMessage && <p className="text-caption-sm text-mute mb-2">{faceMessage}</p>}

      {facesError ? (
        <p className="text-caption-sm text-amber-700">{(facesError as Error).message}</p>
      ) : facesData && facesData.total > 0 ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-caption-sm text-mute">
            <span>检测到 {facesData.total} 张脸</span>
            <button
              type="button"
              onClick={() => refreshFaces()}
              className="inline-flex items-center gap-1 text-primary hover:text-primary-pressed"
            >
              <RefreshCw className="w-3 h-3" />
              刷新
            </button>
          </div>
          <div className="grid grid-cols-1 gap-2">
            {facesData.items.map((face) => (
              <div
                key={face.id}
                className="rounded-md border border-hairline bg-surface-soft p-2"
              >
                <div className="flex gap-3">
                  <div className="w-20 h-20 flex-shrink-0 rounded-md overflow-hidden bg-canvas border border-hairline">
                    {face.face_crop_path ? (
                      <img
                        src={api.projectFaces.cropUrl(projectId, face.id, face.updated_at)}
                        alt={`face-${face.id}`}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-mute">
                        <ScanFace className="w-5 h-5" />
                      </div>
                    )}
                  </div>
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-body-sm font-medium text-ink">face #{face.id}</span>
                      <span className="px-2 py-0.5 rounded-full bg-secondary-bg text-caption-sm text-ink">
                        {face.status}
                      </span>
                      <FaceAssignmentChip face={face} />
                      <button
                        type="button"
                        onClick={() =>
                          setTaggerFaceId(taggerFaceId === face.id ? null : face.id)
                        }
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas"
                      >
                        <Tag className="w-3 h-3" />
                        {face.assignment_person_id ? "改标记" : "标记人物"}
                      </button>
                    </div>
                    <p className="text-caption-sm text-mute">
                      bbox: {face.bbox_x}, {face.bbox_y}, {face.bbox_w}, {face.bbox_h}
                    </p>
                    <div className="flex flex-wrap gap-x-3 gap-y-1 text-caption-sm text-mute">
                      {face.detection_confidence != null && (
                        <span>检测置信度 {(face.detection_confidence * 100).toFixed(0)}%</span>
                      )}
                      {face.face_quality_score != null && (
                        <span>质量 {(face.face_quality_score * 100).toFixed(0)}%</span>
                      )}
                    </div>
                    {face.error_message && (
                      <p className="text-caption-sm text-danger break-all">{face.error_message}</p>
                    )}
                    {tagMessage?.faceId === face.id && (
                      <p className="text-caption-sm text-green-700">{tagMessage.text}</p>
                    )}
                  </div>
                </div>
                {taggerFaceId === face.id && (
                  <FacePersonTagger
                    projectId={projectId}
                    faceId={face.id}
                    onDone={async () => {
                      setTaggerFaceId(null);
                      setTagMessage({ faceId: face.id, text: "人物归属已更新" });
                      await refreshFaces();
                    }}
                    onCancel={() => setTaggerFaceId(null)}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-caption-sm text-mute">
          还没有人脸结果。先在项目配置里启用人脸识别，再点击“手动扫描”。
        </p>
      )}
    </div>
  );
}
