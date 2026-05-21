import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { SearchResultGrid } from "@/components/SearchResultGrid";
import { SearchX, Bug } from "lucide-react";
import { useProjectContext } from "@/contexts/ProjectContext";
import type { SearchMode } from "@/api/types";

const MODES: { value: SearchMode; label: string }[] = [
  { value: "hybrid", label: "自动 Hybrid" },
  { value: "keyword", label: "关键词" },
  { value: "vector", label: "语义 Vector" },
];

export function SearchPage() {
  const [params] = useSearchParams();
  const query = params.get("q") ?? "";
  const { currentProjectId } = useProjectContext();
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [debug, setDebug] = useState(false);

  if (!query) {
    return (
      <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-24 flex flex-col items-center gap-4 text-mute">
        <SearchX className="w-10 h-10" />
        <p className="text-body-sm">在顶部搜索框输入关键词开始搜索</p>
      </main>
    );
  }

  return (
    <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6 space-y-4">
      {/* Mode selector + debug toggle */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center rounded-md border border-border overflow-hidden text-sm">
          {MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => setMode(m.value)}
              className={
                "px-3 py-1.5 transition-colors " +
                (mode === m.value
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-accent text-muted-foreground")
              }
            >
              {m.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer select-none">
          <input
            type="checkbox"
            checked={debug}
            onChange={(e) => setDebug(e.target.checked)}
            className="rounded"
          />
          <Bug className="w-3.5 h-3.5" />
          Debug
        </label>
      </div>

      <SearchResultGrid
        query={query}
        projectId={currentProjectId}
        mode={mode}
        debug={debug}
      />
    </main>
  );
}
