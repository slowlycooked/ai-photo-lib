import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { FaceDetectionListResponse, PersonActionResponse, PersonListResponse } from "@/api";
import { PhotoFacesSection } from "@/components/photo-card/PhotoFacesSection";

const peopleListMock = vi.fn();
const confirmFaceMock = vi.fn();
const createPersonMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      projectPeople: {
        ...actual.api.projectPeople,
        list: (...args: unknown[]) => peopleListMock(...args),
        confirmFace: (...args: unknown[]) => confirmFaceMock(...args),
        create: (...args: unknown[]) => createPersonMock(...args),
      },
    },
  };
});

const baseFace = {
  project_id: 1,
  photo_id: 101,
  bbox_x: 849,
  bbox_y: 511,
  bbox_w: 127,
  bbox_h: 149,
  detection_confidence: 0.86,
  face_quality_score: 0.58,
  face_crop_path: "/thumbs/faces/1.jpg",
  face_crop_hash: null,
  status: "embedded",
  error_message: null,
  detected_at: "2026-01-01T00:00:00",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

const facesData: FaceDetectionListResponse = {
  total: 2,
  page: 1,
  page_size: 50,
  items: [
    {
      ...baseFace,
      id: 50124,
      assignment_person_id: null,
      assignment_person_name: null,
      assignment_status: null,
      assignment_source: null,
    },
    {
      ...baseFace,
      id: 50125,
      assignment_person_id: 18112,
      assignment_person_name: "爸爸 #马丁",
      assignment_status: "human_confirmed",
      assignment_source: "human_label",
    },
  ],
};

const peopleResponse: PersonListResponse = {
  total: 2,
  items: [
    {
      id: 18112,
      project_id: 1,
      display_name: "爸爸 #马丁",
      normalized_name: "爸爸 #马丁",
      is_named: true,
      representative_face_detection_id: null,
      sample_count: 2321,
      confirmed_sample_count: 455,
      auto_assigned_count: 1859,
      review_pending_count: 1,
      created_by: "user",
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-01T00:00:00",
    },
    {
      id: 18113,
      project_id: 1,
      display_name: "妈妈",
      normalized_name: "妈妈",
      is_named: true,
      representative_face_detection_id: null,
      sample_count: 10,
      confirmed_sample_count: 10,
      auto_assigned_count: 0,
      review_pending_count: 0,
      created_by: "user",
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-01T00:00:00",
    },
  ],
};

const personActionResponse: PersonActionResponse = {
  person: peopleResponse.items[0],
};

function renderSection() {
  const refreshFaces = vi.fn().mockResolvedValue(undefined);
  const faceScanMutation = {
    isPending: false,
    mutate: vi.fn(),
  } as unknown as Parameters<typeof PhotoFacesSection>[0]["faceScanMutation"];

  render(
    <QueryClientProvider client={new QueryClient()}>
      <PhotoFacesSection
        projectId={1}
        photoId={101}
        facesData={facesData}
        facesLoading={false}
        facesError={null}
        faceMessage={null}
        faceScanMutation={faceScanMutation}
        refreshFaces={refreshFaces}
      />
    </QueryClientProvider>,
  );
  return { refreshFaces };
}

describe("PhotoFacesSection 人工打标", () => {
  beforeEach(() => {
    peopleListMock.mockReset().mockResolvedValue(peopleResponse);
    confirmFaceMock.mockReset().mockResolvedValue(personActionResponse);
    createPersonMock.mockReset();
  });

  it("显示每张脸的人物归属状态", () => {
    renderSection();

    expect(screen.getByText("未标记人物")).toBeInTheDocument();
    expect(screen.getByText("已确认 · 爸爸 #马丁")).toBeInTheDocument();
    expect(screen.getByText("face #50124")).toBeInTheDocument();
    expect(screen.getByText("face #50125")).toBeInTheDocument();
  });

  it("未标记的脸可以通过选择器打标并确认", async () => {
    const user = userEvent.setup();
    const { refreshFaces } = renderSection();

    const buttons = screen.getAllByText("标记人物");
    expect(buttons).toHaveLength(1);
    await user.click(buttons[0]);

    await waitFor(() => {
      expect(peopleListMock).toHaveBeenCalledWith(
        1,
        false,
        50,
        undefined,
        expect.anything(),
      );
    });

    await user.click(await screen.findByText("妈妈"));

    await waitFor(() => {
      expect(confirmFaceMock).toHaveBeenCalledWith(1, 18113, 50124);
    });
    await waitFor(() => {
      expect(refreshFaces).toHaveBeenCalled();
    });
  });

  it("可以新建人物并直接标记", async () => {
    const user = userEvent.setup();
    const { refreshFaces } = renderSection();

    await user.click(screen.getByText("标记人物"));

    createPersonMock.mockResolvedValue({
      person: { ...peopleResponse.items[0], id: 18199, display_name: "姑姑" },
    } satisfies PersonActionResponse);

    await user.type(await screen.findByPlaceholderText("新人物名称"), "姑姑");
    await user.click(screen.getByText("新建并标记"));

    await waitFor(() => {
      expect(createPersonMock).toHaveBeenCalledWith(1, {
        display_name: "姑姑",
        is_named: true,
      });
    });
    await waitFor(() => {
      expect(confirmFaceMock).toHaveBeenCalledWith(1, 18199, 50124);
    });
    await waitFor(() => {
      expect(refreshFaces).toHaveBeenCalled();
    });
  });

  it("已确认的脸显示改标记入口", () => {
    renderSection();

    expect(screen.getByText("改标记")).toBeInTheDocument();
  });
});
