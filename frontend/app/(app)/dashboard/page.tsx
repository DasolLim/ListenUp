import type { Metadata } from "next";

export const metadata: Metadata = { title: "Dashboard — ListenUp" };

// Center + right-rail content lands in Steps 1.5.4 / 1.5.5.
export default function DashboardPage() {
  return (
    <p className="text-ink-soft">Your tools appear here.</p>
  );
}
