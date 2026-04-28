import { StageProgress } from "@/components/StageProgress";
import { ShadowPanel } from "@/components/ShadowPanel";

export default function ShadowPage() {
  return (
    <div className="flex flex-col h-full bg-background overflow-hidden">
      <StageProgress />
      <div className="flex-1 min-h-0 overflow-hidden">
        <ShadowPanel />
      </div>
    </div>
  );
}
