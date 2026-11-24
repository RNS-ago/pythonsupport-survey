// The page around the dashboard chart. dashboard_template.html defines spec, embedOpt, grow, axes and filterLabels
// before it.

const scheme = document.querySelector('meta[name="color-scheme"]');
const deviceDark = matchMedia('(prefers-color-scheme: dark)');
const isDark = () => scheme.content === 'dark' || (scheme.content !== 'light' && deviceDark.matches);
spec.params.find(param => param.name === 'dark').value = isDark();  // the chart starts in the page's theme

// Vega-Lite moves the Dates brush along whenever the Dates axis rescales, as widening it does, but fails while no
// dates are picked ("can't access property 0 of undefined") and stops the redraw. Then there is nothing to move.
function guardBrush(vega) {
  for (const signal of vega.signals || []) {
    if (signal.name !== 'dates_x') continue;
    for (const handler of signal.on || []) {
      if (handler.events && handler.events.signal === 'dates_scale_trigger') {
        handler.update = 'isArray(dates_week) ? ' + handler.update + ' : dates_x';
      }
    }
  }
  (vega.marks || []).forEach(guardBrush);
  return vega;
}
// Visitors by study start and gender is as tall as the study lines beside it, also when a filter changes how many
// lines there are: its height follows theirs. Vega-Lite can only give it a fixed one.
function matchHeights(vega) {
  vega.signals.find(signal => signal.name === 'study_start_height').update = 'study_lines_height';
  return vega;
}
// Lets the page set the Dates brush by dates, through Vega-Lite's own steps (the brush, its store, the filter):
// `dates_set` [from, to] draws it there, [] clears it. The brush's own signals sit inside the Dates chart.
function brushControl(vega) {
  vega.signals.push({name: 'dates_set', value: null});
  (function walk(group) {
    for (const signal of group.signals || []) {
      if (signal.name === 'dates_x') signal.on.push({
        events: {signal: 'dates_set'},
        update: "length(dates_set) ? [scale('timeline_x', dates_set[0]), scale('timeline_x', dates_set[1])] : []",
      });
    }
    (group.marks || []).forEach(walk);
  })(vega);
  return vega;
}
embedOpt.patch = vega => brushControl(matchHeights(guardBrush(vega)));

// A tooltip as vega-tooltip draws it, a row per field, but a field holding {rows: [[line, visitors], ...]}, as Other
// study lines has, shows how many there are, then a row each, the largest first.
function tooltipRows(value, escape) {
  if (typeof value !== 'object') return escape(value);
  const row = (key, text) => '<tr><td class="key">' + escape(key) + '</td><td class="value">' + escape(text) + '</td></tr>';
  let rows = '';
  for (const [key, text] of Object.entries(value)) {
    if (!Array.isArray(text?.rows)) {
      rows += row(key, text);
      continue;
    }
    rows += row(key, text.rows.length);
    const pairs = text.rows.slice().sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    for (const [line, count] of pairs) rows += row(line, count);
  }
  return '<table>' + rows + '</table>';
}
embedOpt.tooltip = {formatTooltip: tooltipRows};

// A filter's picks are its selection's store; Dates' go through the brush, which then shows them.
function setPicks(view, name, picks) {
  if (name === 'dates') view.signal('dates_set', picks.length ? picks[0].values[0].slice() : []);
  else view.data(name + '_store', picks);
}

// A chip's text: the filter's name and its picks, Dates' as a range of days. A pick of a list of values, as a part of
// Other study lines makes, shows them in brackets.
function describe(name, picks) {
  const day = date => new Date(date).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric'});
  const list = values => values.length === 1 ? values[0] : '(' + values.join(', ') + ')';
  const values = picks.map(pick => pick.values.map(
    (value, i) => pick.fields[i].type === 'R' ? value.map(day).join(' – ') : Array.isArray(value) ? list(value) : value,
  ).join(' · '));
  return filterLabels[name] + ': ' + values.join(', ');
}

// Sets each axis signal to the width its axis's labels and title take in the viewer's font, the widest of the charts
// sharing it, so they start at the chart's left edge, under its title. The notebook's widths are guesses. Returns
// whether any changed.
function fitAxes(view) {
  const need = {};
  (function walk(group) {
    for (const mark of group.items) {
      if (mark.marktype !== 'group') continue;
      const chart = mark.name && mark.name.endsWith('_group') && mark.name.slice(0, -'_group'.length);
      for (const item of mark.items) {
        if (chart in axes) {
          const signal = axes[chart];
          for (const axis of item.items) {
            const box = axis.role === 'axis' && axis.items[0];
            // Only an axis with labels: Vega-Lite draws the grid as a second axis, and a chart a filter empties has
            // none, so it keeps its width for when they come back.
            if (!box || box.orient !== 'left' || !box.items.some(m => m.role === 'axis-label' && m.items.length)) continue;
            // Its bounds are in the chart's coordinates, so x1 is how far it reaches left of the chart's edge.
            need[signal] = Math.max(need[signal] || 0, view.signal(signal) - box.bounds.x1);
          }
        }
        walk(item);
      }
    }
  })(view.scenegraph().root.items[0]);
  let changed = false;
  for (const signal in need) {
    const width = Math.ceil(need[signal]);
    if (width !== view.signal(signal)) {
      view.signal(signal, width);
      changed = true;
    }
  }
  return changed;
}

vegaEmbed('#vis', spec, embedOpt).then(async ({view}) => {
  fitAxes(view);
  // The Dates chart misses the first change of dates_set: spend it on [], which clears nothing.
  view.signal('dates_set', []);
  // Before measuring the page, so view.origin() no longer counts labels hanging left; Vega updates it on resize only.
  await view.resize().runAsync();
  const container = view.container();
  const built = {};
  for (const name in grow) built[name] = view.signal(name);
  const widest = Math.max(...Object.values(built));  // the dividers, which span the page
  // How far the plots start from the left edge: Vega's padding, and view.origin(), what hangs left of them.
  const margin = view.padding().left + view.origin()[0];
  // The page as built, less the widest: both margins, and whatever sticks out past the widest's right end, like a
  // last axis label. The extra width goes to the charts only up to the window's edge. Measured below, once the
  // filters room ends where the dividers do.
  let around;
  let pageWidth = widest;  // where the dividers end, and so the filters room
  let frame = 0;

  function fit() {
    frame = 0;
    const extra = Math.max(0, container.clientWidth - around - widest);
    for (const name in grow) view.signal(name, built[name] + Math.floor(extra * grow[name]));
    pageWidth = widest + extra;
    // Without resize(), Vega keeps the canvas size and cuts off what grew past it.
    return view.resize().runAsync().then(sync);
  }

  // The filters in use, listed in the room the `filters` chart leaves under its title. Switching one off parks its
  // picks here and clears it, so the charts act as without it; switching it on puts them back. Picking in its chart
  // again replaces what was parked.
  const panel = document.getElementById('filters');
  const parked = {};
  // Lucide's x icon (ISC license)
  const removeIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" '
    + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';

  function button(className, text, onClick) {
    const element = document.createElement('button');
    element.type = 'button';
    element.className = className;
    element.textContent = text;
    element.addEventListener('click', onClick);
    return element;
  }

  // After a change from the list: Vega applies it, then the list and the axes follow the new counts.
  const apply = () => view.runAsync().then(() => {
    list();
    refitAxes();
  });

  function chip(name, on, picks) {
    const text = describe(name, picks);
    const toggle = button('switch', text, () => {
      if (on) parked[name] = picks.slice();
      else delete parked[name];
      setPicks(view, name, on ? [] : picks);
      apply();
    });
    toggle.setAttribute('aria-pressed', on);
    toggle.title = text + (on ? ' (on: click to switch it off)' : ' (off: click to switch it on)');
    const remove = button('remove', '', () => {
      delete parked[name];
      setPicks(view, name, []);
      apply();
    });
    remove.innerHTML = removeIcon;
    remove.setAttribute('aria-label', 'Remove ' + text);
    remove.title = 'Remove';
    const element = document.createElement('span');
    element.className = on ? 'filter on' : 'filter';
    element.append(toggle, remove);
    return element;
  }

  function list() {
    const items = [];
    for (const name in filterLabels) {
      const picks = view.data(name + '_store');
      if (picks.length) delete parked[name];
      if (picks.length || parked[name]) items.push(chip(name, picks.length > 0, picks.length ? picks : parked[name]));
    }
    if (items.length) {
      items.push(button('clear', 'Clear all', () => {
        for (const name in filterLabels) {
          delete parked[name];
          setPicks(view, name, []);
        }
        apply();
      }));
    } else {
      const none = document.createElement('span');
      none.className = 'none';
      none.textContent = 'No filters';
      items.push(none);
    }
    panel.replaceChildren(...items);
    return sync();
  }

  // Where the `filters` chart starts: its offset through the groups it's in.
  function locate() {
    let at = null;
    (function walk(group, x, y) {
      for (const mark of group.items) {
        if (mark.marktype !== 'group') continue;
        for (const item of mark.items) {
          if (mark.name === 'filters_group') at = {x: x + item.x, y: y + item.y};
          else walk(item, x + item.x, y + item.y);
        }
      }
    })(view.scenegraph().root.items[0], 0, 0);
    return at;
  }

  // The list sits over the `filters` chart, past the page's margins and 3px down, where the Count buttons' 34px start
  // in their 40. The chart ends where the dividers do, wherever the KPIs' text left it to start, and is as tall as
  // the list, so a long one pushes the charts down instead of covering them.
  function sync() {
    const at = locate();
    const width = pageWidth - at.x;
    const box = container.getBoundingClientRect();
    const top = parseFloat(container.style.paddingTop) + view.padding().top + view.origin()[1];
    panel.style.left = box.left + scrollX + margin + at.x + 'px';
    panel.style.top = box.top + scrollY + top + at.y + 3 + 'px';
    panel.style.width = width + 'px';
    const height = Math.max(40, panel.offsetHeight + 6);
    if (width === view.signal('filters_width') && height === view.signal('filters_height')) return Promise.resolve();
    return view.signal('filters_width', width).signal('filters_height', height).resize().runAsync().then(sync);
  }

  const showTheme = () => view.signal('dark', isDark()).runAsync();

  // As much room above the title as left of the plots; Vega's padding is above it already.
  container.style.paddingTop = Math.max(0, margin - view.padding().top) + 'px';
  document.documentElement.style.setProperty('--page-margin', margin + 'px');
  await list();
  around = container.querySelector('svg, canvas').getBoundingClientRect().width - widest;  // vega-embed draws in an svg
  await fit();
  // A pick in a chart. Vega calls data listeners mid-run, where list() can't start another: list on the next frame.
  let listing = 0;
  const relist = () => { listing = listing || requestAnimationFrame(() => { listing = 0; list(); }); };
  for (const name in filterLabels) view.addDataListener(name + '_store', relist);
  window.addEventListener('resize', () => { frame = frame || requestAnimationFrame(fit); });
  // Filters change the counts, and so the labels: fit the axes again after each click or drag, once Vega has applied
  // it. No resize: the page stays put, only plots move by what their labels gained or lost.
  let refit = 0;
  const refitAxes = () => {
    refit = refit || requestAnimationFrame(async () => {
      refit = 0;
      await view.runAsync();
      if (fitAxes(view)) view.runAsync();
    });
  };
  view.addEventListener('click', refitAxes);
  view.addEventListener('pointerup', refitAxes);
  // The opposite of what is on screen. When that is the device's own theme, follow the device again instead of
  // pinning it; a pick stays when the device switches later.
  document.getElementById('theme').addEventListener('click', () => {
    const target = isDark() ? 'light' : 'dark';
    scheme.content = target === (deviceDark.matches ? 'dark' : 'light') ? 'light dark' : target;
    showTheme();
  });
  deviceDark.addEventListener('change', showTheme);
}).catch(console.error);
