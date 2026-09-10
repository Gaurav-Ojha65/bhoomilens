export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-${status}`}>{status.replace(/_/g, " ")}</span>;
}
