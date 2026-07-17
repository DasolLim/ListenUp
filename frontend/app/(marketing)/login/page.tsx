import type { Metadata } from "next";
import { Suspense } from "react";
import AuthForm from "@/components/AuthForm";

export const metadata: Metadata = { title: "Log in — ListenUp" };

export default function LoginPage() {
  return (
    <div className="mx-auto max-w-sm">
      <Suspense>
        <AuthForm />
      </Suspense>
    </div>
  );
}
