"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { UserIcon } from "@/components/shell/icons";

// Client-only auth status. Renders the logged-out state until the session is
// known so the server and first client render always match (no hydration mismatch).
export default function AuthButton() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!isSupabaseConfigured()) return;
    const supabase = createClient();

    supabase.auth.getClaims().then(({ data }) => {
      setEmail((data?.claims?.email as string | undefined) ?? null);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user?.email ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  async function handleLogout() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/");
    router.refresh();
  }

  if (!email) {
    return (
      <Link
        href="/login"
        aria-label="Log in or register"
        className="btn-primary flex items-center gap-1.5 rounded-full px-4 py-1.5 text-[15px] font-semibold text-on-accent"
      >
        <UserIcon />
        <span>Log in</span>
      </Link>
    );
  }

  return (
    <span className="flex items-center gap-2">
      <Link
        href="/dashboard"
        className="rounded-full px-3 py-1.5 text-[15px] font-medium text-ink-soft transition-colors hover:bg-white/50 hover:text-ink"
      >
        Dashboard
      </Link>
      <button
        type="button"
        onClick={handleLogout}
        className="btn-ghost rounded-full px-4 py-1.5 text-[15px] font-medium text-ink"
      >
        Log out
      </button>
    </span>
  );
}
