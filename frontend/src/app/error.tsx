"use client";
import { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface ErrorProps {
    error: Error & { digest?: string };
    reset: () => void;
}

export default function Error({ error, reset }: ErrorProps) {
    useEffect(() => {
        console.error("[Route Error]", error);
    }, [error]);

    return (
        <div className="flex items-center justify-center h-full min-h-[300px] p-8">
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-6 max-w-md w-full text-center space-y-4">
                <div className="flex items-center justify-center gap-2 text-destructive">
                    <AlertTriangle className="h-5 w-5" />
                    <h2 className="text-base font-semibold">Błąd strony</h2>
                </div>
                <p className="text-sm text-muted-foreground">
                    {error.message || "Wystąpił nieoczekiwany błąd podczas ładowania strony."}
                </p>
                {error.digest && (
                    <p className="text-xs text-muted-foreground/60 font-mono">ID: {error.digest}</p>
                )}
                <button
                    onClick={reset}
                    className="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                    <RefreshCw className="h-3.5 w-3.5" />
                    Spróbuj ponownie
                </button>
            </div>
        </div>
    );
}
