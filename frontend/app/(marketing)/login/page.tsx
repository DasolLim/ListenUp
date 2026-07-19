import type { Metadata } from "next";
import { Suspense } from "react";
import AuthForm from "@/components/AuthForm";
import Orb from "@/components/ui/Orb";

export const metadata: Metadata = { title: "Log in — ListenUp" };

export default function LoginPage() {
  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center gap-6 px-5 pb-20 pt-16 sm:pt-20">
      <Orb size="lg" />
      <p className="max-w-xs text-center leading-relaxed text-ink-soft">
        Sign in to open live captions, voice profiles, and translation.
      </p>
      <div className="glass-card glass-strong w-full p-8">
        <Suspense>
          <AuthForm />
        </Suspense>
      </div>
    </div>
  );
}
