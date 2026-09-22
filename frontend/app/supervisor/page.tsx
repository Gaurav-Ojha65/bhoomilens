"use client";

import Link from "next/link";
import useSWR from "swr";
import { api, DashboardMetrics, SupervisorUser } from "@/lib/api";
import { getCurrentRole } from "@/lib/roles";
import { useEffect, useState } from "react";

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wide text-brand-400">{label}</div>
      <div className="mt-2 text-3xl font-semibold text-brand-700">{value}</div>
    </div>
  );
}

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
  const { data: usersData, error: usersError } = useSWR<{ items: SupervisorUser[] }>(
    allowed ? "supervisor-users" : null,
    () => api.supervisorUsers(),
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

  if (error || usersError) {
    return <p className="text-risk-high">Failed to load supervision data: {String(error || usersError)}</p>;
  }
  if (isLoading || !data || !usersData) return <p>Loading supervision dashboard …</p>;

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
          Monitor application users through their uploaded-record activity and
          review the workload across BhoomiLens.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {statuses.map(([label, value]) => <StatCard key={label} label={label} value={value} />)}
      </div>

      <section className="card overflow-x-auto">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold">Users</h2>
            <p className="text-xs text-brand-400 mt-1">
              Activity derived from authenticated upload ownership in the records table.
            </p>
          </div>
          <span className="text-sm text-brand-400">{usersData.items.length} active users</span>
        </div>
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-brand-400 text-xs uppercase">
              <th className="pb-2 pr-4">User</th>
              <th className="pb-2 pr-4">Records</th>
              <th className="pb-2 pr-4">Needs review</th>
              <th className="pb-2 pr-4">High risk</th>
              <th className="pb-2 pr-4">Approved</th>
              <th className="pb-2 pr-4">Rejected</th>
              <th className="pb-2">Last activity</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-brand-100">
            {usersData.items.map((user) => (
              <tr key={user.email}>
                <td className="py-2 pr-4 font-medium">{user.email}</td>
                <td className="py-2 pr-4">{user.records}</td>
                <td className="py-2 pr-4">{user.needs_review}</td>
                <td className="py-2 pr-4">{user.high_risk}</td>
                <td className="py-2 pr-4">{user.approved}</td>
                <td className="py-2 pr-4">{user.rejected}</td>
                <td className="py-2 text-xs text-brand-400">
                  {user.last_activity?.slice(0, 19).replace("T", " ") ?? "–"}
                </td>
              </tr>
            ))}
            {usersData.items.length === 0 && (
              <tr><td colSpan={7} className="py-6 text-center text-brand-400">No uploaded user activity yet.</td></tr>
            )}
          </tbody>
        </table>
      </section>

      <div className="grid md:grid-cols-2 gap-6">
        <section className="card space-y-3">
          <h2 className="text-lg font-semibold">Supervision actions</h2>
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
                <span className="font-mono">{kind}</span><span className="font-semibold">{count}</span>
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
