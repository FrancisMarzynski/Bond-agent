import { StageProgress } from "@/components/StageProgress";
import { ChatInterface } from "@/components/ChatInterface";
import { EditorPane } from "@/components/EditorPane";
import { CheckpointPanel } from "@/components/CheckpointPanel";

export default function Home() {
  return (
    <div className="flex flex-col h-full bg-background overflow-hidden">
      <StageProgress />
      <div className="flex flex-1 min-h-0 overflow-hidden flex-col md:flex-row">
        {/* Kolumna Czatu — responsywna z ograniczoną szerokością */}
        <div className="w-full md:w-[45%] lg:w-[40%] lg:max-w-2xl min-w-0 flex flex-col border-r overflow-hidden shrink-0">
          <ChatInterface />
        </div>
        {/* Kolumna Edytora — reszta przestrzeni */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-muted/10">
          <CheckpointPanel />
          <EditorPane />
        </div>
      </div>
    </div>
  );
}
