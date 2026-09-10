"use client";

import { useState } from "react";
import { ConfidenceBadge } from "./ConfidenceBadge";

export function FieldRow({
  label,
  fieldKey,
  value,
  confidence,
  editable,
  onSave,
}: {
  label: string;
  fieldKey: string;
  value?: string | number;
  confidence?: number;
  editable: boolean;
  onSave: (field: string, newValue: string | number) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value == null ? "" : String(value));
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    const isNumeric = typeof value === "number";
    const parsed: string | number = isNumeric ? Number(draft) : draft;
    try {
      await onSave(fieldKey, parsed);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid grid-cols-12 items-center gap-2 py-2 border-b border-brand-100 last:border-b-0">
      <div className="col-span-3 text-sm text-brand-400">{label}</div>
      <div className="col-span-6 font-mono text-sm">
        {editing ? (
          <input
            className="w-full rounded border border-brand-100 px-2 py-1 text-sm"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={saving}
          />
        ) : (
          <span>{value == null || value === "" ? "—" : String(value)}</span>
        )}
      </div>
      <div className="col-span-2">
        <ConfidenceBadge value={confidence} />
      </div>
      <div className="col-span-1 text-right">
        {editable && !editing && (
          <button
            className="text-xs underline text-brand-600 hover:text-brand-700"
            onClick={() => {
              setDraft(value == null ? "" : String(value));
              setEditing(true);
            }}
          >
            Edit
          </button>
        )}
        {editing && (
          <div className="flex gap-2 justify-end">
            <button
              className="text-xs text-risk-low font-semibold disabled:opacity-50"
              disabled={saving}
              onClick={save}
            >
              {saving ? "…" : "Save"}
            </button>
            <button
              className="text-xs text-brand-400"
              disabled={saving}
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
