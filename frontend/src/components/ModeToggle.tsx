"use client";
import { Switch } from "@/components/ui/switch";
import { useSession } from "@/hooks/useSession";
import { Badge } from "@/components/ui/badge";

export function ModeToggle() {
    const { mode, persistMode } = useSession();

    return (
        <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Autor</span>
            <Switch
                checked={mode === "shadow"}
                onCheckedChange={(checked) => persistMode(checked ? "shadow" : "author")}
                aria-label="Toggle mode"
            />
            <span className="text-xs text-muted-foreground">Cień</span>
            <Badge variant={mode === "author" ? "default" : "secondary"} className="text-xs ml-1">
                {mode === "author" ? "Autor" : "Cień"}
            </Badge>
        </div>
    );
}
