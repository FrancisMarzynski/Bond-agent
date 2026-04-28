import { StageProgress } from "@/components/StageProgress";
import { ShadowPanel } from "@/components/ShadowPanel";

export default function ShadowPage() {
  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden bg-background">
      <StageProgress />
      <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
        <ShadowPanel />
      </div>
    </div>
  );
}
