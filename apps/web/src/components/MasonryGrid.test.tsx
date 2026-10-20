import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { assignMasonryColumns, getMasonryColumnCount, MasonryGrid } from "./MasonryGrid";

it("mounts each image only once when opening a wide gallery", () => {
  const bounds = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 1400 } as DOMRect);
  const mounts = vi.fn();
  function Item({ id }: { id: number }) {
    useEffect(() => { mounts(id); }, [id]);
    return <img alt={`photo-${id}`} />;
  }
  try {
    render(<MasonryGrid items={Array.from({ length: 50 }, (_, id) => id)} getKey={(id) => id} renderItem={(id) => <Item id={id} />} />);
    expect(screen.getAllByRole("img")).toHaveLength(50);
    expect(mounts).toHaveBeenCalledTimes(50);
  } finally {
    bounds.mockRestore();
  }
});

describe("getMasonryColumnCount", () => {
  it("adapts columns to the grid container width", () => {
    expect(getMasonryColumnCount(520)).toBe(2);
    expect(getMasonryColumnCount(760)).toBe(3);
    expect(getMasonryColumnCount(1100)).toBe(4);
    expect(getMasonryColumnCount(1400)).toBe(5);
  });
});

describe("assignMasonryColumns", () => {
  it("keeps already assigned items in the same columns when new items append", () => {
    const initialItems = [
      { id: 1, height: 1 },
      { id: 2, height: 2 },
      { id: 3, height: 1 },
      { id: 4, height: 1 },
    ];
    const appendedItems = [...initialItems, { id: 5, height: 3 }, { id: 6, height: 1 }];
    const getHeight = (item: { height: number }) => item.height;

    const initialColumns = assignMasonryColumns(initialItems, 3, getHeight).map((column) =>
      column.map((item) => item.id),
    );
    const appendedColumns = assignMasonryColumns(appendedItems, 3, getHeight).map((column) =>
      column.filter((item) => item.id <= 4).map((item) => item.id),
    );

    expect(appendedColumns).toEqual(initialColumns);
  });
});
