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

export function SuggestionInput({
  value,
  onChange,
  suggestions,
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
  const query = (line ? line.text : value).trim().toLowerCase();
  const matches = query
    ? suggestions.filter((s) => s.toLowerCase().includes(query) && s.toLowerCase() !== query)
    : suggestions;

  function pick(s: string) {
    if (line) {
      const next = value.slice(0, line.start) + s + value.slice(line.end);
      pendingCaret.current = line.start + s.length;
      onChange(next);
    } else {
      onChange(s);
    }
  }

  const listbox =
    focused && !disabled && matches.length > 0 ? (
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
          onFocus={() => setFocused(true)}
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
        onFocus={() => setFocused(true)}
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
