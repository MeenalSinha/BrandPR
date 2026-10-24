import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-16">
      <h1 className="text-3xl font-semibold">Page not found</h1>
      <p className="mt-2 text-ink-soft">That address does not exist. <Link className="font-bold text-signal underline" href="/knowledge">Go to Brand knowledge</Link>.</p>
    </div>
  );
}
