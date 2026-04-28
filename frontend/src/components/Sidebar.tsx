"use client";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { PlusCircle, MessageSquare } from "lucide-react";
import { useSession } from "@/hooks/useSession";
import { CorpusStatusPanel } from "@/components/CorpusStatusPanel";

interface SidebarContentProps {
    onNavigate?: () => void;
    renderHeaderActions?: (actions: { handleNewSession: () => void }) => React.ReactNode;
}

export function SidebarContent({
    onNavigate,
    renderHeaderActions,
}: SidebarContentProps) {
    const { threadId, sessions, newSession, switchSession } = useSession();

    const handleNewSession = () => {
        newSession();
        onNavigate?.();
    };

    const handleSwitchSession = (session: (typeof sessions)[number]) => {
        switchSession(session);
        onNavigate?.();
    };

    return (
        <>
            <div className="p-4 flex items-center justify-between">
                <span className="font-semibold text-sm">Bond Agent</span>
                {renderHeaderActions ? (
                    renderHeaderActions({ handleNewSession })
                ) : (
                    <Button variant="ghost" size="sm" onClick={handleNewSession} title="Nowa sesja">
                        <PlusCircle className="h-4 w-4" />
                    </Button>
                )}
            </div>
            <Separator />
            <nav className="flex-1 overflow-y-auto p-2 space-y-1">
                <div className="px-2 py-1 text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                    Historia sesji
                </div>
                {sessions.length > 0 ? (
                    sessions.map((session) => (
                        <button
                            key={session.id}
                            onClick={() => handleSwitchSession(session)}
                            className={`w-full text-left flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${
                                threadId === session.id
                                    ? "bg-accent text-accent-foreground"
                                    : "hover:bg-muted text-muted-foreground hover:text-foreground"
                            }`}
                        >
                            <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                            <span className="truncate flex-1" title={session.title}>{session.title}</span>
                        </button>
                    ))
                ) : (
                    <p className="text-xs text-muted-foreground px-2 py-4 text-center">
                        Brak zapisanych sesji
                    </p>
                )}
            </nav>
            <CorpusStatusPanel />
        </>
    );
}

export function Sidebar() {
    return (
        <aside className="hidden h-full w-64 shrink-0 flex-col border-r bg-muted/30 lg:flex">
            <SidebarContent />
        </aside>
    );
}
