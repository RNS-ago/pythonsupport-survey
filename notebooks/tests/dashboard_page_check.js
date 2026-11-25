// Runs a built dashboard page's scripts in Node.js and checks what dashboard.js does. test_dashboard_page.py builds the
// page and passes what to expect:  node dashboard_page_check.js <page.html> <expected JSON>
//
// There is no browser: a few stand-in elements take the page's DOM calls, Vega draws nothing (renderer 'none') and
// estimates text widths, and clicks call the listeners Vega and dashboard.js registered.
const fs = require('fs');
const vm = require('vm');

const [page, expectedJSON] = process.argv.slice(2);
const expected = JSON.parse(expectedJSON);

function element(tag = 'div') {
  return {
    tagName: tag.toUpperCase(), style: {setProperty() {}}, children: [], childNodes: [], attributes: {}, listeners: {},
    classList: {add() {}, remove() {}, contains: () => false, toggle() {}},
    clientWidth: 2000, offsetHeight: 34, textContent: '', innerHTML: '', content: 'light dark',
    appendChild(child) { this.children.push(child); this.childNodes.push(child); return child; },
    insertBefore(child) { return this.appendChild(child); },
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    removeChild() {}, remove() {}, focus() {},
    setAttribute(key, value) { this.attributes[key] = value; }, getAttribute(key) { return this.attributes[key]; },
    removeAttribute() {}, hasAttribute: () => false, contains: () => false,
    addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }, removeEventListener() {},
    getRootNode: () => document, querySelector: () => element('svg'), querySelectorAll: () => [],
    getBoundingClientRect: () => ({left: 0, top: 0, width: 1500, height: 3000}), getContext: () => null,
  };
}
const byId = {};
const errors = [];
console.error = (...args) => errors.push(args.map(String).join(' '));
globalThis.window = globalThis;
globalThis.ShadowRoot = class {};
globalThis.document = {
  createElement: element, createElementNS: (namespace, tag) => element(tag), head: element('head'), body: element('body'),
  documentElement: element('html'), getElementById: id => (byId[id] ||= element()),
  querySelector: () => (byId.scheme ||= element('meta')), addEventListener() {}, removeEventListener() {},
  fullscreenElement: null,
};
globalThis.matchMedia = () => ({matches: false, addEventListener() {}});
globalThis.requestAnimationFrame = callback => setTimeout(callback, 0);
globalThis.scrollX = 0;
globalThis.scrollY = 0;
globalThis.addEventListener = () => {};

const scripts = [...fs.readFileSync(page, 'utf8').matchAll(/<script type="text\/javascript">\n([\s\S]*?)<\/script>/g)];
let embedded;
scripts.forEach(([, code], i) => {
  vm.runInThisContext(code, {filename: 'script ' + (i + 1)});
  if (i === 0) {
    const vegaEmbed = window.vegaEmbed;
    window.vegaEmbed = (target, spec, options) => (embedded = vegaEmbed(element(), spec, {...options, renderer: 'none'}));
  }
});

let failed = 0;
function check(ok, message) {
  console.log((ok ? 'ok   ' : 'FAIL ') + message);
  if (!ok) failed++;
}
const settle = () => new Promise(resolve => setTimeout(resolve, 300));

(async () => {
  const {view} = await embedded;
  await settle();
  function items(mark = view.scenegraph().root, out = []) {
    for (const item of mark.items || []) {
      out.push(item);
      for (const child of item.items || []) if (child.marktype) items(child, out);
    }
    return out;
  }
  const bars = name => items().filter(item => item.mark && item.mark.marktype === 'rect' && item.mark.name === name);
  const lineBars = () => items().filter(item => item.datum && 'line' in item.datum && 'line_rank' in item.datum);
  const otherParts = () => lineBars().filter(item => item.datum.line === 'Other study lines');
  const kpi = () => items().find(item => item.mark && item.mark.marktype === 'text' && item.datum
    && 'rating' in item.datum && 'unique' in item.datum && Object.keys(item.datum).length < 12).datum;
  const clickHandlers = view._handler.handlers().filter(handler => handler.type === 'click');
  async function click(item, shiftKey = false) {
    const event = {type: 'click', shiftKey, clientX: 0, clientY: 0, preventDefault() {}, stopPropagation() {}};
    for (const handler of clickHandlers) handler.handler(event, item);
    await settle();
  }
  async function press(button) {
    button.listeners.click.forEach(listener => listener());
    await settle();
  }
  const panel = byId.filters;
  const chips = () => panel.children.filter(child => child.className && child.className.startsWith('filter'));
  const stores = () => Object.keys(filterLabels).reduce((n, name) => n + view.data(name + '_store').length, 0);

  check(errors.length === 0, 'the page loads without errors' + (errors.length ? ': ' + errors[0] : ''));
  check(panel.children.length === 1 && panel.children[0].textContent === 'No filters', 'the list of filters says No filters');
  check(kpi().visits === expected.visits, 'All visitors counts every visit: ' + kpi().visits);
  check(view.signal('timeline_width') > expected.timeline_width, 'Dates widens to the window: '
    + view.signal('timeline_width') + 'px, built ' + expected.timeline_width + 'px');
  const guesses = Object.fromEntries(spec.params.filter(param => Object.values(axes).includes(param.name))
    .map(param => [param.name, param.value]));
  const fitted = Object.keys(guesses).filter(name => view.signal(name) !== guesses[name]);
  check(fitted.length > 0 && Object.keys(guesses).every(name => Number.isInteger(view.signal(name))),
    'the y axes are fitted to their labels: ' + fitted.length + ' of ' + Object.keys(guesses).length + ' changed');
  check(view.signal('filters_width') > 0 && panel.style.width === view.signal('filters_width') + 'px',
    'the list of filters fills the room the Filters chart leaves');

  // A filter's chip: on, switched off (its picks parked), on again, removed.
  await click(bars('semester_bars_marks').find(item => item.datum.semester === expected.semester));
  const semesterChip = () => chips().find(chip => chip.children[0].textContent === 'Semester: ' + expected.semester);
  check(semesterChip() && semesterChip().className === 'filter on' && kpi().visits === expected.semester_visits,
    'clicking ' + expected.semester + ' lists it and filters to its ' + kpi().visits + ' visits');
  await press(semesterChip().children[0]);
  check(semesterChip() && semesterChip().className === 'filter' && stores() === 0 && kpi().visits === expected.visits,
    'switching its chip off keeps it listed, off, and the page shows every visit');
  await press(semesterChip().children[0]);
  check(view.data('semester_pick_store').length === 1 && kpi().visits === expected.semester_visits,
    'switching it on again puts the pick back');
  await press(semesterChip().children[1]);
  check(!semesterChip() && stores() === 0 && panel.children[0].textContent === 'No filters', 'its × removes it');

  // Dates, which go through the brush.
  view.signal('dates_set', expected.dates.map(date => new Date(date)));
  await view.runAsync();
  await settle();
  const datesChip = () => chips().find(chip => chip.children[0].textContent.startsWith('Dates: '));
  check(datesChip() && kpi().visits === expected.dates_visits,
    'a Dates brush is listed (' + (datesChip() || {children: [{}]}).children[0].textContent + ') and filters to '
    + kpi().visits + ' visits, expected ' + expected.dates_visits);
  await press(datesChip().children[0]);
  check(view.data('dates_store').length === 0 && datesChip().className === 'filter', 'switching Dates off clears the brush');
  await press(datesChip().children[0]);
  check(view.data('dates_store').length === 1 && kpi().visits === expected.dates_visits, 'switching it on draws it again');
  await click(bars('semester_bars_marks')[0]);
  await press(panel.children.find(child => child.className === 'clear'));
  check(stores() === 0 && chips().length === 0, 'Clear all removes every filter');

  // Other study lines: a part per education, its lines in its tooltip, a click picks them all.
  const parts = otherParts();
  const tooltipsSorted = parts.every(part => {
    const cells = [...tooltipRows(part.tooltip, String).matchAll(/class="key">([^<]*)<\/td><td class="value">([^<]*)</g)];
    const at = cells.findIndex(cell => cell[1] === 'Study lines');
    const counts = cells.slice(at + 1).map(cell => +cell[2]);
    return +cells[at][2] === part.datum.lines.rows.length && counts.length === part.datum.lines.rows.length
      && counts.every((count, i) => i === 0 || counts[i - 1] >= count)
      && counts.reduce((sum, count) => sum + count, 0) === part.datum.visitors;
  });
  check(parts.length > 1 && tooltipsSorted, 'Other study lines: ' + parts.length
    + ' parts, each tooltip lists its lines, largest first, adding up to the part');
  await click(parts[0]);
  check(kpi().visits === parts[0].datum.visits && /\(.+\)$/.test(chips()[0].children[0].textContent),
    'clicking a part picks its lines: ' + kpi().visits + ' visits');
  await click(otherParts()[0]);
  check(stores() === 0, 'clicking it again removes the pick');

  const rows = view.scale('study_lines_y').domain();
  check(rows.slice(-3).join() === 'Other study lines,N/A,Unknown',
    'study lines end with Other study lines, N/A, then Unknown');
  const education = lineBars().find(item => item.datum.line === 'Unknown').datum.education_EN;
  const unknownPart = () => lineBars().find(item => item.datum.line === 'Unknown' && item.datum.education_EN === education);
  const [unknownVisits, unknownVerified] = expected.unknown_parts[education];
  await click(unknownPart());
  check(kpi().visits === unknownVisits && kpi().verified === unknownVerified,
    `clicking Unknown's ${education} part shows its ${kpi().visits} visits, ${kpi().verified} verified,` +
    ` expected ${unknownVisits} and ${unknownVerified}`);
  await click(unknownPart());

  // Study line department: N/A and Unknown last, a click filters by it.
  check(view.scale('line_department_bars_y').domain().slice(-2).join() === 'N/A,Unknown',
    'study line departments end with N/A, then Unknown');
  const departmentBars = bars('line_department_bars_marks');
  check(departmentBars.length > 1 && departmentBars.every(bar => bar.datum.lines.rows.length
    && bar.datum.lines.rows.reduce((sum, row) => sum + row[1], 0) === bar.datum.visitors)
    && Object.keys(departmentBars[0].tooltip).join() === 'Study line department,Average rating,Study lines,'
      + 'All visitors,Identified visitors,Verified visitors,Unique visitors',
    "each study line department's tooltip lists the study lines that add up to it, between the rating and the counts");
  await click(bars('line_department_bars_marks').find(item => item.datum.line_department === 'DTU Compute'));
  check(kpi().visits === expected.compute_line_visits
    && chips()[0].children[0].textContent === 'Study line department: DTU Compute',
    'clicking DTU Compute in Study line department filters to its ' + kpi().visits + ' visits, expected '
    + expected.compute_line_visits);
  await press(panel.children.find(child => child.className === 'clear'));

  // Legend entries pick as a click on their bar does.
  function inChart(item, chart) {
    for (let mark = item.mark; mark; mark = mark.group && mark.group.mark) if (mark.name === chart + '_group') return true;
    return false;
  }
  const entry = (chart, value) => items().find(item => item.mark && item.mark.role === 'legend-label'
    && item.datum.value === value && inChart(item, chart));
  await click(entry('weekday', 'Female'));
  check(view.data('gender_pick_store').length === 1 && kpi().visits === expected.female_visits
    && chips()[0].children[0].textContent === 'Gender: Female',
    'clicking Female in a gender legend picks it: ' + kpi().visits + ' visits, expected ' + expected.female_visits);
  await click(bars('gender_bars_marks').find(item => item.datum.gender === 'Female'));
  check(stores() === 0, "clicking Female's bar takes the legend's pick back");
  await click(entry('ai_course', 'Yes'));
  await click(entry('ai_course', 'No'), true);
  check(view.data('ai_pick_store').length === 2 && kpi().visits === expected.yes_no_visits,
    'shift-clicking a second AI legend entry adds it: ' + kpi().visits + ' visits, expected ' + expected.yes_no_visits);
  await click(entry('ai_course', 'No'));
  check(view.data('ai_pick_store').length === 1 && view.data('ai_pick_store')[0].values[0] === 'Yes',
    'clicking a picked entry takes back only that one');
  await click(entry('ai_course', 'Yes'));
  await click(entry('study_lines', 'Other'));
  const otherPick = view.data('education_pick_store')[0];
  check(otherPick && Array.isArray(otherPick.values[0]) && otherPick.values[0].length > 1
    && kpi().visits === expected.other_visits && /^Education: \(.+\)$/.test(chips()[0].children[0].textContent),
    "clicking Other in the study lines' legend picks its educations: " + kpi().visits + ' visits, expected '
    + expected.other_visits);
  await click(lineBars().find(item => item.datum.line_rank === 1));
  await click(entry('study_lines', 'Other'));
  check(view.data('line_pick_store').length === 1 && view.data('education_pick_store').length === 0,
    "a click on the study lines' legend keeps the study line picked");
  await press(panel.children.find(child => child.className === 'clear'));
  await click(entry('cumulative', 'Earlier Fall semesters'));
  const fallPick = view.data('semester_pick_store')[0];
  check(fallPick && Array.isArray(fallPick.values[0]) && !fallPick.values[0].includes(expected.semester)
    && fallPick.values[0].every(semester => semester.startsWith('Fall')) && kpi().visits === expected.earlier_fall_visits,
    "clicking Earlier Fall semesters in Cumulative's legend picks them: " + kpi().visits + ' visits, expected '
    + expected.earlier_fall_visits);
  await click(entry('cumulative', 'Earlier Fall semesters'));
  check(stores() === 0, 'clicking it again takes them back');

  // The Count buttons change what every bar counts.
  await click(items().find(item => item.datum && item.datum.mode === 'Unique visitors' && item.mark.marktype === 'rect'));
  check(otherParts().every(part => part.datum.lines.rows.reduce((sum, row) => sum + row[1], 0) === part.datum.unique),
    'under Unique visitors, Other study lines counts each student once');

  await press(byId.theme);
  check(view.signal('dark') === true && byId.scheme.content === 'dark', 'the theme button switches to dark');
  await press(byId.theme);
  check(view.signal('dark') === false && byId.scheme.content === 'light dark', 'and back to following the device');

  check(errors.length === 0, 'no errors along the way' + (errors.length ? ': ' + errors[0] : ''));
  process.exitCode = failed ? 1 : 0;
})().catch(error => {
  console.log('FAIL ' + (error.stack || error));
  process.exitCode = 1;
});
