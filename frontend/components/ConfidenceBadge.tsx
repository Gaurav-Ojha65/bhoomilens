export function ConfidenceBadge({ value }: { value?: number }) {
  if (value == null) return <span className="text-brand-400">–</span>;
  const pct = value <= 1 ? value * 100 : value;
  const tone =
    pct >= 90 ? "text-risk-low" : pct >= 70 ? "text-risk-medium" : "text-risk-high";
  const label = pct >= 90 ? "OK" : pct >= 70 ? "review" : "low";
  return (
    <span className={`text-xs font-mono ${tone}`}>
      {pct.toFixed(0)}% <span className="uppercase tracking-wide">{label}</span>
    </span>
  );
}
