"use client";

import { useState } from "react";

/**
 * Minimal document viewer. Uses <img> for images. For PDFs it renders an
 * <iframe> to the presigned URL — the browser's built-in PDF viewer is
 * sufficient for reviewers and it saves us shipping react-pdf's worker.
 */
export function DocumentViewer({
  url,
  contentType,
}: {
  url?: string;
  contentType?: string;
}) {
  const [error, setError] = useState<string | null>(null);
  if (!url) return <div className="text-brand-400">No document available.</div>;

  const isPdf =
    contentType === "application/pdf" || /\.pdf(\?|$)/i.test(url);

  if (error) return <div className="text-risk-high text-sm">{error}</div>;

  if (isPdf) {
    return (
      <iframe
        src={url}
        className="w-full h-[720px] rounded border border-brand-100"
        title="Uploaded document"
      />
    );
  }
  return (
    <img
      src={url}
      alt="Uploaded document"
      className="w-full rounded border border-brand-100 object-contain max-h-[720px]"
      onError={() => setError("Failed to load image.")}
    />
  );
}
