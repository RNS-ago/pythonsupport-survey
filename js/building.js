import { endpoint, tokenEndpoint, qrEndpoint, STORAGE, state, saveSelectedBuilding, qpWD, linkToken } from './config.js';
import { getSavedKey } from './auth.js';
import { showError } from './errors.js';
import { isKiosk, syncFabVisibility } from './kiosk.js';

const overlay = () => document.getElementById('sidebarOverlay');
const sidebar = () => document.getElementById('sidebar');
const openBtn  = () => document.getElementById('openSidebar');

export function openSidebar(){ if (!isKiosk()) { sidebar().classList.remove('-translate-x-full'); overlay().classList.remove('hidden'); document.body.classList.add('overflow-hidden'); }}
export function closeSidebar(){ sidebar().classList.add('-translate-x-full'); overlay().classList.add('hidden'); document.body.classList.remove('overflow-hidden'); }

// Each page has an outer container (index.html) and an inner page (partial); show one, hide the rest.
const PAGES = ['modeSelection', 'buildingSelection', 'survey', 'analytics', 'problemLog'];
function showPage(name){
  for (const p of PAGES) {
    document.getElementById(`${p}Container`).classList.toggle('hidden', p !== name);
    document.getElementById(`${p}Page`)?.classList.toggle('hidden', p !== name);
  }
  syncBackSelectorVisibility();
  syncFabVisibility();
}

export function showModeSelection(){
  if (isKiosk()) return;
  showPage('modeSelection');
}

export function showProblemLog(){
  if (isKiosk()) return;
  showPage('problemLog');
}

export function showBuildingSelection(){
  if (isKiosk()) return;
  showPage('buildingSelection');
}

export function showSurveyForm(){
  showPage('survey');

  // keep the workshop preset logic
  const preferWD = (localStorage.getItem('workshopDay') === 'true');
  const yes = document.getElementById('workshop_yes');
  const no  = document.getElementById('workshop_no');
  if (yes && no) { yes.checked = !!preferWD; no.checked = !preferWD; }
}

export function switchToAnalytics(e){
  if (e) e.preventDefault();
  if (isKiosk() || (new URLSearchParams(location.search).get('t') || new URLSearchParams(location.search).get('token'))) return;
  showPage('analytics');
  closeSidebar();
}

export function switchToSurvey(e){
  if (e) e.preventDefault();
  if (isKiosk()) { showSurveyForm(); return; }
  if (state.selectedBuilding === null) showBuildingSelection(); else showSurveyForm();
  closeSidebar();
}

export function selectBuilding(b){ if (isKiosk()) return; saveSelectedBuilding(b); showSurveyForm(); }
export function selectCustomBuilding(){
  if (isKiosk()) return;
  const input = document.getElementById('customBuilding');
  const n = parseInt(input.value, 10);
  if (!input.value || isNaN(n) || n <= 100 || n >= 500) return showError('Please enter a valid building number (101-499).');
  selectBuilding(n);
}
export function handleEnterKey(e){ if (e.key === 'Enter') selectCustomBuilding(); }

// Admin controls
function wireWorkshopToggle(){
  const t = document.getElementById('workshopDayToggle');
  if (!t) return;
  try { t.checked = localStorage.getItem(STORAGE.WORKSHOP) === 'true'; } catch {}
  t.addEventListener('change', ()=> { try { localStorage.setItem(STORAGE.WORKSHOP, String(t.checked)); } catch {} });
}

async function generateOneTimeLink() {
  if (isKiosk()) return;
  try {
    const resp = await fetch(tokenEndpoint, {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-CSRFToken': getSavedKey()[1] || '' },
    });
    if (!resp.ok) {
      const txt = await resp.text().catch(()=> '');
      showError('Could not generate link. ' + (txt || ''), resp.status);
      return;
    }
    const data = await resp.json().catch(()=>({}));
    const baseUrl = window.location.origin + window.location.pathname;
    const wd = (document.getElementById('workshopDayToggle')?.checked) ? '&wd=1' : '';
    const url = data.url || data.oneTimeUrl || `${baseUrl}?token=${encodeURIComponent(data.token)}${wd}`;
    try { await navigator.clipboard.writeText(url); } catch {}
    alert('Discord link copied to clipboard:\n' + url);
  } catch (e) {
    console.error(e);
    showError('Unexpected error while generating the link.');
  }
}

function wireQRModal(){
  const modal = document.getElementById('qrModal');
  const qrCreate  = document.getElementById('qrCreate');
  const qrClose   = document.getElementById('qrClose');
  const qrCopy    = document.getElementById('qrCopy');
  const qrCanvas  = document.getElementById('qrCanvas');
  const qrImg     = document.getElementById('qrImg');
  const qrLinkInp = document.getElementById('qrLink');
  const qrResult  = document.getElementById('qrResult');
  const qrBuildingInp = document.getElementById('qrBuilding');
  const qrWD = document.getElementById('qrWorkshopDay');
  const qrDaysInp = document.getElementById('qrValidDays');
  const inlineErr = document.getElementById('qrInlineError');

  function open() {
    if (isKiosk()) return;
    qrBuildingInp.value = (state.selectedBuilding ?? '').toString();
    try { qrWD.checked = (localStorage.getItem(STORAGE.WORKSHOP) === 'true'); } catch {}
    if (qrImg) { qrImg.src=''; qrImg.classList.add('hidden'); }
    qrCanvas.classList.remove('hidden'); qrResult.classList.add('hidden');
    if (inlineErr) { inlineErr.textContent=''; inlineErr.classList.add('hidden'); }
    modal.classList.remove('hidden');
  }
  function close(){ modal.classList.add('hidden'); }

  document.getElementById('btnGenerateQR')?.addEventListener('click', open);
  modal?.querySelectorAll('.qr-quick').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      qrBuildingInp.value = btn.getAttribute('data-building');
      inlineErr.classList.add('hidden');
    });
  });

  qrBuildingInp?.addEventListener('input', ()=> inlineErr.classList.add('hidden'));
  qrDaysInp?.addEventListener('input', ()=> inlineErr.classList.add('hidden'));

  async function create(){
    if (isKiosk()) return;
    const val = qrBuildingInp.value.trim(); const num = Number(val);
    if (val==='' || isNaN(num) || num<0 || num>990){
      inlineErr.textContent='Please enter a valid building between 000 and 990 or use a quick option.';
      inlineErr.classList.remove('hidden'); return;
    }
    const days = Number(qrDaysInp.value);
    if (!Number.isInteger(days) || days<1 || days>365){
      inlineErr.textContent='Please enter how many days the QR code stays valid (1-365).';
      inlineErr.classList.remove('hidden'); return;
    }
    const resp = await fetch(qrEndpoint, {
      method:'POST', credentials:'include',
      headers:{ 'Content-Type':'application/json', 'X-CSRFToken': getSavedKey()[1] || '' },
      body: JSON.stringify({ building_number: num, valid_days: days })
    });
    if (!resp.ok){ const txt = await resp.text().catch(()=> ''); return showError('Could not create QR. ' + (txt||''), resp.status); }
    const { token } = await resp.json();
    // Same shape as a one-time link; the backend knows the building and whether the token is reusable.
    const url = `${location.origin}${location.pathname}?t=${encodeURIComponent(token)}${qrWD.checked ? '&wd=1' : ''}`;
    qrLinkInp.value = url;
    if (window.QRCode?.toCanvas){
      const ctx = qrCanvas.getContext('2d'); ctx.clearRect(0,0,qrCanvas.width,qrCanvas.height);
      await QRCode.toCanvas(qrCanvas, url, { width: 280, margin: 2 });
      qrCanvas.classList.remove('hidden'); qrImg.classList.add('hidden');
    } else {
      const e = encodeURIComponent(url);
      qrCanvas.classList.add('hidden'); qrImg.classList.remove('hidden');
      qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=${e}`;
    }
    qrResult.classList.remove('hidden');
  }
  qrCreate?.addEventListener('click', create);
  qrClose?.addEventListener('click', close);
  qrCopy?.addEventListener('click', async ()=>{ try{ await navigator.clipboard.writeText(qrLinkInp.value);}catch{} });
}

export function applySidebarVisibility(){
  const hide = isKiosk() || !!linkToken || !!(new URLSearchParams(location.search).get('b'));
  if (sidebar()) {
    if (hide){ sidebar().hidden=true; sidebar().style.display='none'; sidebar().setAttribute('aria-hidden','true'); sidebar().setAttribute('inert',''); }
    else { sidebar().hidden=false; sidebar().style.display=''; sidebar().removeAttribute('aria-hidden'); sidebar().removeAttribute('inert'); }
  }
  document.getElementById('openSidebar').style.display = hide ? 'none' : '';
  overlay().classList.add('hidden'); overlay().style.display='none';
}

export function syncBackSelectorVisibility(){
  const link = document.getElementById('backSelectorTab');
  if (!link) return;
  const onSelector = !document.getElementById('buildingSelectionContainer').classList.contains('hidden');
  link.style.display = onSelector ? 'none' : '';
}

export function wireBuildingPage(){
  // global functions (for inline onclick in partial)
  window.selectBuilding = selectBuilding;
  window.selectCustomBuilding = selectCustomBuilding;
  window.handleEnterKey = handleEnterKey;
  window.showBuildingSelection = showBuildingSelection;

  document.getElementById('btnGenerateLink')?.addEventListener('click', generateOneTimeLink);
  wireWorkshopToggle();
  wireQRModal();

  // sidebar events
  document.getElementById('openSidebar')?.addEventListener('click', openSidebar);
  document.getElementById('closeSidebar')?.addEventListener('click', closeSidebar);
  document.getElementById('sidebarOverlay')?.addEventListener('click', closeSidebar);

  // tabs
  document.getElementById('surveyTab')?.addEventListener('click', switchToSurvey);
  document.getElementById('analyticsTab')?.addEventListener('click', switchToAnalytics);
  document.getElementById('modeSurvey')?.addEventListener('click', switchToSurvey);
  document.getElementById('modeProblemLog')?.addEventListener('click', showProblemLog);
  document.getElementById('modeTab')?.addEventListener('click', e => { e.preventDefault(); showModeSelection(); closeSidebar(); });
  document.getElementById('backSelectorTab')?.addEventListener('click', e => { e.preventDefault(); showBuildingSelection(); closeSidebar(); });
  document.getElementById('resetTab')?.addEventListener('click', e => { e.preventDefault(); location.href = location.pathname + '?reset=1'; });

  applySidebarVisibility();
  syncBackSelectorVisibility();
  syncFabVisibility();
}