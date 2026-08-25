import { describe, expect, it } from "vitest";
import { assignMasonryColumns, getMasonryColumnCount } from "./MasonryGrid";

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
