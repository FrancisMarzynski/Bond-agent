import { StageProgress } from "@/components/StageProgress";

export default function Home() {
  return (
    <div className="flex flex-col h-full">
      <StageProgress />
      <div className="flex-1 p-4 text-muted-foreground text-sm">
        Interfejs czatu pojawi się w Planie 04.
      </div>
    </div>
  );
}
