/** A small, dependable comparison: the unchanged start and end are trimmed on word boundaries, and what is left in the middle is shown as removed and added. */
export interface Diff { prefix: string; removed: string; added: string; suffix: string; changed: boolean }

export function diffText(before: string, after: string): Diff {
  if (before === after) return { prefix: before, removed: "", added: "", suffix: "", changed: false };
  const a = before.split(/(\s+)/);
  const b = after.split(/(\s+)/);
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) { endA--; endB--; }
  return { prefix: a.slice(0, start).join(""), removed: a.slice(start, endA).join(""), added: b.slice(start, endB).join(""), suffix: a.slice(endA).join(""), changed: true };
}

/** Replaces the first occurrence of `original` in `text`. Returns null when the passage is no longer there, so the caller can say so instead of guessing. */
export function replaceClaim(text: string, original: string, replacement: string): string | null {
  const at = text.indexOf(original);
  return at === -1 ? null : text.slice(0, at) + replacement + text.slice(at + original.length);
}
