import { ValidationFlag } from "@/lib/api";

export function ValidationFlagsList({ flags }: { flags: ValidationFlag[] }) {
  if (!flags?.length) {
    return (
      <div className="text-sm text-risk-low">
        No validation issues detected against the reference registry.
      </div>
    );
  }
  return (
    <ul className="space-y-3">
      {flags.map((f, i) => (
        <li
          key={`${f.issue_type}-${i}`}
          className="rounded-md border border-brand-100 bg-white p-3"
        >
          <div className="flex items-center justify-between">
            <span className={`font-mono text-sm severity-${f.severity}`}>
              {f.issue_type}
            </span>
            <span className={`text-xs uppercase severity-${f.severity}`}>
              {f.severity}
            </span>
          </div>
          <p className="mt-1 text-sm text-brand-700">{f.message}</p>
          {(f.expected !== undefined || f.observed !== undefined) && (
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs font-mono">
              <div>
                <div className="text-brand-400">expected</div>
                <div>
                  {String(f.expected ?? "–")}
                  {f.expected_unit ? ` ${f.expected_unit}` : ""}
                </div>
              </div>
              <div>
                <div className="text-brand-400">observed</div>
                <div>
                  {String(f.observed ?? "–")}
                  {f.observed_unit ? ` ${f.observed_unit}` : ""}
                </div>
              </div>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
