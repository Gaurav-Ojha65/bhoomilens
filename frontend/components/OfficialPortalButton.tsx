export function OfficialPortalButton({
  portal,
}: {
  portal?: { label?: string; url?: string; state?: string; cadastral_map_url?: string | null };
}) {
  if (!portal?.url) {
    return (
      <div className="text-xs text-brand-400">
        No official portal mapped for this state.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <a
        href={portal.url}
        target="_blank"
        rel="noopener noreferrer"
        className="btn-primary"
      >
        Open Official Land Record Portal
        {portal.label ? ` — ${portal.label}` : ""}
      </a>
      {portal.cadastral_map_url && (
        <a
          href={portal.cadastral_map_url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-secondary block w-fit"
        >
          Open Cadastral Map
        </a>
      )}
      <p className="text-xs text-brand-400 max-w-md">
        Official-source verification. Use the government portal to perform the
        final manual verification. BhoomiLens does not claim the document is
        authentic.
      </p>
    </div>
  );
}
