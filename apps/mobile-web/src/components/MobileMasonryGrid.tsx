import { type CSSProperties, type Key, type ReactNode, useEffect, useMemo, useState } from "react";

const DEFAULT_ITEM_HEIGHT = 1;
const ITEM_GAP_HEIGHT = 0.04;

interface MobileMasonryGridProps<TItem> {
  items: TItem[];
  getKey: (item: TItem) => Key;
  getItemHeight?: (item: TItem) => number | null | undefined;
  renderItem: (item: TItem) => ReactNode;
}

function getColumnCount(width: number) {
  return width >= 640 ? 3 : 2;
}

function getInitialColumnCount() {
  if (typeof window === "undefined") {
    return 2;
  }
  return getColumnCount(window.innerWidth);
}

function useMobileMasonryColumnCount() {
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

export function assignMobileMasonryColumns<TItem>(
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

export function MobileMasonryGrid<TItem>({
  items,
  getKey,
  getItemHeight,
  renderItem,
}: MobileMasonryGridProps<TItem>) {
  const columnCount = useMobileMasonryColumnCount();
  const columns = useMemo(
    () => assignMobileMasonryColumns(items, columnCount, getItemHeight),
    [columnCount, getItemHeight, items],
  );
  const style = { "--mobile-grid-columns": columnCount } as CSSProperties;

  return (
    <div className="mobile-grid" style={style}>
      {columns.map((column, columnIndex) => (
        <div key={columnIndex} className="mobile-grid-column">
          {column.map((item) => (
            <div key={getKey(item)}>{renderItem(item)}</div>
          ))}
        </div>
      ))}
    </div>
  );
}
