// Endpoints (change here only)
// Django backend serves this frontend, so API calls go to the same origin.
export const endpoint       = '/api/responses/';
export const csrfEndpoint   = '/api/csrf/';
export const tokenEndpoint  = '/api/links/';
export const qrEndpoint     = '/api/qr-codes/';
export const problemLogEndpoint = '/api/problem-logs/';

export const STORAGE = {
  AUTH: 'surveySupportAuth',
  BUILDING: 'selectedBuilding',
  WORKSHOP: 'workshopDay',
  KIOSK: 'kioskMode',
  FAILSAFE: 'surveyFailsafeQueue',
  OFFLINE: 'surveyOfflineMode',
};

export const params = new URLSearchParams(location.search);
export const linkToken = params.get('t') || params.get('token') || null;
export const qpBuilding = params.get('b');
export const qpWD = params.get('wd') === '1';
export const isQrLink = params.has('b');

// mutable state shared by modules
export const state = {
  selectedBuilding: (() => {
    if (qpBuilding) return Number(qpBuilding);
    try { const v = localStorage.getItem(STORAGE.BUILDING); return v ? Number(v) : null; }
    catch { return null; }
  })()
};

export function saveSelectedBuilding(v){
  state.selectedBuilding = v;
  try { localStorage.setItem(STORAGE.BUILDING, String(v)); } catch {}
}

// reset=1 helper (kept same behavior)
if (params.get('reset') === '1') {
  try { localStorage.removeItem(STORAGE.AUTH); } catch {}
  try { localStorage.removeItem(STORAGE.BUILDING); } catch {}
  ['reset','t','token','b','wd'].forEach(k=>params.delete(k));
  const next = location.pathname + (params.toString() ? `?${params.toString()}` : '');
  location.replace(next);
}