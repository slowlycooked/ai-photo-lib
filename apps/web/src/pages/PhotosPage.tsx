import { ScanPanel } from "@/components/ScanPanel";
import { AIPanel } from "@/components/AIPanel";
import { TimelineGrid } from "@/components/TimelineGrid";
import { useScanStatus, useStartScan } from "@/hooks/useScan";

export function PhotosPage() {
  const { data: scanStatus, isLoading: scanLoading } = useScanStatus();
  const { mutate: startScan, isPending } = useStartScan();

  return (
    <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6 space-y-5">
      <ScanPanel
        status={scanStatus}
        isLoading={scanLoading}
        onStart={() => startScan()}
        isPending={isPending}
      />
      <AIPanel />
      <TimelineGrid />
    </main>
  );
}
