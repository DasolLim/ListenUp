import type { Metadata } from "next";
import { Suspense } from "react";
import AuthForm from "@/components/AuthForm";

export const metadata: Metadata = { title: "Log in — ListenUp" };

export default function LoginPage() {
  return (
    <div className="mx-auto flex max-w-md flex-col justify-center pt-10">
      <div className="glass-card glass-strong p-8">
        <Suspense>
          <AuthForm />
        </Suspense>
      </div>
    </div>
  );
}
