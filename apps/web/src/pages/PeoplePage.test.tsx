import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  PersonActionResponse,
  PersonDetail,
  PersonListResponse,
  PersonReviewListResponse,
  PersonSummary,
  ProjectFaceSettings,
} from "@/api";
import { PeoplePage } from "@/pages/PeoplePage";

const getFaceSettingsMock = vi.fn();
const peopleMock = vi.fn();
const personMock = vi.fn();
const reviewPendingMock = vi.fn();
const createPersonMock = vi.fn();
const renamePersonMock = vi.fn();
const confirmPersonFaceMock = vi.fn();
const rejectPersonFaceMock = vi.fn();
const movePersonFaceMock = vi.fn();
const setRepresentativeFaceMock = vi.fn();
const batchConfirmReviewMock = vi.fn();
const batchRejectReviewMock = vi.fn();
const batchMoveReviewMock = vi.fn();
const mergePersonMock = vi.fn();
const splitPersonMock = vi.fn();
const deletePersonMock = vi.fn();
const useProjectContextMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      projects: {
        ...actual.api.projects,
        getFaceSettings: (...args: unknown[]) => getFaceSettingsMock(...args),
        people: (...args: unknown[]) => peopleMock(...args),
        person: (...args: unknown[]) => personMock(...args),
        reviewPending: (...args: unknown[]) => reviewPendingMock(...args),
        createPerson: (...args: unknown[]) => createPersonMock(...args),
        renamePerson: (...args: unknown[]) => renamePersonMock(...args),
        confirmPersonFace: (...args: unknown[]) => confirmPersonFaceMock(...args),
        rejectPersonFace: (...args: unknown[]) => rejectPersonFaceMock(...args),
        movePersonFace: (...args: unknown[]) => movePersonFaceMock(...args),
        setPersonRepresentativeFace: (...args: unknown[]) => setRepresentativeFaceMock(...args),
        batchConfirmReview: (...args: unknown[]) => batchConfirmReviewMock(...args),
        batchRejectReview: (...args: unknown[]) => batchRejectReviewMock(...args),
        batchMoveReview: (...args: unknown[]) => batchMoveReviewMock(...args),
        mergePerson: (...args: unknown[]) => mergePersonMock(...args),
        splitPerson: (...args: unknown[]) => splitPersonMock(...args),
        deletePerson: (...args: unknown[]) => deletePersonMock(...args),
      },
    },
  };
});

vi.mock("@/contexts/ProjectContext", () => ({
  useProjectContext: () => useProjectContextMock(),
}));

const faceSettings: ProjectFaceSettings = {
  id: 1,
  project_id: 1,
  face_recognition_enabled: true,
  face_provider: "mock-provider",
  face_detector_model: "mock-detector",
  face_embedding_model: "mock-embedding",
  face_runtime: "cpu",
  store_face_crops: true,
  face_crop_storage: "local",
  auto_accept_threshold: 0.9,
  review_threshold: 0.7,
  cluster_threshold: 0.75,
  min_face_size: 24,
  min_detection_confidence: 0.6,
  min_quality_for_prototype: 0.5,
  max_positive_samples_per_person: 50,
  allow_auto_assignment: true,
  require_human_confirmation_for_new_person: true,
  enable_negative_constraints: true,
  enable_person_cannot_links: true,
  created_at: "2026-05-26T00:00:00Z",
  updated_at: "2026-05-26T00:00:00Z",
};

const peopleState: PersonSummary[] = [
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
    review_pending_count: 1,
    created_by: "user",
    created_at: "2026-05-26T00:00:00Z",
    updated_at: "2026-05-26T00:00:00Z",
  },
  {
    id: 102,
    project_id: 1,
    display_name: "人物 2",
    normalized_name: "人物 2",
    is_named: false,
    representative_face_detection_id: null,
    sample_count: 1,
    confirmed_sample_count: 0,
    auto_assigned_count: 1,
    review_pending_count: 0,
    created_by: "system",
    created_at: "2026-05-26T00:00:00Z",
    updated_at: "2026-05-26T00:00:00Z",
  },
];

function buildPeopleResponse(): PersonListResponse {
  return {
    total: peopleState.length,
    items: [...peopleState],
  };
}

function buildDetail(personId: number): PersonDetail {
  const person = peopleState.find((item) => item.id === personId) ?? peopleState[0];
  return {
    ...person,
    assignments: [
      {
        id: 501 + personId,
        project_id: 1,
        person_id: person.id,
        face_detection_id: person.representative_face_detection_id ?? 301,
        assignment_status: person.review_pending_count > 0 ? "review_pending" : "human_confirmed",
        assignment_source: "similarity_match",
        confidence: 0.82,
        similarity_score: 0.78,
        is_positive_sample: false,
        is_training_candidate: true,
        created_at: "2026-05-26T00:00:00Z",
        updated_at: "2026-05-26T00:00:00Z",
        face_detection: {
          id: person.representative_face_detection_id ?? 301,
          project_id: 1,
          photo_id: 10 + person.id,
          bbox_x: 10,
          bbox_y: 10,
          bbox_w: 20,
          bbox_h: 20,
          detection_confidence: 0.9,
          face_quality_score: 0.8,
          face_crop_path: "/tmp/face.jpg",
          face_crop_hash: "hash",
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

const emptyReviewResponse: PersonReviewListResponse = {
  total: 0,
  items: [],
};

function renderPage(initialEntry: string) {
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
          <Route path="/people" element={<PeoplePage />} />
          <Route path="/projects/:projectId/people" element={<PeoplePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PeoplePage", () => {
  beforeEach(() => {
    peopleState.splice(0, peopleState.length, ...[
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
        review_pending_count: 1,
        created_by: "user",
        created_at: "2026-05-26T00:00:00Z",
        updated_at: "2026-05-26T00:00:00Z",
      },
      {
        id: 102,
        project_id: 1,
        display_name: "人物 2",
        normalized_name: "人物 2",
        is_named: false,
        representative_face_detection_id: null,
        sample_count: 1,
        confirmed_sample_count: 0,
        auto_assigned_count: 1,
        review_pending_count: 0,
        created_by: "system",
        created_at: "2026-05-26T00:00:00Z",
        updated_at: "2026-05-26T00:00:00Z",
      },
    ]);

    getFaceSettingsMock.mockReset();
    peopleMock.mockReset();
    personMock.mockReset();
    reviewPendingMock.mockReset();
    createPersonMock.mockReset();
    renamePersonMock.mockReset();
    confirmPersonFaceMock.mockReset();
    rejectPersonFaceMock.mockReset();
    movePersonFaceMock.mockReset();
    setRepresentativeFaceMock.mockReset();
    batchConfirmReviewMock.mockReset();
    batchRejectReviewMock.mockReset();
    batchMoveReviewMock.mockReset();
    mergePersonMock.mockReset();
    splitPersonMock.mockReset();
    deletePersonMock.mockReset();
    useProjectContextMock.mockReset();

    useProjectContextMock.mockReturnValue({
      projects: [{ id: 1, name: "Project A", is_default: true }],
      isLoading: false,
      currentProjectId: 1,
      currentProject: { id: 1, name: "Project A", is_default: true },
      setCurrentProjectId: vi.fn(),
    });

    getFaceSettingsMock.mockResolvedValue(faceSettings);
    peopleMock.mockImplementation(() => Promise.resolve(buildPeopleResponse()));
    personMock.mockImplementation((projectId: number, personId: number) =>
      Promise.resolve(buildDetail(personId)),
    );
    reviewPendingMock.mockResolvedValue(emptyReviewResponse);
    createPersonMock.mockImplementation((projectId: number, body: { display_name?: string }) => {
      const person: PersonActionResponse["person"] = {
        id: 103,
        project_id: 1,
        display_name: body.display_name ?? "Person 103",
        normalized_name: (body.display_name ?? "Person 103").toLowerCase(),
        is_named: true,
        representative_face_detection_id: null,
        sample_count: 0,
        confirmed_sample_count: 0,
        auto_assigned_count: 0,
        review_pending_count: 0,
        created_by: "human_created",
        created_at: "2026-05-26T00:00:00Z",
        updated_at: "2026-05-26T00:00:00Z",
      };
      peopleState.push(person);
      return Promise.resolve({ person });
    });
    renamePersonMock.mockResolvedValue({ person: buildPeopleResponse().items[0] });
    confirmPersonFaceMock.mockResolvedValue({ person: buildPeopleResponse().items[0] });
    rejectPersonFaceMock.mockResolvedValue({ person: buildPeopleResponse().items[0] });
    movePersonFaceMock.mockResolvedValue({
      source_person: buildPeopleResponse().items[0],
      target_person: buildPeopleResponse().items[1],
    });
    setRepresentativeFaceMock.mockResolvedValue({ person: buildPeopleResponse().items[0] });
    batchConfirmReviewMock.mockResolvedValue({
      updated: 1,
      person: buildPeopleResponse().items[0],
      request_id: null,
      operator: null,
      attempts: 1,
    });
    batchRejectReviewMock.mockResolvedValue({
      updated: 1,
      person: buildPeopleResponse().items[0],
      request_id: null,
      operator: null,
      attempts: 1,
    });
    batchMoveReviewMock.mockResolvedValue({
      updated: 1,
      source_person: buildPeopleResponse().items[0],
      target_person: buildPeopleResponse().items[1],
      request_id: null,
      operator: null,
      attempts: 1,
    });
    mergePersonMock.mockResolvedValue({
      moved_assignments: 1,
      source_person: buildPeopleResponse().items[0],
      target_person: buildPeopleResponse().items[1],
    });
    splitPersonMock.mockResolvedValue({
      moved_assignments: 1,
      source_person: buildPeopleResponse().items[0],
      target_person: buildPeopleResponse().items[1],
    });
    deletePersonMock.mockResolvedValue({ deleted: true, message: "Person deleted" });
  });

  it("shows an empty-project prompt when no project is selected", async () => {
    useProjectContextMock.mockReturnValue({
      projects: [],
      isLoading: false,
      currentProjectId: null,
      currentProject: null,
      setCurrentProjectId: vi.fn(),
    });

    renderPage("/people");

    expect(
      screen.getByText("请先选择一个项目，再查看人物页。"),
    ).toBeInTheDocument();
  });

  it("auto-selects the first person when person_id is missing", async () => {
    renderPage("/projects/1/people");

    await screen.findByText("爸爸");
    await waitFor(() => {
      expect(personMock).toHaveBeenCalledWith(1, 101);
    });
  });

  it("passes filter and search text to the people query", async () => {
    const user = userEvent.setup();
    renderPage("/projects/1/people");

    await screen.findByText("爸爸");
    await user.selectOptions(screen.getAllByRole("combobox")[0], "review_pending");
    await user.type(screen.getByPlaceholderText("按人物名搜索"), "爸");

    await waitFor(() => {
      expect(peopleMock).toHaveBeenLastCalledWith(
        1,
        true,
        200,
        expect.objectContaining({
          has_review_pending: true,
          q: "爸",
        }),
      );
    });
  });

  it("creates a person and switches detail to the new record", async () => {
    const user = userEvent.setup();
    renderPage("/projects/1/people");

    await screen.findByText("爸爸");
    await user.type(screen.getByPlaceholderText("新人物名称（可为空）"), "朋友A");
    await user.click(screen.getByRole("button", { name: "创建人物" }));

    await waitFor(() => {
      expect(createPersonMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ display_name: "朋友A", is_named: true }),
      );
    });
    await waitFor(() => {
      expect(personMock).toHaveBeenCalledWith(1, 103);
    });
  });

  it("triggers confirm-face action from the detail panel", async () => {
    const user = userEvent.setup();
    renderPage("/projects/1/people");

    await user.click(await screen.findByRole("button", { name: "确认属于此人" }));

    await waitFor(() => {
      expect(confirmPersonFaceMock).toHaveBeenCalledWith(1, 101, 301);
    });
  });

  it("falls back to a valid merge target when the URL target is missing or invalid", async () => {
    const user = userEvent.setup();
    renderPage("/projects/1/people?person_id=101&merge_target_id=0");

    await screen.findByText("爸爸");
    await user.click(screen.getByRole("button", { name: "合并当前人物" }));

    await waitFor(() => {
      expect(mergePersonMock).toHaveBeenCalledWith(1, 101, {
        target_person_id: 102,
      });
    });
  });
});
