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
      <div role="alert" className="rounded-xl border border-warning bg-white/70 p-4 text-ink">
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
      <h1 className="text-center font-display text-[28px] font-bold">{mode === "login" ? "Log in" : "Create account"}</h1>

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
            className="glass-strong rounded-xl border border-white/60 px-3.5 py-2.5 text-ink shadow-glass outline-none placeholder:text-ink-faint"
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
            className="glass-strong rounded-xl border border-white/60 px-3.5 py-2.5 text-ink shadow-glass outline-none placeholder:text-ink-faint"
          />
        </div>

        {error && (
          <p role="alert" className="rounded-xl border border-error bg-white/70 px-3.5 py-2.5 text-sm text-error-strong">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="rounded-xl border border-success bg-white/70 px-3.5 py-2.5 text-sm text-ink">
            {notice}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="btn-primary rounded-full px-5 py-2.5 font-semibold text-on-accent transition-transform hover:-translate-y-0.5 disabled:opacity-50 disabled:hover:translate-y-0"
        >
          {busy ? "Working…" : mode === "login" ? "Log in" : "Register"}
        </button>
      </form>

      <p className="mt-5 text-sm text-ink-soft">
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
