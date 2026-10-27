import { linkToken, isQrLink } from './config.js';
import { isAuthValid, showLogin, hideLogin, wireLogin, isOfflineMode, setOfflineMode } from './auth.js';
import { wireKiosk, isKiosk } from './kiosk.js';
import { wireBuildingPage, showSurveyForm, showModeSelection } from './building.js';
import { wireSurveyForm } from './survey.js';
import { wireFailsafe } from './failsafe.js';
import { wireProblemLog } from './problem-log.js';

async function loadPartial(selector, url){
  const host = document.querySelector(selector);
  const res = await fetch(url);
  host.innerHTML = await res.text();
}

// Load all partials first
await loadPartial('#sidebarContainer',   './partials/sidebar.html');
await loadPartial('#modeSelectionContainer', './partials/mode-selection.html');
await loadPartial('#buildingSelectionContainer', './partials/building-selection.html');
await loadPartial('#surveyContainer',    './partials/survey-form.html');
await loadPartial('#analyticsContainer', './partials/analytics.html');
await loadPartial('#problemLogContainer', './partials/problem-log.html');
await loadPartial('#modalsContainer',    './partials/modals.html');

// Wire features that depend on DOM. wireBuildingPage also sets the sidebar, back link and
// FAB visibility, and the globals the partials' inline handlers call.
wireLogin();
wireKiosk();
wireBuildingPage();
wireSurveyForm();
wireFailsafe();
wireProblemLog();

// Student-flow layout rule: hide header/pages for students (token/QR or kiosk)
document.body.classList.toggle('student-flow', !!(linkToken || isQrLink || isKiosk()));

// Show/hide login. A supporter already let in without a code stays in
if (linkToken || isQrLink)  { hideLogin(); }
else if (isAuthValid())     { hideLogin(); }
else if (isOfflineMode())   { setOfflineMode(true); hideLogin(); }
else                        { showLogin(); }

// Initial page: students and tablets go straight to the survey; supporters choose a form
if (linkToken || isQrLink || isKiosk()) showSurveyForm();
else                                    showModeSelection();
