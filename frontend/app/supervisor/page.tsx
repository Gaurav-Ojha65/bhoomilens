"use client";

import Link from "next/link";
import useSWR from "swr";
import { api, DashboardMetrics } from "@/lib/api";
import { getCurrentRole } from "@/lib/roles";
import { useEffect, useState } from "react";

export default function SupervisorPage() {
  const [allowed, setAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    getCurrentRole().then((role) => setAllowed(role === "SUPERVISOR")).catch(() => setAllowed(false));
  }, []);

  const { data, error, isLoading } = useSWR<DashboardMetrics>(
    allowed ? "supervisor-metrics" : null,
    () => api.dashboard(),
    { refreshInterval: 15000 },
  );

  if (allowed === null) return <p>Checking supervisor access …</p>;
  if (!allowed) {
    return (
      <div className="card space-y-3">
        <h1 className="text-xl font-semibold">Access denied</h1>
        <p className="text-brand-400">This area is available only to supervisors.</p>
        <Link href="/dashboard" className="btn-primary inline-block">Back to dashboard</Link>
      </div>
    );
  }

  if (error) return <p className="text-risk-high">Failed to load supervision data: {String(error)}</p>;
  if (isLoading || !data) return <p>Loading supervision dashboard …</p>;

  const statuses = [
    ["Total records", data.total_documents],
    ["Needs review", data.needs_review],
    ["High risk", data.high_risk],
    ["Pending", data.pending],
    ["Rejected", data.rejected],
    ["Human approved", data.human_approved],
  ] as const;

  return (
    <div className="space-y-8">
      <div>
        <div className="text-xs uppercase tracking-wide text-brand-400">Supervisor console</div>
        <h1 className="text-2xl font-semibold mt-1">User & Record Supervision</h1>
        <p className="mt-2 text-sm text-brand-400 max-w-2xl">
          Review the live application workload and jump into records requiring
          human attention. Existing BhoomiLens processing remains unchanged.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {statuses.map(([label, value]) => (
          <div className="card" key={label}>
            <div className="text-xs uppercase tracking-wide text-brand-400">{label}</div>
            <div className="mt-2 text-3xl font-semibold text-brand-700">{value}</div>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <section className="card space-y-3">
          <h2 className="text-lg font-semibold">Supervision actions</h2>
          <p className="text-sm text-brand-400">
            Supervisors can inspect the same records available to the application
            and focus on flagged work.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/records" className="btn-secondary">All records</Link>
            <Link href="/review-queue" className="btn-secondary">Review queue</Link>
          </div>
        </section>

        <section className="card space-y-3">
          <h2 className="text-lg font-semibold">Validation workload</h2>
          <ul className="text-sm divide-y divide-brand-100">
            {Object.entries(data.validation_issues).slice(0, 8).map(([kind, count]) => (
              <li key={kind} className="py-2 flex justify-between">
                <span className="font-mono">{kind}</span>
                <span className="font-semibold">{count}</span>
              </li>
            ))}
            {Object.keys(data.validation_issues).length === 0 && (
              <li className="py-2 text-brand-400">No validation issues recorded.</li>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}
