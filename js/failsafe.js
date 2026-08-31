// Offline failsafe: when the Azure proxy can't be reached (or answers with a
// server error) a submission must never be lost. Every failed response is
// queued locally, appended to a plain-text backup file the supporter picks
// once (Documents), and re-sent automatically as soon as the backend answers
// again.
import { endpoint, linkToken, STORAGE } from './config.js';
import { getSavedKey } from './auth.js';

export const FAILSAFE_QUEUE = STORAGE.FAILSAFE;

const FILE_PREFIX  = 'python-support-survey-backup';
const IDB_NAME     = 'surveyFailsafe';
const IDB_STORE    = 'handles';
const HANDLE_KEY   = 'backupFile';
const RETRY_MS     = 60_000;
const MAX_ATTEMPTS = 20;

const HEADER = [
  'saved_at','role','student_number','username','satisfaction',
  'course_number','building','workshop','used_ai','reason'
].join('\t');

/* ---------------------------------------------------------------- queue --- */

export function readQueue() {
  try { return JSON.parse(localStorage.getItem(FAILSAFE_QUEUE) || '[]'); }
  catch { return []; }
}

function writeQueue(records) {
  try { localStorage.setItem(FAILSAFE_QUEUE, JSON.stringify(records)); return true; }
  catch (err) { console.error('failsafe: queue write failed:', err); return false; }
}

export function pendingCount() { return readQueue().length; }

/** Records that still need to reach the text file. */
function unfiled(records = readQueue()) { return records.filter(r => !r.filed); }

/* ------------------------------------------------------------ formatting --- */

function tsv(rec) {
  const p = rec.payload || {};
  const cell = (v) => (v === null || v === undefined || v === '')
    ? '' : String(v).replace(/[\t\r\n]+/g, ' ').trim();
  return [
    rec.ts, p.role, p.student_number, p.username, p.satisfaction,
    p.course_number, p.building_Number,
    p.workshop ? 'yes' : 'no', p.used_ai ? 'yes' : 'no',
    rec.reason
  ].map(cell).join('\t');
}

function backupFileName() {
  return `${FILE_PREFIX}-${new Date().toISOString().slice(0, 10)}.txt`;
}

/* ------------------------------------------ file handle (Documents, etc.) --- */

const canPickFile = () => typeof window.showSaveFilePicker === 'function';

function idb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(IDB_STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror   = () => reject(req.error);
  });
}

function idbOp(mode, fn) {
  return idb().then(db => new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, mode);
    const req = fn(tx.objectStore(IDB_STORE));
    req.onsuccess = () => resolve(req.result);
    req.onerror   = () => reject(req.error);
  })).catch(err => { console.error('failsafe: idb failed:', err); return null; });
}

const loadHandle = () => idbOp('readonly',  s => s.get(HANDLE_KEY));
const saveHandle = (h) => idbOp('readwrite', s => s.put(h, HANDLE_KEY));

async function permission(handle, interactive) {
  if (!handle) return 'denied';
  const opts = { mode: 'readwrite' };
  try {
    let state = await handle.queryPermission(opts);
    if (state === 'prompt' && interactive) state = await handle.requestPermission(opts);
    return state;
  } catch { return 'denied'; }
}

/**
 * Get the backup file handle. Only asks the user to pick one when
 * `interactive` is true — a picker needs a real click to open.
 */
async function getFileHandle(interactive) {
  let handle = await loadHandle();
  if (handle && (await permission(handle, interactive)) === 'granted') return handle;
  if (!interactive || !canPickFile()) return null;

  try {
    handle = await window.showSaveFilePicker({
      suggestedName: backupFileName(),
      startIn: 'documents',
      types: [{ description: 'Text file', accept: { 'text/plain': ['.txt'] } }]
    });
  } catch { return null; }               // user cancelled

  if ((await permission(handle, true)) !== 'granted') return null;
  await saveHandle(handle);
  return handle;
}

/* ------------------------------------------------------------- file write --- */

/**
 * Append every not-yet-filed record to the backup text file.
 * `interactive` must be true when called straight from a click, so the file
 * picker / permission prompt is allowed to open. Returns the number written.
 */
export async function writeBackupFile({ interactive = false } = {}) {
  const records = readQueue();
  const todo = unfiled(records);
  if (!todo.length) return 0;

  const handle = await getFileHandle(interactive);
  if (!handle) return 0;

  try {
    let existing = '';
    try { existing = await (await handle.getFile()).text(); } catch {}

    const lines = todo.map(tsv);
    const body  = existing.trim()
      ? `${existing.replace(/\s*$/, '')}\n${lines.join('\n')}\n`
      : `${HEADER}\n${lines.join('\n')}\n`;

    const writable = await handle.createWritable();
    await writable.write(body);
    await writable.close();
  } catch (err) {
    console.error('failsafe: file write failed:', err);
    return 0;
  }

  markFiled(records, todo);
  return todo.length;
}

/** Fallback for browsers without the file picker: download the same text. */
export function downloadBackupFile() {
  const records = readQueue();
  const todo = unfiled(records);
  if (!todo.length) return 0;

  const text = `${HEADER}\n${todo.map(tsv).join('\n')}\n`;
  const url  = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const a    = document.createElement('a');
  a.href = url;
  a.download = backupFileName();
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);

  markFiled(records, todo);
  return todo.length;
}

/**
 * Mark the just-written records, and drop the ones the backend has refused for
 * good — the file is now their only home, so they only clutter the queue.
 */
function markFiled(records, written) {
  const filed = new Set(written.map(r => r.id));
  writeQueue(
    records
      .map(r => (filed.has(r.id) ? { ...r, filed: true } : r))
      .filter(r => !(r.filed && r.rejected))
  );
  notify();
}

/** What a click on "Save backup" should do, whichever API is available. */
export async function saveBackupNow() {
  const written = await writeBackupFile({ interactive: true });
  return written || downloadBackupFile();
}

/* ---------------------------------------------------------------- capture --- */

/**
 * Called when a submission could not be delivered. Queues it and, when the
 * backup file is already picked and still writable, appends it right away.
 */
export async function saveFailedSubmission(payload, reason = 'network error') {
  const rec = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    ts: new Date().toISOString(),
    reason,
    payload
  };
  const stored = writeQueue(readQueue().concat(rec));
  notify();

  const filed = await writeBackupFile();   // silent: only if already permitted
  return { stored, filed: filed > 0, pending: pendingCount() };
}

/* ------------------------------------------------------------------ retry --- */

let retrying = false;

/** Re-send everything queued. Records the backend rejects are kept, not retried. */
export async function retryPending() {
  if (retrying || !navigator.onLine) return 0;
  const records = readQueue();
  if (!records.length) return 0;

  retrying = true;
  let sent = 0;
  try {
    for (const rec of records) {
      if (rec.rejected || (rec.attempts || 0) >= MAX_ATTEMPTS) continue;

      const headers = { 'Content-Type': 'application/json' };
      if (rec.payload?.token) headers['x-token'] = rec.payload.token;
      else headers['x-api-key'] = getSavedKey()[1] || '';

      let response;
      try {
        response = await fetch(endpoint, {
          method: 'POST', headers, body: JSON.stringify(rec.payload)
        });
      } catch { break; }                  // still offline, stop for now

      if (response.ok) { rec.sent = true; sent++; }
      else if (response.status >= 400 && response.status < 500 && response.status !== 429) {
        rec.rejected = true;              // backend will never accept it
        rec.reason = `${rec.reason} / rejected ${response.status}`;
      } else {
        rec.attempts = (rec.attempts || 0) + 1;
      }
    }
  } finally {
    retrying = false;
  }

  if (sent) { writeQueue(records.filter(r => !r.sent)); notify(); }
  else      { writeQueue(records); }
  return sent;
}

/* --------------------------------------------------------------------- UI --- */

const listeners = new Set();
export function onFailsafeChange(fn) { listeners.add(fn); fn(pendingCount()); }
function notify() { const n = pendingCount(); listeners.forEach(fn => { try { fn(n); } catch {} }); }

export function wireFailsafe() {
  const saveBtn = document.getElementById('saveBackupBtn');
  const tab     = document.getElementById('backupTab');
  const tabCnt  = document.getElementById('backupCount');

  saveBtn?.addEventListener('click', async () => {
    saveBtn.disabled = true;
    const n = await saveBackupNow();
    saveBtn.textContent = n ? `Saved ${n} response${n === 1 ? '' : 's'}` : 'Nothing to save';
    saveBtn.disabled = false;
  });

  tab?.addEventListener('click', async (e) => { e.preventDefault(); await saveBackupNow(); });

  onFailsafeChange((n) => {
    const unsaved = unfiled().length;
    if (saveBtn) {
      // Students on a one-time link have nowhere to put a file — queue silently.
      saveBtn.classList.toggle('hidden', !(unsaved && !linkToken));
      saveBtn.textContent = canPickFile() ? 'Save backup file' : 'Download backup file';
      saveBtn.disabled = false;
    }
    if (tab) {
      const show = !!(n && !linkToken);
      tab.classList.toggle('hidden', !show);
      tab.classList.toggle('flex', show);
      if (tabCnt) tabCnt.textContent = String(n);
    }
  });

  window.addEventListener('online', () => { retryPending(); });
  setInterval(() => { if (pendingCount()) retryPending(); }, RETRY_MS);
  retryPending();

  // Last chance to flag unsaved responses before the tab goes away.
  window.addEventListener('beforeunload', (e) => {
    if (!unfiled().length || linkToken) return;
    e.preventDefault();
    e.returnValue = '';
  });
}
