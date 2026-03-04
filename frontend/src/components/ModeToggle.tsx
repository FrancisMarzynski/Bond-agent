"use client";
import { Switch } from "@/components/ui/switch";
import { useChatStore } from "@/store/chatStore";
import { Badge } from "@/components/ui/badge";

export function ModeToggle() {
    const { mode, setMode } = useChatStore();

    return (
        <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Author</span>
            <Switch
                checked={mode === "shadow"}
                onCheckedChange={(checked) => setMode(checked ? "shadow" : "author")}
                aria-label="Toggle mode"
            />
            <span className="text-xs text-muted-foreground">Shadow</span>
            <Badge variant={mode === "author" ? "default" : "secondary"} className="text-xs ml-1">
                {mode === "author" ? "Author" : "Shadow"}
            </Badge>
        </div>
    );
}
