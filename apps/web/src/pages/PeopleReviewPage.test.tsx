import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PersonBatchActionResponse, PersonBatchMoveResponse, PersonListResponse, PersonReviewListResponse } from "@/api";
import { PeopleReviewPage } from "@/pages/PeopleReviewPage";

const peopleMock = vi.fn();
const reviewPendingMock = vi.fn();
const batchConfirmReviewMock = vi.fn();
const batchRejectReviewMock = vi.fn();
const batchMoveReviewMock = vi.fn();
const useProjectContextMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      projects: {
        ...actual.api.projects,
        people: (...args: unknown[]) => peopleMock(...args),
        reviewPending: (...args: unknown[]) => reviewPendingMock(...args),
        batchConfirmReview: (...args: unknown[]) => batchConfirmReviewMock(...args),
        batchRejectReview: (...args: unknown[]) => batchRejectReviewMock(...args),
        batchMoveReview: (...args: unknown[]) => batchMoveReviewMock(...args),
      },
    },
  };
});

vi.mock("@/contexts/ProjectContext", () => ({
  useProjectContext: () => useProjectContextMock(),
}));

const peopleResponse: PersonListResponse = {
  total: 3,
  items: [
    {
      id: 101,
      project_id: 1,
      display_name: "爸爸",
      normalized_name: "爸爸",
      is_named: true,
      representative_face_detection_id: 301,
      sample_count: 2,
      confirmed_sample_count: 1,
      auto_assigned_count: 0,
      review_pending_count: 2,
      created_by: "user",
      created_at: "2026-05-26T00:00:00Z",
      updated_at: "2026-05-26T00:00:00Z",
    },
    {
      id: 102,
      project_id: 1,
      display_name: "妈妈",
      normalized_name: "妈妈",
      is_named: true,
      representative_face_detection_id: 302,
      sample_count: 1,
      confirmed_sample_count: 1,
      auto_assigned_count: 0,
      review_pending_count: 0,
      created_by: "user",
      created_at: "2026-05-26T00:00:00Z",
      updated_at: "2026-05-26T00:00:00Z",
    },
    {
      id: 103,
      project_id: 1,
      display_name: "人物 3",
      normalized_name: "人物 3",
      is_named: false,
      representative_face_detection_id: null,
      sample_count: 0,
      confirmed_sample_count: 0,
      auto_assigned_count: 0,
      review_pending_count: 1,
      created_by: "system",
      created_at: "2026-05-26T00:00:00Z",
      updated_at: "2026-05-26T00:00:00Z",
    },
  ],
};

function buildReviewResponse(page: number): PersonReviewListResponse {
  if (page === 2) {
    return {
      total: 81,
      items: [
        {
          id: 903,
          project_id: 1,
          person_id: 103,
          face_detection_id: 503,
          assignment_status: "review_pending",
          assignment_source: "similarity_match",
          confidence: 0.72,
          similarity_score: 0.7,
          is_positive_sample: false,
          is_training_candidate: true,
          created_at: "2026-05-26T00:00:00Z",
          updated_at: "2026-05-26T00:00:00Z",
          face_detection: {
            id: 503,
            project_id: 1,
            photo_id: 13,
            bbox_x: 10,
            bbox_y: 10,
            bbox_w: 20,
            bbox_h: 20,
            detection_confidence: 0.9,
            face_quality_score: 0.8,
            face_crop_path: "/tmp/face-503.jpg",
            face_crop_hash: "hash-503",
            status: "embedded",
            error_message: null,
            detected_at: null,
            created_at: "2026-05-26T00:00:00Z",
            updated_at: "2026-05-26T00:00:00Z",
          },
        },
      ],
    };
  }

  return {
    total: 81,
    items: [
      {
        id: 901,
        project_id: 1,
        person_id: 101,
        face_detection_id: 501,
        assignment_status: "review_pending",
        assignment_source: "similarity_match",
        confidence: 0.74,
        similarity_score: 0.71,
        is_positive_sample: false,
        is_training_candidate: true,
        created_at: "2026-05-26T00:00:00Z",
        updated_at: "2026-05-26T00:00:00Z",
        face_detection: {
          id: 501,
          project_id: 1,
          photo_id: 11,
          bbox_x: 10,
          bbox_y: 10,
          bbox_w: 20,
          bbox_h: 20,
          detection_confidence: 0.9,
          face_quality_score: 0.8,
          face_crop_path: "/tmp/face-501.jpg",
          face_crop_hash: "hash-501",
          status: "embedded",
          error_message: null,
          detected_at: null,
          created_at: "2026-05-26T00:00:00Z",
          updated_at: "2026-05-26T00:00:00Z",
        },
      },
      {
        id: 902,
        project_id: 1,
        person_id: 101,
        face_detection_id: 502,
        assignment_status: "review_pending",
        assignment_source: "similarity_match",
        confidence: 0.75,
        similarity_score: 0.72,
        is_positive_sample: false,
        is_training_candidate: true,
        created_at: "2026-05-26T00:00:00Z",
        updated_at: "2026-05-26T00:00:00Z",
        face_detection: {
          id: 502,
          project_id: 1,
          photo_id: 12,
          bbox_x: 10,
          bbox_y: 10,
          bbox_w: 20,
          bbox_h: 20,
          detection_confidence: 0.9,
          face_quality_score: 0.8,
          face_crop_path: "/tmp/face-502.jpg",
          face_crop_hash: "hash-502",
          status: "embedded",
          error_message: null,
          detected_at: null,
          created_at: "2026-05-26T00:00:00Z",
          updated_at: "2026-05-26T00:00:00Z",
        },
      },
    ],
  };
}

function renderPage(initialEntry = "/projects/1/people/review") {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/photos" element={<div>Photos Landing</div>} />
          <Route path="/projects/:projectId/people/review" element={<PeopleReviewPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PeopleReviewPage", () => {
  beforeEach(() => {
    peopleMock.mockReset();
    reviewPendingMock.mockReset();
    batchConfirmReviewMock.mockReset();
    batchRejectReviewMock.mockReset();
    batchMoveReviewMock.mockReset();
    useProjectContextMock.mockReset();

    useProjectContextMock.mockReturnValue({
      projects: [{ id: 1, name: "Project A", is_default: true }],
      isLoading: false,
      currentProjectId: 1,
      currentProject: { id: 1, name: "Project A", is_default: true },
      setCurrentProjectId: vi.fn(),
    });

    peopleMock.mockResolvedValue(peopleResponse);
    reviewPendingMock.mockImplementation((projectId: number, personId: number | null, limit: number, offset: number) => {
      const page = offset >= 80 ? 2 : 1;
      return Promise.resolve(buildReviewResponse(page));
    });

    const batchActionResponse: PersonBatchActionResponse = {
      updated: 2,
      person: peopleResponse.items[0],
      feedback_effects: {
        prototype_rebuilt: true,
        rebuilt_person_ids: [101],
        unknown_rematch_requested: true,
        unknown_rematch_scope: "person",
        unknown_rematch_person_id: 101,
        unknown_rematch_task_id: 77,
        unknown_rematch_task_created: true,
      },
      request_id: "req-1",
      operator: "web_review_page",
      attempts: 1,
    };
    const batchMoveResponse: PersonBatchMoveResponse = {
      updated: 2,
      source_person: peopleResponse.items[0],
      target_person: peopleResponse.items[1],
      feedback_effects: {
        prototype_rebuilt: true,
        rebuilt_person_ids: [101, 102],
        unknown_rematch_requested: true,
        unknown_rematch_scope: "person",
        unknown_rematch_person_id: 102,
        unknown_rematch_task_id: 88,
        unknown_rematch_task_created: false,
      },
      request_id: "req-2",
      operator: "web_review_page",
      attempts: 1,
    };

    batchConfirmReviewMock.mockResolvedValue(batchActionResponse);
    batchRejectReviewMock.mockResolvedValue(batchActionResponse);
    batchMoveReviewMock.mockResolvedValue(batchMoveResponse);
  });

  it("renders grouped review-pending faces by person", async () => {
    renderPage();

    expect(await screen.findByText("人物 #101 · 爸爸")).toBeInTheDocument();
    expect(screen.getByText("当前页待确认 2 张")).toBeInTheDocument();
    expect(screen.getByText("face #501")).toBeInTheDocument();
    expect(screen.getByText("face #502")).toBeInTheDocument();
  });

  it("moves to the next page and requests the next offset", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("第 1 / 2 页");
    await user.click(screen.getByRole("button", { name: "下一页" }));

    await waitFor(() => {
      expect(screen.getByText("第 2 / 2 页")).toBeInTheDocument();
    });
    expect(await screen.findByText("人物 #103 · 人物 3")).toBeInTheDocument();
    expect(reviewPendingMock).toHaveBeenLastCalledWith(1, null, 80, 80);
  });

  it("triggers batch confirm for the grouped faces", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("人物 #101 · 爸爸");
    await user.click(screen.getByRole("button", { name: "批量确认" }));

    await waitFor(() => {
      expect(batchConfirmReviewMock).toHaveBeenCalledWith(
        1,
        101,
        expect.objectContaining({
          face_detection_ids: [501, 502],
          operator: "web_review_page",
          max_retries: 3,
        }),
      );
    });
    expect(await screen.findByText(/批量确认成功：updated=2 attempts=1/)).toBeInTheDocument();
    expect(screen.getByText(/prototype=rebuild\(person=101\)/)).toBeInTheDocument();
    expect(screen.getByText(/rematch=person\/queued\(task=77\)/)).toBeInTheDocument();
  });

  it("triggers batch move with the selected target person", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("人物 #101 · 爸爸");
    await user.selectOptions(screen.getByRole("combobox"), "102");
    await user.click(screen.getByRole("button", { name: "批量移动" }));

    await waitFor(() => {
      expect(batchMoveReviewMock).toHaveBeenCalledWith(
        1,
        101,
        expect.objectContaining({
          face_detection_ids: [501, 502],
          target_person_id: 102,
          operator: "web_review_page",
          max_retries: 3,
        }),
      );
    });
    expect(await screen.findByText(/批量移动成功：updated=2 attempts=1/)).toBeInTheDocument();
    expect(screen.getByText(/prototype=rebuild\(person=101,102\)/)).toBeInTheDocument();
    expect(screen.getByText(/rematch=person\/reused\(task=88\)/)).toBeInTheDocument();
  });

  it("redirects invalid project routes back to /photos", async () => {
    renderPage("/projects/not-a-number/people/review");

    expect(await screen.findByText("Photos Landing")).toBeInTheDocument();
  });
});
