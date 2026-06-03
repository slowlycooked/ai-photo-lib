import type { ReactNode } from "react";

interface InfoRowProps {
  icon: ReactNode;
  label: string;
  value: ReactNode;
}

export function InfoRow({ icon, label, value }: InfoRowProps) {
  return (
    <div className="flex items-start gap-1.5">
      <span className="text-mute mt-0.5 flex-shrink-0">{icon}</span>
      <div>
        <p className="text-caption-sm text-mute">{label}</p>
        <p className="text-body-sm text-ink font-medium">{value}</p>
      </div>
    </div>
  );
}
