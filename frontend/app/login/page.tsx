import type { Metadata } from "next";

export const metadata: Metadata = { title: "Log in — ListenUp" };

export default function LoginPage() {
  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-3xl font-bold">Log in</h1>
      <p className="mt-4 text-zinc-600 dark:text-zinc-300">
        Sign in and registration arrive in the next step (Supabase Auth).
      </p>
    </div>
  );
}
