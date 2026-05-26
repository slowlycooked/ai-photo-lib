import type { ReactNode } from "react";

export function SettingsCard({
  title,
  children,
}: {
  title: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="bg-canvas border border-hairline rounded-md">
      <div className="px-5 py-3 border-b border-hairline">
        <h2 className="text-body-sm font-semibold text-ink">{title}</h2>
      </div>
      <div className="px-5 py-4 space-y-3">{children}</div>
    </section>
  );
}

export function Label({ children }: { children: ReactNode }) {
  return <label className="block text-caption-sm text-mute mb-1">{children}</label>;
}
