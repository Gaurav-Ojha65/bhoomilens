"use client";

import Link from "next/link";
import useSWR from "swr";
import { useState } from "react";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";

const STATUSES = [
  "",
  "PENDING",
  "AUTO_APPROVED",
  "HUMAN_APPROVED",
  "NEEDS_REVIEW",
  "HIGH_RISK",
  "REJECTED",
];

export default function RecordsPage() {
  const [status, setStatus] = useState("");
  const { data, error, isLoading } = useSWR(["records", status], () =>
    api.listRecords(status || undefined),
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Records</h1>
        <select
          className="rounded border border-brand-100 px-3 py-2 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s ? s.replace(/_/g, " ") : "All statuses"}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="text-risk-high">Failed to load: {String(error)}</p>}
      {isLoading && <p>Loading …</p>}
      {data && (
        <div className="card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-brand-400 text-xs uppercase">
                <th className="pb-2 pr-3">Record</th>
                <th className="pb-2 pr-3">Owner</th>
                <th className="pb-2 pr-3">Khasra</th>
                <th className="pb-2 pr-3">Village</th>
                <th className="pb-2 pr-3">State</th>
                <th className="pb-2 pr-3">Status</th>
                <th className="pb-2 pr-3">Confidence</th>
                <th className="pb-2 pr-3">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-100">
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-brand-400">
                    No records.
                  </td>
                </tr>
              )}
              {data.items.map((r) => (
                <tr key={r.record_id} className="hover:bg-brand-50">
                  <td className="py-2 pr-3 font-mono text-xs">
                    <Link href={`/records/${r.record_id}`} className="underline">
                      {r.record_id.slice(0, 22)}…
                    </Link>
                  </td>
                  <td className="py-2 pr-3">{r.owner_name ?? "–"}</td>
                  <td className="py-2 pr-3 font-mono">{r.khasra_number ?? "–"}</td>
                  <td className="py-2 pr-3">{r.village ?? "–"}</td>
                  <td className="py-2 pr-3">{r.state ?? "–"}</td>
                  <td className="py-2 pr-3">
                    <StatusBadge status={r.validation_status} />
                  </td>
                  <td className="py-2 pr-3">
                    <ConfidenceBadge value={r.overall_confidence} />
                  </td>
                  <td className="py-2 pr-3 text-xs text-brand-400">
                    {r.updated_at?.slice(0, 19).replace("T", " ") ?? "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
