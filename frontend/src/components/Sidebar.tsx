"use client";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { PlusCircle, MessageSquare } from "lucide-react";
import { useSession } from "@/hooks/useSession";

export function Sidebar() {
    const { threadId, newSession } = useSession();

    return (
        <aside className="w-64 h-full flex flex-col border-r bg-muted/30 shrink-0">
            <div className="p-4 flex items-center justify-between">
                <span className="font-semibold text-sm">Bond Agent</span>
                <Button variant="ghost" size="sm" onClick={newSession} title="New session">
                    <PlusCircle className="h-4 w-4" />
                </Button>
            </div>
            <Separator />
            <nav className="flex-1 overflow-y-auto p-2 space-y-1">
                {threadId ? (
                    <div className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-accent text-accent-foreground text-sm">
                        <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate font-mono text-xs">{threadId.slice(0, 12)}…</span>
                    </div>
                ) : (
                    <p className="text-xs text-muted-foreground px-2 py-4 text-center">
                        No active session
                    </p>
                )}
            </nav>
        </aside>
    );
}
