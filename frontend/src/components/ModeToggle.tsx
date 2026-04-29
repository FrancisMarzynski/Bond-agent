"use client";
import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Switch } from "@/components/ui/switch";
import { useSession } from "@/hooks/useSession";
import { Badge } from "@/components/ui/badge";

export function ModeToggle() {
    const { persistMode, newSession } = useSession();
    const router = useRouter();
    const pathname = usePathname();

    const isShadow = pathname === "/shadow";

    // Synchronizuje chatStore.mode z aktualną ścieżką (np. nawigacja wstecz/przód, bookmark)
    useEffect(() => {
        persistMode(isShadow ? "shadow" : "author");
    }, [isShadow]); // eslint-disable-line react-hooks/exhaustive-deps

    const handleToggle = (checked: boolean) => {
        if (checked === isShadow) {
            return;
        }

        // Tryby Author i Shadow nie współdzielą aktywnego workspace'u.
        // Przełączenie czyści bieżący stan widoku, a stare sesje zostają
        // dostępne z historii po lewej stronie.
        newSession();
        persistMode(checked ? "shadow" : "author");
        router.push(checked ? "/shadow" : "/");
    };

    return (
        <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Autor</span>
            <Switch
                checked={isShadow}
                onCheckedChange={handleToggle}
                aria-label="Przełącz tryb"
            />
            <span className="text-xs text-muted-foreground">Cień</span>
            <Badge variant={isShadow ? "secondary" : "default"} className="text-xs ml-1">
                {isShadow ? "Cień" : "Autor"}
            </Badge>
        </div>
    );
}
