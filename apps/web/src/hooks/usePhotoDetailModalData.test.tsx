import type { QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Photo } from "@/api";
import { createQueryClientWrapper } from "@/test/queryClient";

const deletePhotoRecordMock = vi.fn();
const facesMock = vi.fn();
const photoAIMock = vi.fn();
const photoMock = vi.fn();
const scanPhotoFacesMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      projects: {
        ...actual.api.projects,
        deletePhotoRecord: (...args: unknown[]) => deletePhotoRecordMock(...args),
        faces: (...args: unknown[]) => facesMock(...args),
        photo: (...args: unknown[]) => photoMock(...args),
        photoAI: (...args: unknown[]) => photoAIMock(...args),
        scanPhotoFaces: (...args: unknown[]) => scanPhotoFacesMock(...args),
      },
    },
  };
});

import { queryKeys } from "@/api/queryKeys";
import { usePhotoDetailModalData } from "@/hooks/usePhotoDetailModalData";

const photo: Photo = {
  id: 42,
  project_id: 7,
  file_name: "IMG_0042.jpg",
  mime_type: "image/jpeg",
  width: 1200,
  height: 800,
  taken_at: "2026-01-01T12:00:00",
  file_size: 1024,
  status: "indexed",
  thumbnail_path: null,
  gps_latitude: null,
  gps_longitude: null,
  country_name: null,
  admin1: null,
  admin2: null,
  city: null,
  district: null,
  formatted_address: null,
  created_at: "2026-01-01T12:00:00",
  updated_at: "2026-01-01T12:00:00",
};

function mockedInvalidateQueryKeys(queryClient: QueryClient) {
  return vi
    .mocked(queryClient.invalidateQueries)
    .mock.calls.map(([arg]) => (arg as { queryKey?: unknown }).queryKey);
}

describe("usePhotoDetailModalData", () => {
  beforeEach(() => {
    deletePhotoRecordMock.mockReset();
    facesMock.mockReset();
    photoAIMock.mockReset();
    photoMock.mockReset();
    scanPhotoFacesMock.mockReset();

    photoMock.mockResolvedValue(photo);
    photoAIMock.mockResolvedValue({
      id: 1,
      photo_id: photo.id,
      model_name: "test-model",
      model_version: null,
      caption: "caption",
      ocr_text: null,
      scene_tags: [],
      object_tags: [],
      activity_tags: [],
      quality_tags: [],
      location_clues: [],
      search_keywords: [],
      semantic_concepts: [],
      people_count: null,
      confidence: null,
      created_at: "2026-01-01T12:00:00",
      updated_at: "2026-01-01T12:00:00",
    });
    facesMock.mockResolvedValue({ total: 0, page: 1, page_size: 50, items: [] });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("updates face scan message and invalidates face-related queries after a successful scan", async () => {
    scanPhotoFacesMock.mockResolvedValue({
      faces_detected: 3,
      review_pending: 2,
      auto_assigned: 1,
      message: "Face scan completed",
    });
    const { queryClient, wrapper } = createQueryClientWrapper();
    vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(
      () => usePhotoDetailModalData({ photo, onClose: vi.fn(), onDeleted: vi.fn() }),
      { wrapper },
    );

    await act(async () => {
      await result.current.faceScanMutation.mutateAsync();
    });

    expect(result.current.faceMessage).toBe("已扫描 3 张脸，新增待审核 2 条，自动归入 1 条");
    expect(scanPhotoFacesMock).toHaveBeenCalledWith(photo.project_id, photo.id);
    expect(mockedInvalidateQueryKeys(queryClient)).toEqual(
      expect.arrayContaining([
        queryKeys.projectFaces(photo.project_id, photo.id),
        queryKeys.projectPhotoDetail(photo.project_id, photo.id),
        ["project-review-page", photo.project_id],
        ["project-people", photo.project_id],
      ]),
    );
  });

  it("invalidates library views and closes the modal after deleting a photo", async () => {
    deletePhotoRecordMock.mockResolvedValue({
      project_id: photo.project_id,
      photo_id: photo.id,
      deleted_thumbnail: true,
      deleted_original: true,
      message: "Photo record deleted",
    });
    const onClose = vi.fn();
    const onDeleted = vi.fn();
    const { queryClient, wrapper } = createQueryClientWrapper();
    vi.spyOn(queryClient, "invalidateQueries");
    vi.stubGlobal("confirm", vi.fn(() => true));

    const { result } = renderHook(
      () => usePhotoDetailModalData({ photo, onClose, onDeleted }),
      { wrapper },
    );

    act(() => {
      result.current.setDeleteOriginal(true);
    });
    act(() => {
      result.current.handleDeleteRecord();
    });

    await waitFor(() => {
      expect(deletePhotoRecordMock).toHaveBeenCalledWith(photo.project_id, photo.id, true);
    });

    expect(onDeleted).toHaveBeenCalledWith(photo.id);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(mockedInvalidateQueryKeys(queryClient)).toEqual(
      expect.arrayContaining([
        queryKeys.photosBase(photo.project_id),
        queryKeys.timeline(photo.project_id),
        queryKeys.tags(photo.project_id),
        queryKeys.projectPhotoDetail(photo.project_id, photo.id),
        queryKeys.projectPhotoAi(photo.project_id, photo.id),
        ["search"],
      ]),
    );
  });
});
