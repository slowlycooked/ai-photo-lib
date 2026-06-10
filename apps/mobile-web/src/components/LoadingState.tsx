export function LoadingState({ label = "加载中..." }: { label?: string }) {
  return (
    <div className="rounded-2xl border border-mobileHairline bg-mobileCard p-5 text-center text-sm text-mobileMute">
      {label}
    </div>
  );
}
