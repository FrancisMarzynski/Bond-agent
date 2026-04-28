"use client";
import { CheckCheck, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
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
  layout?: "sidebar" | "section";
  className?: string;
}

export function AnnotationList({
  annotations,
  activeId,
  onAnnotationClick,
  onApplyAll,
  isStreaming,
  layout = "sidebar",
  className,
}: AnnotationListProps) {
  const showSkeleton = isStreaming && annotations.length === 0;
  const isSection = layout === "section";

  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden",
        isSection ? "w-full" : "w-64 shrink-0 border-r",
        className
      )}
    >
      {/* Header */}
      <div
        className={cn(
          "shrink-0 border-b bg-muted/10",
          isSection
            ? "flex flex-wrap items-center gap-2 px-4 py-3"
            : "flex items-center gap-2 px-3 py-2"
        )}
      >
        <span className="flex-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Adnotacje{annotations.length > 0 && ` (${annotations.length})`}
        </span>
        {annotations.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              "gap-1",
              isSection
                ? "h-7 px-2 text-xs max-sm:w-full sm:ml-auto"
                : "h-6 px-1.5 text-[11px]"
            )}
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
      <div
        className={cn(
          "overflow-y-auto",
          isSection ? "max-h-64 px-4 py-3" : "flex-1 p-2"
        )}
      >
        <div className={cn(isSection ? "grid gap-2 sm:grid-cols-2" : "space-y-1.5")}>
          {/* Skeleton loaders while waiting for analysis */}
          {showSkeleton &&
            [80, 64, 72].map((w) => (
              <div key={w} className="space-y-2 rounded-lg border p-3">
                <div className="h-2.5 animate-pulse rounded bg-muted/50" style={{ width: `${w}%` }} />
                <div className="h-2 w-full animate-pulse rounded bg-muted/40" />
                <div className="h-2 w-3/4 animate-pulse rounded bg-muted/40" />
              </div>
            ))}

          {/* Annotation cards */}
          {annotations.map((ann) => {
            const isActive = activeId === ann.id;
            return (
              <button
                key={ann.id}
                onClick={() => onAnnotationClick(ann)}
                className={[
                  "w-full rounded-lg border p-3 text-left transition-all duration-150",
                  isActive
                    ? "border-amber-300 bg-amber-50 shadow-sm dark:border-amber-700 dark:bg-amber-900/20"
                    : "border-border bg-card hover:border-muted-foreground/30 hover:bg-muted/40",
                ].join(" ")}
              >
                <Badge
                  variant="outline"
                  className="mb-1.5 h-4 px-1.5 font-mono text-[10px]"
                >
                  {ann.id}
                </Badge>

                <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground">
                  {ann.reason}
                </p>

                <div className="mt-2 flex items-start gap-1 text-[11px]">
                  <span
                    className="max-w-[40%] truncate text-red-500/80 line-through"
                    title={ann.original_span}
                  >
                    {ann.original_span}
                  </span>
                  <ChevronRight className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                  <span
                    className="max-w-[40%] truncate text-emerald-600 dark:text-emerald-400"
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
            <p
              className={cn(
                "text-center text-xs text-muted-foreground",
                isSection ? "col-span-full py-4" : "px-2 py-6"
              )}
            >
              Brak adnotacji stylistycznych
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
