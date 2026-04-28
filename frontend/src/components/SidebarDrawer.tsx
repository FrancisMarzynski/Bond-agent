"use client";
import { useEffect, useState } from "react";
import { Menu, PlusCircle, X } from "lucide-react";
import { SidebarContent } from "@/components/Sidebar";
import { Button } from "@/components/ui/button";

export function SidebarDrawer() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={() => setOpen(true)}
        aria-label="Otwórz panel boczny"
      >
        <Menu className="h-4 w-4" />
      </Button>

      {open && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <button
            type="button"
            aria-label="Zamknij panel boczny"
            className="absolute inset-0 bg-background/70 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <aside className="relative z-10 flex h-full w-[min(20rem,calc(100vw-1.5rem))] max-w-full flex-col border-r bg-background shadow-xl">
            <SidebarContent
              onNavigate={() => setOpen(false)}
              renderHeaderActions={({ handleNewSession }) => (
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleNewSession}
                    title="Nowa sesja"
                  >
                    <PlusCircle className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setOpen(false)}
                    title="Zamknij panel"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              )}
            />
          </aside>
        </div>
      )}
    </>
  );
}
