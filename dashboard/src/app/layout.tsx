import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/layout/sidebar";
import Header from "@/components/layout/header";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Smart Signal Control Center",
  description: "Administrative dashboard for the IoT Emergency Signal Preemption System.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} font-sans antialiased h-screen overflow-hidden flex bg-dark-surface text-dark-text-main`}>
        {/* Persistent Shell Layout */}
        <Sidebar />

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <Header />
          <main className="flex-1 overflow-y-auto p-6 lg:p-8">
            <div className="mx-auto max-w-7xl h-full animate-in fade-in duration-500">
              {children}
            </div>
          </main>
        </div>
      </body>
    </html>
  );
}
