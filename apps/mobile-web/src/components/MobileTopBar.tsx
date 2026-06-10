import { Search } from "lucide-react";
import { Link } from "react-router-dom";

export function MobileTopBar({
  title,
  onOpenProjects,
}: {
  title: string;
  onOpenProjects: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-mobileHairline bg-mobileBg/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-3xl items-center justify-between px-4">
        <button
          type="button"
          onClick={onOpenProjects}
          className="max-w-[72%] truncate rounded-lg px-2 py-1 text-left text-sm font-semibold text-mobileInk"
        >
          {title} v
        </button>
        <Link
          to="/search"
          className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-mobileHairline bg-mobileCard text-mobileInk"
          aria-label="打开搜索"
        >
          <Search size={18} />
        </Link>
      </div>
    </header>
  );
}
