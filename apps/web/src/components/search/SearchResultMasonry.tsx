import type { SearchResultItem } from "@/api/types";
import { SearchCard } from "@/components/search/SearchCard";

interface SearchResultMasonryProps {
  items: SearchResultItem[];
  debug?: boolean;
  onPreview?: (item: SearchResultItem) => void;
}

export function SearchResultMasonry({ items, debug, onPreview }: SearchResultMasonryProps) {
  return (
    <div className="masonry-grid">
      {items.map((item) => (
        <SearchCard
          key={item.photo_id}
          item={item}
          debug={debug}
          onPreview={onPreview}
        />
      ))}
    </div>
  );
}
