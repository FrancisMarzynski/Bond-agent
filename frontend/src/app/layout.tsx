import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { SidebarDrawer } from "@/components/SidebarDrawer";
import { ModeToggle } from "@/components/ModeToggle";
import { SessionProvider } from "@/components/SessionProvider";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Bond Agent",
  description: "AI editorial assistant",
};


export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pl">
      <body className={`${inter.className} flex h-screen overflow-hidden bg-background`}>
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <header className="shrink-0 border-b">
            <div className="flex min-h-14 items-center justify-between gap-3 px-3 sm:px-4">
              <div className="flex min-w-0 items-center gap-2">
                <SidebarDrawer />
                <span className="font-medium text-sm text-muted-foreground">Panel sterowania</span>
              </div>
              <ModeToggle />
            </div>
          </header>
          <main className="flex flex-1 flex-col overflow-hidden">
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <ErrorBoundary>
                <SessionProvider>{children}</SessionProvider>
              </ErrorBoundary>
            </div>
          </main>
        </div>
      </body>
    </html>
  );
}
