"use client";
import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  Layers,
  ChevronDown,
  ChevronUp,
  Plus,
} from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { CorpusAddForm } from "@/components/CorpusAddForm";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface DocumentInfo {
  article_id: string;
  title: string;
  source_type: string;
  source_url: string;
  chunk_count: number;
  ingested_at: string | null;
}

interface CorpusStatus {
  article_count: number;
  chunk_count: number;
  low_corpus_warning: string | null;
  documents: DocumentInfo[];
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("pl-PL", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
    });
  } catch {
    return "—";
  }
}

const SOURCE_LABEL: Record<string, string> = {
  own: "własne",
  external: "zewn.",
};

export function CorpusStatusPanel() {
  const [status, setStatus] = useState<CorpusStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/corpus/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: CorpusStatus = await res.json();
      setStatus(data);
      setError(null);
    } catch {
      setError("Błąd pobierania statusu");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function initialFetch() {
      try {
        const res = await fetch(`${API_URL}/api/corpus/status`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: CorpusStatus = await res.json();
        if (!cancelled) {
          setStatus(data);
          setError(null);
        }
      } catch {
        if (!cancelled) setError("Błąd pobierania statusu");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    initialFetch();
    return () => {
      cancelled = true;
    };
  }, []);

  function handleAddSuccess() {
    setShowAddForm(false);
    fetchStatus();
  }

  return (
    <div className="shrink-0">
      <Separator />
      <div className="p-3 space-y-2">
        {/* Header row */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
          >
            <span>Baza wiedzy</span>
            {expanded ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
          </button>
          <button
            onClick={() => setShowAddForm((v) => !v)}
            title={showAddForm ? "Zamknij formularz" : "Dodaj treść"}
            className={`rounded-md p-0.5 transition-colors ${
              showAddForm
                ? "text-foreground bg-muted"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Add form */}
        {showAddForm && (
          <CorpusAddForm
            onSuccess={handleAddSuccess}
            onClose={() => setShowAddForm(false)}
          />
        )}

        {loading && (
          <p className="text-xs text-muted-foreground px-1">Ładowanie…</p>
        )}

        {error && !loading && (
          <p className="text-xs text-destructive px-1">{error}</p>
        )}

        {status && !loading && (
          <>
            {/* Warning */}
            {status.low_corpus_warning && (
              <div className="flex items-start gap-1.5 rounded-md bg-amber-500/10 border border-amber-500/20 px-2 py-1.5">
                <AlertTriangle className="h-3 w-3 text-amber-500 mt-0.5 shrink-0" />
                <p className="text-xs text-amber-600 dark:text-amber-400 leading-snug">
                  Mało danych — {status.article_count}{" "}
                  {status.article_count === 1 ? "artykuł" : "artykułów"}
                </p>
              </div>
            )}

            {/* Counts */}
            <div className="flex items-center gap-3 px-1">
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <BookOpen className="h-3 w-3" />
                <span>{status.article_count}</span>
              </div>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Layers className="h-3 w-3" />
                <span>{status.chunk_count}</span>
              </div>
            </div>

            {/* Document table — shown when expanded */}
            {expanded && (
              <div className="overflow-y-auto max-h-52">
                {status.documents.length === 0 ? (
                  <p className="text-xs text-muted-foreground px-1 py-2 text-center">
                    Brak dokumentów
                  </p>
                ) : (
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-muted-foreground border-b">
                        <th className="text-left font-medium pb-1 pr-1">Nazwa</th>
                        <th className="text-left font-medium pb-1 pr-1 whitespace-nowrap">
                          Źródło
                        </th>
                        <th className="text-left font-medium pb-1 whitespace-nowrap">
                          Data
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {status.documents.map((doc) => (
                        <tr
                          key={doc.article_id}
                          className="border-b border-muted/40 last:border-0"
                        >
                          <td className="py-1 pr-1 max-w-0">
                            <span
                              className="block truncate text-foreground/80"
                              title={doc.title}
                            >
                              {doc.title}
                            </span>
                          </td>
                          <td className="py-1 pr-1 whitespace-nowrap text-muted-foreground">
                            {SOURCE_LABEL[doc.source_type] ?? doc.source_type}
                          </td>
                          <td className="py-1 whitespace-nowrap text-muted-foreground">
                            {formatDate(doc.ingested_at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
