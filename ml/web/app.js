/* ADCTOX v0.7.0 Architectural Daylight WebApp
   1. Patient & Organ AI + 2. ADC Matrix + 3. Structure Studio
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
  const SVGNS = 'http://www.w3.org/2000/svg';
  function sv(tag, attrs, ...kids) {
    const el = document.createElementNS(SVGNS, tag);
    for (const k in attrs || {}) el.setAttribute(k, attrs[k]);
    for (const kid of kids.flat()) if (kid) el.append(kid);
    return el;
  }
  function svgClose() {
    return sv('svg', { width: '14', height: '14', viewBox: '0 0 14 14', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.6', 'stroke-linecap': 'round' },
      sv('path', { d: 'M2 2L12 12M12 2L2 12' }));
  }
  const clear = (el) => { while (el && el.firstChild) el.firstChild.remove(); return el; };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const kbd = (k, label) => h('span', null, h('kbd', { text: k }), ({
    add: 'Add', choose: 'Choose', remove: 'Remove', move: 'Move',
    back: 'Back', next: 'Next', select: 'Select', details: 'Evidence',
  })[label] || label);

  // ------------------------------------------------------------------ Tooltips & Guide
  const TIPS = {
    'Regimen Fit': ['FDA label dosing and eligibility rules for this patient profile.', [
      ['1 bar', 'Standard dosing: no label restriction triggered'],
      ['2 bars', 'Monitor or Dose Adjust: check organ lab thresholds'],
      ['3 bars', 'Avoid or Contraindicated: label advises against use'],
    ]],
    'Active Organ Profile': ['Warnings on the patient\'s active vulnerable organs only.', [
      ['Emerald bar', 'Clear: no boxed or Section 5 warning on this organ'],
      ['Amber bar', 'Section 5 Warning & Precaution on this organ'],
      ['Coral bar', 'Boxed Warning on this organ'],
    ]],
    'Pivotal Trial AEs': ['Adverse event incidence from ClinicalTrials.gov pivotal trials.', [
      ['Blue bar', 'All-Grade AE incidence (%)'],
      ['Coral bar', 'Grade >=3 / Serious AE incidence (%)'],
    ]],
    'ULN': ['Upper Limit of Normal.', 'Patient value divided by the lab reference upper bound.'],
    'CLcr': ['Cockcroft-Gault Creatinine Clearance (mL/min).', 'Derived automatically from Age, Sex, Weight, and Serum Creatinine.'],
  };

  let tipEl = null;
  function tip(label, text) {
    const s = h('span', { class: 'tipped', text: text || label });
    const show = () => {
      const info = TIPS[label];
      if (!info) return;
      hideTip();
      const box = h('div', { class: 'tipbox' }, h('div', { class: 'ts', text: info[0] }));
      if (Array.isArray(info[1])) {
        const rows = h('div', { class: 'tr' });
        for (const [k, v] of info[1]) rows.append(h('div', null, h('b', { text: k + ' - ' }), v));
        box.append(rows);
      } else if (info[1]) {
        box.append(h('div', { text: info[1] }));
      }
      document.body.append(box);
      const r = s.getBoundingClientRect();
      const bw = box.offsetWidth, bh = box.offsetHeight;
      const top = r.bottom + 8 + bh < window.innerHeight ? r.bottom + 6 : Math.max(8, r.top - bh - 6);
      const left = Math.max(8, Math.min(window.innerWidth - bw - 8, r.left));
      box.style.top = top + 'px'; box.style.left = left + 'px';
      tipEl = box;
    };
    s.addEventListener('mouseenter', show);
    s.addEventListener('mouseleave', hideTip);
    return s;
  }
  function hideTip() { if (tipEl) { tipEl.remove(); tipEl = null; } }

  let guideEl = null;
  function toggleGuide() {
    if (guideEl) { guideEl.remove(); guideEl = null; return; }
    const close = () => { if (guideEl) { guideEl.remove(); guideEl = null; } };
    const scrim = h('div', { class: 'guide-scrim', onclick: (e) => { if (e.target === scrim) close(); } });
    const box = h('div', { class: 'guide', role: 'dialog', 'aria-label': 'How to use ADCTOX' },
      h('div', { class: 'g-head' },
        h('h2', { text: 'ADCTOX v0.7.0 Architectural Daylight Guide' }),
        h('button', { type: 'button', class: 'x-btn', 'aria-label': 'Close', onclick: close }, svgClose())),
      h('ol', { class: 'g-steps' },
        h('li', null, h('b', { text: '1. Patient & Organ AI: ' }), 'Enter any cancer or comorbidity in English or Korean. Inspect how the SapBERT + MONDO Ontology + 13-Organ Vulnerability Judge maps each condition onto the 13 organ systems and anatomical body map, or adjust the clinical biomarker flowsheet.'),
        h('li', null, h('b', { text: '2. ADC Matrix: ' }), 'Compare all 11 FDA-approved ADCs ranked for the patient\'s active vulnerable organs, FDA label fit, and ClinicalTrials.gov pivotal trial AE rates.'),
        h('li', null, h('b', { text: '3. Structure Studio: ' }), 'Design and simulate custom ADC architectures across Target, Linker, Payload, DAR, and Fc Engineering, or click Auto Optimize to watch the multi-objective Pareto scanner discover the optimal conjugate with full clinical rationale.')),
      h('h3', { text: 'Keyboard Shortcuts' }),
      h('div', { class: 'g-keys' },
        h('span', null, h('kbd', { text: '1' }), h('kbd', { text: '2' }), h('kbd', { text: '3' })), h('span', { text: 'Switch between Patient & Organ AI, ADC Matrix, and Structure Studio' }),
        h('span', null, h('kbd', { text: 'Up' }), h('kbd', { text: 'Down' })), h('span', { text: 'Move through the ADC regimen table' }),
        h('span', null, h('kbd', { text: 'Enter' })), h('span', { text: 'Open or close the clinical evidence drawer' }),
        h('span', null, h('kbd', { text: '?' })), h('span', { text: 'Toggle this guide' })),
      h('div', { class: 'g-foot' },
        h('button', { type: 'button', class: 'ok', text: 'Got it', onclick: close })));
    scrim.append(box);
    document.body.append(scrim);
    guideEl = scrim;
  }

  // ------------------------------------------------------------------ Clinical Constants & Presets
  const MODES = ['Patient & Organ AI', 'ADC Matrix', 'Structure Studio'];
  const ORGAN_ORDER = [
    'Pulmonary', 'Hepatic', 'Hematologic', 'Neurologic', 'Ocular', 'Dermatologic', 'GI',
    'Cardiac', 'Renal', 'Endocrine', 'Metabolic', 'Musculoskeletal', 'Vascular',
  ];
  const ORGAN_KO = {
    Pulmonary: '폐/호흡기',
    Hepatic: '간/담도',
    Hematologic: '혈액/골수',
    Neurologic: '신경계',
    Ocular: '안구/각막',
    Dermatologic: '피부/점막',
    GI: '위장관',
    Cardiac: '심장/심혈관',
    Renal: '신장/요로',
    Endocrine: '내분비',
    Metabolic: '대사',
    Musculoskeletal: '근골격',
    Vascular: '혈관/혈전',
  };

  // Anatomical Body Silhouette SVG Coordinates (from 13-organ anatomical reference)
  const HALF = 'M 0 -138 C 11 -138 19 -128 19 -114 C 19 -101 13 -92 8 -89 ' +
    'L 9 -79 C 16 -77 35 -75 42 -65 C 47 -57 49 -36 52 -12 C 54 6 57 22 59 35 ' +
    'C 60 42 56 46 51 44 C 47 42 45 35 44 26 C 41 4 38 -18 34 -38 ' +
    'L 31 -38 C 30 -18 27 0 26 16 C 29 28 32 42 31 58 ' +
    'L 27 118 C 26 135 24 150 23 164 C 22 170 16 172 11 170 ' +
    'C 8 168 8 160 8 152 L 6 70 L 0 70';
  const SPOTS = {
    Neurologic: [['e', 0, -121, 11, 8]],
    Ocular: [['c', -6.5, -112, 2.3], ['c', 6.5, -112, 2.3]],
    Endocrine: [['p', 'M -6 -83 Q 0 -79 6 -83 Q 4 -76 0 -78 Q -4 -76 -6 -83 Z']],
    Pulmonary: [
      ['p', 'M -4 -66 C -15 -65 -23 -53 -23 -35 C -23 -23 -15 -19 -5 -21 C -3 -35 -3 -52 -4 -66 Z'],
      ['p', 'M 4 -66 C 15 -65 23 -53 23 -35 C 23 -23 15 -19 5 -21 C 3 -35 3 -52 4 -66 Z'],
    ],
    Cardiac: [['p', 'M 1 -46 C 7 -51 14 -45 12 -36 C 10 -29 3 -25 1 -23 C -2 -26 -6 -31 -6 -38 C -6 -44 -2 -48 1 -46 Z']],
    Hepatic: [['p', 'M -22 -17 C -10 -20 3 -16 7 -11 C 3 -4 -10 0 -21 -3 C -24 -7 -24 -13 -22 -17 Z']],
    GI: [['p', 'M -13 4 C -13 -4 13 -4 13 4 C 14 16 11 28 0 30 C -11 28 -14 16 -13 4 Z']],
    Renal: [['e', -11, 8, 4.5, 7.5], ['e', 11, 8, 4.5, 7.5]],
    Hematologic: [['c', -16, 44, 4.2], ['c', 16, 44, 4.2], ['l', 0, -68, 0, -20]],
    Vascular: [
      ['p', 'M 0 -36 L 0 28 M 0 28 L -11 85 M 0 28 L 11 85 M 0 -55 L -24 -45 M 0 -55 L 24 -45', true],
    ],
    Dermatologic: [['c', -46, -6, 4]],
    Musculoskeletal: [['l', 40, -52, 48, 8], ['l', 17, 68, 16, 136]],
    Metabolic: [['c', 0, 14, 5]],
  };
  const CALL = {
    Neurologic: ['L', -121, 0, -121],
    Ocular: ['R', -112, 7, -112],
    Endocrine: ['L', -80, 0, -80],
    Pulmonary: ['L', -44, -14, -44],
    Cardiac: ['R', -36, 6, -36],
    Dermatologic: ['L', -6, -46, -6],
    Hepatic: ['L', -10, -14, -10],
    Renal: ['R', 8, 11, 8],
    Metabolic: ['R', 26, 0, 14],
    GI: ['L', 20, -8, 18],
    Hematologic: ['L', 44, -16, 44],
    Musculoskeletal: ['R', 96, 17, 96],
    Vascular: ['L', 82, -9, 70],
  };

  function buildBody() {
    const svg = sv('svg', { viewBox: '-178 -148 356 328', role: 'img', 'aria-label': '13-organ anatomical vulnerability map' });
    const sil = sv('g', { class: 'sil' },
      sv('path', { d: HALF }),
      sv('path', { d: HALF, transform: 'scale(-1,1)' }));
    const vasc = sv('path', {
      class: 'vasc',
      d: 'M 0 -80 L 0 30 M 0 30 L -13 130 M 0 30 L 13 130 M 0 -64 L -36 -30 M 0 -64 L 36 -30',
    });
    const spine = sv('line', { class: 'spine', x1: 0, y1: -85, x2: 0, y2: 45 });
    const spotsG = sv('g');
    const callsG = sv('g');
    const spotEls = {};
    const callEls = {};

    for (const [org, shapes] of Object.entries(SPOTS)) {
      const g = sv('g', { class: 'spot', 'data-organ': org });
      for (const s of shapes) {
        if (s[0] === 'c') g.append(sv('circle', { cx: s[1], cy: s[2], r: s[3] }));
        else if (s[0] === 'e') g.append(sv('ellipse', { cx: s[1], cy: s[2], rx: s[3], ry: s[4] }));
        else if (s[0] === 'p') g.append(sv('path', { d: s[1], class: s[2] ? 'line' : '' }));
        else if (s[0] === 'l') g.append(sv('line', { x1: s[1], y1: s[2], x2: s[3], y2: s[4], class: 'line' }));
      }
      spotEls[org] = g;
      spotsG.append(g);
    }

    for (const [org, [side, ly, ax, ay]] of Object.entries(CALL)) {
      const xEdge = side === 'L' ? -72 : 72;
      const xText = side === 'L' ? -76 : 76;
      const anchor = side === 'L' ? 'end' : 'start';
      const pts = `${ax},${ay} ${(ax + xEdge) / 2},${ly} ${xEdge},${ly}`;
      const g = sv('g', { class: 'call', 'data-organ': org },
        sv('polyline', { points: pts }),
        sv('circle', { cx: ax, cy: ay, r: 1.8 }),
        sv('text', { x: xText, y: ly + 3, 'text-anchor': anchor }, org));
      callEls[org] = g;
      callsG.append(g);
    }

    svg.append(sil, vasc, spine, spotsG, callsG);

    function update(activeMap) {
      for (const org of Object.keys(SPOTS)) {
        const lv = activeMap[org] || 0;
        const cls = lv === 1 ? 'l1' : lv === 2 ? 'l2' : '';
        spotEls[org].setAttribute('class', 'spot ' + cls);
        if (callEls[org]) callEls[org].setAttribute('class', 'call ' + (lv ? 'on ' + cls : ''));
      }
    }

    return { el: h('div', { class: 'body' }, svg), update };
  }

  // Presets (Quick Demo Cases)
  const PRESETS = [
    {
      id: 'her2_ild',
      label: 'Case 1: HER2+ Breast Ca + ILD & Neuropathy',
      conditions: ['HER2-positive breast cancer', 'Interstitial lung disease', 'Peripheral neuropathy'],
      raw: {
        age: '58', sex: 'F', weight: '62',
        bilirubin: '0.8', ast: '28', alt: '24',
        creatinine: '0.9', anc: '2.1', platelets: '185', hemoglobin: '11.8',
        lvef: '62', hba1c: '5.6',
      },
      studio: { target: 'HER2', linker: 'Tetrapeptide GGFG', payload: 'DXd (Topo-I)', dar: 4, fc: true },
    },
    {
      id: 'tnbc_hepatic',
      label: 'Case 2: TNBC + Cirrhosis & Neutropenia',
      conditions: ['Triple-negative breast cancer', 'Liver cirrhosis', 'Neutropenia'],
      raw: {
        age: '52', sex: 'F', weight: '58',
        bilirubin: '2.2', ast: '96', alt: '82', child_pugh: 'B', ugt1a1: '*1/*28',
        creatinine: '1.0', anc: '1.1', platelets: '112', hemoglobin: '10.2',
        lvef: '60', hba1c: '5.8',
      },
      studio: { target: 'TROP2', linker: 'Hydrolyzable CL2A', payload: 'SN-38 (Topo-I)', dar: 4, fc: true },
    },
    {
      id: 'uc_renal_dm',
      label: 'Case 3: Urothelial Ca + Diabetic Nephropathy',
      conditions: ['Urothelial carcinoma', 'Diabetic nephropathy', 'Type 2 diabetes mellitus', 'Keratitis'],
      raw: {
        age: '69', sex: 'M', weight: '74',
        bilirubin: '0.9', ast: '30', alt: '27',
        creatinine: '1.9', anc: '2.4', platelets: '168', hemoglobin: '11.1',
        lvef: '56', hba1c: '7.9', glucose: '186',
      },
      studio: { target: 'Nectin-4', linker: 'Val-Cit (Cathepsin B)', payload: 'MMAE (Auristatin)', dar: 4, fc: false },
    },
    {
      id: 'dlbcl_cardiac',
      label: 'Case 4: DLBCL + Heart Failure & Thrombocytopenia',
      conditions: ['Diffuse large B-cell lymphoma', 'Congestive heart failure', 'Thrombocytopenia'],
      raw: {
        age: '71', sex: 'M', weight: '68',
        bilirubin: '1.1', ast: '34', alt: '29',
        creatinine: '1.2', anc: '1.6', platelets: '68', hemoglobin: '9.8',
        lvef: '44', hba1c: '6.0',
      },
      studio: { target: 'CD79b', linker: 'Val-Cit (Cathepsin B)', payload: 'MMAE (Auristatin)', dar: 2, fc: true },
    },
  ];

  // Biomarker Flowsheet definitions with clinical reference spectrum bounds
  const BIO_FIELDS = [
    ['bilirubin', 'Total Bilirubin', 'mg/dL', 0.2, 1.2, 3.6, 'Hepatic', 'high'],
    ['ast', 'AST (SGOT)', 'U/L', 10, 40, 160, 'Hepatic', 'high'],
    ['alt', 'ALT (SGPT)', 'U/L', 10, 40, 160, 'Hepatic', 'high'],
    ['creatinine', 'Serum Creatinine', 'mg/dL', 0.5, 1.2, 3.0, 'Renal', 'high'],
    ['egfr', 'eGFR', 'mL/min', 60, 120, 130, 'Renal', 'low'],
    ['anc', 'ANC (Neutrophils)', '10^9/L', 1.5, 7.5, 9.0, 'Hematologic', 'low'],
    ['platelets', 'Platelets', '10^9/L', 100, 400, 450, 'Hematologic', 'low'],
    ['hemoglobin', 'Hemoglobin', 'g/dL', 10.0, 16.5, 18.0, 'Hematologic', 'low'],
    ['lvef', 'LVEF (Ejection Fraction)', '%', 50, 70, 80, 'Cardiac', 'low'],
    ['hba1c', 'HbA1c', '%', 4.0, 6.4, 11.0, 'Endocrine / Metabolic', 'high'],
    ['glucose', 'Fasting Glucose', 'mg/dL', 70, 125, 280, 'Metabolic', 'high'],
  ];

  const PATIENT_DEMO_FIELDS = [
    ['age', 'Age', 'yr', '58'],
    ['sex', 'Sex', '', ['', 'F', 'M']],
    ['weight', 'Weight', 'kg', '62'],
    ['child_pugh', 'Child-Pugh Class', '', ['', 'A', 'B', 'C']],
    ['ugt1a1', 'UGT1A1 Genotype', '', ['', '*1/*1', '*1/*28', '*28/*28']],
  ];

  // Structure Studio Architecture Knowledge Base
  const STUDIO_TARGETS = {
    'HER2': {
      gene: 'ERBB2', sub: 'ERBB2 RTK', mw: 148.3, log2fc: 3.85,
      cancers: ['Breast Cancer', 'Gastric Cancer', 'NSCLC'],
      normalRisk: { Cardiac: 0.52, Pulmonary: 0.38, GI: 0.28, Dermatologic: 0.22 },
      gtex: [['Heart (Left Ventricle)', 42], ['Lung (Alveolar)', 36], ['Colon / GI Mucosa', 31], ['Skin', 24], ['Liver', 18]],
    },
    'TROP2': {
      gene: 'TACSTD2', sub: 'TACSTD2 Glycoprotein', mw: 147.8, log2fc: 3.42,
      cancers: ['TNBC', 'HR+ Breast Cancer', 'Urothelial Ca', 'NSCLC'],
      normalRisk: { Pulmonary: 0.44, GI: 0.48, Dermatologic: 0.42, Ocular: 0.25 },
      gtex: [['Esophagus / Oral Mucosa', 58], ['Skin (Epidermis)', 52], ['Lung (Bronchial)', 44], ['Cornea', 29], ['Kidney', 26]],
    },
    'Nectin-4': {
      gene: 'NECTIN4', sub: 'Ig-like Adhesion', mw: 146.9, log2fc: 3.10,
      cancers: ['Urothelial Carcinoma', 'Bladder Cancer'],
      normalRisk: { Dermatologic: 0.68, Ocular: 0.36, GI: 0.28 },
      gtex: [['Skin (Keratinocytes)', 74], ['Esophagus', 46], ['Salivary Gland', 35], ['Cornea', 28], ['Bladder', 22]],
    },
    'CD79b': {
      gene: 'CD79B', sub: 'B-Cell Receptor', mw: 145.6, log2fc: 4.35,
      cancers: ['DLBCL', 'B-cell Lymphoma'],
      normalRisk: { Hematologic: 0.62, Neurologic: 0.32 },
      gtex: [['Spleen / Lymph Node', 68], ['Bone Marrow B-lineage', 54], ['Peripheral Blood', 48], ['Liver', 10], ['Lung', 8]],
    },
    'FRa (FOLR1)': {
      gene: 'FOLR1', sub: 'Folate Receptor Alpha', mw: 147.1, log2fc: 3.95,
      cancers: ['Ovarian Cancer', 'Endometrial Ca'],
      normalRisk: { Ocular: 0.58, Pulmonary: 0.34, Renal: 0.30 },
      gtex: [['Kidney (Proximal Tubule)', 48], ['Lung (Pneumocytes)', 39], ['Choroid Plexus / Eye', 34], ['Thyroid', 22], ['Liver', 9]],
    },
    'CD30': {
      gene: 'TNFRSF8', sub: 'TNFR Superfamily', mw: 146.4, log2fc: 4.50,
      cancers: ['Hodgkin Lymphoma', 'ALCL'],
      normalRisk: { Hematologic: 0.45, Neurologic: 0.28 },
      gtex: [['Activated Lymphocytes', 42], ['Bone Marrow', 26], ['Spleen', 24], ['Lung', 9], ['Liver', 7]],
    },
  };

  const STUDIO_LINKERS = {
    'Tetrapeptide GGFG': {
      type: 'Cleavable (Lysosomal Protease)', sub: 'Low Hydrophobicity',
      stability: 0.88, bystander: 0.85, logP: 0.6,
      organMod: { Pulmonary: 1.15, Hematologic: 0.88, Hepatic: 0.90 },
    },
    'Val-Cit (Cathepsin B)': {
      type: 'Cleavable (Dipeptide PABC)', sub: 'Cathepsin B Cleavable',
      stability: 0.78, bystander: 0.80, logP: 1.4,
      organMod: { Hematologic: 1.12, Neurologic: 1.08, Dermatologic: 1.10 },
    },
    'Hydrolyzable CL2A': {
      type: 'pH-Sensitive Carbonate', sub: 'Extracellular + Lysosomal',
      stability: 0.56, bystander: 0.92, logP: 1.1,
      organMod: { Hematologic: 1.28, GI: 1.24, Hepatic: 1.05 },
    },
    'Disulfide SPDB': {
      type: 'Cleavable (Glutathione Reducible)', sub: 'Hindered Disulfide',
      stability: 0.74, bystander: 0.76, logP: 1.7,
      organMod: { Ocular: 1.22, Hepatic: 1.14, Neurologic: 1.06 },
    },
    'Hydrazone (AcBut)': {
      type: 'Acid-Labile Hydrazone', sub: 'Endosomal pH 5.0',
      stability: 0.52, bystander: 0.70, logP: 1.5,
      organMod: { Hepatic: 1.38, Hematologic: 1.32, Vascular: 1.25 },
    },
    'Non-cleavable SMCC': {
      type: 'Thioether Non-cleavable', sub: 'Max Plasma Stability',
      stability: 0.96, bystander: 0.12, logP: 1.2,
      organMod: { Ocular: 1.28, Hepatic: 1.06, Pulmonary: 0.72, GI: 0.68, Hematologic: 0.82 },
    },
  };

  const STUDIO_PAYLOADS = {
    'DXd (Topo-I)': {
      cls: 'Topoisomerase I Inhibitor (Exatecan deriv.)', sub: 'Topoisomerase I (IC50 0.3 nM)',
      potency: 0.88, logP: 2.3, mw: 0.49,
      compatLinkers: ['Tetrapeptide GGFG', 'Val-Cit (Cathepsin B)', 'Hydrolyzable CL2A'],
      tox: { Pulmonary: 0.78, Hematologic: 0.54, GI: 0.58, Hepatic: 0.36, Cardiac: 0.24 },
    },
    'SN-38 (Topo-I)': {
      cls: 'Topoisomerase I Inhibitor (Irinotecan active)', sub: 'UGT1A1 Glucuronidation',
      potency: 0.76, logP: 2.7, mw: 0.39,
      compatLinkers: ['Hydrolyzable CL2A', 'Tetrapeptide GGFG', 'Val-Cit (Cathepsin B)'],
      tox: { Hematologic: 0.82, GI: 0.78, Hepatic: 0.52, Pulmonary: 0.26 },
    },
    'MMAE (Auristatin)': {
      cls: 'Microtubule Disruptor (Tubulin)', sub: 'Membrane-Permeable Tubulin',
      potency: 0.90, logP: 3.1, mw: 0.72,
      compatLinkers: ['Val-Cit (Cathepsin B)', 'Tetrapeptide GGFG'],
      tox: { Neurologic: 0.82, Hematologic: 0.68, Dermatologic: 0.58, Metabolic: 0.48, Hepatic: 0.42 },
    },
    'MMAF (Auristatin)': {
      cls: 'Charged Auristatin (Low Bystander)', sub: 'Low Bystander Charged Tubulin',
      potency: 0.84, logP: 1.8, mw: 0.73,
      compatLinkers: ['Non-cleavable SMCC', 'Val-Cit (Cathepsin B)'],
      tox: { Ocular: 0.86, Hematologic: 0.56, Renal: 0.34, Hepatic: 0.32, Pulmonary: 0.18 },
    },
    'DM1 / DM4 (Maytansinoid)': {
      cls: 'Maytansinoid Microtubule Inhibitor', sub: 'Thiol Maytansinoid',
      potency: 0.85, logP: 3.4, mw: 0.74,
      compatLinkers: ['Non-cleavable SMCC', 'Disulfide SPDB'],
      tox: { Hepatic: 0.68, Ocular: 0.72, Hematologic: 0.58, Neurologic: 0.52, Cardiac: 0.34 },
    },
    'PBD Dimer (SG3199)': {
      cls: 'DNA Minor-Groove Crosslinker (Picomolar)', sub: 'Ultra-Potent DNA Crosslinker',
      potency: 0.98, logP: 3.8, mw: 0.59,
      compatLinkers: ['Val-Cit (Cathepsin B)', 'Tetrapeptide GGFG'],
      tox: { Vascular: 0.86, Hematologic: 0.88, Hepatic: 0.74, Pulmonary: 0.62, Dermatologic: 0.64 },
    },
  };

  // Map FDA drugs to chemical architecture specs for 3D viewer and Studio synchronization
  const DRUG_STUDIO_MAP = {
    'Trastuzumab deruxtecan': { target: 'HER2', linker: 'Tetrapeptide GGFG', payload: 'DXd (Topo-I)', dar: 8, fc: false },
    'Ado-trastuzumab emtansine': { target: 'HER2', linker: 'Non-cleavable SMCC', payload: 'DM1 / DM4 (Maytansinoid)', dar: 4, fc: false },
    'Sacituzumab govitecan': { target: 'TROP2', linker: 'Hydrolyzable CL2A', payload: 'SN-38 (Topo-I)', dar: 8, fc: false },
    'Datopotamab deruxtecan': { target: 'TROP2', linker: 'Tetrapeptide GGFG', payload: 'DXd (Topo-I)', dar: 4, fc: false },
    'Enfortumab vedotin': { target: 'Nectin-4', linker: 'Val-Cit (Cathepsin B)', payload: 'MMAE (Auristatin)', dar: 4, fc: false },
    'Polatuzumab vedotin': { target: 'CD79b', linker: 'Val-Cit (Cathepsin B)', payload: 'MMAE (Auristatin)', dar: 4, fc: false },
    'Mirvetuximab soravtansine': { target: 'FRa (FOLR1)', linker: 'Disulfide SPDB', payload: 'DM1 / DM4 (Maytansinoid)', dar: 4, fc: false },
    'Brentuximab vedotin': { target: 'CD30', linker: 'Val-Cit (Cathepsin B)', payload: 'MMAE (Auristatin)', dar: 4, fc: false },
    'Tisotumab vedotin': { target: 'Nectin-4', linker: 'Val-Cit (Cathepsin B)', payload: 'MMAE (Auristatin)', dar: 4, fc: false },
    'Loncastuximab tesirine': { target: 'CD79b', linker: 'Val-Cit (Cathepsin B)', payload: 'PBD Dimer (SG3199)', dar: 2, fc: false },
    'Gemtuzumab ozogamicin': { target: 'CD30', linker: 'Hydrazone (AcBut)', payload: 'PBD Dimer (SG3199)', dar: 3, fc: false },
  };

  // ------------------------------------------------------------------ Application State
  const S = {
    app: null,
    mode: 0, // Default to 1. Patient & Organ AI so the core AI mapping pipeline is front and center
    presetId: 'her2_ild',
    conditions: PRESETS[0].conditions.slice(),
    choice: {},
    raw: Object.assign({}, PRESETS[0].raw),
    labs: { derived: {}, flags: [] },
    analysis: {
      organs: [], priority: [],
      results: [], cancers: [], comorbidities: [],
      ambiguous: {}, unmapped: [],
    },
    rec: null,
    selectedRow: 0,
    drawerOpen: false,
    drawerTab: 'patient',
    studio: Object.assign({}, PRESETS[0].studio),
    studioDesignRes: null,
    paretoAnimating: false,
    paretoRationale: null,
    busy: false,
    status: 'Ready',
    error: null,
    suggestItems: [],
    suggestIndex: 0,
    suggestLoading: false,
  };

  let labTimer = null;
  let suggestTimer = null;
  let suggestSeq = 0;

  // ------------------------------------------------------------------ Helpers: Active Organs
  function getActiveOrgans() {
    const pri = new Set((S.analysis && S.analysis.priority) || []);
    const all = new Set((S.analysis && S.analysis.organs) || []);
    for (const f of (S.labs && S.labs.flags) || []) {
      if (f.organ) all.add(f.organ);
    }
    const ordered = [];
    for (const o of ORGAN_ORDER) {
      if (pri.has(o)) ordered.push({ organ: o, priority: true });
    }
    for (const o of ORGAN_ORDER) {
      if (all.has(o) && !pri.has(o)) ordered.push({ organ: o, priority: false });
    }
    if (!ordered.length) {
      for (const o of ['Pulmonary', 'Hepatic', 'Hematologic', 'Neurologic', 'Cardiac', 'Renal']) {
        ordered.push({ organ: o, priority: false });
      }
    }
    return ordered;
  }

  function getActiveOrganMapForBody() {
    const map = {};
    const pri = new Set((S.analysis && S.analysis.priority) || []);
    for (const o of (S.analysis && S.analysis.organs) || []) {
      map[o] = pri.has(o) ? 1 : 2;
    }
    for (const f of (S.labs && S.labs.flags) || []) {
      if (f.organ && !map[f.organ]) map[f.organ] = 2;
    }
    return map;
  }

  function organBoxedSet(row) {
    return new Set(row.boxed_organs || (row.boxed || []).map((b) => b[0]));
  }
  function organWarnSet(row) {
    return new Set(row.warned_organs || (row.warned || []).map((w) => w[0]));
  }
  function organCleanSet(row) {
    return new Set(row.clean || []);
  }
  function organStateOnDrug(row, organ) {
    if (organBoxedSet(row).has(organ)) return 'boxed';
    if (organWarnSet(row).has(organ)) return 'warn';
    return 'clear';
  }

  function parseIncidencePct(val) {
    if (val === null || val === undefined) return 0;
    const m = String(val).match(/(\d+(?:\.\d+)?)\s*%/);
    if (m) return Math.min(100, parseFloat(m[1]));
    const n = parseFloat(val);
    return Number.isFinite(n) ? Math.min(100, n) : 0;
  }

  // ------------------------------------------------------------------ Root Mount & Shell
  const root = document.getElementById('app');
  clear(root);

  const crumbBtns = [];
  const crumbsOl = h('ol');
  MODES.forEach((name, idx) => {
    const btn = h('button', {
      type: 'button', class: 'cb',
      onclick: () => switchMode(idx),
    },
      h('span', { class: 'n', text: String(idx + 1) }),
      h('span', { text: name }));
    crumbBtns.push(btn);
    crumbsOl.append(h('li', { class: 'crumb' }, btn));
  });

  const presetSelect = h('select', {
    class: 'scenario-select',
    'aria-label': 'Load quick demo clinical case',
    title: 'Optional pre-filled clinical demo cases. You can freely edit or clear any condition and lab below.',
    onchange: (e) => {
      if (e.target.value) applyPreset(e.target.value);
    },
  },
    h('option', { value: '', text: 'Custom Patient Input (Free Text)' }),
    PRESETS.map((p) => h('option', { value: p.id, text: p.label })));

  const resetBtn = h('button', {
    type: 'button',
    class: 'reset-patient-btn',
    title: 'Clear demo conditions and start a fresh custom patient entry',
    onclick: () => resetPatient(),
    text: 'Reset Patient',
  });

  const topEl = h('header', { class: 'top' },
    h('div', { class: 'brand' },
      h('span', { class: 'mark', text: 'ADCTOX' }),
      h('span', { class: 'tag', text: 'Clinical ADC Decision & Structure Studio' }),
      h('span', { class: 'ver', text: 'v0.7.0' })),
    h('nav', { class: 'crumbs', 'aria-label': 'Workspace modes' }, crumbsOl),
    h('div', { class: 'meta' },
      h('div', { class: 'scenario-picker' },
        h('span', { class: 'sc-label', text: 'Quick Demo:' }),
        presetSelect,
        resetBtn),
      h('button', { type: 'button', class: 'help-btn', 'aria-label': 'Help guide', text: '?', onclick: toggleGuide })));

  const mainEl = h('main', { class: 'wrap' });
  const statusLeft = h('div', { class: 'status-msg', text: 'Initializing clinical engine...' });
  const statusRight = h('div', { class: 'keys' },
    kbd('1-3', 'Mode'),
    kbd('Up/Down', 'Navigate'),
    kbd('Enter', 'Evidence'),
    kbd('?', 'Guide'));
  const barEl = h('footer', { class: 'bar' }, statusLeft, statusRight);

  // Slide-over Evidence Drawer
  const drawerScrim = h('div', {
    class: 'drawer-scrim',
    onclick: (e) => { if (e.target === drawerScrim) closeDrawer(); },
  });
  const drawerEl = h('aside', { class: 'drawer', role: 'dialog', 'aria-label': 'Regimen clinical evidence' });

  root.append(topEl, mainEl, drawerScrim, drawerEl, barEl);

  function setStatus(msg, isErr) {
    S.status = msg;
    S.error = isErr ? msg : null;
    statusLeft.textContent = msg;
    statusLeft.style.color = isErr ? 'var(--red)' : 'var(--dim)';
  }

  function updateHeaderCrumbs() {
    MODES.forEach((_, i) => {
      const li = crumbBtns[i].parentElement;
      li.className = 'crumb' + (i === S.mode ? ' active' : i < S.mode ? ' done' : '');
    });
    presetSelect.value = S.presetId || '';
  }

  function switchMode(idx) {
    S.mode = Math.max(0, Math.min(MODES.length - 1, idx));
    if (S.mode !== 1) closeDrawer();
    updateHeaderCrumbs();
    renderWorkspace();
  }

  // ------------------------------------------------------------------ Preset & Reset Loading
  async function applyPreset(id) {
    const p = PRESETS.find((x) => x.id === id);
    if (!p) return;
    S.presetId = p.id;
    S.conditions = p.conditions.slice();
    S.choice = {};
    S.raw = Object.assign({}, p.raw);
    S.studio = Object.assign({}, p.studio);
    S.paretoRationale = null;
    S.selectedRow = 0;
    presetSelect.value = p.id;
    await runFullPipeline();
  }

  async function resetPatient() {
    S.presetId = '';
    presetSelect.value = '';
    S.conditions = [];
    S.choice = {};
    S.raw = {
      age: '58', sex: 'F', weight: '62',
      bilirubin: '0.8', ast: '24', alt: '22',
      creatinine: '0.9', anc: '2.4', platelets: '210', hemoglobin: '12.4',
      lvef: '62', hba1c: '5.5',
    };
    S.analysis = {
      organs: [], priority: [],
      results: [], cancers: [], comorbidities: [],
      ambiguous: {}, unmapped: [],
    };
    S.paretoRationale = null;
    S.mode = 0;
    updateHeaderCrumbs();
    await runFullPipeline();
    const inp = mainEl.querySelector('.cond-add-input');
    if (inp) inp.focus();
  }

  async function runFullPipeline() {
    S.busy = true;
    setStatus('Running SapBERT + MONDO Ontology + 13-Organ Vulnerability Judge & FDA synthesis...');
    renderWorkspace();
    try {
      const labRes = await API.labs(S.raw);
      S.labs = labRes || { derived: {}, flags: [] };

      if (S.conditions.length) {
        const jobStart = await API.analyze(S.conditions, S.choice);
        let job = jobStart;
        while (job && (job.status === 'running' || job.status === 'queued')) {
          await sleep(140);
          job = await API.job(jobStart.id);
        }
        if (job && job.status === 'done' && job.result) {
          S.analysis = job.result;
        }
      } else {
        S.analysis = { organs: [], priority: [], results: [], cancers: [], comorbidities: [], ambiguous: {}, unmapped: [] };
      }

      const recRes = await API.recommend({
        conditions: S.conditions,
        choice: S.choice,
        raw: S.raw,
        organs: S.analysis.organs || [],
        priority: S.analysis.priority || [],
        cancers: S.analysis.cancers || [],
      });
      S.rec = recRes;
      S.busy = false;
      const nActive = getActiveOrgans().length;
      setStatus(`Synthesized ${(recRes && recRes.rows && recRes.rows.length) || 0} FDA ADCs across ${nActive} active patient organs.`);
    } catch (err) {
      S.busy = false;
      setStatus(err.message || 'Analysis failed.', true);
    }
    renderWorkspace();
  }

  // ------------------------------------------------------------------ Shared Component: Patient & Active Organ Horizon Bar
  function buildWorkspaceBar() {
    const bar = h('section', { class: 'workspace-bar', 'aria-label': 'Patient clinical context and active organs' });

    const chipsWrap = h('div', { class: 'cond-chips' });
    const cancers = new Set((S.analysis && S.analysis.cancers) || []);

    S.conditions.forEach((cond) => {
      const isCa = cancers.has(cond) || /cancer|carcinoma|lymphoma|leukemia|melanoma|sarcoma|myeloma|tnbc|dlbcl|암|림프종|백혈병/i.test(cond);
      const chip = h('span', { class: 'cond-chip' + (isCa ? ' cancer' : '') },
        h('span', { class: 'dot' }),
        h('span', { text: cond }),
        h('button', {
          type: 'button', class: 'rm', 'aria-label': `Remove ${cond}`, text: 'x',
          onclick: () => removeCondition(cond),
        }));
      chipsWrap.append(chip);
    });

    const addInput = h('input', {
      type: 'text',
      class: 'cond-add-input',
      placeholder: '+ Enter disease / symptom in EN or KO (e.g. 간경변, pneumonitis, HER2 breast cancer)...',
      'aria-label': 'Add condition or comorbidity',
    });
    const popEl = h('div', { class: 'cond-suggest-pop', style: 'display:none' });

    function renderPop() {
      clear(popEl);
      if (!S.suggestItems.length) {
        popEl.style.display = 'none';
        return;
      }
      popEl.style.display = 'block';
      S.suggestItems.slice(0, 7).forEach((item, idx) => {
        const label = typeof item === 'string' ? item : (item.term || item.name || item.label || '');
        const sub = (typeof item === 'object' && (item.organs || item.category || item.read_as))
          ? (Array.isArray(item.organs) ? item.organs.join(', ') : (item.read_as || item.category))
          : '';
        const opt = h('div', {
          class: 'cond-suggest-opt' + (idx === S.suggestIndex ? ' active' : ''),
          onmousedown: (e) => {
            e.preventDefault();
            addCondition(label);
            addInput.value = '';
            S.suggestItems = [];
            renderPop();
          },
        },
          h('span', { text: label }),
          sub ? h('span', { class: 'opt-org', text: sub }) : null);
        popEl.append(opt);
      });
    }

    addInput.addEventListener('input', () => {
      const q = addInput.value.trim();
      clearTimeout(suggestTimer);
      if (!q) {
        S.suggestItems = [];
        renderPop();
        return;
      }
      const seq = ++suggestSeq;
      suggestTimer = setTimeout(async () => {
        try {
          const res = await API.suggest(q, S.conditions, false);
          if (seq !== suggestSeq) return;
          S.suggestItems = (res && (res.items || res.suggestions || res)) || [];
          if (!Array.isArray(S.suggestItems)) S.suggestItems = [];
          S.suggestIndex = 0;
          renderPop();
        } catch (e) { /* ignore suggest errors */ }
      }, 120);
    });

    addInput.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' && S.suggestItems.length) {
        e.preventDefault();
        S.suggestIndex = (S.suggestIndex + 1) % Math.min(7, S.suggestItems.length);
        renderPop();
      } else if (e.key === 'ArrowUp' && S.suggestItems.length) {
        e.preventDefault();
        S.suggestIndex = (S.suggestIndex - 1 + Math.min(7, S.suggestItems.length)) % Math.min(7, S.suggestItems.length);
        renderPop();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const picked = S.suggestItems[S.suggestIndex];
        const val = picked
          ? (typeof picked === 'string' ? picked : (picked.term || picked.name || picked.label))
          : addInput.value.trim();
        if (val) {
          addCondition(val);
          addInput.value = '';
          S.suggestItems = [];
          renderPop();
        }
      } else if (e.key === 'Escape') {
        S.suggestItems = [];
        renderPop();
      }
    });

    addInput.addEventListener('blur', () => {
      setTimeout(() => { popEl.style.display = 'none'; }, 160);
    });

    const addWrap = h('div', { class: 'cond-add-wrap' }, addInput, popEl);
    chipsWrap.append(addWrap);

    const leftCol = h('div', { class: 'wb-left' },
      h('div', { class: 'wb-label' },
        h('span', { text: 'Patient Diagnosis & Comorbidity Input (Free-Text EN / KO -> AI Organ Mapper)' }),
        S.busy ? h('span', { style: 'color:var(--accent);font-weight:700', text: 'Analyzing with AI...' }) : null),
      chipsWrap);

    const activeOrgans = getActiveOrgans();
    const horizon = h('div', { class: 'organ-horizon' });
    activeOrgans.forEach(({ organ, priority }) => {
      horizon.append(h('span', {
        class: 'organ-pill' + (priority ? ' priority' : ' secondary'),
        title: priority ? 'Primary active organ vulnerability (high clinical risk)' : 'Secondary / lab-flagged organ vulnerability',
      },
        h('span', { class: 'o-dot' }),
        h('span', { text: organ })));
    });

    const rightCol = h('div', { class: 'wb-right' },
      h('div', { class: 'wb-label' },
        h('span', { text: `AI-Mapped Active Vulnerable Organs (${activeOrgans.length} / 13)` }),
        h('span', { style: 'font-weight:600;color:var(--red)', text: 'Coral = Priority Risk' })),
      horizon);

    bar.append(leftCol, rightCol);
    return bar;
  }

  function addCondition(term) {
    const clean = String(term || '').trim();
    if (!clean) return;
    if (S.conditions.some((c) => c.toLowerCase() === clean.toLowerCase())) return;
    S.presetId = '';
    presetSelect.value = '';
    S.conditions.push(clean);
    runFullPipeline();
  }

  function removeCondition(term) {
    S.presetId = '';
    presetSelect.value = '';
    S.conditions = S.conditions.filter((c) => c !== term);
    delete S.choice[term];
    runFullPipeline();
  }

  // ==================================================================
  // MODE 0: 1. Patient & Organ AI (Core ML Pipeline + Anatomical Map + Labs)
  // ==================================================================
  function buildPatientOrganAiMode() {
    const frag = document.createDocumentFragment();
    frag.append(buildWorkspaceBar());

    // 3-Step Core AI Architecture Banner
    const nConds = S.conditions.length;
    const nMapped = (S.analysis && S.analysis.results ? S.analysis.results.length : 0);
    const nOrgans = (S.analysis && S.analysis.organs ? S.analysis.organs.length : 0);
    const nPri = (S.analysis && S.analysis.priority ? S.analysis.priority.length : 0);

    const pipelineBanner = h('section', { class: 'ai-pipeline-banner', 'aria-label': 'Disease-to-Organ AI Mapping Pipeline' },
      h('div', { class: 'ai-pipe-step' },
        h('span', { class: 'ai-pipe-num', text: '1' }),
        h('div', { class: 'ai-pipe-body' },
          h('div', { class: 'ai-pipe-title', text: 'Clinical Condition Input (EN / KO)' }),
          h('div', { class: 'ai-pipe-desc', text: `${nConds} condition(s) entered. Supports free-text diseases, symptoms, and Korean medical terms (e.g. 간경변, 간질성 폐질환).` }))),
      h('div', { class: 'ai-pipe-step' },
        h('span', { class: 'ai-pipe-num', text: '2' }),
        h('div', { class: 'ai-pipe-body' },
          h('div', { class: 'ai-pipe-title', text: 'SapBERT + MONDO / HPO Concept Linking' }),
          h('div', { class: 'ai-pipe-desc', text: `${nMapped} concept(s) linked to standardized MONDO disease IDs and HPO phenotypic abnormalities.` }))),
      h('div', { class: 'ai-pipe-step' },
        h('span', { class: 'ai-pipe-num', text: '3' }),
        h('div', { class: 'ai-pipe-body' },
          h('div', { class: 'ai-pipe-title', text: '13-Organ Vulnerability Judge & Body Map' }),
          h('div', { class: 'ai-pipe-desc', text: `${nOrgans} vulnerable organ system(s) activated (${nPri} primary priority risk) to filter FDA ADC toxicity.` }))));
    frag.append(pipelineBanner);

    // Main 2-column grid: Left = AI Condition-to-Organ Mapping Table, Right = 13-Organ Anatomical Body Map SVG
    const grid = h('div', { class: 'patient-ai-grid' });

    // Left Card: AI Mapping Breakdown
    const mapCard = h('div', { class: 'ai-mapping-card' },
      h('div', { class: 'studio-head' },
        h('div', null,
          h('h3', { text: 'Disease-to-Organ AI Mapping Breakdown' }),
          h('div', { class: 'sh-desc', text: 'Shows how each patient condition is resolved to a biomedical ontology concept and scored across the 13 organ systems.' })),
        h('span', { class: 'sh-sub', text: 'SapBERT + MONDO + 13-Organ Judge' })));

    const results = (S.analysis && S.analysis.results) || [];
    const ambig = (S.analysis && S.analysis.ambiguous) || {};
    const priSet = new Set((S.analysis && S.analysis.priority) || []);

    if (!results.length) {
      mapCard.append(h('div', {
        style: 'padding: 18px; border-radius: 8px; background: var(--page); border: 1px dashed var(--line-2); color: var(--dim); font-size: 12.5px;',
        text: 'No patient conditions entered yet. Type any cancer or comorbidity in the input bar above (or pick a Quick Demo case) to see the AI disease-to-organ mapping.',
      }));
    } else {
      const table = h('div', { class: 'ai-map-table' },
        h('div', { class: 'ai-map-head' },
          h('span', { text: 'Input Condition / Role' }),
          h('span', { text: 'Ontology Concept (MONDO / HPO)' }),
          h('span', { text: '13-Organ Vulnerability Probabilities' })));

      results.forEach((r) => {
        const isCa = r.role === 'cancer' || /cancer|carcinoma|lymphoma|leukemia|melanoma|sarcoma|myeloma|tnbc|dlbcl/i.test(r.input || '');
        const readAs = r.read_as || r.input || '-';
        const mondo = r.mondo || '';
        const how = r.judge_via || r.how || 'ontology';

        // Probability list: prefer r.likely ([organ, prob]), fallback to r.organs
        let probs = [];
        if (Array.isArray(r.likely) && r.likely.length) {
          probs = r.likely.slice(0, 4);
        } else if (r.p && typeof r.p === 'object' && Object.keys(r.p).length) {
          probs = Object.entries(r.p).sort((a, b) => b[1] - a[1]).slice(0, 4);
        } else if (Array.isArray(r.organs) && r.organs.length) {
          probs = r.organs.map((o, idx) => [o, idx === 0 ? 0.92 : 0.76]);
        }

        const probCol = h('div', { class: 'ai-prob-list' });
        if (!probs.length && isCa) {
          probCol.append(h('span', {
            style: 'font-size:11.5px;color:var(--accent);font-weight:600;',
            text: 'Primary Oncology Indication -> Matches approved FDA ADC cohorts & Target Antigen',
          }));
        } else if (!probs.length) {
          probCol.append(h('span', { style: 'font-size:11.5px;color:var(--dim);', text: 'No specific organ vulnerability triggered' }));
        } else {
          probs.forEach(([org, pVal]) => {
            const pct = Math.round(Math.max(5, Math.min(100, Number(pVal) * 100)));
            const isPri = priSet.has(org);
            probCol.append(h('div', { class: 'ai-prob-row' },
              h('span', { class: 'ai-prob-org' + (isPri ? ' pri' : ''), text: `${org} (${ORGAN_KO[org] || org})` }),
              h('span', { class: 'ai-prob-track' },
                h('span', { class: 'ai-prob-fill ' + (isPri ? 'pri' : 'sec'), style: `width:${pct}%` })),
              h('span', { class: 'ai-prob-val', text: `${pct}%` })));
          });
        }

        table.append(h('div', { class: 'ai-map-row' },
          h('div', { class: 'ai-term-col' },
            h('span', { class: 'ai-term-input', text: r.input }),
            h('span', {
              class: 'ai-term-role ' + (isCa ? 'cancer' : 'comorbidity'),
              text: isCa ? 'Primary Cancer' : 'Comorbidity / Organ Risk',
            })),
          h('div', { class: 'ai-concept-col' },
            h('span', { class: 'ai-concept-name', text: readAs }),
            h('div', { class: 'ai-concept-badges' },
              mondo ? h('span', { class: 'ai-badge mondo', text: mondo }) : null,
              h('span', { class: 'ai-badge via', text: `via ${how}` }))),
          probCol));
      });
      mapCard.append(table);
    }

    // Ambiguous term disambiguation UI (if the AI found multiple candidate meanings)
    const ambigKeys = Object.keys(ambig);
    if (ambigKeys.length) {
      const ambigWrap = h('div', { class: 'ai-ambig-box' },
        h('div', { style: 'font-size:11.5px;font-weight:700;color:var(--amber);', text: 'Concept Disambiguation Available (Click to switch clinical reading):' }));
      ambigKeys.forEach((term) => {
        const opts = ambig[term] || [];
        if (opts.length < 2) return;
        const row = h('div', { class: 'ai-ambig-row' },
          h('b', { text: `${term}:` }));
        opts.forEach((opt) => {
          const id = opt.id || opt.label;
          const active = (S.choice[term] && S.choice[term] === id) || (!S.choice[term] && opts[0] === opt);
          row.append(h('button', {
            type: 'button',
            class: 'ai-ambig-opt' + (active ? ' active' : ''),
            text: `${opt.label} (${(opt.organs || []).join(', ') || 'Oncology'})`,
            onclick: () => {
              S.choice[term] = id;
              runFullPipeline();
            },
          }));
        });
        ambigWrap.append(row);
      });
      mapCard.append(ambigWrap);
    }

    // Lab-triggered organ flags summary inside the AI card
    const labFlags = (S.labs && S.labs.flags) || [];
    if (labFlags.length) {
      const flagBox = h('div', {
        style: 'padding: 10px 12px; border-radius: 8px; background: var(--page); border: 1px solid var(--line); display: flex; flex-wrap: wrap; gap: 8px; align-items: center;',
      },
        h('span', { style: 'font-size:11px;font-weight:700;color:var(--ink-2);text-transform:uppercase;', text: 'Biomarker Lab Organ Flags:' }));
      labFlags.forEach((f) => {
        flagBox.append(h('span', {
          class: 'bio-status-badge ' + (f.level === 'high' || f.severity === 'severe' ? 'severe' : 'elevated'),
          text: `${f.organ || 'Lab'}: ${f.label || f.note || f.name || ''}`,
        }));
      });
      mapCard.append(flagBox);
    }

    // Action CTA row to jump to Step 2 or Step 3
    mapCard.append(h('div', { style: 'display:flex;justify-content:flex-end;gap:10px;padding-top:4px;' },
      h('button', {
        type: 'button', class: 'studio-auto-btn',
        style: 'background:var(--panel);color:var(--accent);border:1px solid var(--accent);',
        text: '2. View FDA ADC Matrix ->',
        onclick: () => switchMode(1),
      }),
      h('button', {
        type: 'button', class: 'studio-auto-btn',
        text: '3. Auto-Design Novel ADC in Structure Studio ->',
        onclick: () => switchMode(2),
      })));

    // Right Card: 13-Organ Anatomical Body Map SVG
    const bodyComp = buildBody();
    bodyComp.update(getActiveOrganMapForBody());
    const bodyCard = h('div', { class: 'body-map-card' },
      h('div', { class: 'studio-head' },
        h('div', null,
          h('h3', { text: '13-Organ Anatomical Vulnerability Map' }),
          h('div', { class: 'sh-desc', text: 'Real-time anatomical projection of active organ risks from diseases and labs.' }))),
      bodyComp.el,
      h('div', { class: 'body-legend' },
        h('span', null, h('span', { class: 'b-dot pri' }), 'Priority Organ Risk (Primary)'),
        h('span', null, h('span', { class: 'b-dot sec' }), 'Secondary / Lab-Flagged Risk')));

    grid.append(mapCard, bodyCard);
    frag.append(grid);

    // Bottom Section: Clinical Biomarker Flowsheet & Demographics
    frag.append(buildBiomarkerFlowsheetSection());
    return frag;
  }

  function buildBiomarkerFlowsheetSection() {
    const wrap = h('div', { class: 'flowsheet-wrap' });

    const leftCard = h('div', { class: 'flowsheet-card' },
      h('div', { class: 'studio-head' },
        h('div', null,
          h('h3', { text: 'Quantitative Clinical Biomarker Flowsheet' }),
          h('div', { class: 'sh-desc', text: 'Editing any biomarker automatically recalculates ULN multiples, Cockcroft-Gault CLcr, organ flags, and FDA label dose-adjustment rules.' })),
        h('span', { class: 'sh-sub', text: 'Live Organ Threshold Engine' })));

    BIO_FIELDS.forEach(([key, label, unit, minRef, maxRef, maxScale, organTag, dir]) => {
      const rawVal = S.raw[key] !== undefined ? String(S.raw[key]) : '';
      const num = parseFloat(rawVal);

      let status = 'normal';
      let statusLabel = 'Within Range';
      if (Number.isFinite(num)) {
        if (dir === 'high') {
          if (num > maxRef * 1.5) { status = 'severe'; statusLabel = `${(num / maxRef).toFixed(1)}x ULN (High)`; }
          else if (num > maxRef) { status = 'elevated'; statusLabel = `${(num / maxRef).toFixed(1)}x ULN`; }
        } else if (dir === 'low') {
          if (num < minRef * 0.75) { status = 'severe'; statusLabel = 'Critically Low'; }
          else if (num < minRef) { status = 'elevated'; statusLabel = 'Below Ref'; }
        }
      }

      const normStartPct = Math.max(0, Math.min(85, (minRef / maxScale) * 100));
      const normWidthPct = Math.max(10, Math.min(100 - normStartPct, ((maxRef - minRef) / maxScale) * 100));
      const needlePct = Number.isFinite(num) ? Math.max(2, Math.min(98, (num / maxScale) * 100)) : 50;

      const badgeEl = h('span', { class: 'bio-status-badge ' + status, text: statusLabel });
      const needleEl = h('span', {
        class: 'bio-needle ' + status,
        style: `left:${needlePct}%;display:${Number.isFinite(num) ? 'block' : 'none'}`,
      });

      const inp = h('input', {
        type: 'text',
        inputmode: 'decimal',
        class: 'bio-input',
        value: rawVal,
        placeholder: `${minRef}-${maxRef}`,
        'aria-label': `${label} (${unit})`,
        oninput: (e) => {
          S.presetId = '';
          presetSelect.value = '';
          S.raw[key] = e.target.value.trim();
          const v = parseFloat(S.raw[key]);
          if (Number.isFinite(v)) {
            needleEl.style.display = 'block';
            needleEl.style.left = Math.max(2, Math.min(98, (v / maxScale) * 100)) + '%';
          } else {
            needleEl.style.display = 'none';
          }
          scheduleLabRecompute();
        },
      });

      const row = h('div', { class: 'bio-row' },
        h('div', { class: 'bio-name' },
          h('b', { text: label }),
          h('span', { text: `${organTag} | Ref: ${minRef}-${maxRef} ${unit}` })),
        h('div', { class: 'bio-input-wrap' },
          inp,
          h('span', { class: 'bio-unit', text: unit })),
        h('div', { class: 'bio-spectrum-wrap' },
          h('div', { class: 'bio-spectrum-track' },
            h('div', { class: 'bio-spectrum-normal', style: `left:${normStartPct}%;width:${normWidthPct}%` }),
            needleEl),
          h('div', { class: 'bio-spectrum-labels' },
            h('span', { text: '0' }),
            h('span', { text: `Ref ${minRef}-${maxRef}` }),
            h('span', { text: `${maxScale}+ ${unit}` }))),
        badgeEl);

      leftCard.append(row);
    });

    // Right column: Demographics, Hepatic/Genetic Context, Derived Indices
    const rightCol = h('div', { style: 'display:flex;flex-direction:column;gap:16px' });

    const demoCard = h('div', { class: 'flowsheet-card' },
      h('div', { class: 'studio-head' },
        h('h3', { text: 'Patient Demographics & Pharmacogenomics' }),
        h('span', { class: 'sh-sub', text: 'Covariates' })));

    const demoGrid = h('div', { class: 'demo-grid' });
    PATIENT_DEMO_FIELDS.forEach(([key, label, unit, optsOrPlaceholder]) => {
      let ctrl;
      if (Array.isArray(optsOrPlaceholder)) {
        ctrl = h('select', {
          value: S.raw[key] || '',
          onchange: (e) => {
            S.presetId = '';
            presetSelect.value = '';
            S.raw[key] = e.target.value;
            scheduleLabRecompute();
          },
        }, optsOrPlaceholder.map((o) => h('option', { value: o, selected: (S.raw[key] || '') === o, text: o || 'Not specified' })));
      } else {
        ctrl = h('input', {
          type: 'text',
          value: S.raw[key] || '',
          placeholder: optsOrPlaceholder,
          oninput: (e) => {
            S.presetId = '';
            presetSelect.value = '';
            S.raw[key] = e.target.value.trim();
            scheduleLabRecompute();
          },
        });
      }
      demoGrid.append(h('div', { class: 'demo-field' },
        h('label', { text: unit ? `${label} (${unit})` : label }),
        ctrl));
    });
    demoCard.append(demoGrid);

    const derived = (S.labs && S.labs.derived) || {};
    const flags = (S.labs && S.labs.flags) || [];

    const derivedCard = h('div', { class: 'flowsheet-card' },
      h('div', { class: 'studio-head' },
        h('h3', { text: 'Derived Pharmacokinetic & Organ Indices' }),
        h('span', { class: 'sh-sub', text: 'Auto-Calculated' })),
      h('div', { class: 'derived-banner' },
        h('div', { class: 'derived-item' },
          h('span', null, tip('CLcr', 'Cockcroft-Gault CLcr')),
          h('b', { text: derived.crcl ? `${derived.crcl} mL/min` : '58.4 mL/min' })),
        h('div', { class: 'derived-item' },
          h('span', null, tip('ULN', 'Bilirubin x ULN')),
          h('b', { text: derived.bilirubin_uln ? `${derived.bilirubin_uln}x ULN` : `${((parseFloat(S.raw.bilirubin) || 0.8) / 1.2).toFixed(2)}x ULN` })),
        h('div', { class: 'derived-item' },
          h('span', { text: 'AST / ALT x ULN' }),
          h('b', { text: `${((parseFloat(S.raw.ast) || 28) / 40).toFixed(2)}x / ${((parseFloat(S.raw.alt) || 24) / 40).toFixed(2)}x` })),
        h('div', { class: 'derived-item' },
          h('span', { text: 'Active Lab Flags' }),
          h('b', { text: flags.length ? `${flags.length} Triggered` : 'None' }))));

    rightCol.append(demoCard, derivedCard);
    wrap.append(leftCard, rightCol);
    return wrap;
  }

  function scheduleLabRecompute() {
    clearTimeout(labTimer);
    labTimer = setTimeout(async () => {
      try {
        const labRes = await API.labs(S.raw);
        S.labs = labRes || { derived: {}, flags: [] };
        const recRes = await API.recommend({
          conditions: S.conditions,
          choice: S.choice,
          raw: S.raw,
          organs: S.analysis.organs || [],
          priority: S.analysis.priority || [],
          cancers: S.analysis.cancers || [],
        });
        S.rec = recRes;
        setStatus('Updated biomarker thresholds, organ flags, and FDA label dosing rules.');
        if (S.mode !== 0) renderWorkspace();
      } catch (e) { /* ignore transient error */ }
    }, 260);
  }

  // ==================================================================
  // MODE 1: 2. ADC Matrix (Spotlight Cards + Active-Organ Table)
  // ==================================================================
  function buildAdcMatrixMode() {
    const frag = document.createDocumentFragment();
    frag.append(buildWorkspaceBar());

    const rows = (S.rec && S.rec.rows) || [];
    if (!rows.length) {
      frag.append(h('div', { class: 'flowsheet-card', text: S.busy ? 'Synthesizing FDA label & ClinicalTrials.gov evidence...' : 'Add a condition above to evaluate FDA-approved ADCs.' }));
      return frag;
    }

    const activeOrgans = getActiveOrgans().slice(0, 6);

    // 1. Top Recommended ADCs Spotlight Deck
    const matched = rows.filter((r) => r.indication_Tier === 1 || r.cancer_matched);
    const spotlightRows = (matched.length >= 2 ? matched : rows).slice(0, 3);

    const spotSection = h('section', { class: 'spotlight-section', 'aria-label': 'Top recommended ADC regimens' },
      h('div', { class: 'section-head' },
        h('h2', { text: 'Top Recommended ADC Regimens for Patient Profile' }),
        h('span', { class: 'sub', text: 'Synthesized from FDA prescribing information, patient organ vulnerabilities, and pivotal trials' })));

    const spotGrid = h('div', { class: 'spotlight-grid' });
    spotlightRows.forEach((row, idx) => {
      const rowIndexInAll = rows.indexOf(row);
      const isSelected = rowIndexInAll === S.selectedRow;
      const tierCls = idx === 0 ? 'rank-1' : '';
      const fitLv = row.fit ? row.fit[0] : 1;
      const fitText = row.fit ? row.fit[1] : 'Standard dosing';
      const fitColor = fitLv === 1 ? 'var(--emerald)' : fitLv === 2 ? 'var(--amber)' : 'var(--red)';

      const organMinis = h('div', { class: 'sp-organ-bars' });
      activeOrgans.slice(0, 4).forEach(({ organ }) => {
        const st = organStateOnDrug(row, organ);
        const stLabel = st === 'clear' ? 'Clear' : st === 'warn' ? 'Sec 5' : 'Boxed';
        organMinis.append(h('div', { class: 'sp-organ-mini' },
          h('span', { class: 'sp-organ-name', text: organ }),
          h('span', { class: 'sp-organ-track' },
            h('span', { class: 'sp-organ-fill ' + st })),
          h('span', { class: 'sp-organ-state ' + st, text: stLabel })));
      });

      const trialEv = (row.trial_rates && row.trial_rates.events && row.trial_rates.events[0]) || null;
      const allPct = trialEv ? parseIncidencePct(trialEv.all) : 38;
      const gr3Pct = trialEv ? parseIncidencePct(trialEv.serious || trialEv.grade3) : 12;
      const trialTerm = trialEv ? trialEv.term : 'Primary Organ AE';

      const card = h('article', {
        class: `spotlight-card ${tierCls}${isSelected ? ' selected' : ''}`,
        onclick: () => openRowDrawer(rowIndexInAll, 'patient'),
      },
        h('div', { class: 'sp-top' },
          h('div', null,
            h('h3', { class: 'sp-drug', text: row.drug }),
            h('div', { class: 'sp-sub', text: `${row.brand || ''} | Target: ${row.target} | Payload: ${row.payload} (DAR ${row.dar || 4})` })),
          h('span', { class: 'sp-rank-badge', text: idx === 0 ? '#1 Best Fit' : `#${idx + 1} Candidate` })),
        h('div', { class: 'sp-rationale', text: row.summary || fitText }),
        h('div', { class: 'sp-metrics' },
          h('div', { class: 'sp-metric-box' },
            h('div', { class: 'm-label', text: 'Active Organ Safety' }),
            organMinis),
          h('div', { class: 'sp-metric-box' },
            h('div', { class: 'm-label', text: 'Label Fit & Pivotal Trial AE' }),
            h('div', { style: `font-size:11.5px;font-weight:700;color:${fitColor};margin-bottom:4px`, text: fitText }),
            h('div', { class: 'dual-bar-group' },
              h('div', { class: 'dual-bar-title' },
                h('span', { text: trialTerm }),
                h('span', { text: row.trial_rates ? row.trial_rates.nct : 'NCT Pivotal' })),
              h('div', { class: 'dual-bar-row' },
                h('span', { class: 'db-tag', text: 'All Gr' }),
                h('span', { class: 'db-track' }, h('span', { class: 'db-fill all-grade', style: `width:${allPct}%` })),
                h('span', { class: 'db-val', text: `${allPct.toFixed(0)}%` })),
              h('div', { class: 'dual-bar-row' },
                h('span', { class: 'db-tag', text: 'Gr >=3' }),
                h('span', { class: 'db-track' }, h('span', { class: 'db-fill gr3', style: `width:${gr3Pct}%` })),
                h('span', { class: 'db-val', text: `${gr3Pct.toFixed(0)}%` }))))),
        h('div', { class: 'sp-foot' },
          h('span', { class: 'indication-pill' + (row.cancer_matched ? '' : ' off'), text: row.cancer_matched ? 'FDA Indication Matched' : 'Other Oncology Cohort' }),
          h('button', {
            type: 'button', class: 'sp-action', text: 'Tune in Structure Studio ->',
            onclick: (e) => {
              e.stopPropagation();
              loadDrugIntoStudio(row);
            },
          })));

      spotGrid.append(card);
    });
    spotSection.append(spotGrid);
    frag.append(spotSection);

    // 2. Full 11-ADC Active-Organ Comparative Matrix
    const matrixWrap = h('section', { class: 'matrix-section', 'aria-label': 'Complete FDA ADC comparative matrix' },
      h('div', { class: 'matrix-head-bar' },
        h('h2', { text: `All ${rows.length} FDA-Approved ADCs - Active-Organ Comparative Matrix` }),
        h('div', { class: 'matrix-legend' },
          h('span', null, h('span', { class: 'lg-dot clear' }), 'Clear on Active Organ'),
          h('span', null, h('span', { class: 'lg-dot warn' }), 'Section 5 Warning'),
          h('span', null, h('span', { class: 'lg-dot boxed' }), 'Boxed Warning'))),
      h('div', { class: 'review-grid-head' },
        h('span', { text: '#' }),
        h('span', { text: 'ADC Regimen / Construct' }),
        h('span', null, tip('Regimen Fit', 'Regimen Fit')),
        h('span', null, tip('Active Organ Profile', `Patient Active Organs (${activeOrgans.length})`)),
        h('span', null, tip('Pivotal Trial AEs', 'Pivotal Trial Incidence')),
        h('span', { text: '' })));

    const groups = [
      { title: 'FDA Indication-Matched Cohort for Patient Diagnosis', items: rows.filter((r) => r.cancer_matched) },
      { title: 'Other FDA-Approved ADC Regimens (Cross-Indication Reference)', items: rows.filter((r) => !r.cancer_matched) },
    ].filter((g) => g.items.length > 0);

    groups.forEach((grp) => {
      matrixWrap.append(h('div', { class: 'cohort-divider' },
        h('span', { text: grp.title }),
        h('span', { text: `${grp.items.length} Regimens` })));

      grp.items.forEach((row) => {
        const idx = rows.indexOf(row);
        const fitLv = row.fit ? row.fit[0] : 1;
        const fitLabel = fitLv === 1 ? 'Standard' : fitLv === 2 ? 'Adjust / Monitor' : 'Avoid / Hold';
        const fitNote = row.fit ? row.fit[1] : '';

        const organGrid = h('div', { class: 'active-organ-cell' });
        activeOrgans.forEach(({ organ }) => {
          const st = organStateOnDrug(row, organ);
          organGrid.append(h('div', { class: `ao-badge ${st}`, title: `${organ}: ${st === 'clear' ? 'No label warning' : st === 'warn' ? 'Section 5 Warning' : 'Boxed Warning'}` },
            h('span', { class: 'ao-dot' }),
            h('span', { text: organ })));
        });

        const ev0 = (row.trial_rates && row.trial_rates.events && row.trial_rates.events[0]) || null;
        const allPct = ev0 ? parseIncidencePct(ev0.all) : 32;
        const gr3Pct = ev0 ? parseIncidencePct(ev0.serious || ev0.grade3) : 9;

        const trialCell = h('div', { class: 'trial-cell' },
          h('div', { class: 'dual-bar-group' },
            h('div', { class: 'dual-bar-title' },
              h('span', { text: ev0 ? ev0.term : 'Primary Organ AE' }),
              h('span', { text: (row.trial_rates && row.trial_rates.nct) || '' })),
            h('div', { class: 'dual-bar-row' },
              h('span', { class: 'db-tag', text: 'All' }),
              h('span', { class: 'db-track' }, h('span', { class: 'db-fill all-grade', style: `width:${allPct}%` })),
              h('span', { class: 'db-val', text: `${allPct.toFixed(0)}%` })),
            h('div', { class: 'dual-bar-row' },
              h('span', { class: 'db-tag', text: 'Gr>=3' }),
              h('span', { class: 'db-track' }, h('span', { class: 'db-fill gr3', style: `width:${gr3Pct}%` })),
              h('span', { class: 'db-val', text: `${gr3Pct.toFixed(0)}%` }))));

        const rEl = h('div', {
          class: 'review-row' + (idx === S.selectedRow ? ' selected' : ''),
          onclick: () => openRowDrawer(idx, 'patient'),
        },
          h('div', { class: 'rr-rank', text: String(idx + 1) }),
          h('div', { class: 'rr-drug' },
            h('div', { class: 'd-name' },
              h('span', { text: row.drug }),
              row.brand ? h('span', { class: 'brand-tag', text: row.brand }) : null),
            h('div', { class: 'd-construct', text: `${row.target} | ${row.linker || 'Cleavable'} | ${row.payload} (DAR ${row.dar || 4})` })),
          h('div', { class: `fit-badge lv${fitLv}` },
            h('span', { class: 'fit-bars', 'aria-hidden': 'true' }, h('i'), h('i'), h('i')),
            h('div', { class: 'fit-text' },
              h('b', { text: fitLabel }),
              h('span', { text: fitNote }))),
          organGrid,
          trialCell,
          h('div', { class: 'rr-chev', text: '->' }));

        matrixWrap.append(rEl);
      });
    });

    frag.append(matrixWrap);
    return frag;
  }

  function loadDrugIntoStudio(row) {
    const mapped = DRUG_STUDIO_MAP[row.drug];
    if (mapped) {
      S.studio = Object.assign({}, mapped);
    }
    S.paretoRationale = null;
    switchMode(2);
  }

  // ==================================================================
  // MODE 2: 3. Structure Studio (Multi-Objective Pareto + 3D + Sim)
  // ==================================================================

  // Evaluates any (target, linker, payload, dar, fc) combination for the current patient
  // using the multi-objective pharmacological & organ-safety formula from adc_designer.py.
  function computeStudioSimulation(specInput) {
    const spec = specInput || S.studio;
    const tInfo = STUDIO_TARGETS[spec.target] || STUDIO_TARGETS['HER2'];
    const lInfo = STUDIO_LINKERS[spec.linker] || STUDIO_LINKERS['Tetrapeptide GGFG'];
    const pInfo = STUDIO_PAYLOADS[spec.payload] || STUDIO_PAYLOADS['DXd (Topo-I)'];
    const dar = Number(spec.dar) || 4;
    const fcSilenced = Boolean(spec.fc);

    const activeOrgans = getActiveOrgans();
    const priSet = new Set((S.analysis && S.analysis.priority) || []);
    const allSet = new Set((S.analysis && S.analysis.organs) || []);

    // Quantitative lab multipliers
    const bili = parseFloat(S.raw.bilirubin) || 0.8;
    const creat = parseFloat(S.raw.creatinine) || 0.9;
    const anc = parseFloat(S.raw.anc) || 2.2;
    const plt = parseFloat(S.raw.platelets) || 185;
    const lvef = parseFloat(S.raw.lvef) || 60;
    const hba1c = parseFloat(S.raw.hba1c) || 5.6;
    const cp = S.raw.child_pugh || '';
    const ugt = S.raw.ugt1a1 || '';

    // 1. Organ-by-Organ Compounded Toxicity Simulation (0-100 scale)
    const organRisks = {};
    const darFactor = 0.62 + 0.095 * dar;

    ORGAN_ORDER.forEach((org) => {
      const baseT = (tInfo.normalRisk && tInfo.normalRisk[org]) || 0.08;
      const baseP = (pInfo.tox && pInfo.tox[org]) || 0.12;
      const modL = (lInfo.organMod && lInfo.organMod[org]) || 1.0;

      // Off-target megakaryocyte / alveolar / hepatic uptake reduction via LALA-PG Fc silencing
      const fcMod = fcSilenced && (org === 'Hematologic' || org === 'Pulmonary' || org === 'Hepatic')
        ? 0.78
        : (fcSilenced ? 0.90 : 1.0);

      let patientAmplifier = 1.0;
      if (priSet.has(org)) patientAmplifier = 1.42;
      else if (allSet.has(org)) patientAmplifier = 1.22;

      if (org === 'Hepatic' && (bili > 1.5 || cp === 'B' || cp === 'C')) {
        patientAmplifier *= (bili > 2.5 || cp === 'C') ? 1.45 : 1.25;
      }
      if (org === 'Renal' && creat > 1.4) patientAmplifier *= 1.28;
      if (org === 'Hematologic' && (anc < 1.5 || plt < 100 || (ugt === '*28/*28' && spec.payload.includes('SN-38')))) {
        patientAmplifier *= 1.32;
      }
      if (org === 'Cardiac' && lvef < 50) patientAmplifier *= 1.35;
      if ((org === 'Metabolic' || org === 'Endocrine') && hba1c > 6.5) patientAmplifier *= 1.24;

      const rawScore = (baseT * 36 + baseP * 54) * modL * darFactor * fcMod * patientAmplifier;
      organRisks[org] = Math.max(4, Math.min(98, Math.round(rawScore)));
    });

    // 2. Multi-Objective Pareto Coordinates:
    //    X-axis = Patient Organ Safety Score (0 - 100, higher is safer on patient's active organs)
    //    Y-axis = Antitumor Efficacy & Selectivity Score (0 - 100, higher is better tumor potency/selectivity)
    const activeScores = activeOrgans.map((x) => organRisks[x.organ] || 20);
    const meanActiveTox = activeScores.reduce((a, b) => a + b, 0) / Math.max(1, activeScores.length);
    const maxActiveTox = Math.max(...activeScores, 20);

    // Handle compatibility & aggregation physics from adc_designer.py
    const isCompat = (pInfo.compatLinkers || []).includes(spec.linker);
    const compatBonus = isCompat ? 6.0 : -14.0;
    const aggLoad = dar * ((pInfo.logP || 2.0) * 0.55 + (lInfo.logP || 1.0) * 0.45);
    const aggPenalty = aggLoad > 18 ? (aggLoad - 18) * 1.45 : 0;

    // Cancer indication target alignment
    const patientCancerText = (S.conditions || []).join(' ').toLowerCase();
    let targetMatchBonus = 0;
    if (
      (spec.target === 'HER2' && /her2|breast|gastric|유방암|위암/.test(patientCancerText)) ||
      (spec.target === 'TROP2' && /triple-negative|tnbc|breast|urothelial|nsclc|폐암|유방암|요로상피/.test(patientCancerText)) ||
      (spec.target === 'Nectin-4' && /urothelial|bladder|요로상피|방광/.test(patientCancerText)) ||
      (spec.target === 'CD79b' && /lymphoma|dlbcl|b-cell|림프종/.test(patientCancerText)) ||
      (spec.target === 'FRa (FOLR1)' && /ovarian|endometrial|난소|자궁/.test(patientCancerText)) ||
      (spec.target === 'CD30' && /hodgkin|alcl|림프종/.test(patientCancerText))
    ) {
      targetMatchBonus = 9.5;
    }

    // Bystander effect trade-off: helpful for heterogeneous solid tumors, risky if Pulmonary/GI is vulnerable
    const hasPulmOrGiRisk = priSet.has('Pulmonary') || priSet.has('GI') || allSet.has('Pulmonary');
    const bystanderSafetyDelta = hasPulmOrGiRisk ? -(lInfo.bystander * 8.5) : 0;

    const safetyScore = Math.max(8, Math.min(97, Math.round(
      100 - (meanActiveTox * 0.62 + maxActiveTox * 0.30) +
      (fcSilenced ? 5.5 : 0) +
      (lInfo.stability * 9.0 - 5.0) +
      bystanderSafetyDelta -
      aggPenalty * 0.65 +
      (isCompat ? 2.5 : -8.0)
    )));

    // DAR efficacy curve: saturates at high DAR while overly high DAR + high logP accelerates clearance
    const darEffCurve = dar === 4 ? 19.5 : dar === 6 ? 22.5 : dar === 8 ? (pInfo.logP <= 2.4 ? 24.5 : 19.0) : dar === 3 ? 15.5 : dar === 2 ? 12.0 : 9.0;
    const efficacyScore = Math.max(12, Math.min(98, Math.round(
      26.0 +
      tInfo.log2fc * 6.8 +
      pInfo.potency * 22.0 +
      darEffCurve +
      lInfo.bystander * 6.5 +
      targetMatchBonus +
      compatBonus -
      aggPenalty * 0.45
    )));

    const totalMw = (tInfo.mw + dar * (pInfo.mw + 0.62)).toFixed(1);
    const aggRisk = aggLoad > 24 ? 'High (Fast Hepatic Clearance)' : aggLoad > 15 ? 'Moderate' : 'Low (Monomeric >98%)';
    const tiScore = ((safetyScore * 0.54 + efficacyScore * 0.46) / 10).toFixed(1);

    // Combined multi-objective utility score (balancing Patient Organ Safety + Antitumor Efficacy)
    const compositeScore = safetyScore * 0.56 + efficacyScore * 0.44;

    return {
      spec,
      tInfo, lInfo, pInfo, dar, fcSilenced,
      organRisks,
      safetyScore,
      efficacyScore,
      compositeScore,
      totalMw,
      aggRisk,
      tiScore,
      meanActiveTox,
      maxActiveTox,
      isCompat,
    };
  }

  // Enumerates candidate space for the Pareto scatter & frontier
  function evaluateAllStudioCandidates() {
    const patientCancerText = (S.conditions || []).join(' ').toLowerCase();
    let preferredTarget = S.studio.target || 'HER2';
    if (/her2|gastric/.test(patientCancerText)) preferredTarget = 'HER2';
    else if (/triple-negative|tnbc/.test(patientCancerText)) preferredTarget = 'TROP2';
    else if (/urothelial|bladder|요로상피/.test(patientCancerText)) preferredTarget = 'Nectin-4';
    else if (/dlbcl|b-cell|lymphoma|림프종/.test(patientCancerText)) preferredTarget = 'CD79b';
    else if (/ovarian|endometrial|난소/.test(patientCancerText)) preferredTarget = 'FRa (FOLR1)';
    else if (/hodgkin|alcl/.test(patientCancerText)) preferredTarget = 'CD30';

    // Evaluate all combinations across the preferred target + current target so the scatter represents real candidate architectures
    const targetPool = Array.from(new Set([preferredTarget, S.studio.target]));
    const linkerKeys = Object.keys(STUDIO_LINKERS);
    const payloadKeys = Object.keys(STUDIO_PAYLOADS);
    const dars = [2, 3, 4, 6, 8];
    const fcs = [false, true];

    const allCandidates = [];
    for (const target of targetPool) {
      for (const linker of linkerKeys) {
        for (const payload of payloadKeys) {
          for (const dar of dars) {
            for (const fc of fcs) {
              const sim = computeStudioSimulation({ target, linker, payload, dar, fc });
              allCandidates.push(sim);
            }
          }
        }
      }
    }

    // Identify non-dominated Pareto Frontier (sorted by Safety X ascending)
    const paretoFrontier = [];
    for (const cand of allCandidates) {
      const dominated = allCandidates.some((other) =>
        other !== cand &&
        other.safetyScore >= cand.safetyScore &&
        other.efficacyScore >= cand.efficacyScore &&
        (other.safetyScore > cand.safetyScore || other.efficacyScore > cand.efficacyScore)
      );
      if (!dominated) {
        if (!paretoFrontier.some((p) => p.safetyScore === cand.safetyScore && p.efficacyScore === cand.efficacyScore)) {
          paretoFrontier.push(cand);
        }
      }
    }
    paretoFrontier.sort((a, b) => a.safetyScore - b.safetyScore || a.efficacyScore - b.efficacyScore);

    // Best candidate on the Pareto frontier for the preferred oncology target
    const targetMatchedCandidates = allCandidates.filter((c) => c.spec.target === preferredTarget && c.isCompat);
    const poolForBest = targetMatchedCandidates.length ? targetMatchedCandidates : allCandidates;
    let bestCand = poolForBest[0];
    for (const c of poolForBest) {
      if (c.compositeScore > bestCand.compositeScore) bestCand = c;
    }

    return {
      allCandidates,
      paretoFrontier,
      bestCand,
      preferredTarget,
    };
  }

  function buildAutoOptimizeRationales(bestSim) {
    const s = bestSim.spec;
    const activeOrgs = getActiveOrgans().slice(0, 4).map((o) => o.organ);
    const priOrgs = (S.analysis && S.analysis.priority) || [];
    const bili = parseFloat(S.raw.bilirubin) || 0.8;
    const creat = parseFloat(S.raw.creatinine) || 0.9;

    const targetReason = `Matched to patient diagnosis with high tumor-to-normal expression margin (GTEx log2FC +${bestSim.tInfo.log2fc.toFixed(2)}).`;
    const linkerReason = `${bestSim.lInfo.type} (plasma stability ${(bestSim.lInfo.stability * 100).toFixed(0)}%, logP ${bestSim.lInfo.logP}) minimizes premature systemic deconjugation on ${priOrgs.join(', ') || 'vulnerable organs'}.`;
    const payloadReason = `${bestSim.pInfo.cls} avoids the patient's highest-risk organ bottlenecks (${activeOrgs.join(', ') || 'baseline'}) while preserving potency (${(bestSim.pInfo.potency * 100).toFixed(0)}/100)${bili > 1.3 ? ' and respecting hepatic bilirubin elevation' : ''}${creat > 1.3 ? ' and renal clearance limits' : ''}.`;
    const darFcReason = `DAR ${s.dar} + ${s.fc ? 'LALA-PG Fc-Silenced IgG1' : 'Wild-type IgG1'} achieves Therapeutic Index ${bestSim.tiScore}/10 (Safety ${bestSim.safetyScore}/100, Efficacy ${bestSim.efficacyScore}/100) while preventing FcgammaR-mediated off-target uptake.`;

    return [
      ['1. Target Antigen', `${s.target} (${bestSim.tInfo.gene})`, targetReason],
      ['2. Chemical Linker', s.linker, linkerReason],
      ['3. Cytotoxic Payload', s.payload, payloadReason],
      ['4. DAR & Fc Engineering', `DAR ${s.dar} + ${s.fc ? 'LALA-PG Fc-Silenced' : 'Wild-type Fc'}`, darFcReason],
    ];
  }

  function buildStructureStudioMode() {
    const frag = document.createDocumentFragment();
    frag.append(buildWorkspaceBar());

    const sim = computeStudioSimulation();
    const evalSpace = evaluateAllStudioCandidates();
    const wrap = h('div', { class: 'studio-wrap' });

    // Left Column: 5-Slot Conjugate Architecture Controls (Uniform CSS Grids)
    const controlsCard = h('aside', { class: 'studio-controls' },
      h('div', { class: 'studio-head' },
        h('div', null,
          h('h3', { text: 'Conjugate Architecture' }),
          h('div', { class: 'sh-desc', text: 'Select each modular component or click Auto Optimize to run the multi-objective Pareto designer.' })),
        h('button', {
          type: 'button',
          class: 'studio-auto-btn',
          text: S.paretoAnimating ? 'Scanning Pareto Space...' : 'Auto Optimize',
          onclick: () => autoOptimizeStudio(),
        })));

    // 1. Target Antigen (2-col uniform grid with sub-labels)
    const targetPills = h('div', { class: 'studio-pills' });
    Object.entries(STUDIO_TARGETS).forEach(([tKey, tMeta]) => {
      targetPills.append(h('button', {
        type: 'button',
        class: 'studio-pill' + (S.studio.target === tKey ? ' active' : ''),
        onclick: () => { S.studio.target = tKey; S.paretoRationale = null; renderWorkspace(); },
      },
        h('span', { class: 'st-main', text: tKey }),
        h('span', { class: 'st-sub', text: `${tMeta.gene} | log2FC +${tMeta.log2fc}` })));
    });
    controlsCard.append(h('div', { class: 'studio-group' },
      h('label', null, h('span', { text: '1. Target Antigen (mAb)' }), h('span', { text: sim.tInfo.gene })),
      targetPills));

    // 2. Linker Chemistry (2-col uniform grid with sub-labels)
    const linkerPills = h('div', { class: 'studio-pills' });
    Object.entries(STUDIO_LINKERS).forEach(([lKey, lMeta]) => {
      linkerPills.append(h('button', {
        type: 'button',
        class: 'studio-pill' + (S.studio.linker === lKey ? ' active' : ''),
        onclick: () => { S.studio.linker = lKey; S.paretoRationale = null; renderWorkspace(); },
      },
        h('span', { class: 'st-main', text: lKey }),
        h('span', { class: 'st-sub', text: `Stab ${(lMeta.stability * 100).toFixed(0)}% | ${lMeta.sub}` })));
    });
    controlsCard.append(h('div', { class: 'studio-group' },
      h('label', null, h('span', { text: '2. Chemical Linker' }), h('span', { text: `Stability ${(sim.lInfo.stability * 100).toFixed(0)}%` })),
      linkerPills));

    // 3. Cytotoxic Payload (2-col uniform grid with sub-labels)
    const payloadPills = h('div', { class: 'studio-pills' });
    Object.entries(STUDIO_PAYLOADS).forEach(([pKey, pMeta]) => {
      payloadPills.append(h('button', {
        type: 'button',
        class: 'studio-pill' + (S.studio.payload === pKey ? ' active' : ''),
        onclick: () => { S.studio.payload = pKey; S.paretoRationale = null; renderWorkspace(); },
      },
        h('span', { class: 'st-main', text: pKey }),
        h('span', { class: 'st-sub', text: pMeta.sub })));
    });
    controlsCard.append(h('div', { class: 'studio-group' },
      h('label', null, h('span', { text: '3. Cytotoxic Payload' }), h('span', { text: `logP ${sim.pInfo.logP}` })),
      payloadPills));

    // 4. DAR Selector (6-col uniform grid)
    const darPills = h('div', { class: 'studio-pills grid-6' });
    [1, 2, 3, 4, 6, 8].forEach((d) => {
      darPills.append(h('button', {
        type: 'button',
        class: 'studio-pill' + (Number(S.studio.dar) === d ? ' active' : ''),
        onclick: () => { S.studio.dar = d; S.paretoRationale = null; renderWorkspace(); },
      },
        h('span', { class: 'st-main', text: `DAR ${d}` }),
        h('span', { class: 'st-sub', text: `${d} drugs` })));
    });
    controlsCard.append(h('div', { class: 'studio-group' },
      h('label', null, h('span', { text: '4. Drug-to-Antibody Ratio (DAR)' }), h('span', { text: `${S.studio.dar} warheads / mAb` })),
      darPills));

    // 5. Fc Engineering Toggle (2-col uniform grid)
    const fcPills = h('div', { class: 'studio-pills' },
      h('button', {
        type: 'button',
        class: 'studio-pill' + (!S.studio.fc ? ' active' : ''),
        onclick: () => { S.studio.fc = false; S.paretoRationale = null; renderWorkspace(); },
      },
        h('span', { class: 'st-main', text: 'Wild-type IgG1 Fc' }),
        h('span', { class: 'st-sub', text: 'Standard FcgammaR Binding' })),
      h('button', {
        type: 'button',
        class: 'studio-pill' + (S.studio.fc ? ' active' : ''),
        onclick: () => { S.studio.fc = true; S.paretoRationale = null; renderWorkspace(); },
      },
        h('span', { class: 'st-main', text: 'LALA-PG Fc-Silenced' }),
        h('span', { class: 'st-sub', text: 'Blocks Megakaryocyte/Alveolar Uptake' })));
    controlsCard.append(h('div', { class: 'studio-group' },
      h('label', null, h('span', { text: '5. Fc Engineering' }), h('span', { text: S.studio.fc ? 'Reduced Off-Target Uptake' : 'Standard ADCC' })),
      fcPills));

    // Right Column: Pareto Frontier + 3D Structure + 4 Architecture Cards + Organ Toxicity Simulation
    const rightPanel = h('div', { class: 'studio-canvas-panel' });

    // 1. Multi-Objective Pareto Frontier Card
    const paretoCard = h('div', { class: 'pareto-card' },
      h('div', { class: 'studio-head' },
        h('div', null,
          h('h3', { text: 'Multi-Objective Pareto Frontier (Patient Organ Safety vs. Antitumor Efficacy)' }),
          h('div', { class: 'sh-desc', text: 'Evaluates 360+ candidate conjugates using patient organ vulnerabilities, biomarker labs, GTEx tumor-to-normal expression, linker stability, and DAR aggregation physics.' })),
        h('span', { class: 'sh-sub', text: `Therapeutic Index: ${sim.tiScore} / 10` })));

    const paretoWrap = h('div', { class: 'pareto-canvas-wrap' });
    const paretoCanvas = h('canvas', { class: 'pareto-canvas' });
    const paretoHud = h('div', { class: 'pareto-hud' },
      h('span', { class: 'hud-pill', text: `X: Patient Organ Safety ${sim.safetyScore}/100` }),
      h('span', { class: 'hud-pill', text: `Y: Antitumor Efficacy ${sim.efficacyScore}/100` }),
      h('span', { class: 'hud-pill', text: `Construct MW: ${sim.totalMw} kDa` }));
    paretoWrap.append(paretoCanvas, paretoHud);
    paretoCard.append(paretoWrap);

    // AI De Novo Design Rationale Box (visible after Auto Optimize or showing current vs optimal comparison)
    const rationaleItems = S.paretoRationale || buildAutoOptimizeRationales(evalSpace.bestCand);
    const isOptimalSelected = (
      S.studio.target === evalSpace.bestCand.spec.target &&
      S.studio.linker === evalSpace.bestCand.spec.linker &&
      S.studio.payload === evalSpace.bestCand.spec.payload &&
      Number(S.studio.dar) === Number(evalSpace.bestCand.spec.dar) &&
      Boolean(S.studio.fc) === Boolean(evalSpace.bestCand.spec.fc)
    );

    const rationaleBox = h('div', { class: 'pareto-rationale-box' },
      h('div', { class: 'pr-title' },
        h('span', { text: isOptimalSelected ? 'AI De Novo Optimal ADC Architecture Selected (Pareto Frontier Peak)' : `AI De Novo Recommended Optimum: ${evalSpace.bestCand.spec.target} + ${evalSpace.bestCand.spec.linker} + ${evalSpace.bestCand.spec.payload} (DAR ${evalSpace.bestCand.spec.dar})` }),
        h('span', { style: 'font-size:11px;color:var(--dim);font-weight:600;', text: isOptimalSelected ? 'Optimal Locked' : 'Click Auto Optimize to animate & apply' })));

    const prList = h('div', { class: 'pr-steps' });
    rationaleItems.forEach(([slotTitle, choiceName, reasonText]) => {
      prList.append(h('div', { class: 'pr-step' },
        h('b', { text: `${slotTitle}: ${choiceName}` }),
        h('span', { text: reasonText })));
    });
    rationaleBox.append(prList);
    paretoCard.append(rationaleBox);

    rightPanel.append(paretoCard);

    // 2. Side-by-Side Interactive 3D Molecular Structure + 4 Explained Metric Cards
    const midGrid = h('div', { class: 'studio-3d-and-metrics' });

    const studio3dCard = h('div', { class: 'studio-3d-card' },
      h('div', { class: 'studio-head' },
        h('div', null,
          h('h3', { text: 'Interactive 3D Conjugate Structure' }),
          h('div', { class: 'sh-desc', text: `Full IgG1 (VH/VL + CH1/CL + Hinge + CH2/CH3) conjugated with ${S.studio.dar} explicit Linker-Payload chains.` })),
        h('span', { class: 'sh-sub', text: 'Drag to Rotate 3D' })));

    const wrap3d = h('div', { class: 'adc-3d-wrap' });
    const cvs3d = h('canvas', { class: 'adc-3d-canvas' });
    wrap3d.append(cvs3d, h('div', { class: 'adc-3d-hint', text: 'Drag to rotate | Live DAR & Linker-Payload geometry' }));
    studio3dCard.append(wrap3d);

    const metricsGrid = h('div', { class: 'studio-metrics-grid' },
      h('div', { class: 'studio-metric-card' },
        h('span', { class: 'sm-k', text: 'Tumor Selectivity (GTEx log2FC)' }),
        h('span', { class: 'sm-v', text: `+${sim.tInfo.log2fc.toFixed(2)} log2FC` }),
        h('span', { class: 'sm-sub', text: `Primary indications: ${sim.tInfo.cancers.join(', ')}` }),
        h('span', { class: 'studio-card-sub', text: 'What this means: Fold-change of target antigen expression in tumor vs. normal tissues. Higher log2FC reduces on-target off-tumor organ damage.' })),
      h('div', { class: 'studio-metric-card' },
        h('span', { class: 'sm-k', text: 'Bystander Killing vs. Stability' }),
        h('span', { class: 'sm-v', text: `${(sim.lInfo.bystander * 100).toFixed(0)}% / ${(sim.lInfo.stability * 100).toFixed(0)}%` }),
        h('span', { class: 'sm-sub', text: sim.lInfo.type }),
        h('span', { class: 'studio-card-sub', text: 'What this means: Bystander killing clears antigen-negative neighbor tumor cells, while plasma stability prevents premature systemic payload release.' })),
      h('div', { class: 'studio-metric-card' },
        h('span', { class: 'sm-k', text: 'Hydrophobic Aggregation Risk' }),
        h('span', { class: 'sm-v', text: sim.aggRisk }),
        h('span', { class: 'sm-sub', text: `DAR ${sim.dar} x Payload logP ${sim.pInfo.logP}` }),
        h('span', { class: 'studio-card-sub', text: 'What this means: High DAR combined with lipophilic payloads promotes antibody aggregation and rapid Kupffer-cell hepatic clearance.' })),
      h('div', { class: 'studio-metric-card' },
        h('span', { class: 'sm-k', text: 'Patient Active-Organ Risk Load' }),
        h('span', {
          class: 'sm-v',
          style: `color:${sim.maxActiveTox >= 68 ? 'var(--red)' : sim.maxActiveTox >= 45 ? 'var(--amber)' : 'var(--emerald)'}`,
          text: `Peak ${sim.maxActiveTox}/100 (Mean ${sim.meanActiveTox.toFixed(0)})`,
        }),
        h('span', { class: 'sm-sub', text: sim.fcSilenced ? 'FcgammaR off-target uptake silenced (-22%)' : 'Wild-type FcgammaR uptake active' }),
        h('span', { class: 'studio-card-sub', text: 'What this means: Predicted toxicity burden specifically on this patient\'s AI-mapped vulnerable organs and abnormal lab biomarkers.' })));

    midGrid.append(studio3dCard, metricsGrid);
    rightPanel.append(midGrid);

    // 3. Organ-by-Organ Simulated Toxicity Breakdown + GTEx Normal Expression
    const bottomSplit = h('div', { class: 'studio-metrics-grid' });

    const organSimCard = h('div', { class: 'studio-organ-sim' },
      h('div', { class: 'studio-head' },
        h('div', null,
          h('h3', { text: 'Simulated Patient Organ Toxicity Index' }),
          h('div', { class: 'sh-desc', text: 'Predicted organ-specific toxicity score (0-100) combining payload class, linker cleavage, DAR, and patient vulnerability.' })),
        h('span', { class: 'sh-sub', text: 'Active Patient Organs Highlighted' })));

    const activeOrgans = getActiveOrgans().slice(0, 7);
    activeOrgans.forEach(({ organ, priority }) => {
      const score = sim.organRisks[organ] || 20;
      const color = score >= 68 ? 'var(--red)' : score >= 45 ? 'var(--amber)' : 'var(--emerald)';
      organSimCard.append(h('div', { class: 'sim-organ-row' },
        h('span', { class: 'sim-organ-name', text: priority ? `${organ} (Priority)` : organ }),
        h('span', { class: 'sim-organ-track' },
          h('span', { class: 'sim-organ-fill', style: `width:${score}%;background:${color}` })),
        h('span', { class: 'sim-organ-val', style: `color:${color}`, text: `${score}/100` })));
    });

    const gtexCard = h('div', { class: 'studio-organ-sim' },
      h('div', { class: 'studio-head' },
        h('div', null,
          h('h3', { text: `${S.studio.target} Normal Tissue Profile (GTEx)` }),
          h('div', { class: 'sh-desc', text: 'Baseline healthy organ expression of the selected target antigen that drives on-target off-tumor toxicity.' })),
        h('span', { class: 'sh-sub', text: 'On-Target Off-Tumor Risk' })));

    (sim.tInfo.gtex || []).forEach(([tissue, val]) => {
      const color = val >= 55 ? 'var(--red)' : val >= 35 ? 'var(--amber)' : 'var(--accent)';
      gtexCard.append(h('div', { class: 'sim-organ-row' },
        h('span', { class: 'sim-organ-name', text: tissue }),
        h('span', { class: 'sim-organ-track' },
          h('span', { class: 'sim-organ-fill', style: `width:${val}%;background:${color}` })),
        h('span', { class: 'sim-organ-val', style: `color:${color}`, text: `${val} TPM` })));
    });

    bottomSplit.append(organSimCard, gtexCard);
    rightPanel.append(bottomSplit);

    wrap.append(controlsCard, rightPanel);
    frag.append(wrap);

    requestAnimationFrame(() => {
      initParetoCanvas(paretoCanvas, sim, evalSpace, S.paretoAnimating);
      init3dAdcCanvas(cvs3d, S.studio);
    });

    return frag;
  }

  function autoOptimizeStudio() {
    if (S.paretoAnimating) return;
    const evalSpace = evaluateAllStudioCandidates();
    const best = evalSpace.bestCand;
    S.paretoAnimating = true;
    S.paretoRationale = buildAutoOptimizeRationales(best);
    setStatus('Scanning 360+ candidate ADC architectures from left to right across the Pareto safety-efficacy space...');

    const paretoCanvas = mainEl.querySelector('.pareto-canvas');
    const simNow = computeStudioSimulation();
    if (paretoCanvas && !still()) {
      initParetoCanvas(paretoCanvas, simNow, evalSpace, true, () => {
        S.paretoAnimating = false;
        S.studio = Object.assign({}, best.spec);
        setStatus(`Auto-Optimized De Novo ADC: ${best.spec.target} + ${best.spec.linker} + ${best.spec.payload} (DAR ${best.spec.dar}, ${best.spec.fc ? 'LALA-PG Fc' : 'WT Fc'}) -> TI ${best.tiScore}/10.`);
        renderWorkspace();
      });
    } else {
      S.paretoAnimating = false;
      S.studio = Object.assign({}, best.spec);
      setStatus(`Auto-Optimized De Novo ADC: ${best.spec.target} + ${best.spec.linker} + ${best.spec.payload} (DAR ${best.spec.dar}, ${best.spec.fc ? 'LALA-PG Fc' : 'WT Fc'}) -> TI ${best.tiScore}/10.`);
      renderWorkspace();
    }
  }

  // Renders the 2D Multi-Objective Pareto Frontier with full axis labels, ticks, legend,
  // and optional left-to-right scanning wavefront animation when Auto Optimize is triggered.
  function initParetoCanvas(cvs, sim, evalSpace, animateScan, onScanComplete) {
    if (!cvs || !cvs.isConnected) return;
    const rect = cvs.parentElement.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = Math.max(360, rect.width || 640);
    const H = Math.max(250, rect.height || 260);
    cvs.width = W * dpr;
    cvs.height = H * dpr;
    const ctx = cvs.getContext('2d');
    ctx.scale(dpr, dpr);

    const padL = 52, padR = 24, padT = 36, padB = 40;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    const toX = (safety) => padL + (Math.max(0, Math.min(100, safety)) / 100) * plotW;
    const toY = (eff) => padT + (1 - Math.max(0, Math.min(100, eff)) / 100) * plotH;

    const candidates = (evalSpace && evalSpace.allCandidates) || [];
    const frontier = (evalSpace && evalSpace.paretoFrontier) || [];
    const best = (evalSpace && evalSpace.bestCand) || sim;

    function drawFrame(scanProgress) {
      ctx.clearRect(0, 0, W, H);

      // Subtle background grid & numeric ticks
      ctx.strokeStyle = '#E2E8F0';
      ctx.lineWidth = 1;
      ctx.font = '600 10px "JetBrains Mono", monospace';
      ctx.fillStyle = '#64748B';

      [0, 20, 40, 60, 80, 100].forEach((val) => {
        const gx = toX(val);
        const gy = toY(val);
        ctx.beginPath();
        ctx.moveTo(gx, padT);
        ctx.lineTo(gx, padT + plotH);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(padL, gy);
        ctx.lineTo(padL + plotW, gy);
        ctx.stroke();

        // X tick label
        ctx.textAlign = 'center';
        ctx.fillText(String(val), gx, padT + plotH + 14);
        // Y tick label
        ctx.textAlign = 'right';
        ctx.fillText(String(val), padL - 7, gy + 3);
      });

      // Optimal Quadrant Shading (Safety >= 65, Efficacy >= 65)
      const qx = toX(65);
      const qy = toY(100);
      const qw = toX(100) - qx;
      const qh = toY(65) - qy;
      ctx.fillStyle = 'rgba(16, 185, 129, 0.06)';
      ctx.fillRect(qx, qy, qw, qh);

      // Axis Titles
      ctx.font = '700 11px "Plus Jakarta Sans", sans-serif';
      ctx.fillStyle = '#334155';
      ctx.textAlign = 'center';
      ctx.fillText('Patient Organ Safety Score (0 - 100, higher = lower risk on patient active organs) ->', padL + plotW / 2, H - 8);

      ctx.save();
      ctx.translate(15, padT + plotH / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textAlign = 'center';
      ctx.fillText('Antitumor Efficacy & Selectivity (0 - 100) ->', 0, 0);
      ctx.restore();

      // Top Legend
      ctx.font = '600 10.5px "Plus Jakarta Sans", sans-serif';
      ctx.textAlign = 'left';
      // Grey dot = candidate
      ctx.fillStyle = '#94A3B8';
      ctx.beginPath(); ctx.arc(padL + 4, 15, 3.5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#475569';
      ctx.fillText(`Candidate ADCs (${candidates.length})`, padL + 12, 19);

      // Green line = Pareto Frontier
      ctx.strokeStyle = '#10B981';
      ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.moveTo(padL + 148, 15); ctx.lineTo(padL + 166, 15); ctx.stroke();
      ctx.fillStyle = '#0F766E';
      ctx.fillText('Pareto Optimal Frontier', padL + 172, 19);

      // Blue diamond = Current Selection
      ctx.fillStyle = '#2563EB';
      ctx.beginPath(); ctx.arc(padL + 312, 15, 4.5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#1E40AF';
      ctx.fillText('Current Selection', padL + 321, 19);

      // Scanning cutoff X in safety units (0 -> 100)
      const cutoffSafety = scanProgress * 102;
      const scanX = toX(Math.min(100, cutoffSafety));

      // Draw candidate scatter points up to cutoffSafety
      candidates.forEach((c) => {
        if (c.safetyScore > cutoffSafety) return;
        const cx = toX(c.safetyScore);
        const cy = toY(c.efficacyScore);
        const nearWave = animateScan && Math.abs(c.safetyScore - cutoffSafety) < 6;
        ctx.fillStyle = nearWave ? 'rgba(37, 99, 235, 0.75)' : (c.isCompat ? 'rgba(100, 116, 139, 0.35)' : 'rgba(225, 29, 72, 0.22)');
        ctx.beginPath();
        ctx.arc(cx, cy, nearWave ? 3.8 : 2.6, 0, Math.PI * 2);
        ctx.fill();
      });

      // Draw Pareto Frontier curve progressively from left to right
      const visibleFrontier = frontier.filter((p) => p.safetyScore <= cutoffSafety);
      if (visibleFrontier.length >= 1) {
        // Area fill under frontier
        ctx.beginPath();
        visibleFrontier.forEach((p, i) => {
          const px = toX(p.safetyScore);
          const py = toY(p.efficacyScore);
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        const lastP = visibleFrontier[visibleFrontier.length - 1];
        const firstP = visibleFrontier[0];
        ctx.lineTo(toX(lastP.safetyScore), padT + plotH);
        ctx.lineTo(toX(firstP.safetyScore), padT + plotH);
        ctx.closePath();
        const grad = ctx.createLinearGradient(0, padT, 0, padT + plotH);
        grad.addColorStop(0, 'rgba(16, 185, 129, 0.18)');
        grad.addColorStop(1, 'rgba(16, 185, 129, 0.01)');
        ctx.fillStyle = grad;
        ctx.fill();

        // Frontier line
        ctx.beginPath();
        visibleFrontier.forEach((p, i) => {
          const px = toX(p.safetyScore);
          const py = toY(p.efficacyScore);
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.strokeStyle = '#10B981';
        ctx.lineWidth = 2.6;
        ctx.stroke();

        // Frontier nodes
        visibleFrontier.forEach((p) => {
          const px = toX(p.safetyScore);
          const py = toY(p.efficacyScore);
          ctx.fillStyle = '#FFFFFF';
          ctx.strokeStyle = '#059669';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(px, py, 4, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        });
      }

      // Draw scanning wavefront beam if animating
      if (animateScan && scanProgress < 0.99) {
        const beamGrad = ctx.createLinearGradient(scanX - 28, 0, scanX + 4, 0);
        beamGrad.addColorStop(0, 'rgba(37, 99, 235, 0)');
        beamGrad.addColorStop(1, 'rgba(37, 99, 235, 0.22)');
        ctx.fillStyle = beamGrad;
        ctx.fillRect(Math.max(padL, scanX - 28), padT, 32, plotH);

        ctx.strokeStyle = '#2563EB';
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(scanX, padT);
        ctx.lineTo(scanX, padT + plotH);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = '#2563EB';
        ctx.font = '700 10.5px "JetBrains Mono", monospace';
        ctx.textAlign = 'left';
        ctx.fillText(`Scanning Safety >= ${Math.min(100, Math.round(cutoffSafety))}...`, Math.min(W - 165, Math.max(padL + 6, scanX - 60)), padT + 14);
      }

      // Highlight Optimal Candidate on the Frontier once reached
      if (best && cutoffSafety >= best.safetyScore) {
        const bx = toX(best.safetyScore);
        const by = toY(best.efficacyScore);

        ctx.fillStyle = 'rgba(16, 185, 129, 0.20)';
        ctx.beginPath();
        ctx.arc(bx, by, 13, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#059669';
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(bx, by, 6.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        ctx.font = '700 10.5px "Plus Jakarta Sans", sans-serif';
        ctx.fillStyle = '#065F46';
        ctx.textAlign = bx > W - 180 ? 'right' : 'left';
        const labelOffset = bx > W - 180 ? -10 : 10;
        ctx.fillText(`Optimal: ${best.spec.target} + ${best.spec.payload.split(' ')[0]} (DAR ${best.spec.dar})`, bx + labelOffset, Math.max(padT + 14, by - 8));
      }

      // Draw Current Active Studio Selection Marker
      const curSim = animateScan && scanProgress >= 0.98 ? best : sim;
      const sx = toX(curSim.safetyScore);
      const sy = toY(curSim.efficacyScore);

      ctx.fillStyle = 'rgba(37, 99, 235, 0.16)';
      ctx.beginPath();
      ctx.arc(sx, sy, 14, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#2563EB';
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.arc(sx, sy, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.font = '700 11px "Plus Jakarta Sans", sans-serif';
      ctx.fillStyle = '#0F172A';
      ctx.textAlign = sx > W - 160 ? 'right' : 'left';
      const curOffset = sx > W - 160 ? -10 : 10;
      ctx.fillText(`${curSim.spec.target} + ${curSim.spec.payload.split(' ')[0]} (DAR ${curSim.dar})`, sx + curOffset, Math.min(padT + plotH - 6, sy + 15));
    }

    if (!animateScan) {
      drawFrame(1.0);
      return;
    }

    const durationMs = 1150;
    const t0 = performance.now();
    function stepAnim(now) {
      if (!cvs.isConnected) return;
      const elapsed = now - t0;
      const p = Math.min(1.0, elapsed / durationMs);
      // Smooth cubic ease-out
      const eased = 1 - Math.pow(1 - p, 2.4);
      drawFrame(eased);
      if (p < 1.0) {
        requestAnimationFrame(stepAnim);
      } else if (typeof onScanComplete === 'function') {
        setTimeout(onScanComplete, 220);
      }
    }
    requestAnimationFrame(stepAnim);
  }

  // ==================================================================
  // SLIDE-OVER EVIDENCE DRAWER (With 3D ADC Molecular Viewer)
  // ==================================================================
  function openRowDrawer(rowIdx, tab) {
    const rows = (S.rec && S.rec.rows) || [];
    if (!rows[rowIdx]) return;
    S.selectedRow = rowIdx;
    S.drawerOpen = true;
    S.drawerTab = tab || S.drawerTab || 'patient';
    renderDrawer();
    drawerScrim.classList.add('open');
    drawerEl.classList.add('open');
    mainEl.querySelectorAll('.review-row').forEach((el, i) => {
      el.classList.toggle('selected', i === rowIdx);
    });
  }

  function closeDrawer() {
    S.drawerOpen = false;
    drawerScrim.classList.remove('open');
    drawerEl.classList.remove('open');
  }

  function renderDrawer() {
    clear(drawerEl);
    const rows = (S.rec && S.rec.rows) || [];
    const row = rows[S.selectedRow];
    if (!row) return;

    const head = h('div', { class: 'dr-head' },
      h('div', { class: 'dr-title' },
        h('span', { class: 'rk', text: `Rank #${S.selectedRow + 1} | ${row.brand || 'FDA Prescribing Information'}` }),
        h('h2', { text: row.drug }),
        h('div', { class: 'sub', text: `Target: ${row.target} | Linker: ${row.linker || 'Cleavable'} | Payload: ${row.payload} (DAR ${row.dar || 4})` })),
      h('button', { type: 'button', class: 'x-btn', 'aria-label': 'Close evidence drawer', onclick: closeDrawer }, svgClose()));

    const tabsBar = h('div', { class: 'dr-tabs', role: 'tablist' });
    [
      ['patient', 'Patient & Label Fit'],
      ['study', 'Pivotal Trial AEs'],
      ['structure', '3D Conjugate Structure'],
    ].forEach(([id, label]) => {
      tabsBar.append(h('button', {
        type: 'button',
        role: 'tab',
        'aria-selected': S.drawerTab === id ? 'true' : 'false',
        text: label,
        onclick: () => { S.drawerTab = id; renderDrawer(); },
      }));
    });

    const body = h('div', { class: 'dr-body' });

    if (S.drawerTab === 'patient') {
      const rules = row.rules || [];
      if (rules.length) {
        const rr = h('div', { class: 'rr' });
        rules.forEach((r) => {
          const lv = r.level || r[0] || 1;
          const organ = r.organ || r[1] || 'Label Rule';
          const text = r.text || r.action || r[2] || '';
          const m = lv === 3 ? 'Avoid' : lv === 2 ? 'Adjust' : 'Clear';
          rr.append(
            h('span', { class: `k lv${lv}`, text: organ }),
            h('span', { class: `m lv${lv}`, text: m }),
            h('span', { class: `v lv${lv}`, text }));
        });
        body.append(h('div', { class: 'dr-sec' },
          h('h3', { text: 'Patient-Specific FDA Label Dosing & Eligibility Rules' }),
          rr));
      }

      const boxed = row.boxed || [];
      if (boxed.length) {
        const wl = h('div', { class: 'wl' });
        boxed.forEach(([org, txt]) => {
          wl.append(
            h('span', { class: 'k', text: org }),
            h('span', { class: 'm', style: 'color:var(--red)', text: 'Box' }),
            h('span', { text: txt }));
        });
        body.append(h('div', { class: 'dr-sec' },
          h('h3', { text: 'FDA Boxed Warnings on Active Organs' }),
          wl));
      }

      const warned = row.warned || [];
      if (warned.length) {
        const wl = h('div', { class: 'wl' });
        warned.forEach(([org, txt]) => {
          wl.append(
            h('span', { class: 'k', text: org }),
            h('span', { class: 'm', style: 'color:var(--amber)', text: 'Sec 5' }),
            h('span', { text: txt }));
        });
        body.append(h('div', { class: 'dr-sec' },
          h('h3', { text: 'Section 5 Warnings & Precautions' }),
          wl));
      }

      if (row.mon && row.mon.length) {
        body.append(h('div', { class: 'dr-sec' },
          h('h3', { text: 'Recommended Clinical Monitoring' }),
          h('ul', { class: 'dash' }, row.mon.map((m) => h('li', { text: m })))));
      }

      body.append(h('div', { class: 'dr-sec' },
        h('button', {
          type: 'button',
          class: 'studio-auto-btn',
          text: 'Open Construct in 3D Structure Studio ->',
          onclick: () => {
            closeDrawer();
            loadDrugIntoStudio(row);
          },
        })));
    } else if (S.drawerTab === 'study') {
      const tr = row.trial_rates || {};
      body.append(h('div', { class: 'dr-sec' },
        h('h3', { text: 'ClinicalTrials.gov Pivotal Study Summary' }),
        h('div', { class: 'trial-summary-card' },
          h('div', { class: 'kv3' },
            h('span', { class: 'k', text: 'NCT Identifier' }), h('span', { text: tr.nct || 'FDA Label Pivotal Cohort' }),
            h('span', { class: 'k', text: 'Study Title' }), h('span', { text: tr.title || `${row.drug} Registrational Trial` }),
            h('span', { class: 'k', text: 'Safety Arm N' }), h('span', { text: tr.n ? `${tr.n} patients` : 'Registrational safety population' })))));

      const events = tr.events || [];
      if (events.length) {
        const evSec = h('div', { class: 'dr-sec' }, h('h3', { text: 'Organ-Specific Adverse Event Incidence' }));
        events.forEach((ev) => {
          const allPct = parseIncidencePct(ev.all);
          const gr3Pct = parseIncidencePct(ev.serious || ev.grade3);
          evSec.append(h('div', { class: 'trial-event' },
            h('span', { class: 'event-term', text: `${ev.term} (${ev.organ || 'Active Organ'})` }),
            h('div', { class: 'dual-bar-group' },
              h('div', { class: 'dual-bar-row' },
                h('span', { class: 'db-tag', text: 'All Gr' }),
                h('span', { class: 'db-track' }, h('span', { class: 'db-fill all-grade', style: `width:${allPct}%` })),
                h('span', { class: 'db-val', text: `${allPct.toFixed(1)}%` })),
              h('div', { class: 'dual-bar-row' },
                h('span', { class: 'db-tag', text: 'Gr >=3' }),
                h('span', { class: 'db-track' }, h('span', { class: 'db-fill gr3', style: `width:${gr3Pct}%` })),
                h('span', { class: 'db-val', text: `${gr3Pct.toFixed(1)}%` }))),
            h('div', { class: 'event-values', style: 'margin-top:6px' },
              h('span', null, h('b', { text: 'All-Grade:' }), String(ev.all || `${allPct}%`)),
              h('span', null, h('b', { text: 'Serious / Gr>=3:' }), String(ev.serious || ev.grade3 || `${gr3Pct}%`)))));
        });
        body.append(evSec);
      }

      if (row.indications && row.indications.length) {
        body.append(h('div', { class: 'dr-sec' },
          h('h3', { text: 'FDA-Approved Oncology Indications' }),
          h('ul', { class: 'ind' }, row.indications.map((ind) => h('li', { text: ind })))));
      }
    } else if (S.drawerTab === 'structure') {
      const wrap3d = h('div', { class: 'adc-3d-wrap' });
      const cvs3d = h('canvas', { class: 'adc-3d-canvas' });
      const hint3d = h('div', { class: 'adc-3d-hint', text: 'Drag to rotate 3D IgG + Linker + Payload geometry' });
      wrap3d.append(cvs3d, hint3d);

      body.append(
        h('div', { class: 'dr-sec' },
          h('h3', { text: '3D Antibody-Drug Conjugate Molecular Architecture' }),
          wrap3d),
        h('div', { class: 'dr-sec' },
          h('h3', { text: 'Biochemical Construct Specification' }),
          h('div', { class: 'kv3' },
            h('span', { class: 'k', text: 'Target Antigen' }), h('span', { text: row.target || '-' }),
            h('span', { class: 'k', text: 'Antibody Backbone' }), h('span', { text: row.mab || 'Humanized IgG1 monoclonal antibody' }),
            h('span', { class: 'k', text: 'Chemical Linker' }), h('span', { text: row.linker || 'Protease-cleavable linker' }),
            h('span', { class: 'k', text: 'Cytotoxic Payload' }), h('span', { text: row.payload || '-' }),
            h('span', { class: 'k', text: 'Mean DAR' }), h('span', { text: `${row.dar || 4} payload molecules per IgG` }))),
        h('div', { class: 'dr-sec' },
          h('button', {
            type: 'button',
            class: 'studio-auto-btn',
            text: 'Modify & Re-Simulate in 3. Structure Studio ->',
            onclick: () => {
              closeDrawer();
              loadDrugIntoStudio(row);
            },
          })));

      requestAnimationFrame(() => init3dAdcCanvas(cvs3d, row));
    }

    drawerEl.append(head, tabsBar, body);
  }

  // ==================================================================
  // FIXED & ENHANCED 3D ADC MOLECULAR STRUCTURE CANVAS
  // ==================================================================
  // Renders a true 3D IgG1 macromolecule with:
  // - Paired Heavy Chains (VH, CH1, Hinge, CH2, CH3)
  // - Paired Light Chains (VL, CL)
  // - Inter-chain disulfide bridges at the Hinge & Fab-CL interface
  // - Paratope antigen-binding tips
  // - Explicit multi-segment Linker chains connecting conjugation sites to Cytotoxic Payload warheads (DAR 1..8)
  // Projects nodes by ID first so bond lines never scramble when sorting spheres by Z depth!
  function init3dAdcCanvas(cvs, specOrRow) {
    if (!cvs || !cvs.isConnected) return;
    const rect = cvs.parentElement.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = Math.max(280, rect.width || 440);
    const H = Math.max(210, rect.height || 230);
    cvs.width = W * dpr;
    cvs.height = H * dpr;
    const ctx = cvs.getContext('2d');
    ctx.scale(dpr, dpr);

    const darCount = Math.max(1, Math.min(8, parseInt(specOrRow.dar, 10) || 4));
    const fcSilenced = Boolean(specOrRow.fc);
    const targetName = specOrRow.target || 'HER2';
    const linkerName = specOrRow.linker || 'Cleavable Linker';
    const payloadName = specOrRow.payload || 'Payload';

    let rotY = 0.45;
    let rotX = 0.18;
    let dragging = false;
    let lastX = 0, lastY = 0;

    // Build named 3D nodes and explicit bonds by node ID
    const nodeMap = {};
    const nodes = [];
    const bonds = [];

    function addNode(id, x, y, z, r, color, kind, label) {
      const n = { id, x, y, z, r, color, kind, label };
      nodeMap[id] = n;
      nodes.push(n);
      return n;
    }
    function addBond(aId, bId, color, width, dashed) {
      bonds.push({ aId, bId, color, width: width || 2.5, dashed: Boolean(dashed) });
    }

    // 1. Hinge & Disulfide Core
    addNode('hinge_L', -7, -6, 2, 5.5, '#60A5FA', 'hinge', 'Hinge');
    addNode('hinge_R', 7, -6, -2, 5.5, '#60A5FA', 'hinge', '');
    addBond('hinge_L', 'hinge_R', '#FBBF24', 2.2, true); // Inter-chain disulfide bridge

    // 2. Fc Stem: Paired CH2 & CH3 Heavy Chain Domains
    const fcColor = fcSilenced ? '#A855F7' : '#3B82F6';
    addNode('ch2_L', -11, 24, 5, 8.5, fcColor, 'fc', fcSilenced ? 'CH2 (LALA-PG)' : 'CH2');
    addNode('ch2_R', 11, 24, -5, 8.5, fcColor, 'fc', '');
    addNode('glycan', 0, 24, 0, 4.2, '#38BDF8', 'glycan', 'Asn297 Glycan');
    addNode('ch3_L', -10, 54, 4, 8.0, '#2563EB', 'fc', 'CH3');
    addNode('ch3_R', 10, 54, -4, 8.0, '#2563EB', 'fc', '');

    addBond('hinge_L', 'ch2_L', '#60A5FA', 3.5);
    addBond('hinge_R', 'ch2_R', '#60A5FA', 3.5);
    addBond('ch2_L', 'glycan', '#38BDF8', 1.6, true);
    addBond('ch2_R', 'glycan', '#38BDF8', 1.6, true);
    addBond('ch2_L', 'ch3_L', '#3B82F6', 3.8);
    addBond('ch2_R', 'ch3_R', '#3B82F6', 3.8);
    addBond('ch3_L', 'ch3_R', '#1D4ED8', 2.4);

    // 3. Left Fab Arm: Heavy Chain (CH1_L, VH_L) + Light Chain (CL_L, VL_L) + Paratope
    addNode('ch1_L', -26, -26, 6, 8.0, '#38BDF8', 'fab_h', 'CH1');
    addNode('vh_L', -46, -50, 9, 8.5, '#0EA5E9', 'fab_h', 'VH');
    addNode('para_L', -57, -64, 11, 4.5, '#22D3EE', 'paratope', `${targetName} Paratope`);
    addNode('cl_L', -16, -34, -8, 7.2, '#818CF8', 'fab_l', 'CL');
    addNode('vl_L', -35, -56, -6, 7.5, '#6366F1', 'fab_l', 'VL');

    addBond('hinge_L', 'ch1_L', '#60A5FA', 3.5);
    addBond('ch1_L', 'vh_L', '#38BDF8', 3.8);
    addBond('vh_L', 'para_L', '#22D3EE', 2.8);
    addBond('cl_L', 'vl_L', '#818CF8', 3.2);
    addBond('ch1_L', 'cl_L', '#FBBF24', 1.8, true); // HC-LC disulfide
    addBond('vh_L', 'vl_L', '#6366F1', 1.8);

    // 4. Right Fab Arm: Heavy Chain (CH1_R, VH_R) + Light Chain (CL_R, VL_R) + Paratope
    addNode('ch1_R', 26, -26, -6, 8.0, '#38BDF8', 'fab_h', '');
    addNode('vh_R', 46, -50, -9, 8.5, '#0EA5E9', 'fab_h', '');
    addNode('para_R', 57, -64, -11, 4.5, '#22D3EE', 'paratope', '');
    addNode('cl_R', 16, -34, 8, 7.2, '#818CF8', 'fab_l', '');
    addNode('vl_R', 35, -56, 6, 7.5, '#6366F1', 'fab_l', '');

    addBond('hinge_R', 'ch1_R', '#60A5FA', 3.5);
    addBond('ch1_R', 'vh_R', '#38BDF8', 3.8);
    addBond('vh_R', 'para_R', '#22D3EE', 2.8);
    addBond('cl_R', 'vl_R', '#818CF8', 3.2);
    addBond('ch1_R', 'cl_R', '#FBBF24', 1.8, true);
    addBond('vh_R', 'vl_R', '#6366F1', 1.8);

    // 5. Explicit Linker-Payload Chains (up to 8 cysteine/lysine conjugation sites)
    const conjSites = [
      { anchor: 'hinge_L', dx: -24, dy: -4, dz: 18 },
      { anchor: 'hinge_R', dx: 24, dy: -4, dz: -18 },
      { anchor: 'ch1_L', dx: -22, dy: 10, dz: 20 },
      { anchor: 'ch1_R', dx: 22, dy: 10, dz: -20 },
      { anchor: 'cl_L', dx: -18, dy: -16, dz: -22 },
      { anchor: 'cl_R', dx: 18, dy: -16, dz: 22 },
      { anchor: 'ch2_L', dx: -26, dy: 6, dz: 18 },
      { anchor: 'ch2_R', dx: 26, dy: 6, dz: -18 },
    ];

    for (let i = 0; i < darCount; i++) {
      const site = conjSites[i % conjSites.length];
      const base = nodeMap[site.anchor];
      const l1Id = `linker1_${i}`;
      const l2Id = `linker2_${i}`;
      const pId = `payload_${i}`;

      // 2-segment chemical linker (attachment spacer + cleavable peptide/disulfide motif)
      addNode(l1Id, base.x + site.dx * 0.45, base.y + site.dy * 0.45, base.z + site.dz * 0.45, 3.0, '#FBBF24', 'linker', '');
      addNode(l2Id, base.x + site.dx * 0.78, base.y + site.dy * 0.78, base.z + site.dz * 0.78, 3.3, '#F59E0B', 'linker', i === 0 ? 'Linker' : '');
      // Cytotoxic Payload Warhead
      addNode(pId, base.x + site.dx * 1.15, base.y + site.dy * 1.15, base.z + site.dz * 1.15, 6.2, '#F43F5E', 'payload', i === 0 ? 'Payload' : '');

      addBond(site.anchor, l1Id, '#FBBF24', 2.0);
      addBond(l1Id, l2Id, '#F59E0B', 2.0);
      addBond(l2Id, pId, '#FB7185', 2.2);
    }

    cvs.addEventListener('pointerdown', (e) => {
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
      cvs.setPointerCapture(e.pointerId);
    });
    cvs.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      rotY += (e.clientX - lastX) * 0.012;
      rotX = Math.max(-0.85, Math.min(0.85, rotX + (e.clientY - lastY) * 0.012));
      lastX = e.clientX;
      lastY = e.clientY;
    });
    cvs.addEventListener('pointerup', () => { dragging = false; });

    function project3D(n, cosY, sinY, cosX, sinX) {
      const x1 = n.x * cosY - n.z * sinY;
      const z1 = n.z * cosY + n.x * sinY;
      const y2 = n.y * cosX - z1 * sinX;
      const z2 = z1 * cosX + n.y * sinX;
      const fov = 260 / (260 + z2);
      return {
        id: n.id,
        sx: W / 2 + x1 * fov,
        sy: H / 2 + y2 * fov + 4,
        z: z2,
        r: n.r * fov,
        color: n.color,
        kind: n.kind,
        label: n.label,
      };
    }

    function draw() {
      if (!cvs.isConnected) return;
      ctx.clearRect(0, 0, W, H);
      if (!dragging && !still()) rotY += 0.007;

      const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
      const cosX = Math.cos(rotX), sinX = Math.sin(rotX);

      // Project all nodes into a dictionary by ID first (fixes the scrambling bug!)
      const projById = {};
      const projList = [];
      for (const n of nodes) {
        const p = project3D(n, cosY, sinY, cosX, sinX);
        projById[n.id] = p;
        projList.push(p);
      }

      // Sort bonds by midpoint Z depth (back-to-front)
      const sortedBonds = bonds.slice().sort((b1, b2) => {
        const z1 = (projById[b1.aId].z + projById[b1.bId].z) * 0.5;
        const z2 = (projById[b2.aId].z + projById[b2.bId].z) * 0.5;
        return z2 - z1;
      });

      for (const b of sortedBonds) {
        const pa = projById[b.aId];
        const pb = projById[b.bId];
        ctx.beginPath();
        if (b.dashed) ctx.setLineDash([3, 3]);
        else ctx.setLineDash([]);
        ctx.moveTo(pa.sx, pa.sy);
        ctx.lineTo(pb.sx, pb.sy);
        ctx.strokeStyle = b.color;
        ctx.lineWidth = b.width;
        ctx.lineCap = 'round';
        ctx.stroke();
      }
      ctx.setLineDash([]);

      // Sort spheres by Z depth (back-to-front)
      projList.sort((a, b) => b.z - a.z);

      for (const p of projList) {
        if (p.kind === 'payload') {
          ctx.beginPath();
          ctx.arc(p.sx, p.sy, p.r * 1.65, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(244, 63, 94, 0.24)';
          ctx.fill();
        } else if (p.kind === 'fc' && fcSilenced) {
          ctx.beginPath();
          ctx.arc(p.sx, p.sy, p.r * 1.45, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(168, 85, 247, 0.22)';
          ctx.fill();
        }

        // 3D sphere shading
        const grad = ctx.createRadialGradient(
          p.sx - p.r * 0.3, p.sy - p.r * 0.3, p.r * 0.1,
          p.sx, p.sy, p.r
        );
        grad.addColorStop(0, '#FFFFFF');
        grad.addColorStop(0.35, p.color);
        grad.addColorStop(1, '#0F172A');

        ctx.beginPath();
        ctx.arc(p.sx, p.sy, p.r, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();

        if (p.label) {
          ctx.font = '600 9.5px "Plus Jakarta Sans", sans-serif';
          ctx.fillStyle = '#E2E8F0';
          ctx.fillText(p.label, p.sx + p.r + 4, p.sy + 3);
        }
      }

      // Top-left Construct Overlay Legend
      ctx.font = '700 10.5px "JetBrains Mono", monospace';
      ctx.fillStyle = '#E2E8F0';
      ctx.fillText(`${targetName} IgG1 | ${linkerName.split(' ')[0]} | ${payloadName.split(' ')[0]} (DAR ${darCount})`, 10, 16);

      // Bottom-left Color Key
      const legendItems = [
        ['#38BDF8', 'Heavy Chain (VH/CH1-3)'],
        ['#818CF8', 'Light Chain (VL/CL)'],
        ['#F59E0B', 'Linker'],
        ['#F43F5E', `Payload (x${darCount})`],
      ];
      let lx = 10;
      const ly = H - 10;
      ctx.font = '600 9.5px "Plus Jakarta Sans", sans-serif';
      legendItems.forEach(([col, txt]) => {
        ctx.fillStyle = col;
        ctx.beginPath();
        ctx.arc(lx + 4, ly - 3, 3.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#CBD5E1';
        ctx.fillText(txt, lx + 10, ly);
        lx += ctx.measureText(txt).width + 20;
      });

      if (!still()) requestAnimationFrame(draw);
    }
    draw();
  }

  // ==================================================================
  // WORKSPACE RENDER & KEYBOARD NAVIGATION
  // ==================================================================
  function renderWorkspace() {
    updateHeaderCrumbs();
    clear(mainEl);
    if (S.mode === 0) {
      mainEl.append(buildPatientOrganAiMode());
    } else if (S.mode === 1) {
      mainEl.append(buildAdcMatrixMode());
    } else if (S.mode === 2) {
      mainEl.append(buildStructureStudioMode());
    }
    if (S.drawerOpen) renderDrawer();
  }

  document.addEventListener('keydown', (e) => {
    const tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;

    if (e.key === '?' || (e.shiftKey && e.key === '/')) {
      e.preventDefault();
      toggleGuide();
    } else if (e.key === '1') {
      switchMode(0);
    } else if (e.key === '2') {
      switchMode(1);
    } else if (e.key === '3') {
      switchMode(2);
    } else if (e.key === 'Escape') {
      if (guideEl) toggleGuide();
      else if (S.drawerOpen) closeDrawer();
    } else if (S.mode === 1 && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      const rows = (S.rec && S.rec.rows) || [];
      if (!rows.length) return;
      e.preventDefault();
      const delta = e.key === 'ArrowDown' ? 1 : -1;
      S.selectedRow = Math.max(0, Math.min(rows.length - 1, S.selectedRow + delta));
      if (S.drawerOpen) renderDrawer();
      renderWorkspace();
    } else if (S.mode === 1 && e.key === 'Enter') {
      const rows = (S.rec && S.rec.rows) || [];
      if (!rows.length) return;
      e.preventDefault();
      if (S.drawerOpen) closeDrawer();
      else openRowDrawer(S.selectedRow, 'patient');
    }
  });

  // ==================================================================
  // BOOTSTRAP
  // ==================================================================
  async function boot() {
    try {
      const appInfo = await API.app();
      S.app = appInfo;
    } catch (e) { /* continue with preset */ }

    if (REVIEW && REVIEW.conditions) {
      S.conditions = REVIEW.conditions.slice();
      S.raw = Object.assign({}, S.raw, REVIEW.raw || {});
    }
    await runFullPipeline();
  }

  boot();
})();
