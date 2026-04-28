import { StageProgress } from "@/components/StageProgress";
import { ChatInterface } from "@/components/ChatInterface";
import { EditorPane } from "@/components/EditorPane";
import { CheckpointPanel } from "@/components/CheckpointPanel";

export default function Home() {
  return (
    <div className="flex flex-col h-full bg-background overflow-hidden">
      <StageProgress />
      <div className="flex flex-1 min-h-0 flex-col overflow-hidden lg:flex-row">
        <div className="flex min-h-[18rem] min-w-0 flex-1 flex-col overflow-hidden border-b lg:w-[40%] lg:max-w-2xl lg:flex-none lg:shrink-0 lg:border-b-0 lg:border-r">
          <ChatInterface />
        </div>
        <div className="flex flex-1 min-w-0 flex-col overflow-hidden bg-muted/10">
          <CheckpointPanel />
          <EditorPane />
        </div>
      </div>
    </div>
  );
}
