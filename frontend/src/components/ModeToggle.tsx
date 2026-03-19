"use client";
import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Switch } from "@/components/ui/switch";
import { useSession } from "@/hooks/useSession";
import { Badge } from "@/components/ui/badge";

export function ModeToggle() {
    const { persistMode } = useSession();
    const router = useRouter();
    const pathname = usePathname();

    const isShadow = pathname === "/shadow";

    // Synchronizuje chatStore.mode z aktualną ścieżką (np. nawigacja wstecz/przód, bookmark)
    useEffect(() => {
        persistMode(isShadow ? "shadow" : "author");
    }, [isShadow]); // eslint-disable-line react-hooks/exhaustive-deps

    const handleToggle = (checked: boolean) => {
        persistMode(checked ? "shadow" : "author");
        router.push(checked ? "/shadow" : "/");
    };

    return (
        <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Autor</span>
            <Switch
                checked={isShadow}
                onCheckedChange={handleToggle}
                aria-label="Toggle mode"
            />
            <span className="text-xs text-muted-foreground">Cień</span>
            <Badge variant={isShadow ? "secondary" : "default"} className="text-xs ml-1">
                {isShadow ? "Cień" : "Autor"}
            </Badge>
        </div>
    );
}
