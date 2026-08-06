import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import type { ReactNode } from "react";
import { Providers } from "@/lib/query-client";
import { ServiceWorkerRegistration } from "@/components/pwa/ServiceWorkerRegistration";
import "@/styles/globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: process.env.NEXT_PUBLIC_APP_NAME ?? "CONNECT.PH Clinic Platform",
  description: "Multi-tenant medical clinic management platform.",
  manifest: "/manifest.json",
  icons: [{ rel: "icon", url: "/icon.svg", type: "image/svg+xml" }],
};

// Phase 20 (item 13): baseline PWA installability metadata - `themeColor`
// belongs in `viewport`, not `metadata`, as of Next.js 15.
export const viewport: Viewport = {
  themeColor: "#2563eb",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans`}>
        <Providers>{children}</Providers>
        <ServiceWorkerRegistration />
      </body>
    </html>
  );
}
