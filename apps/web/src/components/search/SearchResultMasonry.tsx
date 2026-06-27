import type { SearchResultItem } from "@/api/types";
import { MasonryGrid } from "@/components/MasonryGrid";
import { SearchCard } from "@/components/search/SearchCard";

interface SearchResultMasonryProps {
  items: SearchResultItem[];
  debug?: boolean;
  onPreview?: (item: SearchResultItem) => void;
}

export function SearchResultMasonry({ items, debug, onPreview }: SearchResultMasonryProps) {
  return (
    <MasonryGrid
      items={items}
      getKey={(item) => item.photo_id}
      getItemHeight={(item) => (item.width && item.height ? item.height / item.width + 0.6 : 1.35)}
      renderItem={(item) => (
        <SearchCard
          item={item}
          debug={debug}
          onPreview={onPreview}
        />
      )}
    />
  );
}
