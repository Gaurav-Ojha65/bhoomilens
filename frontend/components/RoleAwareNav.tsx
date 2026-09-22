"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchAuthSession, signOut } from "aws-amplify/auth";
import { getCurrentRole, AppRole } from "@/lib/roles";

export function RoleAwareNav() {
  const [role, setRole] = useState<AppRole>("USER");
  const [email, setEmail] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([getCurrentRole(), fetchAuthSession()])
      .then(([currentRole, session]) => {
        if (!active) return;
        setRole(currentRole);
        const claim = session.tokens?.idToken?.payload?.email;
        if (typeof claim === "string") setEmail(claim);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  async function logout() {
    await signOut();
    window.location.href = "/";
  }

  return (
    <nav className="text-sm flex items-center gap-5 flex-wrap justify-end">
      <Link href="/dashboard" className="hover:text-brand-100">Dashboard</Link>
      <Link href="/upload" className="hover:text-brand-100">Upload</Link>
      <Link href="/records" className="hover:text-brand-100">Records</Link>
      <Link href="/review-queue" className="hover:text-brand-100">Review Queue</Link>
      {role === "SUPERVISOR" && (
        <Link
          href="/supervisor"
          className="font-semibold text-white underline decoration-brand-200 underline-offset-4"
        >
          Supervisor
        </Link>
      )}
      <span className="hidden lg:inline text-brand-100" title={email || undefined}>
        {role}
      </span>
      <button
        type="button"
        onClick={logout}
        className="rounded border border-white/30 px-3 py-1.5 hover:bg-white/10"
      >
        Sign out
      </button>
    </nav>
  );
}
