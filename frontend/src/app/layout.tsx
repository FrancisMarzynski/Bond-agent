import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { ModeToggle } from "@/components/ModeToggle";
import { SessionProvider } from "@/components/SessionProvider";

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
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <header className="h-14 border-b flex items-center px-4 justify-between shrink-0">
            <span className="font-medium text-sm text-muted-foreground">Panel sterowania</span>
            <ModeToggle />
          </header>
          <main className="flex-1 overflow-hidden flex flex-col">
            <div className="flex-1 flex flex-col overflow-hidden min-h-0">
              <SessionProvider>
                {children}
              </SessionProvider>
            </div>
          </main>
        </div>
      </body>
    </html>
  );
}
