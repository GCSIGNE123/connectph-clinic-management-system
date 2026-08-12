/**
 * Minimal, dependency-free CSV read/write - matches this codebase's
 * lean-dependency convention (e.g. no PDF library for printing; see
 * `QueueSlipDialog.tsx`). Handles the RFC 4180 essentials actually needed
 * here: quoted fields, embedded commas/quotes/newlines, CRLF or LF line
 * endings. Not a full RFC 4180 parser (no support for BOM stripping or
 * exotic encodings) - sufficient for clinic staff exporting from/importing
 * into Excel/Google Sheets, which is the only realistic real-world source.
 */

function escapeCsvField(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

/** Builds a CSV string (with header row) from an array of row-arrays. */
export function toCsv(headers: string[], rows: (string | number | null | undefined)[][]): string {
  const lines = [headers.map(escapeCsvField).join(",")];
  for (const row of rows) {
    lines.push(row.map((cell) => escapeCsvField(cell === null || cell === undefined ? "" : String(cell))).join(","));
  }
  return lines.join("\r\n");
}

/** Parses a CSV string into an array of header-keyed row objects. The
 * first line is always treated as the header row. Returns `[]` for empty/
 * whitespace-only input. */
export function parseCsv(text: string): Record<string, string>[] {
  const rows = parseCsvRows(text);
  if (rows.length === 0) return [];
  const [header, ...dataRows] = rows;
  return dataRows
    .filter((row) => row.some((cell) => cell.trim() !== "")) // skip blank trailing lines
    .map((row) => Object.fromEntries(header.map((key, i) => [key.trim(), (row[i] ?? "").trim()])));
}

/** Character-level CSV row tokenizer - handles quoted fields containing
 * commas/newlines/escaped quotes, which a naive `split(",")`/`split("\n")`
 * cannot. */
function parseCsvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  let i = 0;

  while (i < text.length) {
    const char = text[i];

    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i += 1;
        continue;
      }
      field += char;
      i += 1;
      continue;
    }

    if (char === '"') {
      inQuotes = true;
      i += 1;
      continue;
    }
    if (char === ",") {
      row.push(field);
      field = "";
      i += 1;
      continue;
    }
    if (char === "\r") {
      i += 1;
      continue;
    }
    if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      i += 1;
      continue;
    }
    field += char;
    i += 1;
  }

  // Final field/row (input doesn't necessarily end with a newline).
  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows;
}

/** Triggers a browser download of the given CSV text. No-ops server-side. */
export function downloadCsv(filename: string, csvText: string): void {
  if (typeof window === "undefined") return;
  const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
