"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

/**
 * Task #8: a plain text input with a filtered, click-to-fill suggestion
 * list underneath - type-to-search, select one, or just keep typing a
 * custom value (never restricted to the list). Generalized from this
 * file's earlier medicine-only suggestion dropdown so the same control
 * works for Dosage/Frequency/Route/Duration/Strength/Form without
 * duplicating the dropdown UI in each place.
 *
 * Task #2: `multiline` renders a textarea instead (the SOAP fields). The
 * suggestions are then matched against - and a selection replaces - only the
 * LINE the caret is on, so the rest of the text is preserved and the field
 * stays fully editable. Single-line behaviour is unchanged.
 *
 * Purely a data-entry convenience - `suggestions` is never treated as an
 * authoritative or clinically-approved list (see
 * `lib/prescription-vocabulary.ts`).
 */

/** The line of `value` that contains `caret`: [start, end) plus its text. */
export function currentLine(value: string, caret: number): { start: number; end: number; text: string } {
  const at = Math.max(0, Math.min(caret, value.length));
  const start = at === 0 ? 0 : value.lastIndexOf("\n", at - 1) + 1;
  const nl = value.indexOf("\n", at);
  const end = nl === -1 ? value.length : nl;
  return { start, end, text: value.slice(start, end) };
}

/**
 * Task #2 enhancement (Doctor SOAP only): an optional grouped view of the suggestion list
 * ("My phrases", "Recently used", "Clinic suggestions", "Starters"). Sections are given in
 * priority order and a phrase is shown once, in the first section that has it. `limit` keeps
 * each section short. Callers that pass only `suggestions` (Task #8, Receptionist/Nurse) keep
 * the original flat list exactly as before.
 */
export type SuggestionSection = { id: string; label: string; items: string[]; limit?: number };

/** Doctor-specific "My Phrases" controls: a star on each row and a Save/Remove action for the current line. */
export type PersonalPhraseControls = {
  /** Lower-cased keys of the phrases the Doctor has already saved for this field. */
  savedKeys: ReadonlySet<string>;
  onSave: (text: string) => void;
  onRemove: (text: string) => void;
  /** A short message to show under the list (e.g. why a phrase could not be saved). */
  notice?: string | null;
};

const MIN_SAVE_LENGTH = 2;
const MAX_SAVE_LENGTH = 80;

/** Cheap client-side check for offering "Save to My Phrases"; the server does the real privacy validation. */
export function isSavablePhrase(text: string): boolean {
  const t = text.trim();
  return t.length >= MIN_SAVE_LENGTH && t.length <= MAX_SAVE_LENGTH && /[\p{L}\p{N}]/u.test(t);
}

export function SuggestionInput({
  value,
  onChange,
  suggestions,
  sections,
  personal,
  onFocus,
  placeholder,
  "aria-label": ariaLabel,
  multiline = false,
  rows = 3,
  disabled = false,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  suggestions: string[];
  sections?: SuggestionSection[];
  personal?: PersonalPhraseControls;
  onFocus?: () => void;
  placeholder?: string;
  "aria-label"?: string;
  multiline?: boolean;
  rows?: number;
  disabled?: boolean;
  className?: string;
}) {
  const [focused, setFocused] = useState(false);
  const [caret, setCaret] = useState(value.length);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const pendingCaret = useRef<number | null>(null);

  // Restore a sensible caret right after a suggestion replaced a line.
  useEffect(() => {
    if (pendingCaret.current === null) return;
    const position = pendingCaret.current;
    pendingCaret.current = null;
    const el = textareaRef.current;
    if (el) {
      el.focus();
      el.setSelectionRange(position, position);
    }
    setCaret(position);
  }, [value]);

  const line = multiline ? currentLine(value, caret) : null;
  const currentText = (line ? line.text : value).trim();
  const query = currentText.toLowerCase();
  const matches = query
    ? suggestions.filter((s) => s.toLowerCase().includes(query) && s.toLowerCase() !== query)
    : suggestions;

  // Grouped view (Doctor SOAP only): filter each section by the current line/segment, then cap it.
  const shownSections = sections
    ? sections
        .map((sec) => ({
          ...sec,
          items: (query ? sec.items.filter((s) => s.toLowerCase().includes(query) && s.toLowerCase() !== query) : sec.items).slice(
            0,
            sec.limit ?? 8
          ),
        }))
        .filter((sec) => sec.items.length > 0)
    : null;
  // "Save to My Phrases" acts on the line/segment the caret is on - never on the whole multi-line block.
  const currentIsSaved = personal ? personal.savedKeys.has(query) : false;
  const canSaveCurrent = personal ? !currentIsSaved && isSavablePhrase(currentText) : false;
  const showPersonalFooter = !!personal && (currentIsSaved || canSaveCurrent || !!personal.notice);

  function pick(s: string) {
    if (line) {
      const next = value.slice(0, line.start) + s + value.slice(line.end);
      pendingCaret.current = line.start + s.length;
      onChange(next);
    } else {
      onChange(s);
    }
  }

  const sectionedListbox =
    shownSections && focused && !disabled && (shownSections.length > 0 || showPersonalFooter) ? (
      <div className="absolute z-10 mt-1 w-full rounded-md border border-border bg-popover shadow-md">
        <div className="max-h-56 overflow-y-auto">
          {shownSections.map((sec) => (
            <div key={sec.id} role="group" aria-label={sec.label}>
              <p className="px-3 pb-0.5 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{sec.label}</p>
              <ul>
                {sec.items.map((s) => {
                  const saved = personal ? personal.savedKeys.has(s.toLowerCase()) : false;
                  return (
                    <li key={`${sec.id}:${s}`} className="flex items-center hover:bg-accent">
                      <button
                        type="button"
                        className="min-w-0 flex-1 px-3 py-1.5 text-left text-sm"
                        onMouseDown={(e) => {
                          e.preventDefault();
                          pick(s);
                        }}
                      >
                        {s}
                      </button>
                      {personal ? (
                        <button
                          type="button"
                          aria-label={saved ? `Remove "${s}" from My Phrases` : `Save "${s}" to My Phrases`}
                          aria-pressed={saved}
                          title={saved ? "Remove from My Phrases" : "Save to My Phrases"}
                          className={`px-3 py-1.5 text-base leading-none ${saved ? "text-amber-500" : "text-muted-foreground hover:text-foreground"}`}
                          onMouseDown={(e) => {
                            e.preventDefault();
                            if (saved) personal.onRemove(s);
                            else personal.onSave(s);
                          }}
                        >
                          {saved ? "★" : "☆"}
                        </button>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
        {personal && showPersonalFooter ? (
          <div className="border-t border-border">
            {currentIsSaved ? (
              <button
                type="button"
                className="block w-full px-3 py-1.5 text-left text-sm text-amber-600 hover:bg-accent"
                onMouseDown={(e) => {
                  e.preventDefault();
                  personal.onRemove(currentText);
                }}
              >
                {`★ Remove "${currentText}" from My Phrases`}
              </button>
            ) : canSaveCurrent ? (
              <button
                type="button"
                className="block w-full px-3 py-1.5 text-left text-sm hover:bg-accent"
                onMouseDown={(e) => {
                  e.preventDefault();
                  personal.onSave(currentText);
                }}
              >
                {`☆ Save "${currentText}" to My Phrases`}
              </button>
            ) : null}
            {personal.notice ? <p className="px-3 py-1 text-xs text-destructive">{personal.notice}</p> : null}
          </div>
        ) : null}
      </div>
    ) : null;

  const listbox = shownSections
    ? sectionedListbox
    : focused && !disabled && matches.length > 0 ? (
      <ul className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-border bg-popover shadow-md">
        {matches.slice(0, 8).map((s) => (
          <li key={s}>
            <button
              type="button"
              className="block w-full px-3 py-1.5 text-left text-sm hover:bg-accent"
              onMouseDown={(e) => {
                e.preventDefault();
                pick(s);
              }}
            >
              {s}
            </button>
          </li>
        ))}
      </ul>
    ) : null;

  if (multiline) {
    return (
      <div className="relative">
        <Textarea
          ref={textareaRef}
          value={value}
          rows={rows}
          disabled={disabled}
          className={className}
          onChange={(e) => {
            setCaret(e.target.selectionStart ?? e.target.value.length);
            onChange(e.target.value);
          }}
          onSelect={(e) => setCaret((e.target as HTMLTextAreaElement).selectionStart ?? 0)}
          onFocus={() => {
            setFocused(true);
            onFocus?.();
          }}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          placeholder={placeholder}
          aria-label={ariaLabel}
        />
        {listbox}
      </div>
    );
  }

  return (
    <div className="relative">
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => {
            setFocused(true);
            onFocus?.();
          }}
        onBlur={() => setTimeout(() => setFocused(false), 150)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        disabled={disabled}
        className={className}
      />
      {listbox}
    </div>
  );
}
