import { useSearchParams } from "react-router-dom";
import { SearchResultGrid } from "@/components/SearchResultGrid";
import { SearchX } from "lucide-react";

export function SearchPage() {
  const [params] = useSearchParams();
  const query = params.get("q") ?? "";

  if (!query) {
    return (
      <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-24 flex flex-col items-center gap-4 text-mute">
        <SearchX className="w-10 h-10" />
        <p className="text-body-sm">在顶部搜索框输入关键词开始搜索</p>
      </main>
    );
  }

  return (
    <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6">
      <SearchResultGrid query={query} />
    </main>
  );
}
