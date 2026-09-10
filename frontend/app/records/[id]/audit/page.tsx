"use client";

import Link from "next/link";
import useSWR from "swr";
import { api } from "@/lib/api";

export default function AuditPage({ params }: { params: { id: string } }) {
  const { data, error, isLoading } = useSWR(
    ["audit", params.id],
    () => api.audit(params.id),
  );

  return (
    <div className="space-y-6">
      <Link
        href={`/records/${params.id}`}
        className="text-xs underline text-brand-600"
      >
        ← Back to record
      </Link>
      <h1 className="text-2xl font-semibold">Audit history</h1>
      {error && <p className="text-risk-high">Failed to load: {String(error)}</p>}
      {isLoading && <p>Loading …</p>}
      {data && (
        <div className="card">
          {data.items.length === 0 ? (
            <p className="text-brand-400">No audit entries yet.</p>
          ) : (
            <ol className="divide-y divide-brand-100">
              {data.items.map((e, i) => (
                <li key={i} className="py-3 text-sm">
                  <div className="flex justify-between items-center">
                    <span className="font-mono text-xs text-brand-400">
                      {e.timestamp}
                    </span>
                    <span className="font-mono text-xs">{e.user}</span>
                  </div>
                  <div className="mt-1">
                    <strong>{e.action}</strong>
                    {e.field && (
                      <>
                        {" · "}
                        <span className="font-mono">{e.field}</span>: {" "}
                        <span className="text-risk-high">
                          {e.old_value ?? "–"}
                        </span>{" "}
                        →{" "}
                        <span className="text-risk-low">
                          {e.new_value ?? "–"}
                        </span>
                      </>
                    )}
                  </div>
                  {e.note && (
                    <div className="mt-1 text-xs text-brand-400">{e.note}</div>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
