"use client";
import { CheckCheck, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Annotation } from "@/store/shadowStore";

// ---------------------------------------------------------------------------
// AnnotationList — sidebar with style-correction cards.
//
// Each card shows the reason + original→replacement diff.
// Clicking a card fires onAnnotationClick (caller handles scroll + highlight).
// "Zastosuj wszystkie" restores the fully-corrected AI version.
// ---------------------------------------------------------------------------

interface AnnotationListProps {
  annotations: Annotation[];
  activeId: string | null;
  onAnnotationClick: (annotation: Annotation) => void;
  onApplyAll: () => void;
  isStreaming: boolean;
}

export function AnnotationList({
  annotations,
  activeId,
  onAnnotationClick,
  onApplyAll,
  isStreaming,
}: AnnotationListProps) {
  const showSkeleton = isStreaming && annotations.length === 0;

  return (
    <div className="w-64 flex flex-col border-r overflow-hidden shrink-0">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b bg-muted/10 shrink-0">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex-1">
          Adnotacje{annotations.length > 0 && ` (${annotations.length})`}
        </span>
        {annotations.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[11px] gap-1 px-1.5"
            onClick={onApplyAll}
            disabled={isStreaming}
            title="Zastosuj wszystkie sugestie"
          >
            <CheckCheck className="h-3 w-3" />
            Zastosuj
          </Button>
        )}
      </div>

      {/* Card list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {/* Skeleton loaders while waiting for analysis */}
        {showSkeleton && (
          <>
            {[80, 64, 72].map((w) => (
              <div key={w} className="rounded-lg border p-3 space-y-2">
                <div className="h-2.5 bg-muted/50 rounded animate-pulse" style={{ width: `${w}%` }} />
                <div className="h-2 bg-muted/40 rounded animate-pulse w-full" />
                <div className="h-2 bg-muted/40 rounded animate-pulse w-3/4" />
              </div>
            ))}
          </>
        )}

        {/* Annotation cards */}
        {annotations.map((ann) => {
          const isActive = activeId === ann.id;
          return (
            <button
              key={ann.id}
              onClick={() => onAnnotationClick(ann)}
              className={[
                "w-full text-left rounded-lg border transition-all duration-150 p-3",
                isActive
                  ? "bg-amber-50 border-amber-300 shadow-sm dark:bg-amber-900/20 dark:border-amber-700"
                  : "bg-card border-border hover:bg-muted/40 hover:border-muted-foreground/30",
              ].join(" ")}
            >
              {/* ID badge */}
              <Badge
                variant="outline"
                className="text-[10px] h-4 font-mono px-1.5 mb-1.5"
              >
                {ann.id}
              </Badge>

              {/* Reason */}
              <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">
                {ann.reason}
              </p>

              {/* Diff: original → replacement */}
              <div className="mt-2 flex items-start gap-1 text-[11px]">
                <span
                  className="text-red-500/80 line-through truncate max-w-[40%]"
                  title={ann.original_span}
                >
                  {ann.original_span}
                </span>
                <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0 mt-0.5" />
                <span
                  className="text-emerald-600 dark:text-emerald-400 truncate max-w-[40%]"
                  title={ann.replacement}
                >
                  {ann.replacement}
                </span>
              </div>
            </button>
          );
        })}

        {/* Empty state after streaming completes */}
        {!isStreaming && annotations.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-6 px-2">
            Brak adnotacji stylistycznych
          </p>
        )}
      </div>
    </div>
  );
}
