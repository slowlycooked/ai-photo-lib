import { describe, expect, it } from "vitest";
import { assignMasonryColumns } from "./MasonryGrid";

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
