import type { CapabilityMaturityItem } from "@/lib/capabilityMaturity";

function badgeClass(level: CapabilityMaturityItem["level"]): string {
  if (level === "stable") {
    return "bg-green-50 border-green-200 text-green-700";
  }
  if (level === "experimental") {
    return "bg-amber-50 border-amber-200 text-amber-700";
  }
  return "bg-sky-50 border-sky-200 text-sky-700";
}

export function CapabilityMaturityBadge({
  item,
  compact = false,
}: {
  item: CapabilityMaturityItem;
  compact?: boolean;
}) {
  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold",
        badgeClass(item.level),
      ].join(" ")}
      title={item.hint}
      aria-label={`${item.capability} 成熟度：${item.levelLabel}。${item.hint}`}
    >
      {compact ? item.levelLabel : `${item.capability} · ${item.levelLabel}`}
    </span>
  );
}
