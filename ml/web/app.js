/* ADCTOX v0.7.0 Architectural Daylight WebApp
   Option A: Active-Organ Horizon Strip + Top ADC Spotlight Hero Cards + Dual-Bar Trial Incidence + Structure Studio.
   Zero framework, zero build step. Supports desktop & Android/iOS PWA. */
(function () {
  'use strict';

  try { sessionStorage.removeItem('adctoxReload'); } catch (e) { /* ignore */ }
  const Q = new URLSearchParams(location.search);
  const MOCK = location.protocol === 'file:' && Q.get('mock') === '1' && window.ADCTOX_MOCK ? window.ADCTOX_MOCK : null;
  const REVIEW = window.ADCTOX_REVIEW;
  const ROOT = document.documentElement;
  const REDUCE = window.matchMedia ? matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
  const still = () => ROOT.classList.contains('still') || REDUCE.matches;

  // ------------------------------------------------------------------ API Client
  async function call(method, url, body) {
    let res;
    const send = () => fetch(url, {
      method, cache: 'no-store',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    try {
      try { res = await send(); } catch (e) {
        if (url === '/api/analyze') throw e;
        await new Promise((go) => setTimeout(go, 200));
        try { res = await send(); } catch (e2) { await new Promise((go) => setTimeout(go, 500)); res = await send(); }
      }
    } catch (e) {
      const err = new Error('ADCTOX server connection closed. Start adctox again to reconnect.');
      err.status = 0; throw err;
    }
    let data = null;
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (!res.ok) {
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

  // ------------------------------------------------------------------ DOM Helpers
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
  const clear = (el) => { while (el && el.firstChild) el.firstChild.remove(); return el; };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const kbd = (k, label) => h('span', null, h('kbd', { text: k }), ({
    add: 'Add', choose: 'Choose', remove: 'Remove', move: 'Move',
    back: 'Back', next: 'Next', select: 'Select', details: 'Evidence',
  })[label] || label);

  // ------------------------------------------------------------------ Tooltips & Guide
  const TIPS = {
    'Regimen Fit': ['FDA label dosing & eligibility rules for this patient profile.', [
      ['1 bar', 'Standard dosing: no label restriction triggered'],
      ['2 bars', 'Monitor or Dose Adjust: check organ lab thresholds'],
      ['3 bars', 'Avoid or Contraindicated: label advises against use'],
    ]],
    'Active Organ Profile': ['Warnings on the patient\'s active vulnerable organs only.', [
      ['Emerald bar', 'Clear: no boxed or Section 5 warning on this organ'],
      ['Amber bar', 'Section 5 Warning on this organ'],
      ['Crimson bar', 'Boxed Warning on this organ'],
    ]],
    'Pivotal Trial vs Control': ['Study-group adverse event incidence in the pivotal trial.', [
      ['ADC', 'Treatment arm incidence (events / sample size)'],
      ['CMP', 'Comparator arm incidence (events / sample size)'],
    ]],
    'Label restriction': ['FDA label rules evaluated against entered conditions and labs.', []],
    'Indication': ['Approved oncology indications on the FDA label.', []],
    'Payload and linker': ['4-part antibody-drug conjugate architecture (Section 12.1).', []],
  };

  const tipBox = h('div', { class: 'tipbox', role: 'tooltip', id: 'tipbox', hidden: true });
  const tipOfEl = new WeakMap();
  function tipped(el, text) {
    const t = text || TIPS[el.textContent];
    if (!t) return el;
    el.classList.add('tipped'); tipOfEl.set(el, t); el.tabIndex = 0; el.setAttribute('aria-describedby', 'tipbox');
    return el;
  }
  function showTip(el) {
    const t = tipOfEl.get(el); if (!t) return;
    clear(tipBox);
    if (typeof t === 'string') tipBox.textContent = t;
    else tipBox.append(
      h('div', { class: 'ts', text: t[0] }),
      t[1] && t[1].length ? h('div', { class: 'tr' }, t[1].map(([k, v]) => h('div', null, h('b', { text: k + ': ' }), h('span', { text: v })))) : null
    );
    tipBox.hidden = false;
    const r = el.getBoundingClientRect(), w = tipBox.offsetWidth, ht = tipBox.offsetHeight;
    const x = Math.min(window.innerWidth - w - 12, Math.max(12, r.left));
    const y = r.bottom + 8 + ht > window.innerHeight - 8 ? r.top - ht - 8 : r.bottom + 8;
    tipBox.style.left = x + 'px'; tipBox.style.top = y + 'px';
  }
  const hideTip = () => { tipBox.hidden = true; };
  document.addEventListener('mouseover', (e) => {
    const t = e.target && e.target.closest ? e.target.closest('.tipped') : null;
    if (t) showTip(t); else if (!tipBox.hidden) hideTip();
  });
  window.addEventListener('scroll', hideTip, true);

  let guide = null;
  function closeGuide() {
    if (!guide) return;
    guide.remove(); guide = null;
    const opener = document.querySelector('.help');
    if (opener) opener.focus();
  }
  function openGuide() {
    if (guide) closeGuide();
    guide = h('div', { class: 'guide-scrim', onclick: (e) => { if (e.target === guide) closeGuide(); } },
      h('div', { class: 'guide', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'g-title' },
        h('div', { class: 'g-head' },
          h('h2', { id: 'g-title', text: 'ADCTOX v0.7.0 Visual Workspace' }),
          h('button', { type: 'button', class: 'x', 'aria-label': 'Close', text: '×', onclick: closeGuide })),
        h('ol', { class: 'g-steps' },
          h('li', null, h('b', { text: '1. ADC Matrix: ' }), 'Top recommended ADCs are highlighted in full-color Spotlight Cards. Lower-ranked drugs recede into monochrome slate rows. Only the patient\'s active organs are graphed.'),
          h('li', null, h('b', { text: '2. Structure Studio: ' }), 'Combine Target Antigen, Linker, Payload, DAR, and Fc-Silencing (LALA-PG) to inspect chemical compatibility, GTEx tissue selectivity, and organ burden.'),
          h('li', null, h('b', { text: '3. Patient & Labs: ' }), 'Search conditions in English or Korean, enter lab values (Cockcroft-Gault CLcr & ULN ratios), and inspect AI condition-organ associations.')),
        h('h3', { text: 'Visual Encodings' }),
        h('div', { class: 'g-keys' },
          h('span', { class: 'sp-status-badge clear', text: 'Standard' }), 'No FDA label restriction triggered for entered profile',
          h('span', { class: 'sp-status-badge monitor', text: 'Monitor / Adjust' }), 'Close clinical monitoring or dose modification advised',
          h('span', { class: 'sp-status-badge avoid', text: 'Avoid' }), 'FDA label advises against use or contraindicated',
          h('span', { class: 'sp-match-tag', text: 'ADC vs CMP' }), 'Pivotal trial treatment arm vs comparator arm incidence'),
        h('div', { class: 'g-foot' },
          h('button', { type: 'button', class: 'ok', text: 'Close', onclick: closeGuide }))));
    document.body.append(guide);
  }

  // ------------------------------------------------------------------ App Data & Clinical Presets
  let APP = null, AX = [], SHORT = {}, REG = {}, REG_I = {}, FIELDS = [], MECH = {};
  const TONE = { contraindicated: 'red', avoid: 'red', insufficient_data: 'ink', no_statement: 'ink', reduce_dose: 'amber', monitor: 'amber', no_adjustment: 'green' };
  const MODES = ['ADC Matrix', 'Structure Studio', 'Patient & Labs'];

  const PRESETS = [
    {
      id: 'her2-ild',
      label: 'HER2+ / ILD + HF',
      conds: [
        { kind: 'mondo', value: 'MONDO:0006244', label: 'HER2 positive breast carcinoma', mondo: 'MONDO:0006244' },
        { kind: 'reg', value: 'interstitial_lung_disease', label: 'Interstitial lung disease (ILD)', mondo: 'MONDO:0015925' },
        { kind: 'reg', value: 'heart_failure', label: 'Heart failure', mondo: 'MONDO:0005252' },
      ],
      raw: { bilirubin: '2.0', creatinine: '1.4', age: '68', sex: 'F', weight: '55' },
      studio: { target: 'HER2 (ERBB2)', linker: 'Tetrapeptide GGFG', payload: 'DXd ( Topo I )', dar: 8, fc: false },
    },
    {
      id: 'dlbcl-cirr',
      label: 'DLBCL / Cirrhosis',
      conds: [
        { kind: 'mondo', value: 'MONDO:0018905', label: 'diffuse large B-cell lymphoma', mondo: 'MONDO:0018905' },
        { kind: 'reg', value: 'cirrhosis', label: 'Cirrhosis', mondo: 'MONDO:0005155' },
        { kind: 'reg', value: 'peripheral_neuropathy', label: 'Peripheral neuropathy', mondo: 'MONDO:0005244' },
      ],
      raw: { bilirubin: '2.4', ast: '95', age: '64', sex: 'M', weight: '72', child_pugh: 'B' },
      studio: { target: 'CD79b', linker: 'Val-Cit PABC', payload: 'MMAE ( Auristatin )', dar: 3.5, fc: false },
    },
    {
      id: 'tnbc-ckd',
      label: 'TNBC / CKD3',
      conds: [
        { kind: 'mondo', value: 'MONDO:0005494', label: 'triple-negative breast carcinoma', mondo: 'MONDO:0005494' },
        { kind: 'reg', value: 'ckd_stage_3', label: 'Chronic kidney disease stage 3', mondo: 'MONDO:0005300' },
      ],
      raw: { creatinine: '1.8', hb: '9.4', anc: '1.3', age: '61', sex: 'F', weight: '58' },
      studio: { target: 'TROP2 (TACSTD2)', linker: 'Hydrolyzable CL2A', payload: 'SN-38 ( Topo I )', dar: 7.6, fc: false },
    },
    {
      id: 'myeloma-eye',
      label: 'Myeloma / Ocular',
      conds: [
        { kind: 'mondo', value: 'MONDO:0009693', label: 'plasma cell myeloma', mondo: 'MONDO:0009693' },
        { kind: 'reg', value: 'dry_eye', label: 'Dry eye syndrome', mondo: 'MONDO:0021107' },
      ],
      raw: { creatinine: '1.2', age: '70', sex: 'M', weight: '68' },
      studio: { target: 'BCMA (TNFRSF17)', linker: 'Non-cleavable mc', payload: 'MMAF ( Auristatin )', dar: 4, fc: true },
    },
  ];

  // ------------------------------------------------------------------ Structure Studio Knowledge Base
  const STUDIO_TARGETS = [
    { id: 'HER2 (ERBB2)', gene: 'ERBB2', refAdc: 'trastuzumab-deruxtecan', selectivity: 4.8, tissues: [
      { organ: 'pulmonary', name: 'Lung alveolar', tpm: 48, max: 100 },
      { organ: 'cardiovascular', name: 'Cardiomyocyte', tpm: 36, max: 100 },
      { organ: 'gastrointestinal', name: 'GI mucosa', tpm: 42, max: 100 },
    ]},
    { id: 'TROP2 (TACSTD2)', gene: 'TACSTD2', refAdc: 'sacituzumab-govitecan', selectivity: 4.1, tissues: [
      { organ: 'gastrointestinal', name: 'Colonic epithelium', tpm: 68, max: 100 },
      { organ: 'dermatologic', name: 'Stratified skin', tpm: 62, max: 100 },
      { organ: 'pulmonary', name: 'Bronchial epithelium', tpm: 39, max: 100 },
    ]},
    { id: 'Nectin-4', gene: 'NECTIN4', refAdc: 'enfortumab-vedotin', selectivity: 3.7, tissues: [
      { organ: 'dermatologic', name: 'Epidermal keratinocyte', tpm: 84, max: 100 },
      { organ: 'metabolic_endocrine', name: 'Salivary / Sweat gland', tpm: 45, max: 100 },
      { organ: 'ocular', name: 'Corneal epithelium', tpm: 34, max: 100 },
    ]},
    { id: 'CD79b', gene: 'CD79B', refAdc: 'polatuzumab-vedotin', selectivity: 5.4, tissues: [
      { organ: 'haematologic', name: 'B-lineage lymphoid', tpm: 72, max: 100 },
      { organ: 'infectious_immune', name: 'Spleen / Lymph node', tpm: 58, max: 100 },
      { organ: 'hepatic', name: 'Hepatic sinusoid', tpm: 12, max: 100 },
    ]},
    { id: 'BCMA (TNFRSF17)', gene: 'TNFRSF17', refAdc: 'belantamab-mafodotin', selectivity: 5.8, tissues: [
      { organ: 'haematologic', name: 'Plasma cell niche', tpm: 66, max: 100 },
      { organ: 'ocular', name: 'Corneal macropinocytosis', tpm: 49, max: 100 },
      { organ: 'renal', name: 'Renal tubular', tpm: 14, max: 100 },
    ]},
    { id: 'FRalpha (FOLR1)', gene: 'FOLR1', refAdc: 'mirvetuximab-soravtansine', selectivity: 4.5, tissues: [
      { organ: 'ocular', name: 'Ocular epithelium', tpm: 54, max: 100 },
      { organ: 'pulmonary', name: 'Type II pneumocyte', tpm: 44, max: 100 },
      { organ: 'renal', name: 'Proximal kidney tubule', tpm: 51, max: 100 },
    ]},
  ];

  const STUDIO_LINKERS = [
    { id: 'Tetrapeptide GGFG', cleavable: true, stability: 88, handle: 'amine_hydroxyl', note: 'Cathepsin B/L-cleavable tetrapeptide; self-immolative aminomethylene releases hydroxy/amine payload' },
    { id: 'Val-Cit PABC', cleavable: true, stability: 76, handle: 'amine', note: 'Cathepsin B-cleavable dipeptide with para-aminobenzyl carbamate spacer for secondary/primary amines' },
    { id: 'Hydrolyzable CL2A', cleavable: true, stability: 54, handle: 'hydroxyl', note: 'pH-sensitive carbonate linker; systemic and intratumoral hydrolysis releases SN-38' },
    { id: 'Non-cleavable mc', cleavable: false, stability: 96, handle: 'amine', note: 'Maleimidocaproyl thioether; requires complete lysosomal proteolysis to release Cys-mc-payload' },
    { id: 'Disulfide SPDB', cleavable: true, stability: 68, handle: 'thiol', note: 'Sterically hindered disulfide cleaved by intracellular glutathione for thiol maytansinoids' },
    { id: 'Acid Hydrazone', cleavable: true, stability: 48, handle: 'ketone', note: 'Acid-labile AcBut hydrazone hydrolyzed in endosomes/lysosomes (pH 4.5-5.0)' },
  ];

  const STUDIO_PAYLOADS = [
    { id: 'DXd ( Topo I )', cls: 'Topoisomerase I inhibitor', perm: true, handle: 'amine_hydroxyl', potency: 92, organs: { pulmonary: 82, haematologic: 68, gastrointestinal: 64, cardiovascular: 38 } },
    { id: 'SN-38 ( Topo I )', cls: 'Topoisomerase I inhibitor (UGT1A1)', perm: true, handle: 'hydroxyl', potency: 78, organs: { haematologic: 86, gastrointestinal: 84, hepatic: 44 } },
    { id: 'MMAE ( Auristatin )', cls: 'Microtubule inhibitor (Auristatin)', perm: true, handle: 'amine', potency: 90, organs: { neurologic: 84, haematologic: 76, dermatologic: 66, hepatic: 52 } },
    { id: 'MMAF ( Auristatin )', cls: 'Charged Auristatin (low permeability)', perm: false, handle: 'amine', potency: 86, organs: { ocular: 92, haematologic: 64, renal: 28 } },
    { id: 'DM4 / DM1 ( Maytansinoid )', cls: 'Microtubule inhibitor (Maytansinoid)', perm: true, handle: 'thiol', potency: 84, organs: { ocular: 74, hepatic: 72, neurologic: 62, haematologic: 58 } },
    { id: 'SG3199 ( PBD Dimer )', cls: 'DNA minor-groove crosslinker', perm: true, handle: 'amine', potency: 98, organs: { haematologic: 92, hepatic: 78, pulmonary: 68, dermatologic: 62 } },
  ];

  // ------------------------------------------------------------------ Session State
  const KEY = 'adctox.web.v070';
  function defaultState() {
    const p = PRESETS[0];
    return {
      mode: 0, // 0: ADC Matrix, 1: Structure Studio, 2: Patient & Labs
      presetId: p.id,
      conds: p.conds.map((c) => Object.assign({}, c)),
      raw: Object.assign({}, p.raw),
      labs: null,
      meanings: {},
      first: null,
      analysis: null,
      result: null,
      sel: -1,
      reviewAdc: null,
      drawer: false,
      labGroup: 'Basic',
      studio: Object.assign({}, p.studio),
    };
  }
  let S = defaultState();
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* ignore */ }
  }
  function restore() {
    try {
      const d = JSON.parse(sessionStorage.getItem(KEY) || 'null');
      if (d && typeof d === 'object' && Array.isArray(d.conds) && d.conds.length) {
        S = Object.assign(defaultState(), d);
      }
    } catch (e) { S = defaultState(); }
  }

  const regName = (id) => (REG[id] ? REG[id].label.replace(/\s*\([^)]*\)/g, '') : id);
  function condList() {
    const reg = S.conds.filter((c) => c.kind === 'reg').map((c) => c.value).sort((a, b) => (REG_I[a] ?? 1e9) - (REG_I[b] ?? 1e9));
    return reg.concat(S.conds.filter((c) => c.kind !== 'reg').map((c) => c.label));
  }
  const condName = (c) => (REG[c] ? regName(c) : c);
  function pickChoice() {
    const out = {};
    for (const c of S.conds) if (c.kind === 'mondo') out[c.label] = c.value;
    return out;
  }
  const allChoice = () => Object.assign(pickChoice(), S.meanings);
  const rawValues = () => Object.fromEntries(Object.entries(S.raw).filter(([, v]) => String(v).trim() !== ''));
  const chipMondo = (c) => c.mondo || (c.kind === 'mondo' ? c.value : c.kind === 'reg' && REG[c.value] ? REG[c.value].mondo || null : null);
  function pickedList() {
    const out = [];
    for (const c of S.conds) {
      if (c.kind === 'reg') out.push(c.value);
      out.push(c.label);
      const m = chipMondo(c);
      if (m) out.push(m);
    }
    for (const v of Object.values(S.meanings)) if (v) out.push(v);
    return [...new Set(out)];
  }

  // ------------------------------------------------------------------ Active Organ Resolution (Never 13 cells!)
  function activeOrgansWithScores() {
    const map = new Map();
    // 1. From completed AI analysis reports
    if (S.analysis && S.analysis.state === 'done') {
      for (const r of S.analysis.reports || []) {
        if (r.source === 'Cancer') continue;
        const used = r.organs || [];
        const pMap = r.p || {};
        for (const o of used) {
          const prev = map.get(o) || { organ: o, score: 0.78, condKey: r.condition };
          const sc = typeof pMap[o] === 'number' && pMap[o] > 0 ? pMap[o] : 0.85;
          if (sc >= prev.score) map.set(o, { organ: o, score: sc, condKey: r.condition });
        }
      }
    }
    // 2. From registry conditions directly (immediate before analysis job finishes)
    for (const c of S.conds) {
      if (c.kind === 'reg' && REG[c.value]) {
        for (const o of REG[c.value].organs || []) {
          if (!map.has(o)) map.set(o, { organ: o, score: 0.88, condKey: c.value });
        }
      }
    }
    // 3. From lab flags
    for (const fl of (S.labs && S.labs.flags) || []) {
      if (String(S.raw[fl.key] || '').trim()) {
        const prev = map.get(fl.organ);
        if (!prev) map.set(fl.organ, { organ: fl.organ, score: 0.82, condKey: null });
      }
    }
    // Order by AXES order, cap at 5 active organs for clean visual density
    return AX.filter((a) => map.has(a)).map((a) => map.get(a));
  }

  // ------------------------------------------------------------------ Page Frame
  let top, crumbsOl, verEl, presetBar, layout, stageBox, bar, barKeys, drawer, drawerTitle, drawerBody;

  function frame() {
    document.title = 'ADCTOX';
    crumbsOl = h('ol');
    verEl = h('div', { class: 'ver', text: '' });
    presetBar = h('div', { class: 'preset-group', role: 'group', 'aria-label': 'Clinical presets' });
    const brandWrap = h('div', { class: 'brand-wrap' },
      h('div', { class: 'brand' },
        h('span', { class: 'brand-bars', 'aria-hidden': 'true' }, h('i'), h('i'), h('i')),
        'ADCToX'),
      verEl);
    top = h('header', { class: 'top' },
      brandWrap,
      h('nav', { class: 'crumbs', 'aria-label': 'Workspace modes' }, crumbsOl),
      h('div', { class: 'right' },
        presetBar,
        h('button', { type: 'button', class: 'help', 'aria-label': 'How it works', title: 'How it works', text: '?', onclick: openGuide })));

    stageBox = h('main', { class: 'stage' });
    layout = h('div', { class: 'layout' }, stageBox);
    barKeys = h('div', { class: 'keys', 'aria-hidden': 'true' });
    bar = h('footer', { class: 'bar' },
      h('span', { text: 'ADCTOX Clinical Decision & Conjugate Architecture Workspace' }),
      barKeys);

    drawerTitle = h('h2', { id: 'dr-title' });
    drawerBody = h('div', { class: 'dr-body' });
    const x = h('button', { class: 'x', type: 'button', 'aria-label': 'Close', text: '×', onclick: () => closeDrawer() });
    drawer = h('div', { class: 'drawer', role: 'dialog', 'aria-modal': 'false', 'aria-labelledby': 'dr-title', 'aria-hidden': 'true' },
      h('div', { class: 'dr-head' }, drawerTitle, x), drawerBody);

    document.body.append(top, h('div', { class: 'shell' }, h('div', { class: 'wrap' }, layout)), bar, drawer, tipBox);
  }

  function renderHeaderControls() {
    clear(crumbsOl);
    MODES.forEach((name, i) => {
      const now = i === S.mode;
      const btn = h('button', {
        class: 'cb', type: 'button',
        'aria-current': now ? 'step' : null,
        onclick: () => switchMode(i),
      }, h('span', { class: 'step-number', 'aria-hidden': 'true', text: String(i + 1) }), name);
      crumbsOl.append(h('li', { class: 'crumb' + (now ? ' now' : '') }, btn));
    });

    clear(presetBar);
    PRESETS.forEach((p) => {
      const b = h('button', {
        type: 'button',
        class: 'preset-btn' + (S.presetId === p.id ? ' active' : ''),
        text: p.label,
        title: 'Load clinical preset: ' + p.label,
        onclick: () => applyPreset(p),
      });
      presetBar.append(b);
    });
  }

  async function applyPreset(p) {
    S.presetId = p.id;
    S.conds = p.conds.map((c) => Object.assign({}, c));
    S.raw = Object.assign({}, p.raw);
    S.meanings = {};
    S.first = null;
    S.analysis = null;
    S.result = null;
    S.sel = 0;
    if (p.studio) S.studio = Object.assign({}, p.studio);
    save();
    closeDrawer(true);
    renderHeaderControls();
    await refreshBackendData();
    switchMode(S.mode, true);
  }

  // ------------------------------------------------------------------ Background Data Sync (/api/labs, /api/recommend, /api/analyze)
  let syncSeq = 0;
  async function refreshBackendData() {
    const seq = ++syncSeq;
    try {
      const labsRes = await API.labs(rawValues());
      if (seq !== syncSeq) return;
      S.labs = labsRes;
    } catch (e) { /* keep existing */ }

    try {
      const labRaw = (S.labs && S.labs.raw) || rawValues();
      const recRes = await API.recommend({
        conditions: condList(),
        raw: labRaw,
        choice: allChoice(),
        first: S.first,
      });
      if (seq !== syncSeq) return;
      S.result = { sig: resultSig(), data: recRes };
      save();
    } catch (e) { /* ignore */ }

    // Trigger non-blocking organ analysis if needed
    runBackgroundAnalysis(seq);
  }

  async function runBackgroundAnalysis(seq) {
    const sig = JSON.stringify([condList(), pickChoice()]);
    if (S.analysis && S.analysis.sig === sig && S.analysis.state === 'done') return;
    if (!condList().length) return;
    try {
      const start = await API.analyze(condList(), pickChoice());
      if (seq !== syncSeq) return;
      const job = start.job;
      for (let k = 0; k < 80; k++) {
        await sleep(200);
        if (seq !== syncSeq) return;
        const r = await API.job(job);
        if (r.state === 'done' || r.state === 'error') {
          S.analysis = {
            sig, state: r.state, error: r.error || null,
            reports: r.reports || [], ambiguous: r.ambiguous || [], unresolved: r.unresolved || [],
          };
          save();
          if (S.mode === 0 || S.mode === 2) renderActiveMode(false);
          return;
        }
      }
    } catch (e) { /* background job optional */ }
  }

  function resultSig() {
    return JSON.stringify([condList(), rawValues(), allChoice(), S.first]);
  }

  // ------------------------------------------------------------------ Unified Patient & Active-Organ Bar (Top of Mode 0 & Mode 1)
  function buildWorkspaceBar(onChanged) {
    const st = { q: '', items: [], cur: -1, timer: 0, seq: 0 };
    const input = h('input', {
      type: 'text',
      role: 'combobox',
      'aria-expanded': 'false',
      'aria-controls': 'wb-sugg',
      'aria-autocomplete': 'list',
      'aria-label': 'Condition, symptom or cancer',
      placeholder: 'Condition, symptom or cancer',
      autocomplete: 'off',
      autocapitalize: 'off',
      spellcheck: 'false',
    });
    const sugg = h('ul', { class: 'wb-sugg', id: 'wb-sugg', role: 'listbox', 'aria-label': 'Suggestions', hidden: true });
    const chipsWrap = h('div', { class: 'wb-chips', 'aria-label': 'Active patient profile' });

    function chipOf(s) {
      const p = s.pick || {};
      if (s.id) return { kind: 'reg', value: s.id, label: s.text, mondo: s.mondo || null };
      if (p.choice) return { kind: 'mondo', value: p.choice, label: p.condition || s.text, mondo: p.choice };
      return { kind: 'text', value: p.condition || s.text, label: p.condition || s.text };
    }

    async function addConditionChip(c) {
      c.label = String(c.label || '').normalize('NFC');
      const m = chipMondo(c);
      if (S.conds.some((x) => (x.kind === c.kind && x.value === c.value) || x.label.toLowerCase() === c.label.toLowerCase() || (m && chipMondo(x) === m))) {
        return;
      }
      S.presetId = null;
      S.conds.push(c);
      save();
      await refreshBackendData();
      if (onChanged) onChanged();
    }

    async function removeConditionChip(idx) {
      const removed = S.conds.splice(idx, 1)[0];
      if (removed) {
        delete S.meanings[removed.label];
        if (S.first === removed.label || S.first === removed.value) S.first = null;
      }
      S.presetId = null;
      save();
      await refreshBackendData();
      if (onChanged) onChanged();
    }

    function renderChips() {
      clear(chipsWrap);
      const P = (S.result && S.result.data && S.result.data.patient) || {};
      const cancerConds = new Set((P.cancers || []).map((c) => c.condition));

      S.conds.forEach((c, idx) => {
        const isCancer = cancerConds.has(c.label) || cancerConds.has(c.value) || /carcinoma|cancer|lymphoma|myeloma|leukemia|tumor/i.test(c.label);
        const rm = h('button', {
          type: 'button', class: 'x',
          'aria-label': 'Remove ' + c.label,
          text: '×',
          onclick: () => removeConditionChip(idx),
        });
        chipsWrap.append(h('span', { class: 'p-chip' + (isCancer ? ' cancer-chip' : '') },
          h('span', { text: c.label }), rm));
      });

      // Summary lab chips (clickable to jump to Patient & Labs mode)
      const L = S.labs || {};
      const sh = (L.derived && L.derived.shown) || {};
      const labBadges = [];
      if (sh.bili) labBadges.push(`Bili ${sh.bili}xULN`);
      else if (S.raw.bilirubin) labBadges.push(`Bili ${S.raw.bilirubin} mg/dL`);
      if (sh.crcl) labBadges.push(`CLcr ${sh.crcl} mL/min`);
      else if (S.raw.creatinine) labBadges.push(`Cr ${S.raw.creatinine} mg/dL`);
      if (S.raw.lvef) labBadges.push(`LVEF ${S.raw.lvef}%`);

      if (labBadges.length) {
        chipsWrap.append(h('button', {
          type: 'button',
          class: 'p-chip lab-chip',
          title: 'Edit laboratory values',
          text: labBadges.join('  /  '),
          onclick: () => switchMode(2),
        }));
      } else {
        chipsWrap.append(h('button', {
          type: 'button',
          class: 'p-chip lab-chip',
          text: '+ Labs',
          onclick: () => switchMode(2),
        }));
      }
    }

    function renderSugg() {
      clear(sugg);
      const show = st.items.length > 0 && st.q.trim() !== '';
      sugg.hidden = !show;
      input.setAttribute('aria-expanded', show ? 'true' : 'false');
      if (!show) return;
      st.items.slice(0, 7).forEach((it, i) => {
        const li = h('li', {
          class: 'opt', role: 'option',
          'aria-selected': i === st.cur ? 'true' : 'false',
        },
        h('span', { class: 'nm' },
          h('span', { class: 'main', text: it.kind === 'raw' ? `+ Add "${it.text}"` : it.s.text }),
          it.s && it.s.sub ? h('span', { class: 'sub', text: it.s.sub }) : null));
        li.addEventListener('mousedown', (e) => {
          e.preventDefault();
          pickItem(it);
        });
        sugg.append(li);
      });
    }

    async function pickItem(it) {
      input.value = '';
      st.q = '';
      st.items = [];
      renderSugg();
      if (it.kind === 'raw') await addConditionChip({ kind: 'text', value: it.text, label: it.text });
      else await addConditionChip(chipOf(it.s));
    }

    async function runSuggest() {
      const q = st.q.trim();
      const seq = ++st.seq;
      if (!q) { st.items = []; renderSugg(); return; }
      try {
        const r = await API.suggest(q, pickedList());
        if (seq !== st.seq) return;
        const out = [];
        for (const s of r.names || []) out.push({ kind: 's', s });
        for (const s of r.symptoms || []) out.push({ kind: 'sym', s });
        out.push({ kind: 'raw', text: q });
        st.items = out;
        st.cur = 0;
        renderSugg();
      } catch (e) {
        st.items = [{ kind: 'raw', text: q }];
        st.cur = 0;
        renderSugg();
      }
    }

    input.addEventListener('input', () => {
      st.q = input.value;
      clearTimeout(st.timer);
      if (!st.q.trim()) { st.items = []; renderSugg(); return; }
      st.timer = setTimeout(runSuggest, 120);
    });
    input.addEventListener('blur', () => { setTimeout(() => { sugg.hidden = true; input.setAttribute('aria-expanded', 'false'); }, 150); });
    input.addEventListener('keydown', (e) => {
      if (e.isComposing || e.keyCode === 229) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        if (!st.items.length) return;
        e.preventDefault();
        const max = Math.min(7, st.items.length) - 1;
        st.cur = Math.max(0, Math.min(max, st.cur + (e.key === 'ArrowDown' ? 1 : -1)));
        renderSugg();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (st.items[st.cur]) pickItem(st.items[st.cur]);
        else if (st.q.trim()) pickItem({ kind: 'raw', text: st.q.trim() });
      } else if (e.key === 'Escape') {
        st.q = ''; input.value = ''; st.items = []; renderSugg();
      }
    });

    renderChips();

    // Right side: Active Organ Horizon Strip (ONLY the patient's active organs!)
    const activeOrgans = activeOrgansWithScores();
    const organsGrid = h('div', { class: 'active-organs-grid' });
    if (activeOrgans.length) {
      activeOrgans.forEach((item) => {
        const pct = Math.round(Math.max(15, Math.min(100, item.score * 100)));
        const isPrio = item.condKey && S.first === item.condKey;
        const btn = h('button', {
          type: 'button',
          class: 'organ-meter-btn' + (isPrio ? ' prio-active' : ''),
          title: item.condKey ? 'Click to prioritize ' + (SHORT[item.organ] || item.organ) + ' safety in ADC ranking' : (SHORT[item.organ] || item.organ),
          onclick: async () => {
            if (!item.condKey) return;
            S.first = S.first === item.condKey ? null : item.condKey;
            save();
            await refreshBackendData();
            if (onChanged) onChanged();
          },
        },
        h('div', { class: 'om-top' },
          h('span', { class: 'om-name', text: SHORT[item.organ] || item.organ }),
          h('span', { class: 'om-val', text: isPrio ? 'Priority 1' : `${pct}%` })),
        h('div', { class: 'om-track' },
          h('i', { class: 'om-fill', style: `width:${pct}%` })));
        organsGrid.append(btn);
      });
    } else {
      organsGrid.append(h('span', { class: 'dim', text: 'No vulnerable organs flagged yet' }));
    }

    return h('section', { class: 'workspace-bar', 'aria-label': 'Patient and active organ profile' },
      h('div', { class: 'wb-left' },
        h('div', { class: 'wb-search-row' },
          h('div', { class: 'wb-input-wrap' },
            h('span', { class: 'dim', 'aria-hidden': 'true', text: '+' }),
            input),
          h('button', { type: 'button', class: 'wb-btn', text: 'Labs & AI', onclick: () => switchMode(2) }),
          sugg),
        chipsWrap),
      h('div', { class: 'wb-right' },
        h('div', { class: 'horizon-head' },
          h('span', { class: 'horizon-label', text: `Active Patient Organs (${activeOrgans.length})` }),
          h('span', { class: 'horizon-sub', text: S.first ? 'Prioritized' : 'Click organ to weight first' })),
        organsGrid));
  }

  // ------------------------------------------------------------------ Helpers for ADC Cards & Rows
  function getArchPills(adcId, row) {
    const m = MECH[adcId];
    if (m) {
      const pills = [];
      if (m.target) pills.push(m.target.split(';')[0].trim());
      if (m.payload_class) pills.push(m.payload_class.replace(/\s*inhibitor/i, '').trim());
      if (m.dar) pills.push('DAR ' + String(m.dar).replace(/^~/, ''));
      return pills;
    }
    const p = row && row.detail && row.detail.payload;
    if (p && p.rows) {
      return p.rows.slice(0, 3).map(([, v]) => v.split(',')[0]);
    }
    return [];
  }

  function statusInfo(row) {
    const detail = row.detail || {};
    const reason = (detail.reasons || []).find((r) => r.status === row.status && !!r.sure === !!row.sure) || (detail.reasons || []).find((r) => r.status === row.status);
    if (row.status === 'None' || row.status === 'No change') {
      return { tone: 'clear', bars: 'clear', label: 'Standard', full: 'Standard dosing' };
    }
    if (reason && reason.code === 'contraindicated') {
      return { tone: 'avoid', bars: 'avoid', label: 'Contraindicated', full: 'Contraindicated' };
    }
    if (row.status === 'Avoid') {
      return { tone: 'avoid', bars: 'avoid', label: row.sure ? 'Avoid' : 'Avoid (check)', full: 'Avoid use' };
    }
    if (row.status === 'Lower dose' || (reason && reason.code === 'reduce_dose')) {
      return { tone: 'monitor', bars: 'monitor', label: 'Dose adjust', full: 'Dose adjustment' };
    }
    if (row.status === 'Monitor') {
      return { tone: 'monitor', bars: 'monitor', label: 'Monitor', full: 'Close monitoring' };
    }
    return { tone: 'limited', bars: 'limited', label: 'Limited data', full: 'Not studied in cohort' };
  }

  function organStatusForRow(row, organ) {
    const detail = row.detail || {};
    const allWarnings = [].concat(detail.warnings || [], detail.other_warnings || []);
    const found = allWarnings.find((w) => w.organ === organ);
    if (!found) return { cls: 'clear', tag: 'Clear', title: 'No label warning on ' + (SHORT[organ] || organ) };
    if (String(found.mark).trim() === '!!') {
      return { cls: 'boxed', tag: 'Boxed', title: 'Boxed Warning: ' + found.text };
    }
    return { cls: 'warn', tag: 'Warn', title: 'Section 5 Warning: ' + found.text };
  }

  function primaryTrialEvent(row, activeOrgans) {
    const t = row.detail && row.detail.trial;
    if (!t || !t.trial || t.no_results || !Array.isArray(t.organs)) return null;
    // Pick event on first active organ that has events, or fallback to any organ event
    for (const item of activeOrgans) {
      const o = t.organs.find((x) => x.organ === item.organ);
      if (o && o.events && o.events.length) return { trial: t, organ: item.organ, ev: o.events[0] };
    }
    for (const o of t.organs) {
      if (o.events && o.events.length) return { trial: t, organ: o.organ, ev: o.events[0] };
    }
    return null;
  }

  function buildDualBar(trialHit) {
    if (!trialHit) {
      return h('span', { class: 'dim', style: 'font-size:11px', text: 'Single-arm / registry' });
    }
    const { trial, ev } = trialHit;
    const adcPct = (100 * ev.a) / Math.max(1, ev.n);
    const cmpPct = ev.comp ? (100 * ev.comp[0]) / Math.max(1, ev.comp[1]) : null;
    const scaleMax = Math.max(25, adcPct, cmpPct || 0);

    return h('div', {
      class: 'dual-bar-group',
      title: `${trial.trial}: ${ev.term}\nADC (${trial.regimen}): ${ev.a}/${ev.n} (${ev.pct})` + (ev.comp ? `\nControl (${trial.comparator.regimen}): ${ev.comp[0]}/${ev.comp[1]} (${ev.comp_pct})` : ''),
    },
    h('div', { class: 'dual-bar-title' },
      h('span', { text: ev.term }),
      h('span', { class: 'dim', text: trial.trial })),
    h('div', { class: 'dual-bar-row' },
      h('span', { class: 'db-tag', text: 'ADC' }),
      h('span', { class: 'db-track' }, h('i', { class: 'db-fill-adc', style: `width:${Math.min(100, (adcPct / scaleMax) * 100).toFixed(1)}%` })),
      h('span', { class: 'db-pct', text: ev.pct })),
    cmpPct !== null ? h('div', { class: 'dual-bar-row' },
      h('span', { class: 'db-tag', text: 'CMP' }),
      h('span', { class: 'db-track' }, h('i', { class: 'db-fill-cmp', style: `width:${Math.min(100, (cmpPct / scaleMax) * 100).toFixed(1)}%` })),
      h('span', { class: 'db-pct cmp', text: ev.comp_pct })) : null);
  }

  // ------------------------------------------------------------------ Mode 0: Visual ADC Matrix (Spotlight Hero Cards + Monochrome Cohort Table)
  function buildAdcMatrixMode() {
    const box = h('div', { class: 's5' });
    box.append(buildWorkspaceBar(() => renderMatrixContent()));
    const content = h('div');
    box.append(content);

    function renderMatrixContent() {
      clear(content);
      const res = S.result && S.result.data;
      if (!res || !Array.isArray(res.rows)) {
        content.append(h('div', { class: 'panel', style: 'padding:24px' }, h('span', { class: 'dim', text: 'Loading ADC matrix...' })));
        return;
      }
      const P = res.patient || {};
      shownPatient = P;
      const hasCancer = !!(P.cancers || []).length;
      const rows = res.rows;
      const activeOrgans = activeOrgansWithScores();

      // Determine Top Recommended Spotlight ADCs:
      // Indicated (when cancer entered) and not Avoid, up to top 2 rank tier
      const topCandidates = rows.filter((r) => (hasCancer ? r.indicated === true : true) && r.status !== 'Avoid');
      const spotlightRows = (topCandidates.length ? topCandidates : rows).slice(0, 2);
      const spotlightSet = new Set(spotlightRows.map((r) => r.adc));

      // 1. Spotlight Section for Top Recommended ADCs (Full Cobalt/Emerald Color & Larger Cards)
      const spGrid = h('div', { class: 'spotlight-grid' });
      const cardEls = new Map();

      spotlightRows.forEach((row) => {
        const idx = rows.indexOf(row);
        const st = statusInfo(row);
        const pills = getArchPills(row.adc, row);
        const trialHit = primaryTrialEvent(row, activeOrgans);

        const organBars = h('div', { class: 'sp-organ-bars' });
        (activeOrgans.length ? activeOrgans.slice(0, 4) : [{ organ: 'hepatic' }, { organ: 'pulmonary' }, { organ: 'haematologic' }]).forEach((item) => {
          const os = organStatusForRow(row, item.organ);
          organBars.append(h('div', { class: 'sp-organ-row', title: os.title },
            h('span', { class: 'sp-organ-name', text: SHORT[item.organ] || item.organ }),
            h('span', { class: 'sp-organ-track' }, h('i', { class: 'sp-organ-fill ' + os.cls })),
            h('span', { class: 'sp-organ-state ' + os.cls, text: os.tag })));
        });

        const card = h('article', {
          class: 'spotlight-card',
          tabindex: '0',
          'aria-selected': S.sel === idx ? 'true' : 'false',
          onclick: () => { selectRow(idx, false); openDrawer(); },
          onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectRow(idx, false); openDrawer(); } },
        },
        h('div', { class: 'sp-head' },
          h('div', { class: 'sp-title-group' },
            h('div', { class: 'sp-rank-row' },
              h('span', { class: 'sp-rank', text: `TOP #${row.rank}` }),
              hasCancer && row.indicated ? h('span', { class: 'sp-match-tag', text: (row.cancers && row.cancers[0]) || 'Indicated' }) : null),
            h('h2', { class: 'sp-name', text: row.name }),
            pills.length ? h('div', { class: 'sp-arch' }, pills.map((p) => h('span', { class: 'arch-pill', text: p }))) : null),
          h('span', { class: 'sp-status-badge ' + st.tone, text: st.full })),
        h('div', { class: 'sp-metrics' },
          h('div', { class: 'sp-metric-box' },
            h('span', { class: 'sp-metric-label', text: 'Patient Active Organs' }),
            organBars),
          h('div', { class: 'sp-metric-box' },
            h('span', { class: 'sp-metric-label', text: 'Pivotal Trial Incidence' }),
            buildDualBar(trialHit))));

        cardEls.set(idx, card);
        spGrid.append(card);
      });

      content.append(h('section', { class: 'spotlight-section', 'aria-label': 'Top recommended ADCs' },
        h('div', { class: 'sec-bar' },
          h('span', { class: 'sec-kicker', text: 'Primary Recommendation Spotlight' }),
          h('span', { class: 'dim', style: 'font-size:11.5px', text: 'Click any card or row for FDA label & trial evidence' })),
        spGrid));

      // 2. Full Cohort Comparison Table (Lower-ranked rows rendered in quiet monochrome slate)
      let filter = 'all';
      const relevant = (row) => (hasCancer ? row.indicated === true : true);
      const restricted = (row) => row.status && !['None', 'No change'].includes(row.status);
      const filters = [
        ['all', 'All Approved ADCs', rows.length, () => true],
        ['relevant', 'Cancer Match', rows.filter(relevant).length, relevant],
        ['restrictions', 'Label Restrictions', rows.filter(restricted).length, restricted],
      ];

      const tabs = h('div', { class: 'review-filters', role: 'group', 'aria-label': 'Filter ADCs' });
      const toolbar = h('div', { class: 'review-toolbar' },
        tabs,
        h('button', { type: 'button', class: 'export-button', text: 'Export Clinical Summary', onclick: () => saveReview(res) }));
      content.append(toolbar);

      const grid = h('div', { class: 'review-grid', role: 'grid', 'aria-label': 'ADC Cohort Matrix' },
        h('div', { class: 'review-grid-head', role: 'row' },
          h('span', { role: 'columnheader', text: '#' }),
          h('span', { role: 'columnheader', text: 'ADC & Architecture' }),
          tipped(h('span', { role: 'columnheader', text: 'Regimen Fit' })),
          tipped(h('span', { role: 'columnheader', text: 'Active Organ Profile' })),
          tipped(h('span', { role: 'columnheader', text: 'Pivotal Trial vs Control' }))));

      const trs = [];
      let visible = rows.map((_, i) => i);

      rows.forEach((row, i) => {
        const isTop = spotlightSet.has(row.adc);
        const st = statusInfo(row);
        const pills = getArchPills(row.adc, row);
        const trialHit = primaryTrialEvent(row, activeOrgans);

        const miniOrgans = h('div', { class: 'active-organ-cell', role: 'gridcell' });
        (activeOrgans.length ? activeOrgans.slice(0, 3) : [{ organ: 'hepatic' }, { organ: 'pulmonary' }]).forEach((item) => {
          const os = organStatusForRow(row, item.organ);
          miniOrgans.append(h('div', { class: 'mini-organ-bar ' + os.cls, title: os.title },
            h('span', { text: SHORT[item.organ] || item.organ }),
            h('b', null, h('i')),
            h('span', { class: 'mo-tag', text: os.cls === 'boxed' ? '!!' : os.cls === 'warn' ? '!' : 'OK' })));
        });

        const tr = h('div', {
          class: 'review-row ' + (isTop ? 'tier-top' : 'tier-muted'),
          role: 'row',
          tabindex: i === S.sel ? '0' : '-1',
          'aria-selected': i === S.sel ? 'true' : 'false',
        },
        h('div', { class: 'rank-cell', role: 'gridcell', text: `#${row.rank}` }),
        h('div', { class: 'drug-cell', role: 'gridcell' },
          h('div', { class: 'drug-name-row' },
            h('span', { class: 'drug-name', text: row.name }),
            hasCancer && row.indicated ? h('span', { class: 'sp-match-tag', text: 'Match' }) : null),
          h('span', { class: 'drug-meta', text: pills.join('  /  ') || (row.cancers || []).join(', ') })),
        h('div', { class: 'status-cell', role: 'gridcell' },
          h('span', { class: 'reg-bars ' + st.bars, 'aria-hidden': 'true' }, h('i'), h('i'), h('i')),
          h('span', { class: 'status-pill ' + (st.tone === 'clear' ? 'neutral' : st.tone), text: st.label })),
        miniOrgans,
        h('div', { class: 'trial-cell', role: 'gridcell' }, buildDualBar(trialHit)));

        tr.addEventListener('click', () => { selectRow(i, true); openDrawer(); });
        trs.push(tr);
        grid.append(tr);
      });

      const filterBtns = filters.map(([id, label, count, fn]) => {
        const b = h('button', { type: 'button', class: 'filter-tab', 'aria-pressed': id === filter ? 'true' : 'false' },
          label, h('span', { class: 'filter-count', text: count }));
        b.addEventListener('click', () => {
          filter = id;
          filterBtns.forEach((btn, k) => btn.setAttribute('aria-pressed', filters[k][0] === id ? 'true' : 'false'));
          visible = rows.map((r, idx) => (fn(r) ? idx : -1)).filter((idx) => idx >= 0);
          trs.forEach((tr, idx) => { tr.hidden = !visible.includes(idx); });
        });
        tabs.append(b);
        return b;
      });

      content.append(grid);

      function selectRow(i, focusRow) {
        S.sel = i;
        S.reviewAdc = rows[i] ? rows[i].adc : null;
        save();
        trs.forEach((tr, k) => {
          tr.setAttribute('aria-selected', k === i ? 'true' : 'false');
          tr.tabIndex = k === i ? 0 : -1;
        });
        cardEls.forEach((card, k) => {
          card.setAttribute('aria-selected', k === i ? 'true' : 'false');
        });
        if (focusRow && trs[i]) trs[i].focus({ preventScroll: false });
        if (S.drawer && rows[i]) fillDrawer(rows[i]);
      }

      resultKeys = (e) => {
        if (!visible.length) return;
        const at = visible.indexOf(S.sel);
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          const nextIdx = visible[Math.max(0, Math.min(visible.length - 1, (at < 0 ? 0 : at) + (e.key === 'ArrowDown' ? 1 : -1)))];
          selectRow(nextIdx, true);
        } else if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openDrawer();
        }
      };

      openDrawer = () => {
        if (S.sel < 0 && rows.length) S.sel = 0;
        if (rows[S.sel]) {
          fillDrawer(rows[S.sel]);
          showDrawer();
        }
      };
      returnFocus = () => { if (trs[S.sel]) trs[S.sel].focus({ preventScroll: true }); };
      keepRow = () => { if (S.mode === 0 && trs[S.sel] && trs[S.sel].isConnected) trs[S.sel].scrollIntoView({ block: 'nearest' }); };

      if (S.reviewAdc) {
        const foundIdx = rows.findIndex((r) => r.adc === S.reviewAdc);
        if (foundIdx >= 0) S.sel = foundIdx;
      }
      if (S.sel < 0 && rows.length) S.sel = 0;
      selectRow(S.sel, false);
      if (S.drawer && rows[S.sel]) openDrawer();
    }

    renderMatrixContent();
    clear(barKeys);
    add(barKeys, [kbd('↑↓', 'select'), kbd('Enter', 'details')]);
    return box;
  }

  // ------------------------------------------------------------------ Mode 1: Structure & Combination Studio (4-Part Conjugate Design)
  function buildStructureStudioMode() {
    const box = h('div', { class: 's-studio' });
    box.append(buildWorkspaceBar(() => renderStudioCanvas()));
    const wrap = h('div', { class: 'studio-wrap' });
    const controls = h('aside', { class: 'studio-controls panel', 'aria-label': 'Conjugate Architecture Controls' });
    const canvas = h('div', { class: 'studio-canvas' });
    wrap.append(controls, canvas);
    box.append(wrap);

    function renderControls() {
      clear(controls);
      const makeGroup = (label, items, current, onPick) => {
        const pills = h('div', { class: 'studio-pills' });
        items.forEach((it) => {
          const val = typeof it === 'string' ? it : it.id;
          const b = h('button', {
            type: 'button',
            class: 'st-pill',
            'aria-pressed': val === current ? 'true' : 'false',
            text: val,
            onclick: () => { onPick(val); save(); renderControls(); renderStudioCanvas(); },
          });
          pills.append(b);
        });
        return h('div', { class: 'studio-group' }, h('span', { class: 'studio-label', text: label }), pills);
      };

      controls.append(
        makeGroup('1. Target Antigen (mAb)', STUDIO_TARGETS, S.studio.target, (v) => { S.studio.target = v; }),
        makeGroup('2. Chemical Linker', STUDIO_LINKERS, S.studio.linker, (v) => { S.studio.linker = v; }),
        makeGroup('3. Cytotoxic Payload', STUDIO_PAYLOADS, S.studio.payload, (v) => { S.studio.payload = v; }),
        makeGroup('4. Drug-to-Antibody Ratio (DAR)', ['2', '3.5', '4', '6', '7.6', '8'], String(S.studio.dar), (v) => { S.studio.dar = parseFloat(v); }),
        makeGroup('5. Fc Gamma Receptor Engineering', ['Wild-type IgG1', 'Fc-Silenced (LALA-PG)'], S.studio.fc ? 'Fc-Silenced (LALA-PG)' : 'Wild-type IgG1', (v) => { S.studio.fc = v.includes('LALA'); })
      );
    }

    function renderStudioCanvas() {
      clear(canvas);
      const tgt = STUDIO_TARGETS.find((x) => x.id === S.studio.target) || STUDIO_TARGETS[0];
      const lnk = STUDIO_LINKERS.find((x) => x.id === S.studio.linker) || STUDIO_LINKERS[0];
      const pld = STUDIO_PAYLOADS.find((x) => x.id === S.studio.payload) || STUDIO_PAYLOADS[0];
      const dar = Number(S.studio.dar) || 4;
      const fcSilenced = !!S.studio.fc;

      // 1. Chemical Handle Compatibility
      const handleMatch = lnk.handle === pld.handle || lnk.handle.includes(pld.handle) || pld.handle.includes(lnk.handle);
      // 2. Bystander Effect
      const bystander = lnk.cleavable && pld.perm;
      // 3. Hydrophobic Aggregation / Clearance adjustment for high DAR
      const darPenalty = dar > 4 && !lnk.id.includes('GGFG') && !lnk.id.includes('CL2A') ? (dar - 4) * 5.5 : (dar - 4) * 2.0;
      const stabilityScore = Math.max(25, Math.min(98, Math.round(lnk.stability - Math.max(0, darPenalty))));

      // Top Summary Metrics Bar
      const hero = h('div', { class: 'studio-hero panel' },
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: 'Chemical Conjugation Gate' }),
          h('span', { class: 'sh-val ' + (handleMatch ? 't-green' : 't-amber'), text: handleMatch ? 'Compatible Handle' : 'Spacer Required' }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${handleMatch ? 100 : 55}%;background:${handleMatch ? 'var(--emerald)' : 'var(--amber)'}` }))),
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: 'Tumor / Normal Selectivity' }),
          h('span', { class: 'sh-val', text: `+${tgt.selectivity.toFixed(1)} log2FC` }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${Math.min(100, tgt.selectivity * 16)}%;background:var(--accent)` }))),
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: 'Bystander Killing Capacity' }),
          h('span', { class: 'sh-val', text: bystander ? 'Active Diffusion' : 'Cell-Autonomous' }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${bystander ? 92 : 34}%;background:${bystander ? 'var(--accent)' : 'var(--dim)'}` }))),
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: 'Plasma Linker Stability' }),
          h('span', { class: 'sh-val', text: `${stabilityScore}% Intact` }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${stabilityScore}%;background:var(--emerald)` }))));

      // Panel A: Patient Active Organ Burden for Designed Conjugate vs Approved Reference
      const activeOrgans = activeOrgansWithScores();
      const organsToShow = activeOrgans.length ? activeOrgans : [
        { organ: 'pulmonary', score: 0.85 },
        { organ: 'hepatic', score: 0.78 },
        { organ: 'haematologic', score: 0.72 },
        { organ: 'cardiovascular', score: 0.65 },
      ];

      const organRows = h('div', { class: 'expr-list' });
      organsToShow.forEach((item) => {
        const basePld = pld.organs[item.organ] || 32;
        const onTarget = (tgt.tissues.find((t) => t.organ === item.organ) || { tpm: 15 }).tpm * 0.45;
        const darFactor = 0.75 + (dar / 8) * 0.42;
        const fcFactor = fcSilenced && ['pulmonary', 'haematologic', 'ocular', 'hepatic'].includes(item.organ) ? 0.82 : 1.0;
        const burden = Math.min(98, Math.round((basePld * 0.65 + onTarget) * darFactor * fcFactor));
        const color = burden >= 75 ? 'var(--red)' : burden >= 52 ? 'var(--amber)' : 'var(--emerald)';

        organRows.append(h('div', { class: 'expr-row' },
          h('span', { class: 'ex-name', text: SHORT[item.organ] || item.organ }),
          h('span', { class: 'ex-track' }, h('i', { class: 'ex-fill', style: `width:${burden}%;background:${color}` })),
          h('span', { class: 'ex-val', style: `color:${color}`, text: `${burden} idx` })));
      });

      // Panel B: GTEx Normal Tissue Target Expression Profile
      const gtexRows = h('div', { class: 'expr-list' });
      tgt.tissues.forEach((t) => {
        gtexRows.append(h('div', { class: 'expr-row' },
          h('span', { class: 'ex-name', text: SHORT[t.organ] || t.organ }),
          h('span', { class: 'ex-track' }, h('i', { class: 'ex-fill', style: `width:${t.tpm}%;background:var(--accent)` })),
          h('span', { class: 'ex-val', text: `${t.tpm} nTPM` })));
      });

      const grid2 = h('div', { class: 'studio-grid-2' },
        h('section', { class: 'studio-card panel' },
          h('h3', { text: 'Patient Active Organ Toxicity Index (Simulated Architecture)' }),
          organRows,
          h('p', { class: 'dim', style: 'margin:12px 0 0;font-size:11.5px', text: fcSilenced ? 'LALA-PG Fc-silencing active: off-target FcgammaR alveolar macrophage and megakaryocyte uptake reduced.' : 'Wild-type IgG1 Fc: standard FcgammaR-mediated immune effector & macrophage uptake.' })),
        h('section', { class: 'studio-card panel' },
          h('h3', { text: `GTEx Normal Tissue Expression (${tgt.gene})` }),
          gtexRows,
          h('p', { class: 'dim', style: 'margin:12px 0 0;font-size:11.5px', text: lnk.note })));

      canvas.append(hero, grid2);
    }

    renderControls();
    renderStudioCanvas();
    clear(barKeys);
    add(barKeys, [kbd('1-3', 'Switch Mode')]);
    return box;
  }

  // ------------------------------------------------------------------ Mode 2: Full Patient, Lab & AI Organ Editor
  const touched = new Set();
  function buildPatientLabsMode() {
    const box = h('div', { class: 's2' });
    box.append(buildWorkspaceBar(() => {
      refreshBackendData().then(() => renderPatientLabsBody());
    }));
    const bodyWrap = h('div');
    box.append(bodyWrap);

    function renderPatientLabsBody() {
      clear(bodyWrap);
      // 1. Categorized Lab Editor (preserving .groups { columns: 2 } container layout)
      const groupNames = ((APP && APP.labs && APP.labs.groups) || []).filter((g) => FIELDS.some((f) => f.group === g));
      let activeGroup = groupNames.includes(S.labGroup) ? S.labGroup : (groupNames[0] || 'Basic');
      const groupLabels = {
        Basic: 'Basic & Anthropometrics', Kidney: 'Renal Function', Liver: 'Hepatic Panel',
        Blood: 'Haematology', Glucose: 'Metabolic', Pancreas: 'Pancreatic',
        Thyroid: 'Thyroid', Cardio: 'Cardiovascular', Genotype: 'Pharmacogenomics',
      };
      const groupButtons = new Map();
      const rows = {};

      function selectGroup(name) {
        activeGroup = name;
        S.labGroup = name;
        save();
        groups.forEach((g) => { g.hidden = g.dataset.group !== name; });
        groupButtons.forEach((btn, k) => btn.setAttribute('aria-pressed', k === name ? 'true' : 'false'));
      }

      function labRow(f) {
        const id = 'lab-' + f.key;
        const err = h('div', { class: 'err', id: id + '-err', hidden: true });
        const flag = h('span', { class: 'flag', hidden: true });
        const state = h('span', { class: 'lab-state', id: id + '-state' });
        const ok = h('span', { class: 'ok', hidden: true, text: 'OK' });
        const anchor = f.uln !== null && f.uln !== undefined ? `ULN ${f.uln}` : '';
        const anc = f.kind === 'number' && anchor ? h('span', { class: 'anc', text: anchor }) : null;
        const unit = h('span', { class: 'unit' }, f.kind === 'number' ? f.unit : null, anc, flag, ok, state);

        let control;
        if (f.kind === 'number') {
          control = h('input', {
            class: 'num', id, type: 'text', inputmode: 'decimal',
            autocomplete: 'off', spellcheck: 'false', placeholder: '—',
            value: S.raw[f.key] || '',
          });
          control.addEventListener('input', () => {
            S.raw[f.key] = control.value;
            S.presetId = null;
            save();
          });
          control.addEventListener('blur', async () => {
            touched.add(f.key);
            await refreshBackendData();
            refreshLabIndicators();
          });
        } else {
          const opts = f.kind === 'sex' ? [['M', 'M'], ['F', 'F']] : f.kind === 'child_pugh' ? [['A', 'A'], ['B', 'B'], ['C', 'C']] : [['y', 'Yes'], ['n', 'No']];
          const norm = (v) => String(v || '').trim().toUpperCase().slice(0, 1);
          const btns = opts.map(([v, label]) => h('button', {
            type: 'button', role: 'radio', text: label, 'data-v': v,
            'aria-checked': norm(S.raw[f.key]) === norm(v) ? 'true' : 'false',
            onclick: async () => {
              S.raw[f.key] = norm(S.raw[f.key]) === norm(v) ? '' : v;
              S.presetId = null;
              save();
              await refreshBackendData();
              renderPatientLabsBody();
            },
          }));
          control = h('div', { class: 'seg', role: 'radiogroup', id, 'aria-label': f.label }, btns);
        }

        const row = h('div', { class: 'lab' },
          h('label', { for: f.kind === 'number' ? id : null, text: f.label }),
          control, unit, err);
        rows[f.key] = { row, err, flag, ok, control, f, anc, state };
        return row;
      }

      const groups = groupNames.map((g) => {
        const fs = FIELDS.filter((f) => f.group === g);
        return h('section', { class: 'group', 'data-group': g, hidden: g !== activeGroup },
          h('h2', { class: 'h2', text: groupLabels[g] || g }),
          fs.map(labRow));
      });

      const groupNav = h('nav', { class: 'lab-nav', 'aria-label': 'Lab categories' }, groupNames.map((name) => {
        const btn = h('button', {
          type: 'button',
          'aria-pressed': name === activeGroup ? 'true' : 'false',
          onclick: () => selectGroup(name),
        }, h('span', { text: groupLabels[name] || name }), h('span', { class: 'lab-count' }));
        groupButtons.set(name, btn);
        return btn;
      }));

      function refreshLabIndicators() {
        const r = S.labs || {};
        const errs = r.errors || {}, flags = r.flags || [];
        groupButtons.forEach((button, name) => {
          const fs = FIELDS.filter((f) => f.group === name && !f.key.startsWith('uln_'));
          const n = fs.filter((f) => String(S.raw[f.key] ?? '').trim()).length;
          button.querySelector('.lab-count').textContent = n ? `${n}` : '';
        });
        for (const k in rows) {
          const { err, flag, control } = rows[k];
          const msg = errs[k] && touched.has(k) && String(S.raw[k] || '').trim() ? String(errs[k]) : '';
          err.hidden = !msg; err.textContent = msg;
          const fl = flags.filter((x) => x.key === k && String(S.raw[k] || '').trim());
          flag.hidden = !fl.length;
          flag.textContent = fl.length ? (SHORT[fl[0].organ] || fl[0].organ) : '';
          if (control.classList) {
            control.classList.toggle('bad', !!msg);
            control.classList.toggle('flg', !!fl.length && !msg);
          }
        }
      }

      refreshLabIndicators();
      bodyWrap.append(h('div', { class: 'lab-workspace' }, groupNav, h('div', { class: 'groups' }, groups)));
    }

    renderPatientLabsBody();
    return box;
  }

  // ------------------------------------------------------------------ Secondary Drill-Down Drawer (FDA Label + Pivotal Trial + 4-Part Architecture)
  let openDrawer = () => {}, returnFocus = () => {}, keepRow = () => {}, resultKeys = null, settle = 0, shownPatient = {};

  function docked(on) {
    ROOT.classList.toggle('docked', on);
    clearTimeout(settle);
    settle = setTimeout(() => keepRow(), still() ? 0 : 300);
  }
  function showDrawer() {
    S.drawer = true; save();
    if (!drawer.classList.contains('open')) docked(true);
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
  }
  function closeDrawer(silent) {
    S.drawer = false;
    if (!silent) save();
    if (!drawer || !drawer.classList.contains('open')) return;
    const inside = drawer.contains(document.activeElement);
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    docked(false);
    if (inside) returnFocus();
  }

  function section(title, ...kids) {
    return h('section', { class: 'dsec' }, title ? tipped(h('h3', { class: 'h2', text: title })) : null, kids);
  }

  function fillDrawer(row) {
    if (!row) return;
    const d = row.detail || {};
    drawerTitle.textContent = row.name;
    clear(drawerBody);
    drawerBody.scrollTop = 0;

    // 1. Label Restriction
    const rs = d.reasons || [];
    const ruleText = (r) => {
      const b = String(r.basis || '').replace(/^if /, '');
      return b === '-' ? 'Applies to all patients' : b;
    };
    const secRestriction = section('Label restriction', rs.length ? h('div', { class: 'rsl' }, rs.map((r) => h('div', { class: 'rr' },
      h('div', { class: 'rh' },
        h('span', { class: 'k', text: SHORT[r.organ] || r.organ }),
        h('span', { class: `s t-${TONE[r.code] || 'dim'}`, text: r.status })),
      h('div', { class: 'pl' },
        r.patient ? [h('span', { class: 'pk', text: 'Patient' }), h('span', { class: 'pv', text: r.patient })] : null,
        h('span', { class: 'pk', text: 'FDA Rule' }), h('span', { class: 'lv2', text: ruleText(r) })))))
      : h('p', { class: 'dim', text: 'No label restriction triggered for entered values.' }));

    // 2. Warnings on Patient's Active Organs
    const ws = d.warnings || [];
    const secPatientWarn = section("Warnings on the patient's organs", ws.length ? h('div', { class: 'wl' }, ws.map((w) => [
      h('span', { class: 'k', text: SHORT[w.organ] || w.organ }),
      h('span', { class: 'm ' + (w.mark.trim() === '!!' ? 't-red' : 't-amber'), text: w.mark.trim() }),
      h('span', { text: w.text.replace(/;\s*/g, ', ') }),
    ])) : h('p', { class: 'dim', text: 'No boxed or Section 5 warnings on the patient\'s active organs.' }));

    // 3. Pre-treatment checks & Missing inputs
    const secChecks = (d.checks || []).length ? section('Pre-treatment checks', h('ul', { class: 'dash' }, d.checks.map((c) => h('li', { text: c })))) : null;
    const secMissing = (d.missing || []).length ? section('Missing inputs',
      h('ul', { class: 'dash' }, d.missing.map((m) => h('li', { text: m }))),
      h('button', { type: 'button', class: 'review-link', text: 'Enter lab values', onclick: () => { closeDrawer(); switchMode(2); } })) : null;

    // 4. Pivotal Trial Context & Dual-Bar Events
    const t = d.trial && d.trial.trial && !d.trial.no_results ? d.trial : null;
    const secTrial = t ? section('Trial context',
      h('p', { style: 'margin:0 0 6px;font-weight:700', text: `${t.trial}${t.phase ? ' (Phase ' + t.phase + ')' : ''}` }),
      h('p', { class: 'dim', style: 'margin:0 0 6px;font-size:12px', text: t.population || '' }),
      h('p', { style: 'margin:0 0 4px;font-size:12px', text: `ADC Arm: ${t.regimen} (n=${t.n})` }),
      t.comparator ? h('p', { class: 'dim', style: 'margin:0 0 8px;font-size:12px', text: `Control Arm: ${t.comparator.regimen} (n=${t.comparator.n})` }) : null,
      /^NCT\d{8}$/.test(t.nct || '') ? h('a', { class: 'review-link', href: 'https://clinicaltrials.gov/study/' + t.nct, target: '_blank', rel: 'noopener noreferrer', text: `ClinicalTrials.gov ${t.nct} ↗` }) : null
    ) : section('Trial context', h('p', { class: 'dim', text: (d.trial && d.trial.no_results) || 'Single-arm or registry clinical study.' }));

    const trialEvents = [];
    for (const o of (t && t.organs) || []) {
      for (const e of o.events || []) {
        trialEvents.push(h('div', { class: 'trial-event' },
          buildDualBar({ trial: t, organ: o.organ, ev: e }),
          h('div', { class: 'event-values', style: 'margin-top:6px' },
            h('span', null, h('b', { text: `${e.a}/${e.n}` }), ' ADC'),
            e.comp ? h('span', null, h('b', { text: `${e.comp[0]}/${e.comp[1]}` }), ' Comparator') : null)));
      }
    }
    const secEvents = trialEvents.length ? section('Study events', ...trialEvents) : null;

    // 5. 4-Part Conjugate Structure & Indications
    const m = MECH[row.adc];
    const kvRows = m ? [
      ['Target Antigen', m.target],
      ['Antibody Backbone', m.antibody],
      ['Chemical Linker', m.linker],
      ['Cytotoxic Payload', m.payload],
      ['Payload Class', m.payload_class],
      ['Average DAR', m.dar],
    ].filter(([, v]) => v) : ((d.payload && d.payload.rows) || []);

    const secPayload = section('Payload and linker',
      kvRows.length ? h('div', { class: 'kv3' }, kvRows.map(([k, v]) => [h('span', { class: 'k', text: k }), h('span', { text: v })])) : null,
      h('button', {
        type: 'button', class: 'review-link', style: 'margin-top:8px',
        text: 'Open in Structure Studio →',
        onclick: () => { closeDrawer(); switchMode(1); },
      }));

    const secInd = section('Indication',
      d.indication ? h('ul', { class: 'ind' }, d.indication.split(/;\s*/).filter(Boolean).map((x) => h('li', { text: x }))) : null);

    const wo = d.other_warnings || [];
    const secOtherWarn = wo.length ? section('Warnings on other organs', h('div', { class: 'wl' }, wo.map((w) => [
      h('span', { class: 'k', text: SHORT[w.organ] || w.organ }),
      h('span', { class: 'm ' + (w.mark.trim() === '!!' ? 't-red' : 't-amber'), text: w.mark.trim() }),
      h('span', { text: w.text.replace(/;\s*/g, ', ') }),
    ]))) : null;

    const tabGroups = {
      Patient: [secRestriction, secPatientWarn, secChecks, secMissing].filter(Boolean),
      Study: [secTrial, secEvents].filter(Boolean),
      'Structure & Label': [secPayload, secInd, secOtherWarn].filter(Boolean),
    };

    const nav = h('div', { class: 'evidence-tabs', role: 'group', 'aria-label': 'Evidence tabs' });
    const allSecs = Object.values(tabGroups).flat();

    function switchTab(name) {
      allSecs.forEach((s) => { s.hidden = !tabGroups[name].includes(s); });
      [...nav.children].forEach((b) => b.setAttribute('aria-pressed', b.dataset.view === name ? 'true' : 'false'));
    }

    Object.keys(tabGroups).forEach((name) => {
      nav.append(h('button', {
        type: 'button', text: name, 'data-view': name,
        onclick: () => switchTab(name),
      }));
    });

    drawerBody.append(nav, ...allSecs);
    switchTab('Patient');
  }

  function saveReview(result) {
    if (!REVIEW || !REVIEW.reviewText) return;
    const text = REVIEW.reviewText(APP, condList().map(condName), rawValues(), FIELDS, result);
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
    const link = h('a', { href: url, download: 'ADCToX-review.txt' });
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // ------------------------------------------------------------------ Mode Switching & Keyboard Navigation
  function switchMode(m, keepDrawer) {
    if (!keepDrawer) closeDrawer(true);
    S.mode = m;
    save();
    renderHeaderControls();
    renderActiveMode(true);
    window.scrollTo(0, 0);
  }

  function renderActiveMode(animate) {
    clear(stageBox);
    stageBox.classList.remove('enter');
    const builder = [buildAdcMatrixMode, buildStructureStudioMode, buildPatientLabsMode][S.mode] || buildAdcMatrixMode;
    stageBox.append(builder());
    if (animate && !still()) {
      void stageBox.offsetWidth;
      stageBox.classList.add('enter');
    }
  }

  document.addEventListener('keydown', (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (guide) {
      if (e.key === 'Escape') { e.preventDefault(); closeGuide(); }
      return;
    }
    if (e.key === 'Escape' && S.drawer) {
      e.preventDefault();
      closeDrawer();
      return;
    }
    const t = e.target;
    const inInput = t && t.closest && t.closest('input, textarea, select');
    if (!inInput && S.mode === 0 && resultKeys && ['ArrowDown', 'ArrowUp', 'Enter'].includes(e.key)) {
      if (!drawer.contains(t)) resultKeys(e);
    }
  });

  // ------------------------------------------------------------------ Boot Sequence
  async function start() {
    frame();
    try {
      APP = await API.app();
    } catch (e) {
      stageBox.append(h('div', { class: 'panel', style: 'padding:24px;margin-top:20px' },
        h('h2', { style: 'margin:0 0 8px', text: 'ADCTOX' }),
        h('p', { class: 'dim', text: e.message })));
      return;
    }
    AX = APP.axes || [];
    SHORT = Object.assign({}, APP.organ_short || {});
    (APP.registry || []).forEach((r, i) => { REG[r.id] = r; REG_I[r.id] = i; });
    FIELDS = (APP.labs && APP.labs.fields) || [];
    (APP.mechanisms || []).forEach((m) => { if (m && m.adc_id) MECH[m.adc_id] = m; });
    verEl.textContent = 'v' + (APP.version || '0.7.0');

    restore();
    renderHeaderControls();
    // Render immediately so DOM has .crumbs and search input without waiting, then populate live matrix
    renderActiveMode(false);
    await refreshBackendData();
    renderActiveMode(false);
  }

  start();
})();
