import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectSelector } from "./ProjectSelector";

const useProjectContextMock = vi.fn();

vi.mock("@/contexts/ProjectContext", () => ({
  useProjectContext: () => useProjectContextMock(),
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
}

function renderSelector(initialEntries = ["/"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <ProjectSelector />
      <LocationProbe />
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

  it("navigates project-scoped people pages when switching projects", async () => {
    const setCurrentProjectId = vi.fn();
    useProjectContextMock.mockReturnValue({
      projects: [
        { id: 1, name: "Alpha", description: null },
        { id: 2, name: "Beta", description: null },
      ],
      currentProject: { id: 1, name: "Alpha", description: null },
      setCurrentProjectId,
      isLoading: false,
    });

    renderSelector(["/projects/1/people?person_id=99"]);

    await userEvent.click(screen.getByRole("button", { name: /Alpha/ }));
    await userEvent.click(screen.getByRole("option", { name: /Beta/ }));

    expect(setCurrentProjectId).toHaveBeenCalledWith(2);
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/2/people");
    expect(screen.getByTestId("location")).not.toHaveTextContent("person_id");
  });
});
