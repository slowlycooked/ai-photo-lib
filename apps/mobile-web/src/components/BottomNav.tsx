import { Images, Search, UserRound } from "lucide-react";
import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";

function NavItem({
  to,
  label,
  icon,
}: {
  to: string;
  label: string;
  icon: ReactNode;
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex flex-1 flex-col items-center gap-1 py-2 text-xs ${
          isActive ? "text-mobileAccent" : "text-mobileMute"
        }`
      }
    >
      {icon}
      <span>{label}</span>
    </NavLink>
  );
}

export function BottomNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-mobileHairline bg-mobileCard/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-3xl px-2">
        <NavItem to="/photos" label="照片" icon={<Images size={18} />} />
        <NavItem to="/search" label="搜索" icon={<Search size={18} />} />
        <NavItem to="/me" label="我的" icon={<UserRound size={18} />} />
      </div>
    </nav>
  );
}
