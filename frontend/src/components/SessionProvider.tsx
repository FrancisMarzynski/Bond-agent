/**
 * SessionProvider — montowany w root layout.
 *
 * Jest jedynym właścicielem logiki bootstrap sesji przy starcie:
 *  1. Odczyt thread_id i mode z sessionStorage
 *  2. Pobranie historii sesji z backendu (GET /api/chat/history/{thread_id})
 *  3. Zasilenie magazynów Zustand (messages, draft, stage, hitlPause, itp.)
 *  4. Polling historii gdy sesja jest w stanie "running" (committed disconnect recovery)
 *
 * Renderuje children dopiero po zakończeniu pierwszego przywrócenia stanu
 * (isRestoring = false), dzięki czemu UI nie miga z pustym stanem przy odświeżeniu.
 *
 * Żaden inny komponent nie powinien wywoływać logiki restore — useSession()
 * nie wywołuje już /history automatycznie przy każdym mount.
 */
"use client";
import { useSessionBootstrap } from "@/hooks/useSessionBootstrap";

export function SessionProvider({ children }: { children: React.ReactNode }) {
    const { isRestoring } = useSessionBootstrap();

    if (isRestoring) {
        return (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                <span>Ładowanie sesji…</span>
            </div>
        );
    }

    return <>{children}</>;
}
