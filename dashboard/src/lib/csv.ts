/** RFC-4180 field escaping: wrap in quotes and double any embedded quote. */
function csvField(value: string): string {
  if (/[",\r\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export function toCsv(columns: readonly string[], rows: ReadonlyArray<readonly string[]>): string {
  const header = columns.map(csvField).join(',');
  const body = rows.map((r) => r.map(csvField).join(','));
  return [header, ...body].join('\r\n');
}

/** Triggers a client-side Blob download. No network, no server round-trip. */
export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
