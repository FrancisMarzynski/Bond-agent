/**
 * SessionProvider — montowany w root layout.
 * Odpowiada za:
 *  1. Odczyt thread_id z sessionStorage przy starcie
 *  2. Pobranie historii sesji z backendu (GET /api/chat/history/{thread_id})
 *  3. Zasilenie magazynu Zustand (messages, draft, stage, hitlPause)
 *
 * Renderuje children dopiero po zakończeniu przywracania stanu (isRestoring = false),
 * dzięki czemu UI nie miga z pustym stanem przy odświeżeniu strony.
 */
"use client";
import { useSession } from "@/hooks/useSession";

export function SessionProvider({ children }: { children: React.ReactNode }) {
    const { isRestoring } = useSession();

    if (isRestoring) {
        // Minimalistyczny placeholder — blokuje render dzieci do czasu przywrócenia stanu
        return (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                <span>Ładowanie sesji…</span>
            </div>
        );
    }

    return <>{children}</>;
}
