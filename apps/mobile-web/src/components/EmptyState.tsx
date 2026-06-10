export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-mobileHairline bg-mobileCard px-6 py-10 text-center">
      <h3 className="text-base font-semibold text-mobileInk">{title}</h3>
      <p className="mt-2 text-sm text-mobileMute">{description}</p>
    </div>
  );
}
