"use client";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
    children: ReactNode;
    fallback?: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error("[ErrorBoundary] Uncaught render error:", error, info.componentStack);
    }

    private handleReset = () => {
        this.setState({ hasError: false, error: null });
    };

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) return this.props.fallback;

            return (
                <div className="flex items-center justify-center h-full min-h-[200px] p-8">
                    <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-6 max-w-md w-full text-center space-y-4">
                        <div className="flex items-center justify-center gap-2 text-destructive">
                            <AlertTriangle className="h-5 w-5" />
                            <h2 className="text-base font-semibold">Wystąpił nieoczekiwany błąd</h2>
                        </div>
                        <p className="text-sm text-muted-foreground">
                            {this.state.error?.message || "Nieznany błąd aplikacji. Spróbuj odświeżyć stronę."}
                        </p>
                        <div className="flex gap-2 justify-center">
                            <button
                                onClick={this.handleReset}
                                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md border border-input bg-background hover:bg-muted transition-colors"
                            >
                                <RefreshCw className="h-3.5 w-3.5" />
                                Spróbuj ponownie
                            </button>
                            <button
                                onClick={() => window.location.reload()}
                                className="px-4 py-2 text-sm rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                            >
                                Odśwież stronę
                            </button>
                        </div>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
