"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

type Mode = "login" | "register";

// Map raw Supabase errors to friendly, actionable copy.
function friendlyError(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("invalid login credentials")) {
    return "That email and password don't match. Check them and try again.";
  }
  if (lower.includes("email not confirmed")) {
    return "Please confirm your email first — check your inbox for the confirmation link.";
  }
  if (lower.includes("already registered")) {
    return "That email already has an account. Try logging in instead.";
  }
  if (lower.includes("at least 6 characters")) {
    return "Password must be at least 6 characters.";
  }
  return message;
}

export default function AuthForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!isSupabaseConfigured()) {
    return (
      <div role="alert" className="rounded-lg border border-amber-400 bg-amber-50 p-4 text-amber-900 dark:bg-amber-950 dark:text-amber-100">
        <h1 className="font-semibold">Sign-in unavailable</h1>
        <p className="mt-1 text-sm">
          Authentication isn&apos;t configured in this environment. Set{" "}
          <code>NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
          <code>NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY</code>.
        </p>
      </div>
    );
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const supabase = createClient();
      if (mode === "login") {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) {
          setError(friendlyError(error.message));
          return;
        }
        router.push(searchParams.get("redirect") ?? "/");
        router.refresh();
      } else {
        const { data, error } = await supabase.auth.signUp({ email, password });
        if (error) {
          setError(friendlyError(error.message));
          return;
        }
        if (data.session) {
          router.push(searchParams.get("redirect") ?? "/");
          router.refresh();
        } else {
          setNotice("Account created. Check your email for a confirmation link, then log in.");
          setMode("login");
        }
      }
    } catch {
      setError("Something went wrong reaching the sign-in service. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-bold">{mode === "login" ? "Log in" : "Create account"}</h1>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="email" className="text-sm font-medium">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border border-zinc-300 bg-transparent px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-1 dark:border-zinc-700"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="password" className="text-sm font-medium">
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            minLength={6}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded border border-zinc-300 bg-transparent px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-1 dark:border-zinc-700"
          />
        </div>

        {error && (
          <p role="alert" className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="rounded border border-green-300 bg-green-50 px-3 py-2 text-sm text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200">
            {notice}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="rounded bg-zinc-900 px-4 py-2 font-medium text-white hover:bg-zinc-700 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          {busy ? "Working…" : mode === "login" ? "Log in" : "Register"}
        </button>
      </form>

      <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">
        {mode === "login" ? (
          <>
            No account?{" "}
            <button
              type="button"
              onClick={() => {
                setMode("register");
                setError(null);
                setNotice(null);
              }}
              className="underline focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              Register
            </button>
          </>
        ) : (
          <>
            Already have an account?{" "}
            <button
              type="button"
              onClick={() => {
                setMode("login");
                setError(null);
                setNotice(null);
              }}
              className="underline focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              Log in
            </button>
          </>
        )}
      </p>
    </div>
  );
}
