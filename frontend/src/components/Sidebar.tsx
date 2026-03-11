"use client";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { PlusCircle, MessageSquare } from "lucide-react";
import { useSession } from "@/hooks/useSession";

export function Sidebar() {
    const { threadId, sessions, newSession, switchSession } = useSession();

    return (
        <aside className="w-64 h-full flex flex-col border-r bg-muted/30 shrink-0">
            <div className="p-4 flex items-center justify-between">
                <span className="font-semibold text-sm">Bond Agent</span>
                <Button variant="ghost" size="sm" onClick={newSession} title="Nowa sesja">
                    <PlusCircle className="h-4 w-4" />
                </Button>
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
                            onClick={() => switchSession(session.id)}
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
        </aside>
    );
}
