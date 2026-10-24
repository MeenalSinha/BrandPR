"use client";
import { useMemo, useState } from "react";

import { Field, Notice } from "@/components/ui";
import { useBrand } from "@/components/providers";
import { api, ApiError, errorMessage } from "@/lib/api";
import { diffText, replaceClaim } from "@/lib/diff";
import { FINDING_LABELS, SEVERITY_LABELS } from "@/lib/format";
import type { ContentItem, CorrectionInput, Finding, Suggestion } from "@/types/api";

type Tracked = CorrectionInput & { suggestionText?: string | null };

/**
 * Corrects a revision by writing the NEXT revision. The original text stays untouched on the left; nothing is saved until
 * "Save as new revision". An AI suggestion is only a proposal: it changes the draft only when the person presses Accept.
 */
export function RevisionEditor({ base, findings, onSaved, onCancel, onConflict }: {
  base: ContentItem; findings: Finding[]; onSaved: (item: ContentItem) => void; onCancel: () => void; onConflict: (latestId: string | null) => void;
}) {
  const { actor } = useBrand();
  const [title, setTitle] = useState(base.title);
  const [text, setText] = useState(base.content);
  const [note, setNote] = useState("");
  const [tracked, setTracked] = useState<Record<string, Tracked>>({});
  const [suggestions, setSuggestions] = useState<Record<string, Suggestion>>({});
  const [manual, setManual] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const actionable = findings.filter((f) => f.status !== "supported");
  const diff = useMemo(() => diffText(base.content, text), [base.content, text]);
  const unchanged = text === base.content && title.trim() === base.title;
  const say = (id: string, m: string) => setMessages((x) => ({ ...x, [id]: m }));

  async function suggest(f: Finding) {
    setBusyId(f.id);
    say(f.id, "");
    try {
      const s = await api.suggestCorrection(f.id);
      setSuggestions((x) => ({ ...x, [f.id]: s }));
    } catch (e) {
      say(f.id, errorMessage(e));
    } finally {
      setBusyId(null);
    }
  }

  function accept(f: Finding, s: Suggestion) {
    if (!s.replacement_text) return;
    const next = replaceClaim(text, f.claim_text, s.replacement_text);
    if (next === null) return say(f.id, "This claim is no longer in your draft, so the suggestion cannot be applied. Edit the text directly.");
    setText(next);
    setTracked((t) => ({ ...t, [f.id]: { finding_id: f.id, decision: "accepted", source: "ai", original_text: f.claim_text, replacement_text: s.replacement_text } }));
    setSuggestions((x) => { const { [f.id]: _gone, ...rest } = x; return rest; });
    say(f.id, "Suggestion applied to your draft. You can still edit it.");
  }

  function reject(f: Finding, s: Suggestion) {
    setTracked((t) => ({ ...t, [f.id]: { finding_id: f.id, decision: "rejected", source: "ai", original_text: f.claim_text, replacement_text: null } }));
    setSuggestions((x) => { const { [f.id]: _gone, ...rest } = x; return rest; });
    say(f.id, "Suggestion rejected. Your draft is unchanged.");
    void s;
  }

  function applyManual(f: Finding) {
    const replacement = (manual[f.id] ?? "").trim();
    if (!replacement) return say(f.id, "Type the replacement wording first.");
    const next = replaceClaim(text, f.claim_text, replacement);
    if (next === null) return say(f.id, "This claim is no longer in your draft. Edit the text directly.");
    setText(next);
    setTracked((t) => ({ ...t, [f.id]: { finding_id: f.id, decision: "manual", source: "manual", original_text: f.claim_text, replacement_text: replacement } }));
    say(f.id, "Replacement applied to your draft.");
  }

  async function save() {
    setSaving(true);
    setError(null);
    // An accepted suggestion that the person then edited is recorded as "modified".
    const corrections = Object.values(tracked).map(({ suggestionText: _s, ...c }) =>
      c.decision === "accepted" && c.replacement_text && !text.includes(c.replacement_text) ? { ...c, decision: "modified" as const } : c);
    try {
      const item = await api.createRevision(base.id, { title: title.trim() !== base.title ? title.trim() : null, content: text, change_note: note.trim() || null, corrections });
      onSaved(item);
    } catch (e) {
      if (e instanceof ApiError && e.code === "revision_conflict") {
        setError(`${e.message} Your text is still in this editor.`);
        onConflict(e.details.find((d) => d.field === "latest_revision_id")?.message ?? null);
      } else if (e instanceof ApiError && e.code === "actor_required") {
        setError("Enter your name in the sidebar first. Revisions record who made them.");
      } else setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-label="Revision editor" className="space-y-5 border border-signal bg-sheet p-5">
      <header>
        <h2 className="text-xl font-semibold">Correct as revision {base.revision_number + 1}</h2>
        <p className="text-sm text-ink-soft">Revision {base.revision_number} is kept exactly as it is. Your changes are saved as a new revision that must be reviewed and approved on its own.</p>
      </header>
      {!actor.trim() && <Notice kind="warning">Enter your name in the sidebar before saving. Revisions record who made them.</Notice>}
      {error && <Notice kind="error">{error}</Notice>}

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="label">Original (revision {base.revision_number}, read only)</p>
          <p data-testid="original-text" className="whitespace-pre-wrap border border-rule bg-paper p-3 font-serif text-[16px] leading-relaxed">{base.content}</p>
        </div>
        <Field label={`Your revision (revision ${base.revision_number + 1})`} htmlFor="rev-text" hint={`${text.length.toLocaleString()} characters`}>
          <textarea id="rev-text" className="input font-serif" rows={9} value={text} onChange={(e) => setText(e.target.value)} />
        </Field>
      </div>

      <div data-testid="diff" aria-label="Changes">
        <p className="label">What changed</p>
        {!diff.changed ? <p className="text-sm text-ink-soft">No changes yet.</p> : (
          <p className="whitespace-pre-wrap border border-rule p-3 font-serif text-[16px] leading-relaxed">
            {diff.prefix}{diff.removed && <del data-testid="diff-removed" className="bg-state-expired-wash text-state-expired">{diff.removed}</del>}{diff.added && <ins data-testid="diff-added" className="bg-state-current-wash text-state-current no-underline">{diff.added}</ins>}{diff.suffix}
          </p>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Title" htmlFor="rev-title"><input id="rev-title" className="input" value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="What did you change and why?" htmlFor="rev-note" hint="Optional. Shown in the revision history."><input id="rev-note" className="input" value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} /></Field>
      </div>

      <div>
        <h3 className="text-lg font-semibold">Findings to address ({actionable.length})</h3>
        {actionable.length === 0 && <p className="text-sm text-ink-soft">The latest review of this revision has no open findings. You can still edit the text.</p>}
        <ul className="mt-2 space-y-3">
          {actionable.map((f) => {
            const s = suggestions[f.id];
            const cited = f.evidence.filter((e) => e.role !== "related_source");
            return (
              <li key={f.id} data-testid="correction-finding" className="space-y-3 border border-rule bg-paper p-4">
                <p><strong>{FINDING_LABELS[f.status]}</strong> &middot; {SEVERITY_LABELS[f.severity]}{tracked[f.id] ? ` · ${tracked[f.id].decision}` : ""}</p>
                <p className="font-serif text-lg">&ldquo;{f.claim_text}&rdquo;</p>
                <p className="text-sm">{f.explanation}</p>
                {f.recommended_action && <p className="text-sm"><strong>Suggested action:</strong> {f.recommended_action}</p>}
                {cited.length ? cited.map((e) => (
                  <blockquote key={e.id} data-testid="correction-evidence" className="border-l-2 border-rule-strong pl-3 text-sm">
                    <strong>{e.fact_name}:</strong> {e.fact_value}{e.fact_qualifications ? ` (${e.fact_qualifications})` : ""}
                    {e.excerpt && <span className="block font-serif">{e.excerpt}</span>}
                    {e.source_title && <span className="block text-ink-soft">{e.source_title}{e.source_page ? `, page ${e.source_page}` : ""}</span>}
                  </blockquote>
                )) : <p className="text-sm font-bold text-state-unapproved">No approved evidence backs this claim. Edit or remove it, or ask the fact owner to approve a fact.</p>}

                <div className="flex flex-wrap items-end gap-3">
                  <button className="btn btn-secondary" disabled={busyId === f.id} onClick={() => suggest(f)}>{busyId === f.id ? "Asking" : "Suggest wording (AI)"}</button>
                  <div className="min-w-[14rem] flex-1">
                    <label className="label" htmlFor={`manual-${f.id}`}>Or write the replacement yourself</label>
                    <div className="flex gap-2">
                      <input id={`manual-${f.id}`} className="input" value={manual[f.id] ?? ""} onChange={(e) => setManual((m) => ({ ...m, [f.id]: e.target.value }))} />
                      <button className="btn btn-secondary" onClick={() => applyManual(f)}>Replace claim</button>
                    </div>
                  </div>
                </div>
                {messages[f.id] && <p role="status" data-testid="correction-message" className="text-sm font-bold">{messages[f.id]}</p>}
                {s && (
                  <div data-testid="suggestion" className="space-y-2 border-l-4 border-signal bg-signal-wash p-3">
                    <p className="text-sm font-bold">Proposed by AI. A person must check it against the evidence.</p>
                    {s.replacement_text ? (
                      <p className="font-serif text-lg"><del className="text-state-expired">{s.original_text}</del> <ins className="text-state-current no-underline">{s.replacement_text}</ins></p>
                    ) : <p>No safe replacement could be proposed. {s.cannot_suggest_reason}</p>}
                    {s.rationale && <p className="text-sm">{s.rationale}</p>}
                    {s.warnings.map((w) => <p key={w} className="text-sm font-bold text-state-unapproved">{w}</p>)}
                    <div className="flex gap-2">
                      <button className="btn btn-primary" disabled={!s.replacement_text} onClick={() => accept(f, s)}>Accept suggestion</button>
                      <button className="btn btn-secondary" onClick={() => reject(f, s)}>Reject suggestion</button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      <div className="flex flex-wrap gap-3">
        <button className="btn btn-primary" disabled={saving || unchanged || !text.trim()} onClick={save}>{saving ? "Saving" : "Save as new revision"}</button>
        <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        {unchanged && <p className="self-center text-sm text-ink-soft">Change the text or title to save a revision.</p>}
      </div>
    </section>
  );
}
