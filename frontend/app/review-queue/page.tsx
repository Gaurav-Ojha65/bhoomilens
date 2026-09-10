"use client";

import Link from "next/link";
import useSWR from "swr";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";

export default function ReviewQueuePage() {
  const { data, error, isLoading } = useSWR("review-queue", () => api.reviewQueue(), {
    refreshInterval: 10000,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Review queue</h1>
      <p className="text-sm text-brand-400 max-w-xl">
        Records with <code>NEEDS_REVIEW</code> or <code>HIGH_RISK</code> status,
        oldest first.
      </p>

      {error && <p className="text-risk-high">Failed to load: {String(error)}</p>}
      {isLoading && <p>Loading …</p>}
      {data && (
        <div className="grid gap-3">
          {data.items.length === 0 && (
            <div className="card text-brand-400">
              Nothing in the queue right now.
            </div>
          )}
          {data.items.map((r) => (
            <Link
              key={r.record_id}
              href={`/records/${r.record_id}`}
              className="card hover:ring-brand-400 transition"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs font-mono text-brand-400">
                    {r.record_id}
                  </div>
                  <div className="mt-1 text-sm">
                    <strong>{r.owner_name ?? "–"}</strong> · Khasra{" "}
                    <span className="font-mono">{r.khasra_number ?? "–"}</span> · {r.village ?? "–"}, {r.state ?? "–"}
                  </div>
                  <div className="mt-2 flex gap-4 items-center">
                    <StatusBadge status={r.validation_status} />
                    <ConfidenceBadge value={r.overall_confidence} />
                    {r.validation_flags?.length > 0 && (
                      <span className="text-xs text-risk-medium">
                        {r.validation_flags.length} issue
                        {r.validation_flags.length === 1 ? "" : "s"}
                      </span>
                    )}
                  </div>
                </div>
                <span className="btn-secondary">Open</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
