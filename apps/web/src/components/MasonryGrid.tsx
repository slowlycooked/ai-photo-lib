import { type CSSProperties, type Key, type ReactNode, useEffect, useMemo, useState } from "react";

const DEFAULT_ITEM_HEIGHT = 1;
const ITEM_GAP_HEIGHT = 0.04;

interface MasonryGridProps<TItem> {
  items: TItem[];
  getKey: (item: TItem) => Key;
  getItemHeight?: (item: TItem) => number | null | undefined;
  renderItem: (item: TItem) => ReactNode;
  className?: string;
}

function getColumnCount(width: number) {
  if (width >= 1280) {
    return 5;
  }
  if (width >= 1024) {
    return 4;
  }
  if (width >= 640) {
    return 3;
  }
  return 2;
}

function getInitialColumnCount() {
  if (typeof window === "undefined") {
    return 2;
  }
  return getColumnCount(window.innerWidth);
}

function useMasonryColumnCount() {
  const [columnCount, setColumnCount] = useState(getInitialColumnCount);

  useEffect(() => {
    const updateColumnCount = () => {
      setColumnCount(getColumnCount(window.innerWidth));
    };

    updateColumnCount();
    window.addEventListener("resize", updateColumnCount);
    return () => window.removeEventListener("resize", updateColumnCount);
  }, []);

  return columnCount;
}

export function assignMasonryColumns<TItem>(
  items: TItem[],
  columnCount: number,
  getItemHeight?: (item: TItem) => number | null | undefined,
) {
  const safeColumnCount = Math.max(1, columnCount);
  const columns = Array.from({ length: safeColumnCount }, () => [] as TItem[]);
  const heights = Array.from({ length: safeColumnCount }, () => 0);

  for (const item of items) {
    const targetColumn = heights.indexOf(Math.min(...heights));
    const rawHeight = getItemHeight?.(item) ?? DEFAULT_ITEM_HEIGHT;
    const itemHeight = Number.isFinite(rawHeight) && rawHeight > 0 ? rawHeight : DEFAULT_ITEM_HEIGHT;

    columns[targetColumn].push(item);
    heights[targetColumn] += itemHeight + ITEM_GAP_HEIGHT;
  }

  return columns;
}

export function MasonryGrid<TItem>({
  items,
  getKey,
  getItemHeight,
  renderItem,
  className,
}: MasonryGridProps<TItem>) {
  const columnCount = useMasonryColumnCount();
  const columns = useMemo(
    () => assignMasonryColumns(items, columnCount, getItemHeight),
    [columnCount, getItemHeight, items],
  );
  const style = { "--masonry-columns": columnCount } as CSSProperties;

  return (
    <div className={["masonry-grid", className].filter(Boolean).join(" ")} style={style}>
      {columns.map((column, columnIndex) => (
        <div key={columnIndex} className="masonry-column">
          {column.map((item) => (
            <div key={getKey(item)}>{renderItem(item)}</div>
          ))}
        </div>
      ))}
    </div>
  );
}
