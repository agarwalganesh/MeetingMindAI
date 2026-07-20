// Column order shared by the CSV and Excel exports of the action-items table.
const ACTION_HEADERS = ['Task', 'Owner', 'Deadline', 'Priority', 'Status'];

const safeName = (title) => (title || 'meeting').trim().replace(/[^\w.-]+/g, '_') || 'meeting';

const triggerDownload = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

const actionRows = (meeting) =>
  (meeting.action_items || []).map((a) => ({
    Task: a.task || '',
    Owner: a.owner || '',
    Deadline: a.deadline || '',
    Priority: a.priority || '',
    Status: a.status || '',
  }));

// --- CSV (dependency-free; opens directly in Excel/Sheets) ---
const csvEscape = (val) => {
  const s = String(val ?? '');
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function exportActionItemsCSV(meeting) {
  const rows = actionRows(meeting);
  const lines = [ACTION_HEADERS.join(',')];
  for (const r of rows) {
    lines.push(ACTION_HEADERS.map((h) => csvEscape(r[h])).join(','));
  }
  // Prepend a BOM so Excel detects UTF-8 (preserves accented names, etc.).
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  triggerDownload(blob, `${safeName(meeting.title)}_action_items.csv`);
}

// --- Excel .xlsx (SheetJS) ---
// xlsx is heavy, so it's dynamically imported — it only ships to the browser
// when the user actually exports to Excel, keeping the main bundle lean.
export async function exportActionItemsXLSX(meeting) {
  const XLSX = await import('xlsx');
  const rows = actionRows(meeting);
  const data = rows.length ? rows : [{ Task: '', Owner: '', Deadline: '', Priority: '', Status: '' }];
  const ws = XLSX.utils.json_to_sheet(data, { header: ACTION_HEADERS });
  ws['!cols'] = [{ wch: 50 }, { wch: 18 }, { wch: 20 }, { wch: 12 }, { wch: 12 }];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Action Items');
  XLSX.writeFile(wb, `${safeName(meeting.title)}_action_items.xlsx`);
}

// --- Transcript as Markdown ---
export function exportTranscriptMarkdown(meeting) {
  const out = [`# ${meeting.title || 'Meeting'} — Transcript`, ''];
  if (meeting.created_at) {
    out.push(`_Date: ${new Date(meeting.created_at).toLocaleString()}_`, '');
  }
  if (meeting.summary_executive) {
    out.push('## Executive Summary', '', meeting.summary_executive, '');
  }
  out.push('## Transcript', '');
  const transcript = meeting.transcript || '_No transcript available._';
  for (const line of transcript.split('\n')) {
    out.push(line);
  }
  const blob = new Blob([out.join('\n')], { type: 'text/markdown;charset=utf-8;' });
  triggerDownload(blob, `${safeName(meeting.title)}_transcript.md`);
}
