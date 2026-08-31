import { endpoint, STORAGE } from './config.js';
// Reset everything on refresh except the saved API key and any responses the
// failsafe still holds for a backend that was unreachable.
try {
  const keep = [STORAGE.AUTH, STORAGE.FAILSAFE, STORAGE.OFFLINE].map(k => [k, localStorage.getItem(k)]);
  localStorage.clear();
  for (const [k, v] of keep) if (v !== null) localStorage.setItem(k, v);
} catch {}
export function getSavedKey() {
  try { const saved = localStorage.getItem(STORAGE.AUTH); return saved ? saved.split("|") : [null,null]; }
  catch { return [null,null]; }
}
const today = () => new Date().toISOString().slice(0, 10);

export function isAuthValid() {
  const [date, key] = getSavedKey();
  return date === today() && !!key;
}

export function clearSavedKey() {
  try { localStorage.removeItem(STORAGE.AUTH); } catch {}
}

/** 401/403 are about the caller's code, never about the response it carried. */
export function isCredentialFault(status) {
  return status === 401 || status === 403;
}

/* --------------------------------------------------- offline code override ---
 * The daily code can only be checked against the proxy, so when the proxy is
 * unreachable there is no way to verify one — and no point in blocking a
 * supporter who is standing in front of a queue of students. In that case we
 * let them in with no code at all; every response goes to the failsafe queue,
 * and the code is asked for once the proxy answers again, before anything is
 * uploaded. The flag is day-scoped, like the code it stands in for.
 */
export function isOfflineMode() {
  try { return localStorage.getItem(STORAGE.OFFLINE) === today(); }
  catch { return false; }
}

export function setOfflineMode(on) {
  try {
    if (on) localStorage.setItem(STORAGE.OFFLINE, today());
    else    localStorage.removeItem(STORAGE.OFFLINE);
  } catch {}
  document.body.classList.toggle('offline-mode', !!on);
  document.getElementById('offlineBadge')?.classList.toggle('hidden', !on);
}

/** True when the proxy answers at all — any status counts, 401 included. */
export async function probeBackend() {
  try {
    await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ping: true })
    });
    return true;
  } catch { return false; }
}

/** Decide, at start-up, whether the daily code is needed at all. */
export async function gateLogin() {
  if (isAuthValid()) { setOfflineMode(false); hideLogin(); return; }
  if (await probeBackend()) { setOfflineMode(false); showLogin(); return; }
  enterOfflineMode();
}

function enterOfflineMode() {
  setOfflineMode(true);
  hideLogin();
  settleCodePrompt(false);
}

/* A proxy that answers but refuses every code is as unusable as one that is
 * down, yet re-asking on a timer would just nag. Once the supporter has opted
 * out — or the code has been refused too often to be worth re-asking — stop
 * prompting for the rest of the page's life; a reload starts the gate over. */
let promptSuppressed = false;
export function suppressCodePrompt() { promptSuppressed = true; }
export function isCodePromptSuppressed() { return promptSuppressed; }

/* The login modal doubles as a prompt the failsafe can await. */
let codePrompt = null;

/** Show the login modal and resolve true once a valid code is stored. */
export function requireCode(note) {
  if (codePrompt) return codePrompt.promise;
  const el = document.getElementById('loginNote');
  if (el) { el.textContent = note || ''; el.classList.toggle('hidden', !note); }
  showLogin();
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  codePrompt = { promise, resolve };
  return promise;
}

function settleCodePrompt(ok) {
  const p = codePrompt;
  codePrompt = null;
  document.getElementById('loginNote')?.classList.add('hidden');
  p?.resolve(ok);
}
export function showLogin() {
  document.getElementById("loginModal").classList.remove("hidden");
  document.getElementById("mainWrapper").classList.add("pointer-events-none", "opacity-40");
  setTimeout(() => { const inp = document.getElementById("accessCodeInput"); if (inp) { inp.focus(); inp.select(); } }, 0);
}
export function hideLogin() {
  document.getElementById("loginModal").classList.add("hidden");
  document.getElementById("mainWrapper").classList.remove("pointer-events-none", "opacity-40");
  document.getElementById("loginError").classList.add("hidden");
}

// Refusals to sit through before offering to work without a code at all.
const MAX_CODE_TRIES = 3;

export function wireLogin() {
  let refusals = 0;
  const offlineBtn = document.getElementById("loginOffline");

  offlineBtn?.addEventListener("click", () => {
    // A deliberate opt-out: collect now, sort the code out later.
    suppressCodePrompt();
    document.getElementById("loginError").classList.add("hidden");
    enterOfflineMode();
  });

  const submit = async () => {
    const input = document.getElementById("accessCodeInput").value.trim();
    let reachable = true;
    const ok = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-api-key": input },
      body: JSON.stringify({ ping: true })
    }).then(r => r.ok).catch(() => { reachable = false; return false; });

    if (ok) {
      try { localStorage.setItem(STORAGE.AUTH, `${today()}|${input}`); } catch {}
      setOfflineMode(false);
      hideLogin();
      document.getElementById("accessCodeInput").value = "";
      settleCodePrompt(true);
      refusals = 0;
      document.getElementById("loginError").classList.add("hidden");
      offlineBtn?.classList.add("hidden");
      // Anything collected while the proxy was down can go up now.
      import('./failsafe.js').then(m => m.retryPending()).catch(() => {});
    } else if (!reachable) {
      // No proxy, no way to check a code — let them work and keep the responses.
      document.getElementById("accessCodeInput").value = "";
      enterOfflineMode();
    } else {
      document.getElementById("loginError").classList.remove("hidden");
      // The proxy is answering but will not take this code. After a few tries
      // that is indistinguishable from an outage, so offer the override.
      if (++refusals >= MAX_CODE_TRIES) offlineBtn?.classList.remove("hidden");
    }
  };

  document.getElementById("codeSubmit").addEventListener("click", submit);
  document.getElementById("accessCodeInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); submit(); }
  });
  document.addEventListener('keydown', (e) => {
    const modal = document.getElementById('loginModal');
    if (modal && !modal.classList.contains('hidden') && e.key === 'Enter') {
      e.preventDefault();
      submit();
    }
  });
}