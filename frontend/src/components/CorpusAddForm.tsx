"use client";
import { type DragEvent, type FormEvent, type ReactNode, useRef, useState } from "react";
import {
  FileText,
  Link2,
  Upload,
  X,
  CheckCircle2,
  AlertCircle,
  Loader2,
  FileUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Tab = "text" | "link" | "file";
type SourceType = "own" | "external";

interface IngestResult {
  article_id: string;
  title: string;
  chunks_added: number;
  source_type: string;
  warnings: string[];
}

interface BatchIngestResult {
  articles_ingested: number;
  total_chunks: number;
  source_type: string;
  warnings: string[];
}

type SuccessResult = IngestResult | BatchIngestResult;

interface CorpusAddFormProps {
  onSuccess: () => void;
  onClose: () => void;
}

function SourceTypeToggle({
  value,
  onChange,
}: {
  value: SourceType;
  onChange: (v: SourceType) => void;
}): ReactNode {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">Źródło:</span>
      <div className="flex rounded-md border overflow-hidden text-xs">
        <button
          type="button"
          onClick={() => onChange("own")}
          className={`px-2 py-1 transition-colors ${
            value === "own"
              ? "bg-foreground text-background font-medium"
              : "text-muted-foreground hover:bg-muted"
          }`}
        >
          własne
        </button>
        <button
          type="button"
          onClick={() => onChange("external")}
          className={`px-2 py-1 transition-colors border-l ${
            value === "external"
              ? "bg-foreground text-background font-medium"
              : "text-muted-foreground hover:bg-muted"
          }`}
        >
          zewn.
        </button>
      </div>
    </div>
  );
}

export function CorpusAddForm({ onSuccess, onClose }: CorpusAddFormProps) {
  const [activeTab, setActiveTab] = useState<Tab>("text");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<SuccessResult | null>(null);

  // Text tab state
  const [textTitle, setTextTitle] = useState("");
  const [textContent, setTextContent] = useState("");
  const [textSource, setTextSource] = useState<SourceType>("own");

  // Link tab state
  const [linkUrl, setLinkUrl] = useState("");
  const [linkSource, setLinkSource] = useState<SourceType>("external");

  // File tab state
  const [file, setFile] = useState<File | null>(null);
  const [fileTitle, setFileTitle] = useState("");
  const [fileSource, setFileSource] = useState<SourceType>("own");
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function resetState() {
    setError(null);
    setSuccess(null);
    setLoading(false);
  }

  function handleTabChange(tab: Tab) {
    setActiveTab(tab);
    resetState();
  }

  async function handleTextSubmit(e: FormEvent) {
    e.preventDefault();
    if (!textContent.trim()) {
      setError("Wpisz treść artykułu.");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`${API_URL}/api/corpus/ingest/text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: textContent,
          title: textTitle || "Bez tytułu",
          source_type: textSource,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail ?? `HTTP ${res.status}`);
      }
      const data: IngestResult = await res.json();
      setSuccess(data);
      setTextContent("");
      setTextTitle("");
      setTimeout(onSuccess, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd zapisu");
    } finally {
      setLoading(false);
    }
  }

  async function handleLinkSubmit(e: FormEvent) {
    e.preventDefault();
    if (!linkUrl.trim()) {
      setError("Podaj adres URL.");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`${API_URL}/api/corpus/ingest/url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: linkUrl,
          source_type: linkSource,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail ?? `HTTP ${res.status}`);
      }
      const data: BatchIngestResult = await res.json();
      setSuccess(data);
      setLinkUrl("");
      setTimeout(onSuccess, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd pobierania URL");
    } finally {
      setLoading(false);
    }
  }

  async function handleFileSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Wybierz plik do przesłania.");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("source_type", fileSource);
      formData.append("title", fileTitle || file.name);

      const res = await fetch(`${API_URL}/api/corpus/ingest/file`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail ?? `HTTP ${res.status}`);
      }
      const data: IngestResult = await res.json();
      setSuccess(data);
      setFile(null);
      setFileTitle("");
      setTimeout(onSuccess, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd przesyłania pliku");
    } finally {
      setLoading(false);
    }
  }

  function handleFileDrop(e: DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) acceptFile(dropped);
  }

  function acceptFile(f: File) {
    const allowed = [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/plain",
    ];
    const ext = f.name.split(".").pop()?.toLowerCase();
    if (!allowed.includes(f.type) && !["pdf", "docx", "txt"].includes(ext ?? "")) {
      setError("Obsługiwane formaty: PDF, DOCX, TXT");
      return;
    }
    setFile(f);
    setError(null);
    if (!fileTitle) setFileTitle(f.name.replace(/\.[^.]+$/, ""));
  }

  const tabs: { id: Tab; label: string; icon: ReactNode }[] = [
    { id: "text", label: "Tekst", icon: <FileText className="h-3 w-3" /> },
    { id: "link", label: "Link", icon: <Link2 className="h-3 w-3" /> },
    { id: "file", label: "Plik", icon: <Upload className="h-3 w-3" /> },
  ];

  function SuccessBanner() {
    if (!success) return null;
    const isArticle = "article_id" in success;
    const count = isArticle
      ? (success as IngestResult).chunks_added
      : (success as BatchIngestResult).total_chunks;
    return (
      <div className="flex items-start gap-1.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 px-2 py-1.5">
        <CheckCircle2 className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" />
        <p className="text-xs text-emerald-600 dark:text-emerald-400">
          Dodano — {count}{" "}
          {count === 1 ? "fragment" : "fragmentów"}
        </p>
      </div>
    );
  }

  function ErrorBanner() {
    if (!error) return null;
    return (
      <div className="flex items-start gap-1.5 rounded-md bg-destructive/10 border border-destructive/20 px-2 py-1.5">
        <AlertCircle className="h-3 w-3 text-destructive mt-0.5 shrink-0" />
        <p className="text-xs text-destructive leading-snug">{error}</p>
      </div>
    );
  }

  return (
    <div className="border rounded-lg bg-background/60 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Dodaj treść
        </span>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Zamknij"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-2 text-xs transition-colors border-b-2 ${
              activeTab === tab.id
                ? "border-foreground text-foreground font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground"
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="p-3 space-y-2.5">
        {/* TEXT TAB */}
        {activeTab === "text" && (
          <form onSubmit={handleTextSubmit} className="space-y-2">
            <input
              type="text"
              placeholder="Tytuł (opcjonalnie)"
              value={textTitle}
              onChange={(e) => setTextTitle(e.target.value)}
              className="w-full text-xs bg-background border rounded px-2 py-1.5 placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <textarea
              placeholder="Wklej treść artykułu…"
              value={textContent}
              onChange={(e) => setTextContent(e.target.value)}
              rows={5}
              className="w-full text-xs bg-background border rounded px-2 py-1.5 placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <div className="flex items-center justify-between">
              <SourceTypeToggle value={textSource} onChange={setTextSource} />
              <Button
                type="submit"
                size="sm"
                disabled={loading || !!success}
                className="h-7 text-xs"
              >
                {loading ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  "Dodaj"
                )}
              </Button>
            </div>
          </form>
        )}

        {/* LINK TAB */}
        {activeTab === "link" && (
          <form onSubmit={handleLinkSubmit} className="space-y-2">
            <input
              type="url"
              placeholder="https://example.com/artykul"
              value={linkUrl}
              onChange={(e) => setLinkUrl(e.target.value)}
              className="w-full text-xs bg-background border rounded px-2 py-1.5 placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <p className="text-xs text-muted-foreground">
              Tekst zostanie automatycznie pobrany ze strony.
            </p>
            <div className="flex items-center justify-between">
              <SourceTypeToggle value={linkSource} onChange={setLinkSource} />
              <Button
                type="submit"
                size="sm"
                disabled={loading || !!success}
                className="h-7 text-xs"
              >
                {loading ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  "Pobierz"
                )}
              </Button>
            </div>
          </form>
        )}

        {/* FILE TAB */}
        {activeTab === "file" && (
          <form onSubmit={handleFileSubmit} className="space-y-2">
            {/* Drop zone */}
            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleFileDrop}
              className={`relative flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed cursor-pointer transition-colors py-5 ${
                isDragging
                  ? "border-foreground bg-muted/40"
                  : "border-muted-foreground/30 hover:border-muted-foreground/60 hover:bg-muted/20"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.txt"
                className="sr-only"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) acceptFile(f);
                }}
              />
              {file ? (
                <>
                  <FileUp className="h-5 w-5 text-foreground" />
                  <span className="text-xs font-medium text-foreground text-center px-2 truncate max-w-full">
                    {file.name}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {(file.size / 1024).toFixed(0)} KB
                  </span>
                </>
              ) : (
                <>
                  <Upload className="h-5 w-5 text-muted-foreground" />
                  <p className="text-xs text-muted-foreground text-center leading-snug">
                    Przeciągnij plik lub kliknij
                    <br />
                    <span className="text-muted-foreground/60">PDF, DOCX, TXT</span>
                  </p>
                </>
              )}
            </div>

            {file && (
              <input
                type="text"
                placeholder="Tytuł (opcjonalnie)"
                value={fileTitle}
                onChange={(e) => setFileTitle(e.target.value)}
                className="w-full text-xs bg-background border rounded px-2 py-1.5 placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
            )}

            <div className="flex items-center justify-between">
              <SourceTypeToggle value={fileSource} onChange={setFileSource} />
              <Button
                type="submit"
                size="sm"
                disabled={!file || loading || !!success}
                className="h-7 text-xs"
              >
                {loading ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  "Prześlij"
                )}
              </Button>
            </div>
          </form>
        )}

        {/* Feedback banners */}
        <SuccessBanner />
        <ErrorBanner />
      </div>
    </div>
  );
}
