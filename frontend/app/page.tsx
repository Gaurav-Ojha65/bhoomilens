import Link from "next/link";

export default function HomePage() {
  return (
    <div className="space-y-8">
      <section className="card">
        <h1 className="text-2xl font-semibold text-brand-700">
          BhoomiLens Reviewer Console
        </h1>
        <p className="mt-2 text-brand-400 max-w-2xl">
          Upload land records, watch them flow through the AWS ingestion
          pipeline, and review anything that isn&apos;t clean.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/dashboard" className="btn-primary">Go to dashboard</Link>
          <Link href="/upload" className="btn-secondary">Upload a document</Link>
          <Link href="/review-queue" className="btn-secondary">Open review queue</Link>
        </div>
      </section>

      <section className="card text-sm text-brand-400">
        <p>
          Reference data is <strong className="text-brand-700">synthetic</strong>.
          BhoomiLens never claims a document is authentic. When a record is
          consistent, the app links you to the correct state land-record portal
          for final verification.
        </p>
      </section>
    </div>
  );
}
