"use client";
import { type DragEvent, type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import {
  FileText,
  Link2,
  Upload,
  X,
  CheckCircle2,
  AlertCircle,
  Loader2,
  FileUp,
  HardDrive,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { API_URL, MAX_FILE_SIZE_BYTES } from "@/config";

type Tab = "text" | "link" | "file" | "drive";
type SourceType = "own" | "external";

interface CorpusAddFormProps {
  onSuccess: () => void;
  onClose: () => void;
}

interface FileIngestResponse {
  article_id: string;
  title: string;
  chunks_added: number;
  source_type: string;
  warnings: string[];
}

interface BatchIngestResponse {
  articles_ingested: number;
  total_chunks: number;
  source_type: string;
  warnings: string[];
}

function getHttpFallbackError(status: number): string {
  return `Błąd serwera (HTTP ${status})`;
}

function getPolishCountForm(count: number, one: string, few: string, many: string): string {
  if (count === 1) return one;
  if (count % 10 >= 2 && count % 10 <= 4 && !(count % 100 >= 12 && count % 100 <= 14)) {
    return few;
  }
  return many;
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
  const [justSucceeded, setJustSucceeded] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [progress, setProgress] = useState(0);

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

  // Drive tab state
  const [driveFolder, setDriveFolder] = useState("");
  const [driveSource, setDriveSource] = useState<SourceType>("own");

  // Simulated progress bar: counts up to ~85% while loading, snaps to 100% on success
  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | null = null;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    if (loading) {
      setProgress(5);
      intervalId = setInterval(() => {
        setProgress((p) => Math.min(p + Math.random() * 12 + 3, 85));
      }, 400);
    } else if (justSucceeded) {
      setProgress(100);
    } else {
      timeoutId = setTimeout(() => setProgress(0), 600);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [loading, justSucceeded]);

  // Auto-clear the success indicator after 3 s
  useEffect(() => {
    if (!justSucceeded) return;
    const id = setTimeout(() => setJustSucceeded(false), 3000);
    return () => clearTimeout(id);
  }, [justSucceeded]);

  function resetState() {
    setError(null);
    setJustSucceeded(false);
    setSuccessMsg("");
    setLoading(false);
  }

  function handleTabChange(tab: Tab) {
    setActiveTab(tab);
    resetState();
  }

  function clearErrorOnEdit() {
    if (error) {
      setError(null);
    }
  }

  async function handleTextSubmit(e: FormEvent) {
    e.preventDefault();
    if (!textContent.trim()) {
      setError("Wpisz treść artykułu.");
      return;
    }
    setLoading(true);
    setError(null);
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
        throw new Error(detail?.detail ?? getHttpFallbackError(res.status));
      }
      await res.json();
      setTextContent("");
      setTextTitle("");
      setSuccessMsg("Tekst dodany do korpusu");
      setJustSucceeded(true);
      onSuccess();
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
        throw new Error(detail?.detail ?? getHttpFallbackError(res.status));
      }
      const data = (await res.json()) as BatchIngestResponse;
      if (data.articles_ingested === 0 || data.total_chunks === 0) {
        setJustSucceeded(false);
        setSuccessMsg("");
        setError(data.warnings[0] ?? "Nie udało się pobrać artykułu z podanego adresu.");
        return;
      }

      setLinkUrl("");
      setSuccessMsg("Artykuł pobrany i dodany");
      setJustSucceeded(true);
      onSuccess();
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
        throw new Error(detail?.detail ?? getHttpFallbackError(res.status));
      }
      const data = (await res.json()) as FileIngestResponse;
      if (data.chunks_added === 0) {
        setJustSucceeded(false);
        setSuccessMsg("");
        setError(data.warnings[0] ?? "Plik nie został zaindeksowany.");
        return;
      }

      setFile(null);
      setFileTitle("");
      setSuccessMsg("Plik zaindeksowany");
      setJustSucceeded(true);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd przesyłania pliku");
    } finally {
      setLoading(false);
    }
  }

  async function handleDriveSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = driveFolder.trim();
    if (!trimmed) {
      setError("Podaj ID folderu Google Drive.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/corpus/ingest/drive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_id: trimmed, source_type: driveSource }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail ?? getHttpFallbackError(res.status));
      }
      const data = (await res.json()) as BatchIngestResponse;
      if (data.articles_ingested === 0 || data.total_chunks === 0) {
        setJustSucceeded(false);
        setSuccessMsg("");
        setError(data.warnings[0] ?? "Nie udało się zaindeksować folderu Google Drive.");
        return;
      }

      setDriveFolder("");
      setSuccessMsg(
        `Zaindeksowano ${data.articles_ingested} ${getPolishCountForm(data.articles_ingested, "plik", "pliki", "plików")} · ` +
          `${data.total_chunks} ${getPolishCountForm(data.total_chunks, "fragment", "fragmenty", "fragmentów")}`
      );
      setJustSucceeded(true);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd indeksowania Drive");
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
    if (f.size > MAX_FILE_SIZE_BYTES) {
      setError(
        `Plik jest za duży (${(f.size / 1024 / 1024).toFixed(1)} MB). Maksymalny rozmiar: ${MAX_FILE_SIZE_BYTES / 1024 / 1024} MB.`
      );
      return;
    }
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
    { id: "drive", label: "Drive", icon: <HardDrive className="h-3 w-3" /> },
  ];

  function SuccessBanner() {
    if (!justSucceeded) return null;
    return (
      <div className="flex items-start gap-1.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 px-2 py-1.5">
        <CheckCircle2 className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" />
        <p className="text-xs text-emerald-600 dark:text-emerald-400 leading-snug">{successMsg}</p>
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

      {/* Progress bar — visible during loading and briefly on success */}
      {progress > 0 && (
        <Progress
          value={progress}
          className="h-0.5 rounded-none"
        />
      )}

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
              onChange={(e) => {
                setTextTitle(e.target.value);
                clearErrorOnEdit();
              }}
              className="w-full text-xs bg-background border rounded px-2 py-1.5 placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <textarea
              placeholder="Wklej treść artykułu…"
              value={textContent}
              onChange={(e) => {
                setTextContent(e.target.value);
                clearErrorOnEdit();
              }}
              rows={5}
              className="w-full text-xs bg-background border rounded px-2 py-1.5 placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <div className="flex items-center justify-between">
              <SourceTypeToggle value={textSource} onChange={setTextSource} />
              <Button type="submit" size="sm" disabled={loading} className="h-7 text-xs">
                {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Dodaj"}
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
              onChange={(e) => {
                setLinkUrl(e.target.value);
                clearErrorOnEdit();
              }}
              className="w-full text-xs bg-background border rounded px-2 py-1.5 placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <p className="text-xs text-muted-foreground">
              Tekst zostanie automatycznie pobrany ze strony.
            </p>
            <div className="flex items-center justify-between">
              <SourceTypeToggle value={linkSource} onChange={setLinkSource} />
              <Button type="submit" size="sm" disabled={loading} className="h-7 text-xs">
                {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Pobierz"}
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
                onChange={(e) => {
                  setFileTitle(e.target.value);
                  clearErrorOnEdit();
                }}
                className="w-full text-xs bg-background border rounded px-2 py-1.5 placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
            )}

            <div className="flex items-center justify-between">
              <SourceTypeToggle value={fileSource} onChange={setFileSource} />
              <Button
                type="submit"
                size="sm"
                disabled={!file || loading}
                className="h-7 text-xs"
              >
                {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Prześlij"}
              </Button>
            </div>
          </form>
        )}

        {/* DRIVE TAB */}
        {activeTab === "drive" && (
          <form onSubmit={handleDriveSubmit} className="space-y-2">
            <input
              type="text"
              placeholder="ID folderu Google Drive"
              value={driveFolder}
              onChange={(e) => {
                setDriveFolder(e.target.value);
                clearErrorOnEdit();
              }}
              className="w-full text-xs bg-background border rounded px-2 py-1.5 placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring font-mono"
            />
            <p className="text-xs text-muted-foreground leading-snug">
              ID z URL folderu:{" "}
              <span className="font-mono text-muted-foreground/70 break-all">
                …/folders/<strong>ID_FOLDERU</strong>
              </span>
            </p>
            <div className="flex items-center justify-between">
              <SourceTypeToggle value={driveSource} onChange={setDriveSource} />
              <Button type="submit" size="sm" disabled={loading} className="h-7 text-xs">
                {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Indeksuj"}
              </Button>
            </div>
          </form>
        )}

        {/* Status banners */}
        <SuccessBanner />
        <ErrorBanner />
      </div>
    </div>
  );
}
