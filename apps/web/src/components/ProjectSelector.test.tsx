import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectSelector } from "./ProjectSelector";

const useProjectContextMock = vi.fn();

vi.mock("@/contexts/ProjectContext", () => ({
  useProjectContext: () => useProjectContextMock(),
}));

function renderSelector() {
  return render(
    <MemoryRouter>
      <ProjectSelector />
    </MemoryRouter>,
  );
}

describe("ProjectSelector", () => {
  beforeEach(() => {
    useProjectContextMock.mockReset();
  });

  it("shows an empty state when the user has no accessible projects", () => {
    useProjectContextMock.mockReturnValue({
      projects: [],
      currentProject: null,
      setCurrentProjectId: vi.fn(),
      isLoading: false,
    });

    renderSelector();

    expect(screen.getByLabelText("无可访问项目")).toBeInTheDocument();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});
