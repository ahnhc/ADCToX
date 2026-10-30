/* ADCTOX browser UI: the TUI's five steps (ml/form.py, ml/recommend.py) over the local server's /api (ml/webapp.py).
   No framework, no build step. index.html?mock=1 runs on the fixtures in mock.js (window.ADCTOX_MOCK, same shapes). */
(function () {
  'use strict';

  const Q = new URLSearchParams(location.search);
  // the mock and its parameters (theme, motion, step, adc, q) only for the page opened as a file; over http they are ignored
  const MOCK = location.protocol === 'file:' && Q.get('mock') === '1' && window.ADCTOX_MOCK ? window.ADCTOX_MOCK : null;
  const ROOT = document.documentElement;
  const REDUCE = window.matchMedia ? matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
  const still = () => ROOT.classList.contains('still') || REDUCE.matches;

  // ------------------------------------------------------------------ the server: one small object (the mock has the same methods)
  async function call(method, url, body) {
    const res = await fetch(url, {
      method, cache: 'no-store',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (!res.ok) {                        // the server's error line as it sent it, and the whole answer with it
      const err = new Error((data && data.error) || `HTTP ${res.status}`);
      err.status = res.status; err.data = data;
      throw err;
    }
    return data;
  }
  const API = MOCK || {
    app: () => call('GET', '/api/app'),
    suggest: (q, picked, ai) => call('GET', '/api/suggest?' + new URLSearchParams(
      [['q', q]].concat((picked || []).map((p) => ['picked', p]), ai ? [['ai', '1']] : []))),
    labs: (raw) => call('POST', '/api/labs', { raw }),
    analyze: (conditions, choice) => call('POST', '/api/analyze', { conditions, choice }),
    job: (id) => call('GET', '/api/analyze/' + encodeURIComponent(id)),
    recommend: (body) => call('POST', '/api/recommend', body),
  };

  // ------------------------------------------------------------------ DOM helpers
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    if (props) for (const k in props) {
      const v = props[k];
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    add(el, kids);
    return el;
  }
  function add(el, kids) {
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false || kid === '') continue;
      el.append(kid.nodeType ? kid : String(kid));
    }
    return el;
  }
  const SVGNS = 'http://www.w3.org/2000/svg';
  function sv(tag, attrs, ...kids) {
    const el = document.createElementNS(SVGNS, tag);
    for (const k in attrs || {}) el.setAttribute(k, attrs[k]);
    for (const kid of kids.flat()) if (kid) el.append(kid);
    return el;
  }
  const clear = (el) => { while (el.firstChild) el.firstChild.remove(); return el; };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const kbd = (k, label) => h('span', null, h('kbd', { text: k }), label);

  // ------------------------------------------------------------------ app data (GET /api/app)
  let APP = null, AX = [], SHORT = {}, REG = {}, REG_I = {}, FIELDS = [], STEPS = [];
  const TONE = { contraindicated: 'red', avoid: 'red', insufficient_data: 'amber', no_statement: 'amber', reduce_dose: 'cyan', monitor: 'cyan', no_adjustment: 'green' };
  const STATE_TONE = { None: 'green', Monitor: 'cyan', 'No data': 'amber', 'Not studied': 'amber', Avoid: 'red' };

  // ------------------------------------------------------------------ state (kept in sessionStorage; nothing on the server)
  const KEY = 'adctox.web.1';
  const blank = () => ({ step: 0, reached: 0, conds: [], raw: {}, labs: null, meanings: {}, first: null, analysis: null, result: null, sel: -1, drawer: false });
  let S = blank();
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* private mode: the page still works */ }
  }
  function restore() {
    try { const d = JSON.parse(sessionStorage.getItem(KEY) || 'null'); if (d && typeof d === 'object') S = Object.assign(blank(), d); } catch (e) { S = blank(); }
  }

  // conditions as form.run sends them: registry picks in registry order, then the typed texts in the order they were added
  const regName = (id) => (REG[id] ? REG[id].label.replace(/\s*\([^)]*\)/g, '') : id);        // recommend.condition_name
  function condList() {
    const reg = S.conds.filter((c) => c.kind === 'reg').map((c) => c.value).sort((a, b) => (REG_I[a] ?? 1e9) - (REG_I[b] ?? 1e9));
    return reg.concat(S.conds.filter((c) => c.kind !== 'reg').map((c) => c.label));
  }
  const condName = (c) => (REG[c] ? regName(c) : c);
  function pickChoice() {                 // {typed name: MONDO id} for the names picked from the suggestions
    const out = {};
    for (const c of S.conds) if (c.kind === 'mondo') out[c.label] = c.value;
    return out;
  }
  const allChoice = () => Object.assign(pickChoice(), S.meanings);
  const rawValues = () => Object.fromEntries(Object.entries(S.raw).filter(([, v]) => String(v).trim() !== ''));
  // a chip's MONDO id: its own, or its registry entry's (Cirrhosis and "Cirrhosis of liver" are one disease)
  const chipMondo = (c) => c.mondo || (c.kind === 'mondo' ? c.value : c.kind === 'reg' && REG[c.value] ? REG[c.value].mondo || null : null);
  function pickedList() {                 // /api/suggest picked=: every chip's registry id, text and MONDO id, and the readings chosen
    const out = [];
    for (const c of S.conds) { if (c.kind === 'reg') out.push(c.value); out.push(c.label); const m = chipMondo(c); if (m) out.push(m); }
    for (const v of Object.values(S.meanings)) if (v) out.push(v);
    return [...new Set(out)];
  }
  // Every number on the page is the server's text (labs.shown, form.likely, recommend._event_text); the page never rounds one.

  // ------------------------------------------------------------------ the 13-cell organ strip (AXES order) with the short names
  function strip(organs, opts) {
    const on = new Set(organs || []);
    const o = opts || {};
    const names = AX.filter((a) => on.has(a)).map((a) => SHORT[a]);
    return h('span', { class: 'strip', title: names.join(', ') || null },
      h('span', { class: 'cells', 'aria-hidden': 'true' }, AX.map((a) => h('i', { class: on.has(a) ? 'on' : null }))),
      o.names === false ? null : names.length ? h('span', { class: 'names', text: names.join(' ') }) : o.none === '' ? null : h('span', { class: 'none', text: o.none || '-' }));
  }

  // ================================================================== body map
  // The silhouette: the right half as points, mirrored, through a centripetal Catmull-Rom spline (so it is symmetric by construction).
  const HALF = [
    [180, 22], [193, 24.5], [202.5, 31.5], [207, 44], [207.5, 58], [205.5, 71], [201, 83.5], [196, 92.5], [192.5, 99.5],
    [193, 106.5], [195, 114.5],
    [203, 121.5], [217, 126.5], [230, 131], [240.5, 137], [248, 145.5], [252.5, 156], [255.5, 171],
    [258, 190], [263, 220], [267.5, 250], [274, 276], [278.5, 305], [282.5, 335],
    [288, 351], [291, 367], [290.5, 383], [286.5, 395.5], [281, 401.5], [275.5, 398], [272.5, 384], [270.5, 367], [267.5, 350], [264, 336],
    [256, 305], [247.5, 276], [242.5, 251], [236, 222], [230.5, 202],
    [228.5, 215], [226.5, 235], [223.5, 254], [222, 268], [223.5, 288], [228.5, 308], [232, 329], [232.5, 346],
    [230, 371], [226.5, 400], [222.5, 430], [218.5, 457], [217, 476], [218.5, 500], [218, 525], [213, 552], [208, 579],
    [211, 594], [213, 606], [208.5, 614], [199.5, 616], [192.5, 612], [190.5, 602],
    [191.5, 584], [190.8, 560], [188.2, 530], [187.6, 505], [189, 478], [187.8, 455], [185, 425], [182.6, 398], [181, 372],
    [180, 355]];
  function figurePath() {
    const pts = HALF.concat(HALF.slice(1, -1).reverse().map(([x, y]) => [360 - x, y]));
    const n = pts.length, f = (v) => +v.toFixed(2);
    const dist = (a, b) => Math.sqrt(Math.hypot(b[0] - a[0], b[1] - a[1])) || 1e-6;
    let d = `M${f(pts[0][0])} ${f(pts[0][1])}`;
    for (let i = 0; i < n; i++) {
      const p0 = pts[(i - 1 + n) % n], p1 = pts[i], p2 = pts[(i + 1) % n], p3 = pts[(i + 2) % n];
      const d1 = dist(p0, p1), d2 = dist(p1, p2), d3 = dist(p2, p3);
      const c1 = [0, 1].map((k) => (d1 * d1 * p2[k] - d2 * d2 * p0[k] + (2 * d1 * d1 + 3 * d1 * d2 + d2 * d2) * p1[k]) / (3 * d1 * (d1 + d2)));
      const c2 = [0, 1].map((k) => (d3 * d3 * p1[k] - d2 * d2 * p3[k] + (2 * d3 * d3 + 3 * d3 * d2 + d2 * d2) * p2[k]) / (3 * d3 * (d3 + d2)));
      d += `C${f(c1[0])} ${f(c1[1])} ${f(c2[0])} ${f(c2[1])} ${f(p2[0])} ${f(p2[1])}`;
    }
    return d + 'Z';
  }
  // marker spots per organ axis [x, y, glow size] in the 360 x 640 frame; skin is the outline itself (its spot is for the name)
  const SPOTS = {
    neurologic: [[180, 46, 74]],
    ocular: [[169.5, 63, 20], [190.5, 63, 20]],
    otologic: [[153.5, 66, 20], [206.5, 66, 20]],
    infectious_immune: [[168, 101, 17], [192, 101, 17], [135, 193, 18], [225, 193, 18]],
    metabolic_endocrine: [[180, 116, 24]],
    haematologic: [[180, 149, 22], [151, 318, 22], [209, 318, 22]],
    musculoskeletal: [[119, 150, 26], [241, 150, 26], [149, 346, 26], [211, 346, 26]],
    pulmonary: [[160.5, 182, 56], [199.5, 182, 56]],
    cardiovascular: [[188, 212, 46]],
    hepatic: [[161, 246, 54]],
    renal: [[156.5, 274, 26], [203.5, 274, 26]],
    gastrointestinal: [[181, 294, 56]],
    dermatologic: [[134, 420, 16]],
  };
  // where an organ's name goes when it is lit: side and the spot the leader starts from
  const CALL = {
    neurologic: ['right', 0], ocular: ['left', 0], otologic: ['right', 1], infectious_immune: ['right', 1], metabolic_endocrine: ['left', 0],
    haematologic: ['left', 0], musculoskeletal: ['right', 1], pulmonary: ['left', 0], cardiovascular: ['right', 0], hepatic: ['left', 0],
    renal: ['right', 1], gastrointestinal: ['left', 0], dermatologic: ['left', 0],
  };

  function buildBody() {
    const P = figurePath(), VB = '0 0 360 640';
    const stop = (o, style) => sv('stop', { offset: o, style });
    const base = sv('svg', { class: 'bm-base', viewBox: VB, 'aria-hidden': 'true', focusable: 'false' },
      sv('defs', null,
        sv('pattern', { id: 'bm-grid', width: 20, height: 20, patternUnits: 'userSpaceOnUse' }, sv('path', { d: 'M20 0H0V20', fill: 'none', style: 'stroke: var(--grid)', 'stroke-width': 1 })),
        sv('pattern', { id: 'bm-grid2', width: 100, height: 100, patternUnits: 'userSpaceOnUse', x: 80, y: 20 }, sv('path', { d: 'M100 0H0V100', fill: 'none', style: 'stroke: var(--grid-2)', 'stroke-width': 1 })),
        sv('radialGradient', { id: 'bm-fade', cx: '.5', cy: '.47', r: '.6' }, stop('0', 'stop-color:#fff'), stop('.7', 'stop-color:#fff;stop-opacity:.55'), stop('1', 'stop-color:#fff;stop-opacity:0')),
        sv('mask', { id: 'bm-mask' }, sv('rect', { width: 360, height: 640, fill: 'url(#bm-fade)' })),
        sv('linearGradient', { id: 'bm-fill', x1: 0, y1: 0, x2: 0, y2: 1 }, stop('0', 'stop-color:var(--fig-top)'), stop('1', 'stop-color:var(--fig-bot)')),
        sv('radialGradient', { id: 'bm-hl', gradientUnits: 'userSpaceOnUse', cx: 180, cy: 205, r: 150, gradientTransform: 'translate(180 205) scale(1 2.1) translate(-180 -205)' },
          stop('0', 'stop-color:var(--fig-hl)'), stop('1', 'stop-color:var(--fig-hl);stop-opacity:0')),
        sv('radialGradient', { id: 'bm-floor', cx: '.5', cy: '.5', r: '.5' }, stop('0', 'stop-color:var(--floor)'), stop('1', 'stop-color:var(--floor);stop-opacity:0')),
        sv('clipPath', { id: 'bm-clip' }, sv('path', { d: P })),
        sv('filter', { id: 'bm-blur', x: '-10%', y: '-10%', width: '120%', height: '120%' }, sv('feGaussianBlur', { stdDeviation: 4.5 })),
        sv('filter', { id: 'bm-soft', x: '-10%', y: '-10%', width: '120%', height: '120%' }, sv('feGaussianBlur', { stdDeviation: 2.6 }))),
      sv('g', { mask: 'url(#bm-mask)' }, sv('rect', { width: 360, height: 640, fill: 'url(#bm-grid)' }), sv('rect', { width: 360, height: 640, fill: 'url(#bm-grid2)' })),
      sv('ellipse', { cx: 180, cy: 619, rx: 72, ry: 8, fill: 'url(#bm-floor)' }),
      sv('path', { d: P, fill: 'url(#bm-fill)' }),
      sv('path', { d: P, fill: 'url(#bm-hl)' }),
      sv('g', { 'clip-path': 'url(#bm-clip)' },
        sv('path', { d: P, fill: 'none', style: 'stroke: var(--fig-shade)', 'stroke-width': 10, filter: 'url(#bm-blur)' }),
        sv('path', { d: P, fill: 'none', style: 'stroke: var(--fig-rim)', 'stroke-width': 2.2 })),
      sv('path', { d: P, fill: 'none', style: 'stroke: var(--fig-line)', 'stroke-width': 1 }));
    const skin = sv('svg', { class: 'bm-skin', viewBox: VB, 'aria-hidden': 'true', focusable: 'false' },
      sv('path', { d: P, fill: 'none', style: 'stroke: var(--glow)', 'stroke-width': 5, 'stroke-opacity': '.4', filter: 'url(#bm-soft)' }),
      sv('path', { d: P, fill: 'none', style: 'stroke: var(--glow)', 'stroke-width': 1.4 }));
    const ring = sv('svg', { class: 'bm-ring', viewBox: VB, 'aria-hidden': 'true', focusable: 'false' },
      sv('path', { d: P, fill: 'none', 'stroke-width': 1.3, 'stroke-dasharray': '3 3.5' }));
    const lines = sv('svg', { class: 'bm-lines', viewBox: VB, 'aria-hidden': 'true', focusable: 'false' });
    const marks = h('div', { class: 'mks', style: 'container-type: inline-size' });
    const byAxis = {};
    for (const a of Object.keys(SPOTS)) {
      byAxis[a] = SPOTS[a].map(([x, y, size]) => {
        const mk = h('div', { class: 'mk', style: `left:${(x / 3.6).toFixed(3)}%;top:${(y / 6.4).toFixed(3)}%;--s:${(size / 3.6).toFixed(2)}cqw` },
          h('i', { class: 'g' }), h('i', { class: 'r' }), h('i', { class: 'c' }), h('i', { class: 'hit' }), h('i', { class: 'tip', 'data-axis': a }));
        marks.append(mk);
        return mk;
      });
    }
    const labels = h('div', { class: 'mks' });
    const fig = h('div', { class: 'bm-fig', role: 'img' }, base, skin, ring, lines, marks, labels);
    const cap = h('div', { class: 'bm-cap', 'aria-live': 'polite' });
    const legend = h('div', { class: 'bm-legend', hidden: true },
      h('div', null, h('span', null, 'Organ priority'), h('span', null, h('i', { class: 'lg1' }), '1'), h('span', null, h('i', { class: 'lg2' }), '2+')),
      h('div', null, h('span', null, h('i', { class: 'lgb' }), 'Boxed warning'), h('span', null, h('i', { class: 'lgw' }), 'Warning')));
    const el = h('div', { class: 'bm panel' }, fig, cap, legend);
    let last = '';

    function update(st) {
      const lit = st.lit || {}, rings = st.rings || {};
      const sig = JSON.stringify([lit, rings, st.caption || '', !!st.legend]);
      if (sig === last) return;
      last = sig;
      for (const a in byAxis) {
        const cls = 'mk' + (lit[a] ? ' ' + lit[a] : '') + (rings[a] ? ' r' + rings[a] : '');
        for (const mk of byAxis[a]) if (mk.className !== cls) mk.className = cls;
      }
      const skinCls = ['skin-on', 'skin-l1', 'skin-l2', 'skin-rb', 'skin-rw'];
      fig.classList.remove(...skinCls);
      if (lit.dermatologic) fig.classList.add('skin-' + lit.dermatologic);
      if (rings.dermatologic) fig.classList.add('skin-r' + rings.dermatologic);
      // names of the lit organs at the sides, with a hairline to the organ
      clear(labels); clear(lines);
      const sides = { left: [], right: [] };
      for (const a of AX) if (lit[a] && SPOTS[a]) {
        const [side, k] = CALL[a]; const [x, y] = SPOTS[a][k];
        sides[side].push({ a, x, y, ly: y, lv: lit[a] });
      }
      for (const side of ['left', 'right']) {
        const items = sides[side].sort((p, q) => p.y - q.y);
        for (let i = 1; i < items.length; i++) items[i].ly = Math.max(items[i].ly, items[i - 1].ly + 15);
        for (const it of items) {
          const lx = side === 'left' ? 62 : 298;
          const cls = it.lv === 'l2' ? 'l2' : '';
          lines.append(sv('line', { x1: side === 'left' ? lx + 4 : lx - 4, y1: it.ly, x2: it.x + (side === 'left' ? -5 : 5), y2: it.y, class: cls }));
          labels.append(h('span', {
            class: `co ${side} ${cls}`, text: SHORT[it.a],
            style: `top:${(it.ly / 6.4).toFixed(3)}%;` + (side === 'left' ? `right:${((360 - lx) / 3.6).toFixed(3)}%` : `left:${(lx / 3.6).toFixed(3)}%`),
          }));
        }
      }
      const names = AX.filter((a) => lit[a]).map((a) => SHORT[a]);
      fig.setAttribute('aria-label', 'Body map' + (names.length ? ': ' + names.join(', ') : ''));
      cap.textContent = st.caption || '';
      legend.hidden = !st.legend;
    }
    function names(short) {               // the hover names, once /api/app has sent organ_short
      for (const tip of marks.querySelectorAll('.tip')) tip.textContent = short[tip.dataset.axis] || '';
    }
    update({});
    return { el, update, names };
  }

  // ================================================================== page frame
  let top, crumbsOl, verEl, layout, stageBox, side, bar, barLeft, barKeys, barBtn, drawer, drawerTitle, drawerBody, body;

  function frame() {
    document.title = 'ADCTOX';
    crumbsOl = h('ol');
    verEl = h('div', { class: 'ver', text: '' });
    top = h('header', { class: 'top' }, h('div', { class: 'brand', text: 'ADCTOX' }), h('nav', { class: 'crumbs', 'aria-label': '단계' }, crumbsOl), verEl);
    stageBox = h('main', { class: 'stage' });
    body = buildBody();
    side = h('aside', { class: 'side', 'aria-label': 'Body map', hidden: true }, body.el);
    layout = h('div', { class: 'layout' }, side, stageBox);
    barLeft = h('div', { class: 'left', 'aria-live': 'polite' });
    barKeys = h('div', { class: 'keys', 'aria-hidden': 'true' });
    barBtn = h('button', { class: 'go', type: 'button', hidden: true });      // setBar shows it
    barBtn.addEventListener('click', () => barBtn._act && barBtn._act());
    bar = h('footer', { class: 'bar' }, barLeft, barKeys, barBtn);
    drawerTitle = h('h2', { id: 'dr-title' });
    drawerBody = h('div', { class: 'dr-body' });
    const x = h('button', { class: 'x', type: 'button', 'aria-label': '닫기', text: '×', onclick: () => closeDrawer() });
    drawer = h('div', { class: 'drawer', role: 'dialog', 'aria-modal': 'false', 'aria-labelledby': 'dr-title', 'aria-hidden': 'true' },
      h('div', { class: 'dr-head' }, drawerTitle, x), drawerBody);
    document.body.append(top, h('div', { class: 'wrap' }, layout), bar, drawer);
  }

  function setBar(o) {
    clear(barLeft); add(barLeft, [o.left || '']);
    clear(barKeys); add(barKeys, o.keys || []);
    const b = o.button;
    barBtn.hidden = !b;
    if (b) {
      clear(barBtn); add(barBtn, [b.label, b.key ? h('kbd', { text: b.key }) : null]);
      barBtn.disabled = !!b.disabled; barBtn.className = 'go' + (b.quiet ? ' quiet' : ''); barBtn._act = b.act;
    }
  }

  // ------------------------------------------------------------------ crumbs
  function analysisOrgans() {
    const a = S.analysis;
    if (!a || a.state !== 'done') return [];
    const on = new Set();
    for (const r of a.reports || []) for (const o of organsOf(r)) on.add(o);
    return AX.filter((o) => on.has(o));
  }
  function summary(i) {
    if (i === 0) return condList().map(condName).join(', ');
    if (i === 1) { const n = Object.keys(rawValues()).length; return n ? `${n}개 입력` : '입력 없음'; }
    if (i === 2) {
      const a = S.analysis; if (!a || a.state !== 'done') return '';
      const names = analysisOrgans().map((o) => SHORT[o]);
      if ((a.reports || []).some((r) => r.source === 'Cancer')) names.push('Cancer');
      return names.join(', ') || '-';
    }
    if (i === 3) { const p = patientConds().find((c) => c.key === S.first); return p ? p.name : '자동 (질환 중증도 순)'; }
    return '';
  }
  function renderCrumbs() {
    clear(crumbsOl);
    const prio = S.step >= 2 ? hasPriority() : true;
    STEPS.forEach((name, i) => {
      const skipped = i === 3 && S.step > 3 && !prio;
      const done = i < S.step && !skipped;
      const now = i === S.step;
      const cls = 'crumb' + (now ? ' now' : done ? ' done' : skipped ? ' skip' : '');
      const cb = done ? h('button', { class: 'cb', type: 'button', text: name, onclick: () => go(i) }) : h('span', { class: 'cb', text: name, 'aria-current': now ? 'step' : null });
      const sum = done ? summary(i) : '';
      crumbsOl.append(h('li', { class: cls }, cb, sum ? h('span', { class: 'sum', text: sum, title: sum }) : null));
    });
  }

  // ------------------------------------------------------------------ stage switching: one motion at a time
  let cleanup = null;
  function go(n, keepDrawer) {
    if (cleanup) { cleanup(); cleanup = null; }
    const reopen = S.drawer;
    closeDrawer(true);
    if (keepDrawer) S.drawer = reopen;
    S.step = n; S.reached = Math.max(S.reached, n); save();
    const bodyOn = n >= 2;
    const wasHidden = side.hidden;
    side.hidden = !bodyOn;
    layout.classList.toggle('body-on', bodyOn);
    side.classList.remove('enter');
    if (bodyOn && wasHidden && !still()) { void side.offsetWidth; side.classList.add('enter'); }
    renderCrumbs();
    clear(stageBox);
    stageBox.classList.remove('enter');
    const build = [stage1, stage2, stage3, stage4, stage5][n];
    const node = build();
    stageBox.append(node);
    if (!still()) { void stageBox.offsetWidth; stageBox.classList.add('enter'); }
    window.scrollTo(0, 0);
    if (n < 2) body.update({});
  }
  let busy = false;                       // a step change waiting on the server: PgDn, PgUp and the bar button do nothing meanwhile
  async function next() {
    if (busy) return;
    if (S.step === 0) {
      if (!S.conds.length) { stageNote('질환을 하나 이상 추가하세요'); return; }
      go(1);
    } else if (S.step === 1) {
      busy = true; barBtn.setAttribute('aria-busy', 'true');
      try { if (await labsCommit() && S.step === 1) go(2); } finally { busy = false; barBtn.removeAttribute('aria-busy'); }
    } else if (S.step === 2) {
      const a = S.analysis;
      if (a && a.state === 'done') go(hasPriority() ? 3 : 4);
      else if (a && a.state === 'error') go(0);
    } else if (S.step === 3) go(4);
  }
  function prev() {
    if (busy) return;
    if (S.step === 4) go(hasPriority() ? 3 : 2);
    else if (S.step > 0) go(S.step - 1);
  }
  let stageNote = () => {};

  // ================================================================== step 1: 질환
  function stage1() {
    const st = { q: '', listQ: null, pending: null, items: [], cur: -1, moved: false, armed: false, timer: 0, aiTimer: 0, busyTimer: 0, seq: 0, aiSeq: 0, fresh: -1, lastKey: 0 };
    const chips = h('ul', { class: 'chips', 'aria-label': '선택한 질환' });
    const input = h('input', {
      type: 'text', role: 'combobox', 'aria-expanded': 'false', 'aria-controls': 'sugg', 'aria-autocomplete': 'list', 'aria-label': '질환',
      placeholder: '질환명, 증상, 암종을 입력하세요', autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false',
    });
    const list = h('ul', { class: 'sugg panel', id: 'sugg', role: 'listbox', 'aria-label': '추천', hidden: true });
    const note = h('div', { class: 'note', role: 'status' });
    const status = h('div', { class: 'note busy', 'aria-live': 'polite' });       // the TUI's status line: a search still running, or failed
    const about = h('p', { class: 'about', text: `기저질환, 암종, 검사 수치로 FDA 승인 ADC ${APP.n_adcs || 15}개를 경고가 적은 순서로 보여 줍니다.` });
    stageNote = (t) => { note.textContent = t; };
    const SYM_BUSY = '증상으로 질환 찾는 중 ...   처음 한 번은 모델을 불러 10초쯤 걸립니다';
    // suggest: a text of 4 or more characters and 2 or more words that is not a list of names reads as a sentence (symptom search, no AI names)
    const sentence = (q, parts) => q.length >= 4 && q.split(/\s+/).length >= 2 && !(parts && parts.length);

    const chipKeys = () => {
      const k = new Set();
      for (const c of S.conds) { k.add(`${c.kind}:${c.value}`); k.add('name:' + c.label.toLowerCase()); const m = chipMondo(c); if (m) k.add('mondo:' + m); }
      return k;
    };
    function chipOf(s) {                  // what form.run gets for the row (s.pick): a registry id, or a name with its MONDO or HP id
      const p = s.pick || {};
      if (s.id) return { kind: 'reg', value: s.id, label: s.text, mondo: s.mondo || null };
      if (p.choice) return { kind: 'mondo', value: p.choice, label: p.condition || s.text, mondo: p.choice };
      return { kind: 'text', value: p.condition || s.text, label: p.condition || s.text };
    }
    function addChip(c) {
      const m = chipMondo(c);
      if (S.conds.some((x) => (x.kind === c.kind && x.value === c.value) || x.label.toLowerCase() === c.label.toLowerCase() || (m && chipMondo(x) === m))) return `이미 선택됨: ${c.label}`;
      S.conds.push(c); st.fresh = S.conds.length - 1; save();
      return `추가: ${c.label}`;
    }
    function build(q, r) {                // form.Form.conditions' rows: the split, names, AI names, then diseases from symptoms, then the text as typed
      const have = chipKeys(), seen = new Set(), out = [];
      const fresh = (s) => {
        const keys = [s.id ? 'reg:' + s.id : null, s.mondo ? 'mondo:' + s.mondo : null, 'name:' + String(s.text).toLowerCase(), s.sub ? 'name:' + s.sub.toLowerCase() : null].filter(Boolean);
        if (keys.some((k) => have.has(k) || seen.has(k))) return false;
        keys.forEach((k) => seen.add(k)); return true;
      };
      if (r.parts && r.parts.length) out.push({ kind: 'split', words: r.parts });
      for (const s of r.names || []) if (fresh(s)) out.push({ kind: 's', s });
      for (const s of r.ai || []) if (fresh(s)) out.push({ kind: 'ai', s });
      const sym = (r.symptoms || []).filter(fresh);
      if (sym.length) { out.push({ kind: 'head', text: '증상이나 문장으로 찾은 질환' }); sym.forEach((s) => out.push({ kind: 'sym', s })); }
      out.push({ kind: 'raw', text: q });
      return out;
    }
    const itemKey = (x) => x.kind + ':' + (x.s ? x.s.id || x.s.mondo || x.s.text : x.words ? x.words.join(',') : x.text);
    const selectable = (i) => st.items[i] && st.items[i].kind !== 'head';
    function renderChips() {
      clear(chips);
      S.conds.forEach((c, i) => {
        const x = h('button', { class: 'x', type: 'button', 'aria-label': `${c.label} 빼기`, text: '×' });
        x.addEventListener('click', () => { S.conds.splice(i, 1); save(); st.armed = false; note.textContent = `뺌: ${c.label}`; renderChips(); input.focus(); });
        chips.append(h('li', { class: 'chip' + (i === st.fresh && !still() ? ' fresh' : '') + (st.armed && i === S.conds.length - 1 ? ' armed' : '') }, h('span', { class: 'lbl', text: c.label }), x));
      });
      st.fresh = -1;
      chips.hidden = !S.conds.length;
      about.hidden = !!(S.conds.length || st.q);
      setBar({
        keys: [kbd('Enter', '추가'), kbd('↑↓', '선택'), S.conds.length ? kbd('× 또는 Backspace', '빼기') : null],
        button: { label: '다음', key: 'PgDn', act: next },
      });
    }
    function renderList() {
      clear(list);
      const show = st.items.length > 0 && st.q.trim() !== '';
      list.hidden = !show;
      input.setAttribute('aria-expanded', show ? 'true' : 'false');
      if (!show) { input.removeAttribute('aria-activedescendant'); return; }
      st.items.forEach((it, i) => {
        if (it.kind === 'head') { list.append(h('li', { class: 'head', role: 'presentation', text: it.text })); return; }
        const on = i === st.cur;
        let left;
        if (it.kind === 'split') left = h('span', { class: 'nm main', text: '각각 따로 추가: ' + it.words.join(', ') });
        else if (it.kind === 'raw') left = h('span', { class: 'nm main' }, h('span', { class: 'pre', text: '+ 입력한 그대로 추가:' }), it.text);
        else {                            // names only (the organs come with the analysis); a symptom row says what it matched
          const tail = it.kind === 'sym' ? it.s.why || '' : it.s.sub || '';
          left = h('span', { class: 'nm' }, h('span', { class: 'main', text: it.s.text }), tail ? h('span', { class: 'sub', text: tail }) : null,
            it.kind === 'ai' ? h('span', { class: 'tag', text: 'AI' }) : null);
        }
        const li = h('li', { class: 'opt', role: 'option', id: 'sg-' + i, 'aria-selected': on ? 'true' : 'false' }, left);
        li.addEventListener('mousedown', (e) => e.preventDefault());
        li.addEventListener('mousemove', () => { if (st.cur !== i) { st.cur = i; st.moved = true; mark(); } });
        li.addEventListener('click', () => { st.cur = i; pick(); });
        list.append(li);
      });
      mark();
    }
    function mark() {
      for (const li of list.querySelectorAll('.opt')) li.setAttribute('aria-selected', li.id === 'sg-' + st.cur ? 'true' : 'false');
      if (st.cur >= 0 && selectable(st.cur)) {
        input.setAttribute('aria-activedescendant', 'sg-' + st.cur);
        const li = list.querySelector('#sg-' + st.cur);
        if (li) li.scrollIntoView({ block: 'nearest' });
      } else input.removeAttribute('aria-activedescendant');
    }
    function quiet() {                    // drop the searches in flight and their status line
      clearTimeout(st.timer); clearTimeout(st.aiTimer); clearTimeout(st.busyTimer);
      st.timer = st.aiTimer = st.busyTimer = 0; st.seq++; st.aiSeq++; status.textContent = '';
    }
    async function search() {
      clearTimeout(st.timer); st.timer = 0;
      clearTimeout(st.aiTimer); st.aiSeq++;
      const q = st.q.trim(), seq = ++st.seq;
      clearTimeout(st.busyTimer);
      if (!q) { st.items = []; st.listQ = ''; status.textContent = ''; renderList(); return; }
      if (sentence(q)) st.busyTimer = setTimeout(() => { if (seq === st.seq) status.textContent = SYM_BUSY; }, 250);
      let r;
      const pending = API.suggest(q, pickedList());
      st.pending = { q, p: pending };
      try { r = await pending; } catch (e) { r = { q, names: [], parts: [], ai: [], symptoms: [], symptoms_error: null }; }
      if (seq !== st.seq) return;
      clearTimeout(st.busyTimer);
      status.textContent = r.symptoms_error ? '증상 검색 실패: ' + r.symptoms_error : '';
      st.items = build(q, r); st.listQ = q;
      st.cur = st.items.findIndex((x, i) => selectable(i)); st.moved = false;
      renderList();
      // the AI names: a second request about 500 ms after the last key, when the models are installed and the text is not a sentence
      if (APP.has_learned && q.length >= 2 && !sentence(q, r.parts)) {
        st.aiTimer = setTimeout(() => searchAI(q, seq), Math.max(0, 500 - (performance.now() - st.lastKey)));
      }
    }
    async function searchAI(q, seq) {
      if (seq !== st.seq) return;
      const aseq = ++st.aiSeq;
      st.busyTimer = setTimeout(() => { if (aseq === st.aiSeq) status.textContent = 'AI 추천 찾는 중 ...'; }, 250);
      let r = null;
      try { r = await API.suggest(q, pickedList(), true); } catch (e) { r = null; }
      if (aseq !== st.aiSeq) return;      // a newer key or search: this answer is stale
      clearTimeout(st.busyTimer); status.textContent = '';
      if (!r || r.q !== q || st.q.trim() !== q || seq !== st.seq || !(r.ai || []).length) return;
      const was = st.moved ? st.items[st.cur] : null;      // a cursor the user moved stays on its row; else it is on the best row again
      st.items = build(q, r);
      const k = was ? st.items.findIndex((x) => itemKey(x) === itemKey(was)) : -1;
      st.cur = k >= 0 ? k : st.items.findIndex((x, i) => selectable(i));
      renderList();
    }
    function reset() { input.value = ''; st.q = ''; quiet(); st.items = []; st.cur = -1; st.listQ = ''; renderList(); renderChips(); }
    function addItem(it) {
      if (it.kind === 'split') return it.words.map((w) => addChip({ kind: 'text', value: w, label: w })).join('   ');
      if (it.kind === 'raw') return addChip({ kind: 'text', value: it.text, label: it.text });
      return addChip(chipOf(it.s));
    }
    function pick() {
      const it = st.items[st.cur];
      if (!it) return;
      note.textContent = addItem(it); reset(); input.focus();
    }
    async function enter(q) {             // Enter before the list for q has come: its best row once it comes, even if typing went on
      let r = null;
      try { r = await (st.pending && st.pending.q === q ? st.pending.p : API.suggest(q, pickedList())); } catch (e) { r = null; }
      if (S.step !== 0 || !input.isConnected) return;
      const it = (r ? build(q, r) : [{ kind: 'raw', text: q }]).find((x) => x.kind !== 'head');
      note.textContent = addItem(it);
      if (st.q.trim() === q) reset();
      else { renderChips(); clearTimeout(st.timer); st.timer = setTimeout(search, 0); }     // the text typed since keeps its own list
    }
    input.addEventListener('input', () => {
      st.q = input.value; note.textContent = ''; st.lastKey = performance.now();
      if (st.armed) { st.armed = false; renderChips(); }
      quiet();
      if (!st.q.trim()) { st.items = []; st.listQ = ''; renderList(); renderChips(); return; }
      about.hidden = true;
      st.timer = setTimeout(search, 150);
    });
    input.addEventListener('keydown', async (e) => {
      if (e.isComposing || e.keyCode === 229) return;          // a Korean syllable still being composed: this key is the IME's
      if (st.armed && e.key !== 'Backspace') { st.armed = false; note.textContent = ''; renderChips(); }     // any other key drops the mark
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!st.items.length) return;
        const dir = e.key === 'ArrowDown' ? 1 : -1;
        let i = st.cur;
        do { i += dir; } while (i >= 0 && i < st.items.length && !selectable(i));
        if (i >= st.items.length) return;
        st.cur = i < 0 ? -1 : i; st.moved = true; mark();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const q = st.q.trim();
        if (!q) { note.textContent = S.conds.length ? '다음 단계는 PgDn' : '질환명, 증상, 암종을 입력하세요'; return; }
        if (st.listQ !== q) enter(q);       // the list for q has not come yet
        else if (st.cur >= 0 && selectable(st.cur)) pick();
        else { note.textContent = addChip({ kind: 'text', value: q, label: q }); reset(); }      // no row chosen: the text as typed
      } else if (e.key === 'Escape') {
        if (st.q) { e.preventDefault(); reset(); }
      } else if (e.key === 'Backspace' && !input.value) {
        if (!S.conds.length) return;
        e.preventDefault();
        if (st.armed) { const c = S.conds.pop(); save(); st.armed = false; note.textContent = `뺌: ${c.label}`; }
        else { st.armed = true; note.textContent = `한 번 더 누르면 뺌: ${S.conds[S.conds.length - 1].label}`; }
        renderChips();
      }
    });
    const node = h('div', { class: 's1' },
      h('div', { class: 'hero' }, h('h1', { class: 'logo', 'aria-label': 'ADCToX' }, h('span', { class: 'a', text: 'ADC' }), h('span', { class: 'b', text: 'ToX' })), about),
      chips, h('div', { class: 'field' }, h('span', { class: 'pr', 'aria-hidden': 'true', text: '›' }), input), list, note, status);
    renderChips();
    const preset = MOCK && Q.get('q') && !stage1.preset ? Q.get('q') : '';
    if (preset) { stage1.preset = true; input.value = preset; st.q = preset; about.hidden = true; search(); }
    setTimeout(() => { if (S.step === 0) input.focus({ preventScroll: true }); }, 0);
    cleanup = () => { quiet(); stageNote = () => {}; };
    return node;
  }

  // ================================================================== step 2: 검사 수치
  const touched = new Set();
  let labsTimer = 0, labsSeq = 0, labUI = null, labsErr = '';
  async function labsNow() {               // POST /api/labs; the answer for the latest values is kept, and returned to its caller either way
    clearTimeout(labsTimer); labsTimer = 0;
    const seq = ++labsSeq;
    let r = null;
    try { r = await API.labs(rawValues()); } catch (e) { if (seq === labsSeq) { labsErr = e.message; if (labUI) labUI(); } return null; }
    if (seq === labsSeq) { labsErr = ''; S.labs = r; save(); if (labUI) labUI(); }
    return r;
  }
  function labsSoon() { clearTimeout(labsTimer); labsTimer = setTimeout(labsNow, 250); }
  async function labsCommit() {
    const r = await labsNow();
    if (!r) return false;                   // the server's error line is in the bar
    const errs = r.errors || {};
    const bad = FIELDS.filter((f) => errs[f.key]);
    if (!bad.length) return true;
    bad.forEach((f) => touched.add(f.key));
    if (labUI) labUI();
    const el = document.getElementById('lab-' + bad[0].key);
    if (el) el.focus();
    return false;
  }
  function derivedLine() {                 // form.Form.labs' line: x ULN of the fields that have one, then the CLcr lines, as the server wrote them
    const L = S.labs || {}, sh = (L.derived && L.derived.shown) || {};
    const out = [];
    for (const f of FIELDS) {
      const k = f.key === 'bilirubin' ? 'bili' : f.key;
      if (k !== 'crcl' && f.uln !== null && f.uln !== undefined && sh[k] !== undefined && sh[k] !== null) out.push(`${f.label} ${sh[k]}×ULN`);
    }
    for (const n of L.notes || []) if (String(n).startsWith('CLcr')) out.push(String(n));
    return out;
  }
  function stage2() {
    const order = [];                       // focusable controls, in field order
    const rows = {};
    const groups = (APP.labs.groups || []).map((g) => {
      const fs = FIELDS.filter((f) => f.group === g);
      if (!fs.length) return null;
      return h('section', { class: 'group panel', 'aria-label': g }, h('h2', { class: 'h2', text: g }), fs.map(labRow));
    }).filter(Boolean);

    function move(f, dir) {
      const i = order.findIndex((o) => o.key === f.key);
      const t = order[i + dir];
      if (t) t.focus();
    }
    function labRow(f) {
      const id = 'lab-' + f.key;
      const err = h('div', { class: 'err', id: id + '-err', hidden: true });
      const flag = h('span', { class: 'flag', hidden: true });
      const anchor = f.uln !== null && f.uln !== undefined ? `ULN ${f.uln}` : '';      // the reference the x ULN uses; the range is in the error line
      const unit = h('span', { class: 'unit' }, f.kind === 'number' ? f.unit : null, f.kind === 'number' && anchor ? h('span', { class: 'anc', text: anchor }) : null, flag);
      let control;
      if (f.kind === 'number') {
        control = h('input', { class: 'num', id, type: 'text', inputmode: 'decimal', autocomplete: 'off', spellcheck: 'false', 'aria-describedby': id + '-err', value: S.raw[f.key] || '' });
        control.addEventListener('input', () => { S.raw[f.key] = control.value; touched.delete(f.key); save(); labsSoon(); refresh(); });
        control.addEventListener('blur', () => { if (control.value.trim()) touched.add(f.key); labsNow(); });
        control.addEventListener('keydown', (e) => {
          if (e.isComposing || e.keyCode === 229) return;
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); move(f, e.key === 'ArrowDown' ? 1 : -1); }
          else if (e.key === 'Enter') { e.preventDefault(); touched.add(f.key); labsNow().then((r) => { if (r && !(r.errors || {})[f.key] && S.step === 1) move(f, 1); }); }
          else if (e.key === 'Escape') { control.value = ''; S.raw[f.key] = ''; save(); labsSoon(); refresh(); }
        });
        control.key = f.key;
        order.push(control);
      } else {
        const opts = f.kind === 'sex' ? [['M', 'M'], ['F', 'F']] : f.kind === 'child_pugh' ? [['A', 'A'], ['B', 'B'], ['C', 'C']] : [['y', 'Yes'], ['n', 'No']];
        const norm = (v) => String(v || '').trim().toUpperCase().slice(0, 1);
        const btns = opts.map(([v, label]) => h('button', { type: 'button', role: 'radio', text: label, 'data-v': v, 'aria-label': `${f.label} ${label}` }));
        control = h('div', { class: 'seg', role: 'radiogroup', id, 'aria-label': f.label }, btns);
        const sync = () => {
          const cur = norm(S.raw[f.key]);
          let focusable = null;
          btns.forEach((b) => { const on = norm(b.dataset.v) === cur; b.setAttribute('aria-checked', on ? 'true' : 'false'); b.tabIndex = -1; if (on) focusable = b; });
          (focusable || btns[0]).tabIndex = 0;
        };
        const set = (v) => { S.raw[f.key] = norm(S.raw[f.key]) === norm(v) ? '' : v; save(); sync(); labsNow(); refresh(); };
        btns.forEach((b, k) => {
          b.addEventListener('click', () => set(b.dataset.v));
          b.addEventListener('keydown', (e) => {
            if (e.isComposing || e.keyCode === 229) return;
            if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
              e.preventDefault();
              const t = btns[(k + (e.key === 'ArrowRight' ? 1 : btns.length - 1)) % btns.length];
              t.focus(); S.raw[f.key] = t.dataset.v; save(); sync(); labsNow(); refresh();
            } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); move(f, e.key === 'ArrowDown' ? 1 : -1); }
            else if (e.key === 'Enter') { e.preventDefault(); move(f, 1); }
          });
        });
        sync();
        order.push({ key: f.key, focus: () => (btns.find((b) => b.tabIndex === 0) || btns[0]).focus() });
      }
      const row = h('div', { class: 'lab' }, h('label', { for: f.kind === 'number' ? id : null, text: f.label, id: id + '-l' }), control, unit, err);
      rows[f.key] = { row, err, flag, control, f };
      return row;
    }
    function refresh() {
      const r = S.labs || {};
      const errs = r.errors || {}, flags = r.flags || [];
      for (const k in rows) {
        const { err, flag, control, f } = rows[k];
        const msg = errs[k] && touched.has(k) && String(S.raw[k] || '').trim() ? String(errs[k]) : '';      // form._lab_error, as sent
        err.hidden = !msg; err.textContent = msg;
        if (control.classList) control.classList.toggle('bad', !!msg);
        const fl = flags.filter((x) => x.key === k && String(S.raw[k] || '').trim());
        flag.hidden = !fl.length;
        flag.textContent = fl.length ? '→ ' + [...new Set(fl.map((x) => SHORT[x.organ] || x.organ))].join(', ') : '';
        flag.title = fl.map((x) => x.why).join('\n');
      }
      const parts = derivedLine();
      setBar({
        left: labsErr ? h('span', { class: 'err-line', text: labsErr }) : parts.map((t) => h('span', { class: 'info', text: t })),
        keys: [kbd('↑↓', '이동'), kbd('PgUp', '이전')],
        button: { label: '다음', key: 'PgDn', act: next },
      });
    }
    labUI = refresh;
    const node = h('div', { class: 's2' }, h('h1', { class: 'title', text: '검사 수치' }), h('p', { class: 'lead', text: '아는 것만 입력하세요' }), h('div', { class: 'groups' }, groups));
    refresh();
    labsNow();
    setTimeout(() => { const first = order.find((o) => !String(S.raw[o.key] || '').trim()) || order[0]; if (first && S.step === 1) first.focus({ preventScroll: true }); }, 0);
    cleanup = () => { labUI = null; };
    return node;
  }

  // ================================================================== step 3: AI 장기 분석
  function readingOf(r) {                 // the reading picked for an input that reads as several diseases; undefined when there is none to pick
    const amb = S.analysis && (S.analysis.ambiguous || []).find((a) => a.text === r.condition);
    if (!amb || !Object.prototype.hasOwnProperty.call(S.meanings, r.condition)) return undefined;
    return amb.readings.find((x) => x.mondo === S.meanings[r.condition]) || null;
  }
  function organsOf(r) {                  // the organs the recommendation uses; for an input that reads as several diseases, the picked reading's
    if (r.source === 'Cancer') return [];
    const rd = readingOf(r);
    if (rd !== undefined) return rd ? rd.organs || [] : [];
    return r.organs || [];
  }
  const shownName = (r) => r.shown || (REG[r.condition] ? regName(r.condition) : r.condition);
  function patientConds() {
    const out = [];
    for (const r of (S.analysis && S.analysis.reports) || []) {
      const organs = organsOf(r);
      if (organs.length) out.push({ key: r.condition, name: shownName(r), organs: AX.filter((a) => organs.includes(a)) });
    }
    return out;
  }
  function hasPriority() {                // form.run step 3: two or more conditions (lab findings included) on different organs
    const pc = patientConds();
    const labs = [...new Set(((S.labs && S.labs.flags) || []).filter((f) => String(S.raw[f.key] || '').trim()).map((f) => f.organ))];
    const sets = new Set(pc.map((c) => c.organs.join()).concat(labs));
    return pc.length + labs.length >= 2 && sets.size >= 2;
  }
  let analysisRun = 0;
  const myJobs = new Set();               // the analyses this page posted; after a reload a stored job id is not polled (its answer may be taken)
  function analysisSig() { return JSON.stringify([condList(), pickChoice()]); }
  function keepAnalysis(job, r) {         // a finished job is handed out once: keep it at once, whatever the page shows by then
    const A = S.analysis;
    if (!A || A.job !== job) return;
    Object.assign(A, { state: r.state, error: r.error || null, elapsed: r.elapsed, usage: r.usage || '', reports: r.reports || [], ambiguous: r.ambiguous || [], unresolved: r.unresolved || [] });
    save();
  }

  function stage3() {
    const box = h('div');
    const node = h('div', { class: 's3' }, h('h1', { class: 'title', text: 'AI 장기 분석' }), box);
    const run = ++analysisRun;
    const sig = analysisSig();
    let ticker = 0, ui = null, rerun = false;
    const cells = {};                     // condition -> its Organs cells in the review table
    cleanup = () => { analysisRun++; clearInterval(ticker); };

    // the TUI's wait: the step the model reports with a dot cycle, the inputs, and the process's CPU and RAM (form.Form.analyze)
    function running() {
      clear(box);
      ui = { st: h('span', { class: 'st' }), dots: h('span', { class: 'dots', 'aria-hidden': 'true' }), secs: h('span', { class: 'secs' }), usage: h('div', { class: 'usage' }) };
      ui.track = h('div', { class: 'track', role: 'progressbar', 'aria-label': 'AI 장기 분석' }, h('span'));
      box.append(h('div', { class: 'run' }, ui.track,
        h('div', { class: 'pline' }, h('span', null, ui.st, ui.dots), ui.secs),
        h('div', { class: 'who', text: condList().map(condName).join(', ') }), ui.usage));
      setBar({ keys: [kbd('PgUp', '이전')], button: { label: '다음', key: 'PgDn', disabled: true, act: next } });
    }
    function failed(msg) {
      clearInterval(ticker);
      clear(box);
      box.append(h('div', { class: 'fail' }, h('h2', { class: 'h2', text: 'AI 분석을 완료하지 못했습니다' }), h('p', { class: 'msg', text: msg })));
      setBar({ keys: [kbd('PgUp', '이전')], button: { label: '질환 입력으로 돌아가기', act: () => go(0) } });
    }
    function finish() {
      clearInterval(ticker);
      const A = S.analysis;
      if (A.state === 'error') failed(A.error || 'error');
      else { defaultMeanings(); review(true); }
      renderCrumbs();
    }
    async function poll(job) {
      myJobs.add(job);
      if (!ui) running();
      const t0 = performance.now();
      const w = { text: '', queued: false, base: 0, at: t0, usage: '' };
      const set = (el, t) => { if (el.textContent !== t) el.textContent = t; };
      const paint = () => {
        const now = performance.now();
        set(ui.st, w.text);
        set(ui.dots, !w.text ? '' : still() ? '...' : '.'.repeat(1 + Math.floor(((now - t0) / 1000) * 2.5) % 3));
        set(ui.secs, w.text && !w.queued ? `${(w.base + (now - w.at) / 1000).toFixed(1)} s` : '');
        set(ui.usage, w.usage);
        ui.track.setAttribute('aria-valuetext', w.text);
      };
      paint();
      clearInterval(ticker);
      ticker = setInterval(paint, 100);
      for (let k = 0; ; k++) {
        if (k) await sleep(250);
        if (run !== analysisRun) return;
        let r;
        try { r = await API.job(job); } catch (e) { r = e.status === 404 ? { state: 'gone' } : { state: 'error', error: e.message }; }
        if (r.state === 'done' || r.state === 'error') keepAnalysis(job, r);
        if (run !== analysisRun) return;
        const A = S.analysis;
        if (A && A.job === job && (A.state === 'done' || A.state === 'error')) { finish(); return; }     // this answer, or the one an earlier visit took
        if (r.state === 'gone') {          // the server no longer has the job (taken, dropped or restarted): run it again, once
          if (rerun) { A.state = 'error'; A.error = 'unknown analysis job'; save(); failed(A.error); return; }
          rerun = true; start(); return;
        }
        w.text = r.state === 'queued' ? '분석 대기 중' : r.step_text || (w.queued ? '' : w.text);
        w.queued = r.state === 'queued';
        if (typeof r.elapsed === 'number') { w.base = r.elapsed; w.at = performance.now(); }
        if (r.usage) w.usage = r.usage;
        paint();
      }
    }
    async function start() {
      const mine = S.analysis = { sig, state: 'running', job: null, reports: [], ambiguous: [], unresolved: [] };
      save();
      running();
      try {
        const r = await API.analyze(condList(), pickChoice());
        if (S.analysis === mine) { mine.job = r.job; myJobs.add(r.job); save(); }      // kept even if the page moved on, so coming back polls it
        if (run !== analysisRun) return;
        poll(r.job);
      } catch (e) { if (S.analysis === mine) { mine.state = 'error'; mine.error = e.message; save(); } if (run === analysisRun) failed(e.message); }
    }

    function review(cascade) {
      clear(box);
      const A = S.analysis, reps = A.reports || [];
      const ambText = new Set((A.ambiguous || []).map((a) => a.text));
      if (reps.some((r) => r.fallback)) box.append(h('p', { class: 'warnline', text: 'Organ judge 오류, MONDO linker로 대체' }));
      const table = h('div', { class: 'review', role: 'table', 'aria-label': 'AI 장기 분석' },
        h('div', { class: 'rv-head', role: 'row' }, ['Input', 'Organs', 'Read as'].map((t) => h('span', { role: 'columnheader', text: t }))));
      reps.forEach((r, i) => {
        const cell = h('span', { role: 'cell' }, organCell(r));
        (cells[r.condition] = cells[r.condition] || []).push({ cell, r });
        const tag = ambText.has(r.condition) && r.tag ? String(r.tag).split(':')[0] : '';    // '2 meanings' (they are picked below)
        table.append(h('div', { class: 'rv-row' + (cascade && !still() ? ' in' : ''), role: 'row', style: `--i:${i}` },
          h('span', { class: 'inp', role: 'cell', text: shownName(r) }),
          cell,
          h('span', { class: 'read', role: 'cell' }, r.read_as ? h('span', { class: 'rd', text: r.read_as }) : null, h('span', { class: 'how', text: r.how || '' }), tag ? h('span', { class: 'mean', text: tag }) : null)));
      });
      box.append(table);
      if (A.usage) box.append(h('p', { class: 'usage', text: A.usage }));
      if ((A.ambiguous || []).length) box.append(meanings());
      setBar({ keys: [kbd('PgUp', '이전')], button: { label: '다음', key: 'PgDn', act: next } });
      lightAnalysis(cascade);
    }
    function organCell(r) {               // form.likely: the judge's three most probable organs (and a used one outside them), as the server wrote them
      const used = organsOf(r);
      if (!used.length) {
        const rd = readingOf(r);
        const text = r.source === 'Cancer' ? r.no_organs || 'Cancer' : rd === undefined ? r.no_organs || '-' : rd ? 'none of 13' : '-';
        return h('span', { class: text === 'Cancer' ? 'cancer' : 'dim', text });
      }
      const same = used.length === (r.organs || []).length && used.every((o) => r.organs.includes(o));
      const lk = same && (r.likely || []).length ? r.likely : used.map((o) => ({ organ: o, used: true, p: null, text: null }));
      if (!lk.some((x) => x.text)) return strip(used);
      return h('span', { class: 'orgcell' }, strip(used, { names: false }),
        h('span', { class: 'p3' }, lk.map((x) => [
          h('span', { class: 'o' + (x.used ? ' used' : ''), text: SHORT[x.organ] || x.organ }),
          h('span', { class: 'bar1', 'aria-hidden': 'true' }, h('b', { class: x.used ? 'used' : null, style: `width:${Math.max(2, Math.min(100, (x.p || 0) * 100))}%` })),
          h('span', { class: 'v', text: x.text || '' })])));
    }
    function meanings() {
      const wrap = h('div', { class: 'meanings' }, h('h2', { class: 'h2', text: '입력하신 질환 확인' }),
        h('p', { class: 'lead', text: '여러 질환으로 읽히는 입력이 있습니다. 의도한 질환을 골라 주세요.' }));
      for (const g of S.analysis.ambiguous) {
        const opts = g.readings.map((r) => ({ id: r.mondo, label: r.name || r.mondo, organs: r.organs || [], hpo: r.hpo || String(r.mondo || '').startsWith('HP:') }));
        opts.push({ id: null, label: '모름', organs: null });
        const qid = 'mq-' + g.text.replace(/\W/g, '_');
        const changed = (id) => {
          S.meanings[g.text] = id; save();
          for (const { cell, r } of cells[g.text] || []) { clear(cell); cell.append(organCell(r)); }
          lightAnalysis(false); renderCrumbs();
        };
        wrap.append(h('div', { class: 'mgroup' }, h('p', { class: 'q', text: g.text, id: qid }),
          radioList(opts, S.meanings[g.text] === undefined ? opts[0].id : S.meanings[g.text], changed,
            (o) => [h('span', { class: 'lbl' }, o.label, o.hpo ? h('span', { class: 'tag', text: '증상' }) : null),
              o.organs === null ? null : o.organs.length ? strip(o.organs) : h('span', { class: 'dim', text: '13개 장기 밖' })],
            qid)));
      }
      return wrap;
    }

    const A = S.analysis;
    if (A && A.sig === sig && A.state === 'done') { defaultMeanings(); review(false); }
    else if (A && A.sig === sig && A.state === 'running' && A.job && myJobs.has(A.job)) poll(A.job);    // back on this step while it runs
    else start();                         // nothing stored, or a reload that finds a job id without its answer: run it again
    return node;
  }
  function defaultMeanings() {            // form.meanings: the reading the analysis applied (the server's default), else the first
    for (const g of (S.analysis && S.analysis.ambiguous) || []) {
      if (Object.prototype.hasOwnProperty.call(S.meanings, g.text)) continue;
      S.meanings[g.text] = g.default !== undefined ? g.default : (g.readings[0] || { mondo: null }).mondo;
    }
    save();
  }
  let lightTimers = [];
  function lightAnalysis(cascade) {        // the organs of each reviewed input light as its row appears
    lightTimers.forEach(clearTimeout); lightTimers = [];
    const reps = (S.analysis && S.analysis.reports) || [];
    const lit = {};
    const apply = () => body.update({ lit: Object.assign({}, lit) });
    if (!cascade || still()) { reps.forEach((r) => organsOf(r).forEach((o) => { lit[o] = 'on'; })); apply(); return; }
    body.update({});
    reps.forEach((r, i) => lightTimers.push(setTimeout(() => { organsOf(r).forEach((o) => { lit[o] = 'on'; }); apply(); }, 120 + i * 40)));
  }

  // generic radio list (meanings, priority): arrow keys move the choice, Enter goes on
  function radioList(opts, value, onChange, render, labelledby, onEnter) {
    const ul = h('ul', { class: 'radios', role: 'radiogroup', 'aria-labelledby': labelledby || null });
    const lis = opts.map((o) => {
      const li = h('li', { class: 'ropt', role: 'radio', tabindex: '-1' }, h('span', { class: 'dot', 'aria-hidden': 'true' }), render(o));
      li.addEventListener('click', () => choose(o, li, true));
      return li;
    });
    let cur = opts.findIndex((o) => o.id === value);
    if (cur < 0) cur = 0;
    function paint() { lis.forEach((li, i) => { li.setAttribute('aria-checked', i === cur ? 'true' : 'false'); li.tabIndex = i === cur ? 0 : -1; }); }
    function choose(o, li, focus) { cur = opts.indexOf(o); paint(); if (focus) li.focus(); onChange(o.id); }
    lis.forEach((li, i) => li.addEventListener('keydown', (e) => {
      if (e.isComposing || e.keyCode === 229) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const j = Math.max(0, Math.min(lis.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
        choose(opts[j], lis[j], true);
      } else if (e.key === ' ') { e.preventDefault(); choose(opts[i], li, true); }
      else if (e.key === 'Enter' && onEnter) { e.preventDefault(); onEnter(); }
    }));
    paint();
    add(ul, lis);
    ul.focusFirst = () => lis[cur] && lis[cur].focus({ preventScroll: true });
    return ul;
  }

  // ================================================================== step 4: 우선순위
  function stage4() {
    const pc = patientConds();
    if (S.first && !pc.some((c) => c.key === S.first)) S.first = null;
    const opts = [{ id: null, label: '자동 (질환 중증도 순)', organs: null }].concat(pc.map((c) => ({ id: c.key, label: c.name, organs: c.organs })));
    const preview = (id) => {
      const lit = {};
      for (const c of pc) for (const o of c.organs) lit[o] = 'on';
      if (id) { for (const o in lit) lit[o] = 'l2'; for (const o of (pc.find((c) => c.key === id) || {}).organs || []) lit[o] = 'l1'; }
      body.update({ lit });
    };
    const list = radioList(opts, S.first, (id) => { S.first = id; save(); preview(id); },
      (o) => [h('span', { class: 'lbl', text: o.label }), o.organs ? strip(o.organs) : null], 's4-title', next);
    const node = h('div', { class: 's4' }, h('h1', { class: 'title', id: 's4-title', text: '가장 걱정되는 질환' }), h('p', { class: 'lead', text: APP.first_text }), list);
    preview(S.first);
    setBar({ keys: [kbd('↑↓', '고르기'), kbd('PgUp', '이전')], button: { label: '다음', key: 'PgDn', act: next } });
    setTimeout(() => { if (S.step === 3) list.focusFirst(); }, 0);
    return node;
  }

  // ================================================================== step 5: 결과
  function restriction(row) {             // recommend._result_list's state: None / Monitor / No data / Not studied / Avoid, '?' when a missing value could change it
    return { text: row.status + (row.sure ? '' : '?'), tone: STATE_TONE[row.status] || 'dim', sure: !!row.sure };
  }
  function previewCells(row) {            // recommend._organ_preview (the server's): two warned patient organs, + for more; one other warned organ, + for more
    const pv = row.preview || { patient: [], other: [] }, own = pv.patient || [], other = pv.other || [];
    const cell = (c, more) => (c ? { o: c.organ, boxed: c.mark === '!!', more: !!more } : { none: true });
    return [cell(own[0]), own.length ? (own[1] ? cell(own[1], own.length > 2) : { blank: true }) : cell(null), cell(other[0], other.length > 1)];
  }
  function ocNode(c) {
    if (c.blank) return h('span', { class: 'oc' });
    if (c.none) return h('span', { class: 'oc n', text: '-' });
    return h('span', { class: 'oc ' + (c.boxed ? 'b' : 'w') }, h('span', { class: 'mk2', text: c.boxed ? '!!' : '!' }), SHORT[c.o] || c.o, c.more ? h('span', { class: 'plus', text: '+' }) : null);
  }
  const legendNode = (cls) => h('div', { class: cls },
    h('span', null, h('b', { class: 't-red', text: '!!' }), 'Boxed warning'), h('span', null, h('b', { class: 't-amber', text: '!' }), 'Warning'),
    h('span', null, h('b', { text: '+' }), 'more organs'), h('span', null, h('b', { text: '?' }), 'needs a value not entered'));
  function resultSig() { return JSON.stringify([condList(), rawValues(), allChoice(), S.first]); }

  function stage5() {
    const box = h('div');
    const node = h('div', { class: 's5' }, box);
    let alive = true;
    cleanup = () => { alive = false; resultKeys = null; };
    setBar({ left: legendNode('legend'), keys: [kbd('↑↓', 'ADC 고르기'), kbd('Enter', '이유'), kbd('PgUp', '이전 단계')], button: { label: '새 환자로 시작', quiet: true, act: restart } });
    const sig = resultSig();
    if (S.result && S.result.sig === sig) draw(S.result.data);
    else {
      const wait = setTimeout(() => { if (alive && !box.firstChild) box.append(h('div', { class: 'run' }, h('div', { class: 'track', role: 'progressbar', 'aria-label': '결과' }, h('span')))); }, 250);
      const lab = (S.labs && S.labs.raw) || {};
      API.recommend({ conditions: condList(), raw: lab, choice: allChoice(), first: S.first })
        .then((data) => { clearTimeout(wait); if (!alive) return; S.result = { sig, data }; save(); draw(data, true); })
        .catch((e) => { clearTimeout(wait); if (!alive) return; clear(box); box.append(h('div', { class: 'fail' }, h('h2', { class: 'h2', text: '결과' }), h('p', { class: 'msg', text: e.message }))); });
    }
    function draw(res, fresh) {
      clear(box);
      const rows = res.rows || [], P = res.patient || {}, levels = P.organ_levels || {};
      // Key values (the selected ADC's: its restriction's values first) | Organ priority
      const keyList = h('ul');
      const keyValues = (i) => {
        const vals = i >= 0 && rows[i] && rows[i].detail && rows[i].detail.values ? rows[i].detail.values : P.values || [];
        clear(keyList); add(keyList, [vals.length ? vals.map((v) => h('li', { text: v })) : h('li', { class: 'none', text: 'Not entered' })]);
      };
      const prio = P.organ_priority || [];
      box.append(h('div', { class: 'ctx panel' },
        h('div', null, h('h2', { class: 'h2', text: 'Key values' }), keyList),
        h('div', null, h('h2', { class: 'h2', text: 'Organ priority' }),
          h('ul', null, prio.length ? prio.map(([l, organs]) => h('li', null, h('span', { class: 'lv', text: String(l) }),
            organs.map((o) => h('span', { class: 'org' + (l > 1 ? ' l2' : ''), text: SHORT[o] || o })))) : h('li', { class: 'none', text: 'None specified' })))));
      if ((P.unmapped || []).length) box.append(h('p', { class: 'unmapped', text: (P.estimated ? 'Unvalidated estimate: ' : 'Unmapped: ') + P.unmapped.join(', ') }));

      const grid = h('div', { class: 'grid', role: 'grid', 'aria-label': 'ADC', 'aria-rowcount': String(rows.length + 1) },
        h('div', { class: 'grid-h', role: 'row' },
          h('span', { class: 'rk', role: 'columnheader', text: '#' }), h('span', { role: 'columnheader', text: 'ADC' }),
          h('span', { role: 'columnheader', text: 'Label restriction' }), h('span', { class: 'po', role: 'columnheader', text: 'Patient organs' }),
          h('span', { role: 'columnheader', text: 'Other' })));
      const trs = [];
      let prevRank = null;
      rows.forEach((row, i) => {
        if (row.indicated === false && (i === 0 || rows[i - 1].indicated !== false)) grid.append(h('div', { class: 'sep', role: 'row' }, h('span', { role: 'gridcell', text: 'Other cancers' })));
        const rs = restriction(row), cells = previewCells(row);
        const rank = row.rank !== prevRank ? String(row.rank) : '';
        prevRank = row.rank;
        const mine = cells.slice(0, 2).filter((c) => c.o);
        const tr = h('div', { class: 'tr', role: 'row', tabindex: '-1', 'aria-selected': 'false', 'aria-rowindex': String(i + 2), 'data-i': String(i) },
          h('span', { class: 'rk', role: 'gridcell', text: rank }),
          h('span', { class: 'nm', role: 'gridcell', text: row.name }),
          h('span', { class: `rs t-${rs.tone}` + (rs.sure ? ' sure' : ''), role: 'gridcell', text: rs.text }),
          cells.map((c) => h('span', { role: 'gridcell' }, ocNode(c))),
          h('span', { class: 'pt', 'aria-hidden': 'true' }, 'Patient: ', mine.length ? mine.map(ocNode) : '-', '   Other: ', ocNode(cells[2])));
        tr.addEventListener('click', () => { select(i, true); openDrawer(); });
        tr.addEventListener('mouseenter', () => hover(i));
        trs.push(tr);
        grid.append(tr);
      });
      grid.addEventListener('mouseleave', () => hover(-1));
      resultKeys = (e) => {
        const i = S.sel < 0 ? 0 : S.sel;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); select(Math.max(0, Math.min(rows.length - 1, S.sel < 0 ? 0 : i + (e.key === 'ArrowDown' ? 1 : -1))), true); }
        else if (e.key === 'Home') { e.preventDefault(); select(0, true); }
        else if (e.key === 'End') { e.preventDefault(); select(rows.length - 1, true); }
        else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (S.sel < 0) select(0, true); openDrawer(); }
      };
      grid.addEventListener('keydown', resultKeys);
      box.append(h('div', { class: 'adcs' }, grid), legendNode('legend narrow'));      // the legend is in the bar; under the list only on a phone
      if (fresh && !still()) box.classList.add('fadein');

      let hov = -1;
      function bodyFor() {
        const lit = {};
        for (const [o, l] of Object.entries(levels)) lit[o] = l <= 1 ? 'l1' : 'l2';
        const k = hov >= 0 ? hov : S.sel;
        const rings = {};
        if (k >= 0 && rows[k]) {
          const row = rows[k];
          for (const a of AX) {
            const l = (row.levels && row.levels[a]) || (row.boxed.includes(a) ? 'boxed' : row.warn.includes(a) ? 'W&P' : '');
            if (l === 'boxed') rings[a] = 'b'; else if (l === 'W&P') rings[a] = 'w';
          }
        }
        body.update({ lit, rings, caption: k >= 0 && rows[k] ? rows[k].name : '', legend: true });
      }
      function hover(i) { hov = i; bodyFor(); }
      function select(i, focus) {
        S.sel = i; save();
        trs.forEach((t, k) => { t.setAttribute('aria-selected', k === i ? 'true' : 'false'); t.tabIndex = k === i ? 0 : -1; });
        if (i >= 0 && trs[i]) { if (focus) trs[i].focus({ preventScroll: false }); }
        if (S.drawer) fillDrawer(rows[i]);
        keyValues(i);
        bodyFor();
      }
      openDrawer = () => { if (S.sel < 0 || !rows[S.sel]) return; fillDrawer(rows[S.sel]); showDrawer(); };
      returnFocus = () => { if (trs[S.sel]) trs[S.sel].focus({ preventScroll: true }); };
      if (S.sel < 0 || S.sel >= rows.length) S.sel = rows.length ? 0 : -1;
      select(S.sel, false);
      setTimeout(() => {
        if (S.step === 4 && trs[S.sel] && trs[S.sel].isConnected && !drawer.contains(document.activeElement)) trs[S.sel].focus({ preventScroll: true });
      }, 0);
      const want = MOCK && Q.get('adc') && !mockAdcUsed ? String(Q.get('adc')).replace(/_/g, '-') : null;
      mockAdcUsed = true;
      if (want) { const k = rows.findIndex((r) => r.adc === want || r.adc.replace(/_/g, '-') === want); if (k >= 0) { select(k, false); openDrawer(); } }
      else if (S.drawer && S.sel >= 0) openDrawer();
    }
    return node;
  }
  let mockAdcUsed = false;
  function restart() {
    try { sessionStorage.removeItem(KEY); } catch (e) { /* ignore */ }
    S = blank(); touched.clear();
    go(0);
  }

  // ------------------------------------------------------------------ detail drawer
  let openDrawer = () => {}, returnFocus = () => {}, resultKeys = null;
  function showDrawer() {
    S.drawer = true; save();
    drawer.classList.add('open'); drawer.setAttribute('aria-hidden', 'false');
  }
  function closeDrawer(silent) {
    S.drawer = false;
    if (!silent) save();
    if (!drawer || !drawer.classList.contains('open')) return;
    const inside = drawer.contains(document.activeElement);
    drawer.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true');
    if (inside) returnFocus();
  }
  // recommend._event_text as sent ('pneumonitis 25/404 (6.2%, vs 0.0%), serious 10/404'); only the comparator's part is set dim
  const evNode = (text) => h('span', { class: 'ev' }, String(text || '').split(/(, vs [^),;]*)/).map((p, k) => (k % 2 ? h('span', { class: 'vs', text: p }) : p)));
  function section(title, ...kids) { return h('section', { class: 'dsec' }, title ? h('h3', { class: 'h2', text: title }) : null, kids); }
  function fillDrawer(row) {
    if (!row) return;
    const d = row.detail || {};
    drawerTitle.textContent = row.name;
    clear(drawerBody);
    drawerBody.scrollTop = 0;
    const first = [];
    if (d.indication) first.push(h('p', { class: 'ind', text: d.indication }));
    const rs = d.reasons || [];
    first.push(h('div', { class: 'reasons' }, rs.length ? rs.map((r) => [
      h('span', { class: 'k', text: r.organ }),
      h('span', { class: `s t-${TONE[r.code] || 'dim'}` + (r.sure ? ' sure' : ''), text: r.status }),
      h('span', { class: 'b', text: r.basis })]) : h('span', { class: 'solo', text: 'No applicable label restriction' })));
    drawerBody.append(section(null, first));
    const ws = d.warnings || [];
    if (ws.length) drawerBody.append(section("Warnings on the patient's organs", h('div', { class: 'wl' }, ws.map((w) => [
      h('span', { class: 'k', text: SHORT[w.organ] || w.organ }),
      h('span', { class: 'm ' + (w.mark === '!!' ? 't-red' : 't-amber'), text: w.mark.trim() }),
      h('span', { text: w.text })]))));
    const t = d.trial;
    if (t && t.no_results) drawerBody.append(section("Trial results on the patient's organs", h('p', { class: 'line', text: t.no_results })));
    else if (t && t.trial) {
      const head = t.line || t.trial;          // recommend.trial_lines' title line
      drawerBody.append(section("Trial results on the patient's organs",
        h('p', { class: 'trial-t', title: t.nct || null, text: head }),
        h('div', { class: 'kv' }, (t.organs || []).map((o) => [
          h('span', { class: 'k', text: SHORT[o.organ] || o.organ }),
          h('span', { class: 'v' }, (o.events || []).length ? o.events.map((e, k) => [k ? '; ' : '', evNode(e.text)]) : (o.none || o.text || ''))]))));
    }
    if ((d.missing || []).length) drawerBody.append(section('Missing inputs', h('ul', { class: 'dash' }, d.missing.map((m) => h('li', { text: m })))));
    if (d.payload) drawerBody.append(section('Payload and linker', h('p', { class: 'line', text: d.payload.line }), d.payload.note ? h('p', { class: 'note2', text: d.payload.note }) : null));
    if ((d.checks || []).length) drawerBody.append(section('Pre-treatment checks', h('ul', { class: 'dash' }, d.checks.map((c) => h('li', { text: c })))));
  }

  // ------------------------------------------------------------------ keys that work everywhere (the TUI's)
  document.addEventListener('keydown', (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === 'PageDown') { e.preventDefault(); next(); }
    else if (e.key === 'PageUp') { e.preventDefault(); prev(); }
    else if (e.key === 'Escape' && S.drawer) { e.preventDefault(); closeDrawer(); }
    else if (S.step === 4 && resultKeys && !e.defaultPrevented && ['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(e.key)) {
      const t = e.target;                // keys that land on the page itself (not a field, button or the drawer) work the ADC list
      const page = t === document.body || t === document.documentElement || (stageBox.contains(t) && !t.closest('input, textarea, select, button, [role="radio"], a'));
      if (page && !drawer.contains(t)) resultKeys(e);
    }
  });

  // ================================================================== start
  async function start() {
    frame();
    try {
      APP = await API.app();
    } catch (e) {
      stageBox.append(h('div', { class: 'fail' }, h('h2', { class: 'h2', text: 'ADCTOX' }), h('p', { class: 'msg', text: e.message })));
      return;
    }
    AX = APP.axes || [];
    SHORT = APP.organ_short || {};
    body.names(SHORT);
    (APP.registry || []).forEach((r, i) => { REG[r.id] = r; REG_I[r.id] = i; });
    FIELDS = (APP.labs && APP.labs.fields) || [];
    STEPS = APP.steps || ['질환', '검사 수치', 'AI 장기 분석', '우선순위', '결과'];
    verEl.textContent = APP.version || '';
    if (APP.models) verEl.title = 'models ' + APP.models;

    let step = null;
    if (MOCK && Q.get('step')) {            // ?mock=1&step=N: that stage, with the example patient entered for the steps before it
      const n = Math.max(1, Math.min(5, parseInt(Q.get('step'), 10) || 1)) - 1;
      const fx = MOCK.fixture();
      S = blank();
      S.conds = fx.conds.map((c) => Object.assign({}, c));
      if (n >= 1) { S.raw = Object.assign({}, fx.raw); S.labs = await API.labs(rawValues()); }
      if (n >= 3 || (n === 2 && Q.get('analysis') === 'done')) { S.analysis = MOCK.analysisDone(condList(), pickChoice()); S.analysis.sig = analysisSig(); defaultMeanings(); }
      S.reached = n; step = n;
    } else {
      restore();
      step = Math.max(0, Math.min(4, S.step | 0));
      if (step >= 3 && !(S.analysis && S.analysis.state === 'done')) step = 2;
    }
    go(step, true);
  }
  start();
})();
