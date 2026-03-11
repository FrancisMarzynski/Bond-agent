import { StageProgress } from "@/components/StageProgress";
import { ChatInterface } from "@/components/ChatInterface";
import { EditorPane } from "@/components/EditorPane";
import { CheckpointPanel } from "@/components/CheckpointPanel";

export default function Home() {
  return (
    <div className="flex flex-col h-full bg-background overflow-hidden">
      <StageProgress />
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Kolumna Czatu — 40% szerokości */}
        <div className="w-[40%] min-w-0 flex flex-col border-r overflow-hidden">
          <ChatInterface />
        </div>
        {/* Kolumna Edytora — 60% szerokości */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-muted/10">
          <CheckpointPanel />
          <EditorPane />
        </div>
      </div>
    </div>
  );
}
