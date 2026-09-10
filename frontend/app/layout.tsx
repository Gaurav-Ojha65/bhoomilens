import type { Metadata } from "next";
import "./globals.css";
import { AmplifyProvider } from "@/components/AmplifyProvider";
import Link from "next/link";

export const metadata: Metadata = {
  title: "BhoomiLens",
  description:
    "AI-Powered Land Record Digitization, Validation & Verification Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AmplifyProvider>
          <header className="bg-brand-700 text-white">
            <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
              <Link href="/" className="text-lg font-semibold tracking-tight">
                BhoomiLens
              </Link>
              <nav className="text-sm flex gap-6">
                <Link href="/dashboard" className="hover:text-brand-100">
                  Dashboard
                </Link>
                <Link href="/upload" className="hover:text-brand-100">
                  Upload
                </Link>
                <Link href="/records" className="hover:text-brand-100">
                  Records
                </Link>
                <Link href="/review-queue" className="hover:text-brand-100">
                  Review Queue
                </Link>
              </nav>
            </div>
          </header>
          <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
          <footer className="max-w-7xl mx-auto px-6 py-6 text-xs text-brand-400">
            BhoomiLens — prototype. Reference data is synthetic. Final
            verification must happen on the official state land-record portal.
          </footer>
        </AmplifyProvider>
      </body>
    </html>
  );
}
