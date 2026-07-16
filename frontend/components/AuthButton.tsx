"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

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
        className="flex items-center gap-1.5 rounded-full border border-zinc-300 px-3 py-1.5 hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-zinc-700 dark:hover:bg-zinc-900"
      >
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 12a5 5 0 1 0-5-5 5 5 0 0 0 5 5Zm0 2c-3.34 0-10 1.67-10 5v3h20v-3c0-3.33-6.66-5-10-5Z" />
        </svg>
        <span>Log in</span>
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <span className="max-w-40 truncate text-sm text-zinc-600 dark:text-zinc-400" title={email}>
        {email}
      </span>
      <button
        type="button"
        onClick={handleLogout}
        className="rounded-full border border-zinc-300 px-3 py-1.5 hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-zinc-700 dark:hover:bg-zinc-900"
      >
        Log out
      </button>
    </div>
  );
}
