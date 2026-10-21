"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard");
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-page">
      <div className="text-center">
        <div className="h-8 w-8 border-4 border-brand border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="mt-4 text-fg-3">Redirecting to dashboard...</p>
      </div>
    </div>
  );
}
