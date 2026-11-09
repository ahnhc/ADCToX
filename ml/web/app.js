/* ADCTOX v0.7.0 Architectural Daylight WebApp
   Active-Organ Matrix + 3D Structure Studio + Biomarker Flowsheet
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
      ['Amber bar', 'Section 5 Warning on this organ'],
      ['Crimson bar', 'Boxed Warning on this organ'],
    ]],
    'Pivotal Trial vs Control': ['Study-group adverse event incidence in pivotal registration trial.', [
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
          h('button', { type: 'button', class: 'x-btn', 'aria-label': 'Close', onclick: closeGuide }, svgClose())),
        h('ol', { class: 'g-steps' },
          h('li', null, h('b', { text: '1. ADC Matrix: ' }), 'Top recommended ADCs are highlighted in Spotlight Cards. Lower-ranked drugs recede into monochrome slate rows. Only the patient\'s active organs are graphed.'),
          h('li', null, h('b', { text: '2. Structure Studio: ' }), 'Combine Target Antigen, Linker, Payload, DAR, and Fc-Silencing (LALA-PG) to inspect chemical compatibility, GTEx tissue selectivity, and organ burden.'),
          h('li', null, h('b', { text: '3. Patient and Labs: ' }), 'Search conditions in English or Korean, inspect clinical biomarker flowsheets, and review AI condition-organ associations.')),
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
  const MODES = ['ADC Matrix', 'Structure Studio', 'Patient and Labs'];

  const PRESETS = [
    {
      id: 'her2-ild',
      title: 'HER2+ Breast / ILD and Heart Failure',
      desc: 'Pulmonary and cardiac vulnerability with elevated baseline bilirubin and creatinine',
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
      title: 'DLBCL / Hepatic Cirrhosis',
      desc: 'Hepatic impairment and pre-existing peripheral neuropathy requiring careful payload selection',
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
      title: 'TNBC / Stage 3 CKD and Cytopenia',
      desc: 'Renal clearance constraint and borderline cytopenias prior to systemic ADC initiation',
      conds: [
        { kind: 'mondo', value: 'MONDO:0005494', label: 'triple-negative breast carcinoma', mondo: 'MONDO:0005494' },
        { kind: 'reg', value: 'ckd_stage_3', label: 'Chronic kidney disease stage 3', mondo: 'MONDO:0005300' },
      ],
      raw: { creatinine: '1.8', hb: '9.4', anc: '1.3', age: '61', sex: 'F', weight: '58' },
      studio: { target: 'TROP2 (TACSTD2)', linker: 'Hydrolyzable CL2A', payload: 'SN-38 ( Topo I )', dar: 7.6, fc: false },
    },
    {
      id: 'myeloma-eye',
      title: 'Multiple Myeloma / Ocular Keratopathy',
      desc: 'Corneal epithelial vulnerability assessing ocular toxicity risk of auristatin/maytansinoid ADCs',
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
      { organ: 'pulmonary', name: 'Lung alveolar', tpm: 48 },
      { organ: 'cardiovascular', name: 'Cardiomyocyte', tpm: 36 },
      { organ: 'gastrointestinal', name: 'GI mucosa', tpm: 42 },
    ], popover: 'Receptor tyrosine kinase amplified in breast/gastric cancers. Normal expression in lung alveolar cells and cardiomyocytes.' },
    { id: 'TROP2 (TACSTD2)', gene: 'TACSTD2', refAdc: 'sacituzumab-govitecan', selectivity: 4.1, tissues: [
      { organ: 'gastrointestinal', name: 'Colonic epithelium', tpm: 68 },
      { organ: 'dermatologic', name: 'Stratified skin', tpm: 62 },
      { organ: 'pulmonary', name: 'Bronchial epithelium', tpm: 39 },
    ], popover: 'Transmembrane glycoprotein highly expressed across epithelial carcinomas; baseline normal expression in GI mucosa and skin keratinocytes.' },
    { id: 'Nectin-4', gene: 'NECTIN4', refAdc: 'enfortumab-vedotin', selectivity: 3.7, tissues: [
      { organ: 'dermatologic', name: 'Epidermal keratinocyte', tpm: 84 },
      { organ: 'metabolic_endocrine', name: 'Salivary / Sweat gland', tpm: 45 },
      { organ: 'ocular', name: 'Corneal epithelium', tpm: 34 },
    ], popover: 'Cell adhesion molecule enriched in urothelial carcinomas; high skin expression explains severe rash / SJS-TEN adverse events.' },
    { id: 'CD79b', gene: 'CD79B', refAdc: 'polatuzumab-vedotin', selectivity: 5.4, tissues: [
      { organ: 'haematologic', name: 'B-lineage lymphoid', tpm: 72 },
      { organ: 'infectious_immune', name: 'Spleen / Lymph node', tpm: 58 },
      { organ: 'hepatic', name: 'Hepatic sinusoid', tpm: 12 },
    ], popover: 'B-cell antigen receptor signaling component restricted to B-cells; exceptionally high tumor-to-normal selectivity outside lymphoid compartments.' },
    { id: 'BCMA (TNFRSF17)', gene: 'TNFRSF17', refAdc: 'belantamab-mafodotin', selectivity: 5.8, tissues: [
      { organ: 'haematologic', name: 'Plasma cell niche', tpm: 66 },
      { organ: 'ocular', name: 'Corneal macropinocytosis', tpm: 49 },
      { organ: 'renal', name: 'Renal tubular', tpm: 14 },
    ], popover: 'B-cell maturation antigen expressed on mature plasma cells; corneal toxicity occurs via off-target macropinocytosis rather than on-target binding.' },
    { id: 'FRalpha (FOLR1)', gene: 'FOLR1', refAdc: 'mirvetuximab-soravtansine', selectivity: 4.5, tissues: [
      { organ: 'ocular', name: 'Ocular epithelium', tpm: 54 },
      { organ: 'pulmonary', name: 'Type II pneumocyte', tpm: 44 },
      { organ: 'renal', name: 'Proximal kidney tubule', tpm: 51 },
    ], popover: 'Folate receptor alpha overexpressed in platinum-resistant ovarian cancer; polarized apical expression in kidney tubules and corneal epithelial cells.' },
  ];

  const STUDIO_LINKERS = [
    { id: 'Tetrapeptide GGFG', cleavable: true, stability: 88, handle: 'amine_hydroxyl', note: 'Cathepsin B/L-cleavable tetrapeptide; self-immolative aminomethylene releases hydroxy/amine payload', popover: 'Enzymatically cleaved in lysosomes by cathepsins. High plasma stability (88%) prevents premature extracellular payload shedding.' },
    { id: 'Val-Cit PABC', cleavable: true, stability: 76, handle: 'amine', note: 'Cathepsin B-cleavable dipeptide with para-aminobenzyl carbamate spacer for secondary/primary amines', popover: 'Validated dipeptide linker. Readily cleaved inside endosomes; moderate plasma carboxylesterase cleavage in rodents.' },
    { id: 'Hydrolyzable CL2A', cleavable: true, stability: 54, handle: 'hydroxyl', note: 'pH-sensitive carbonate linker; systemic and intratumoral hydrolysis releases SN-38', popover: 'Short PEGylated carbonate linker. pH-sensitive hydrolysis allows gradual release in acidic tumor microenvironments.' },
    { id: 'Non-cleavable mc', cleavable: false, stability: 96, handle: 'amine', note: 'Maleimidocaproyl thioether; requires complete lysosomal proteolysis to release Cys-mc-payload', popover: 'Ultra-stable thioether bond. Payload remains attached to cysteine; lacks membrane diffusion, preventing bystander toxicity.' },
    { id: 'Disulfide SPDB', cleavable: true, stability: 68, handle: 'thiol', note: 'Sterically hindered disulfide cleaved by intracellular glutathione for thiol maytansinoids', popover: 'Hindered disulfide linker cleaved selectively by high intracellular glutathione concentrations.' },
    { id: 'Acid Hydrazone', cleavable: true, stability: 48, handle: 'ketone', note: 'Acid-labile AcBut hydrazone hydrolyzed in endosomes/lysosomes (pH 4.5-5.0)', popover: 'Legacy acid-labile linker. Hydrolyzed in acidic lysosomes; higher spontaneous systemic release rate.' },
  ];

  const STUDIO_PAYLOADS = [
    { id: 'DXd ( Topo I )', cls: 'Topoisomerase I inhibitor', perm: true, handle: 'amine_hydroxyl', potency: 92, organs: { pulmonary: 82, haematologic: 68, gastrointestinal: 64, cardiovascular: 38 }, popover: 'Exatecan derivative with ~10x higher potency than SN-38. High membrane permeability drives potent bystander killing of neighboring antigen-negative tumor cells.' },
    { id: 'SN-38 ( Topo I )', cls: 'Topoisomerase I inhibitor (UGT1A1)', perm: true, handle: 'hydroxyl', potency: 78, organs: { haematologic: 86, gastrointestinal: 84, hepatic: 44 }, popover: 'Active metabolite of irinotecan. Hepatic clearance via UGT1A1 glucuronidation; neutropenia and severe diarrhea are primary toxicities.' },
    { id: 'MMAE ( Auristatin )', cls: 'Microtubule inhibitor (Auristatin)', perm: true, handle: 'amine', potency: 90, organs: { neurologic: 84, haematologic: 76, dermatologic: 66, hepatic: 52 }, popover: 'Synthetic dolastatin 10 antimitotic. Highly lipophilic and neutral at physiologic pH; strong bystander activity with dose-limiting peripheral neuropathy.' },
    { id: 'MMAF ( Auristatin )', cls: 'Charged Auristatin (low permeability)', perm: false, handle: 'amine', potency: 86, organs: { ocular: 92, haematologic: 64, renal: 28 }, popover: 'Carboxy-terminal phenylalanine confers negative charge, blocking passive membrane diffusion. Minimizes systemic bystander damage while accumulating in corneal epithelium.' },
    { id: 'DM4 / DM1 ( Maytansinoid )', cls: 'Microtubule inhibitor (Maytansinoid)', perm: true, handle: 'thiol', potency: 84, organs: { ocular: 74, hepatic: 72, neurologic: 62, haematologic: 58 }, popover: 'Thiol-containing tubulin inhibitor. Metabolized primarily via hepatic CYP3A4; associated with reversible transaminase elevations and thrombocytopenia.' },
    { id: 'SG3199 ( PBD Dimer )', cls: 'DNA minor-groove crosslinker', perm: true, handle: 'amine', potency: 98, organs: { haematologic: 92, hepatic: 78, pulmonary: 68, dermatologic: 62 }, popover: 'Ultra-potent DNA alkylator binding minor groove without distorting helix. Active against non-dividing cells; dose-limiting delayed myelosuppression and fluid retention.' },
  ];

  // ------------------------------------------------------------------ Session State
  const KEY = 'adctox.web.v070';
  function defaultState() {
    const p = PRESETS[0];
    return {
      mode: 0,
      presetId: p.id,
      conds: p.conds.map((c) => Object.assign({}, c)),
      raw: Object.assign({}, p.raw),
      labs: null,
      meanings: {},
      first: null,
      analysis: null,
      result: null,
      sel: 0,
      reviewAdc: null,
      drawer: false,
      drawerTab: 'Patient',
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

  function activeOrgansWithScores() {
    const map = new Map();
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
    for (const c of S.conds) {
      if (c.kind === 'reg' && REG[c.value]) {
        for (const o of REG[c.value].organs || []) {
          if (!map.has(o)) map.set(o, { organ: o, score: 0.88, condKey: c.value });
        }
      }
    }
    for (const fl of (S.labs && S.labs.flags) || []) {
      if (String(S.raw[fl.key] || '').trim()) {
        const prev = map.get(fl.organ);
        if (!prev) map.set(fl.organ, { organ: fl.organ, score: 0.82, condKey: null });
      }
    }
    return AX.filter((a) => map.has(a)).map((a) => map.get(a));
  }

  // ------------------------------------------------------------------ Page Shell & Navigation
  let top, crumbsOl, verEl, scenarioDropdown, layout, stageBox, bar, barKeys, drawer, drawerTitle, drawerBody;

  function frame() {
    document.title = 'ADCTOX';
    crumbsOl = h('ol');
    verEl = h('div', { class: 'ver', text: '' });
    scenarioDropdown = h('div', { class: 'scenario-dropdown' });

    const brandWrap = h('div', { class: 'brand-wrap' },
      h('div', { class: 'brand' },
        h('span', { class: 'brand-bars', 'aria-hidden': 'true' }, h('i'), h('i'), h('i')),
        'ADCToX'),
      verEl);

    top = h('header', { class: 'top' },
      brandWrap,
      h('nav', { class: 'crumbs', 'aria-label': 'Workspace modes' }, crumbsOl),
      h('div', { class: 'right' },
        scenarioDropdown,
        h('button', { type: 'button', class: 'help', 'aria-label': 'How it works', title: 'How it works', text: '?', onclick: openGuide })));

    stageBox = h('main', { class: 'stage' });
    layout = h('div', { class: 'layout' }, stageBox);
    barKeys = h('div', { class: 'keys', 'aria-hidden': 'true' });
    bar = h('footer', { class: 'bar' },
      h('span', { text: 'ADCTOX Clinical Decision and Conjugate Architecture Workspace' }),
      barKeys);

    drawerTitle = h('h2', { id: 'dr-title' });
    drawerBody = h('div', { class: 'dr-body' });
    const xBtn = h('button', { class: 'x-btn', type: 'button', 'aria-label': 'Close', onclick: () => closeDrawer() }, svgClose());
    drawer = h('div', { class: 'drawer', role: 'dialog', 'aria-modal': 'false', 'aria-labelledby': 'dr-title', 'aria-hidden': 'true' },
      h('div', { class: 'dr-head' }, drawerTitle, xBtn), drawerBody);

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

    clear(scenarioDropdown);
    const activePreset = PRESETS.find((p) => p.id === S.presetId) || PRESETS[0];
    const trigger = h('button', {
      type: 'button', class: 'scenario-btn', 'aria-haspopup': 'true', 'aria-expanded': 'false',
      title: 'Load quick clinical demo cases. You can freely edit or clear conditions anytime.',
      onclick: () => {
        const exp = menu.hidden;
        menu.hidden = !exp;
        trigger.setAttribute('aria-expanded', String(exp));
      },
    },
    h('span', { class: 'dim', text: 'Quick Demo:' }),
    h('strong', { class: 'scenario-current', text: S.presetId ? activePreset.title.split('/')[0].trim() : 'Custom Patient' }),
    sv('svg', { class: 'chevron', width: '10', height: '6', viewBox: '0 0 10 6', stroke: 'currentColor', 'stroke-width': '1.5', fill: 'none' },
      sv('path', { d: 'M1 1L5 5L9 1' })));

    const resetBtn = h('button', {
      type: 'button', class: 'reset-patient-btn', text: 'New Patient',
      title: 'Clear entered conditions and start custom patient input',
      onclick: () => resetPatient(),
    });

    const menu = h('div', { class: 'scenario-menu panel', hidden: true });
    PRESETS.forEach((p) => {
      const item = h('button', {
        type: 'button', class: 'scenario-item' + (p.id === S.presetId ? ' active' : ''),
        onclick: () => {
          menu.hidden = true;
          trigger.setAttribute('aria-expanded', 'false');
          applyPreset(p);
        },
      },
      h('span', { class: 'sc-title', text: p.title }),
      h('span', { class: 'sc-desc', text: p.desc }));
      menu.append(item);
    });

    document.addEventListener('click', (e) => {
      if (!scenarioDropdown.contains(e.target)) {
        menu.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
      }
    });

    scenarioDropdown.append(trigger, resetBtn, menu);
  }

  function resetPatient() {
    S.presetId = null;
    S.conds = [];
    S.raw = {};
    S.meanings = {};
    S.first = null;
    S.analysis = null;
    S.result = null;
    S.sel = 0;
    save();
    renderHeaderControls();
    refreshBackendData().then(() => renderActiveMode(true));
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

  // ------------------------------------------------------------------ Background Data Sync
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
    } catch (e) { /* background optional */ }
  }

  function resultSig() {
    return JSON.stringify([condList(), rawValues(), allChoice(), S.first]);
  }

  // ------------------------------------------------------------------ Unified Patient Context Bar
  function buildWorkspaceBar(onChanged) {
    const st = { q: '', items: [], cur: -1, timer: 0, seq: 0 };
    const input = h('input', {
      type: 'text', role: 'combobox', 'aria-expanded': 'false', 'aria-controls': 'wb-sugg',
      'aria-autocomplete': 'list', 'aria-label': 'Condition, symptom or cancer',
      placeholder: 'Condition, symptom or cancer', autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false',
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
          type: 'button', class: 'x-btn', 'aria-label': 'Remove ' + c.label,
          onclick: () => removeConditionChip(idx),
        }, svgClose());
        chipsWrap.append(h('span', { class: 'p-chip' + (isCancer ? ' cancer-chip' : '') },
          h('span', { text: c.label }), rm));
      });

      const L = S.labs || {};
      const sh = (L.derived && L.derived.shown) || {};
      const labBadges = [];
      if (S.raw.bilirubin) labBadges.push(`Bilirubin ${S.raw.bilirubin} mg/dL`);
      if (sh.crcl) labBadges.push(`CLcr ${sh.crcl} mL/min`);
      else if (S.raw.creatinine) labBadges.push(`Creatinine ${S.raw.creatinine} mg/dL`);
      if (S.raw.lvef) labBadges.push(`LVEF ${S.raw.lvef}%`);

      if (labBadges.length) {
        chipsWrap.append(h('button', {
          type: 'button', class: 'p-chip lab-chip', title: 'Open Patient and Labs flowsheet',
          text: labBadges.join('  /  '), onclick: () => switchMode(2),
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
          class: 'opt', role: 'option', 'aria-selected': i === st.cur ? 'true' : 'false',
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

    const activeOrgans = activeOrgansWithScores();
    const organsGrid = h('div', { class: 'active-organs-grid' });
    if (activeOrgans.length) {
      activeOrgans.forEach((item) => {
        const pct = Math.round(Math.max(15, Math.min(100, item.score * 100)));
        const isPrio = item.condKey && S.first === item.condKey;
        const btn = h('button', {
          type: 'button', class: 'organ-meter-btn' + (isPrio ? ' prio-active' : ''),
          title: item.condKey ? 'Prioritize ' + (SHORT[item.organ] || item.organ) + ' safety in ADC ranking' : (SHORT[item.organ] || item.organ),
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
      organsGrid.append(h('span', { class: 'dim', text: 'No vulnerable organs flagged' }));
    }

    return h('section', { class: 'workspace-bar', 'aria-label': 'Patient and active organ profile' },
      h('div', { class: 'wb-left' },
        h('div', { class: 'wb-search-row' },
          h('div', { class: 'wb-input-wrap' },
            h('span', { class: 'dim', 'aria-hidden': 'true', text: '+' }),
            input),
          sugg),
        chipsWrap),
      h('div', { class: 'wb-right' },
        h('div', { class: 'horizon-head' },
          h('span', { class: 'horizon-label', text: `Patient Active Organs (${activeOrgans.length})` }),
          h('span', { class: 'horizon-sub', text: S.first ? 'Priority Active' : 'Select organ to prioritize' })),
        organsGrid));
  }

  // ------------------------------------------------------------------ Helpers for Drug Cards & Rows
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
    if (p && p.rows) return p.rows.slice(0, 3).map(([, v]) => v.split(',')[0]);
    return [];
  }

  function statusInfo(row) {
    const detail = row.detail || {};
    const reason = (detail.reasons || []).find((r) => r.status === row.status && !!r.sure === !!row.sure) || (detail.reasons || []).find((r) => r.status === row.status);
    if (row.status === 'None' || row.status === 'No change') return { tone: 'clear', bars: 'clear', label: 'Standard', full: 'Standard dosing' };
    if (reason && reason.code === 'contraindicated') return { tone: 'avoid', bars: 'avoid', label: 'Contraindicated', full: 'Contraindicated' };
    if (row.status === 'Avoid') return { tone: 'avoid', bars: 'avoid', label: row.sure ? 'Avoid' : 'Avoid (check)', full: 'Avoid use' };
    if (row.status === 'Lower dose' || (reason && reason.code === 'reduce_dose')) return { tone: 'monitor', bars: 'monitor', label: 'Dose adjust', full: 'Dose adjustment' };
    if (row.status === 'Monitor') return { tone: 'monitor', bars: 'monitor', label: 'Monitor', full: 'Close monitoring' };
    return { tone: 'limited', bars: 'limited', label: 'Limited data', full: 'Not studied in cohort' };
  }

  function organStatusForRow(row, organ) {
    const detail = row.detail || {};
    const allWarnings = [].concat(detail.warnings || [], detail.other_warnings || []);
    const found = allWarnings.find((w) => w.organ === organ);
    if (!found) return { cls: 'clear', tag: 'Clear', title: 'No label warning on ' + (SHORT[organ] || organ) };
    if (String(found.mark).trim() === '!!') return { cls: 'boxed', tag: 'Boxed', title: 'Boxed Warning: ' + found.text };
    return { cls: 'warn', tag: 'Warn', title: 'Section 5 Warning: ' + found.text };
  }

  function primaryTrialEvent(row, activeOrgans) {
    const t = row.detail && row.detail.trial;
    if (!t || !t.trial || t.no_results || !Array.isArray(t.organs)) return null;
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
    if (!trialHit) return h('span', { class: 'dim', style: 'font-size:11px', text: 'Single-arm trial' });
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

  // ------------------------------------------------------------------ Mode 0: Visual ADC Matrix
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

      const topCandidates = rows.filter((r) => (hasCancer ? r.indicated === true : true) && r.status !== 'Avoid');
      const spotlightRows = (topCandidates.length ? topCandidates : rows).slice(0, 2);
      const spotlightSet = new Set(spotlightRows.map((r) => r.adc));

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
          class: 'spotlight-card', tabindex: '0',
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
          h('span', { class: 'sec-kicker', text: 'Primary Recommendation' }),
          h('span', { class: 'dim', style: 'font-size:11.5px', text: 'Click card for 3D architecture and FDA trial evidence' })),
        spGrid));

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
        h('button', { type: 'button', class: 'export-button', text: 'Export Summary', onclick: () => saveReview(res) }));
      content.append(toolbar);

      const grid = h('div', { class: 'review-grid', role: 'grid', 'aria-label': 'ADC Cohort Matrix' },
        h('div', { class: 'review-grid-head', role: 'row' },
          h('span', { role: 'columnheader', text: '#' }),
          h('span', { role: 'columnheader', text: 'ADC and Architecture' }),
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
          role: 'row', tabindex: i === S.sel ? '0' : '-1',
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

  // ------------------------------------------------------------------ Mode 1: Structure & Combination Studio (with Pareto Scan Simulation)
  let simAnimId = 0;
  function buildStructureStudioMode() {
    const box = h('div', { class: 's-studio' });
    box.append(buildWorkspaceBar(() => renderStudioCanvas()));
    const wrap = h('div', { class: 'studio-wrap' });
    const controls = h('aside', { class: 'studio-controls panel', 'aria-label': 'Conjugate Architecture Controls' });
    const canvas = h('div', { class: 'studio-canvas' });
    wrap.append(controls, canvas);
    box.append(wrap);

    let isOptimizing = false;
    let autoRationale = null;

    function computeStudioSimulation(specInput) {
      const spec = specInput || S.studio;
      const tgt = STUDIO_TARGETS.find((x) => x.id === spec.target) || STUDIO_TARGETS[0];
      const lnk = STUDIO_LINKERS.find((x) => x.id === spec.linker) || STUDIO_LINKERS[0];
      const pld = STUDIO_PAYLOADS.find((x) => x.id === spec.payload) || STUDIO_PAYLOADS[0];
      const dar = Number(spec.dar) || 4;
      const fcSilenced = Boolean(spec.fc);

      const activeOrgs = activeOrgansWithScores();
      const isCompat = lnk.handle === pld.handle || lnk.handle.includes(pld.handle) || pld.handle.includes(lnk.handle);
      const aggPenalty = dar > 4 ? (dar - 4) * 3.5 : 0;

      let totalOrganTox = 0;
      activeOrgs.forEach((ao) => {
        const basePld = pld.organs[ao.organ] || 35;
        const onTarget = (tgt.tissues.find((t) => t.organ === ao.organ) || { tpm: 15 }).tpm * 0.4;
        const darFactor = 0.75 + (dar / 8) * 0.45;
        const fcFactor = fcSilenced && ['pulmonary', 'haematologic', 'ocular', 'hepatic'].includes(ao.organ) ? 0.78 : 1.0;
        totalOrganTox += (basePld * 0.6 + onTarget) * darFactor * fcFactor * (ao.score || 0.8);
      });
      const meanTox = activeOrgs.length ? totalOrganTox / activeOrgs.length : 38;
      const safetyScore = Math.max(10, Math.min(96, Math.round(100 - meanTox * 0.85 + (lnk.stability - 70) * 0.35 + (fcSilenced ? 6 : 0) - aggPenalty * 0.5)));

      const bystander = lnk.cleavable && pld.perm;
      const efficacyScore = Math.max(15, Math.min(98, Math.round(
        tgt.selectivity * 9.8 +
        pld.potency * 0.35 +
        (dar >= 4 ? 14 : dar * 3) +
        (bystander ? 7 : 0) +
        (isCompat ? 4 : -8)
      )));

      return { spec, tgt, lnk, pld, dar, fcSilenced, safetyScore, efficacyScore, isCompat, meanTox, bystander };
    }

    function evaluateAllStudioCandidates() {
      const cands = [];
      const dars = [2, 3.5, 4, 6, 7.6, 8];
      const fcs = [false, true];
      STUDIO_TARGETS.forEach((t) => {
        STUDIO_LINKERS.forEach((l) => {
          STUDIO_PAYLOADS.forEach((p) => {
            dars.forEach((d) => {
              fcs.forEach((fc) => {
                cands.push(computeStudioSimulation({ target: t.id, linker: l.id, payload: p.id, dar: d, fc }));
              });
            });
          });
        });
      });

      const pareto = [];
      cands.forEach((c) => {
        const dominated = cands.some((o) =>
          o.safetyScore >= c.safetyScore && o.efficacyScore >= c.efficacyScore &&
          (o.safetyScore > c.safetyScore || o.efficacyScore > c.efficacyScore)
        );
        if (!dominated) {
          if (!pareto.some((p) => p.safetyScore === c.safetyScore && p.efficacyScore === c.efficacyScore)) {
            pareto.push(c);
          }
        }
      });
      pareto.sort((a, b) => a.safetyScore - b.safetyScore || a.efficacyScore - b.efficacyScore);

      let best = pareto[0] || cands[0];
      let maxUtil = -1;
      pareto.forEach((p) => {
        const util = p.safetyScore * 0.55 + p.efficacyScore * 0.45;
        if (util > maxUtil) { maxUtil = util; best = p; }
      });

      return { cands, pareto, best };
    }

    function buildAutoOptimizeRationales(bestSim) {
      const s = bestSim.spec;
      const activeOrgs = activeOrgansWithScores().map((o) => SHORT[o.organ] || o.organ);
      return [
        ['1. Target Antigen', s.target, `Matched to oncology diagnosis with tumor selectivity margin (+${bestSim.tgt.selectivity} log2FC).`],
        ['2. Chemical Linker', s.linker, `High plasma stability (${bestSim.lnk.stability}%) prevents premature payload shed on ${activeOrgs.join(', ') || 'vulnerable organs'}.`],
        ['3. Cytotoxic Payload', s.payload, `Compatible with linker handle while avoiding dose-limiting toxicity bottlenecks on active organs.`],
        ['4. DAR & Fc Engineering', `DAR ${s.dar} + ${s.fc ? 'Fc-Silenced (LALA-PG)' : 'Wild-type IgG1'}`, `Balances antitumor efficacy (${bestSim.efficacyScore}/100) with active organ safety (${bestSim.safetyScore}/100).`],
      ];
    }

    function renderControls() {
      clear(controls);
      const headAction = h('div', { class: 'studio-head-action' },
        h('span', { class: 'sec-kicker', text: 'Conjugate Architecture' }),
        h('button', {
          type: 'button', class: 'btn-optimize', text: isOptimizing ? 'Scanning...' : 'Auto Optimize',
          onclick: () => runOptimizationSimulation(),
        }));
      controls.append(headAction);

      const makeGroup = (label, items, current, onPick, isGrid6) => {
        const pills = h('div', { class: 'studio-pills' + (isGrid6 ? ' grid-6' : '') });
        items.forEach((it) => {
          const val = typeof it === 'string' ? it : it.id;
          const popoverText = typeof it === 'object' && it.popover ? it.popover : null;
          const b = h('button', {
            type: 'button', class: 'st-pill', 'aria-pressed': val === current ? 'true' : 'false',
            text: val,
            onmouseenter: (e) => {
              if (popoverText) showMicroPopover(b, popoverText);
            },
            onmouseleave: () => hideMicroPopover(),
            onclick: () => {
              onPick(val); save(); renderControls(); renderStudioCanvas();
            },
          });
          pills.append(b);
        });
        return h('div', { class: 'studio-group' }, h('span', { class: 'studio-label', text: label }), pills);
      };

      controls.append(
        makeGroup('1. Target Antigen (mAb)', STUDIO_TARGETS, S.studio.target, (v) => { S.studio.target = v; autoRationale = null; }),
        makeGroup('2. Chemical Linker', STUDIO_LINKERS, S.studio.linker, (v) => { S.studio.linker = v; autoRationale = null; }),
        makeGroup('3. Cytotoxic Payload', STUDIO_PAYLOADS, S.studio.payload, (v) => { S.studio.payload = v; autoRationale = null; }),
        makeGroup('4. Drug-to-Antibody Ratio (DAR)', ['2', '3.5', '4', '6', '7.6', '8'], String(S.studio.dar), (v) => { S.studio.dar = parseFloat(v); autoRationale = null; }, true),
        makeGroup('5. Fc Engineering', ['Wild-type IgG1', 'Fc-Silenced (LALA-PG)'], S.studio.fc ? 'Fc-Silenced (LALA-PG)' : 'Wild-type IgG1', (v) => { S.studio.fc = v.includes('LALA'); autoRationale = null; })
      );
    }

    let popoverEl = null;
    function showMicroPopover(targetBtn, text) {
      hideMicroPopover();
      popoverEl = h('div', { class: 'micro-popover', text });
      targetBtn.append(popoverEl);
    }
    function hideMicroPopover() {
      if (popoverEl) { popoverEl.remove(); popoverEl = null; }
    }

    function runOptimizationSimulation() {
      if (isOptimizing) return;
      isOptimizing = true;
      renderControls();
      renderStudioCanvas(true);
    }

    function renderStudioCanvas(animateScan) {
      clear(canvas);
      const sim = computeStudioSimulation();
      const evalSpace = evaluateAllStudioCandidates();
      const tgt = sim.tgt;
      const lnk = sim.lnk;
      const pld = sim.pld;
      const dar = sim.dar;
      const fcSilenced = sim.fcSilenced;
      const handleMatch = sim.isCompat;
      const bystander = sim.bystander;
      const stabilityScore = Math.max(25, Math.min(98, Math.round(lnk.stability - (dar > 4 ? (dar - 4) * 2.5 : 0))));

      // 1. Pareto Frontier Architecture Simulator Canvas
      const simWrap = h('section', { class: 'sim-canvas-panel panel' });
      const simHead = h('div', { class: 'sim-canvas-head' },
        h('span', { class: 'sim-canvas-title', text: 'Multi-Objective Pareto Frontier (Patient Organ Safety vs. Antitumor Efficacy)' }),
        h('span', { class: 'sim-canvas-status', text: animateScan ? 'Scanning candidate space...' : `Safety ${sim.safetyScore} / Efficacy ${sim.efficacyScore}` }));

      const chartWrap = h('div', { class: 'sim-chart-wrap' });
      const cvs = h('canvas', { class: 'sim-canvas' });
      chartWrap.append(cvs);
      simWrap.append(simHead, chartWrap);

      // AI De Novo Design Rationale Box
      const activeRationale = autoRationale || buildAutoOptimizeRationales(evalSpace.best);
      const isOptimal = (
        S.studio.target === evalSpace.best.spec.target &&
        S.studio.linker === evalSpace.best.spec.linker &&
        S.studio.payload === evalSpace.best.spec.payload &&
        Number(S.studio.dar) === Number(evalSpace.best.spec.dar) &&
        Boolean(S.studio.fc) === Boolean(evalSpace.best.spec.fc)
      );

      const rBox = h('div', { class: 'sim-rationale-box' },
        h('div', { class: 'srb-title' },
          h('span', { text: isOptimal ? 'AI De Novo Optimal ADC Architecture Locked' : `AI Recommended Optimum: ${evalSpace.best.spec.target} + ${evalSpace.best.spec.linker} (DAR ${evalSpace.best.spec.dar})` }),
          h('span', { style: 'font-size:10.5px;color:var(--dim);font-weight:600', text: isOptimal ? 'Pareto Frontier Peak' : 'Click Auto Optimize to scan and apply' })),
        h('div', { class: 'srb-steps' },
          activeRationale.map(([title, choice, desc]) => h('div', { class: 'srb-step' },
            h('b', { text: `${title}: ${choice}` }),
            h('span', { text: desc })))));
      simWrap.append(rBox);

      // 2. Metrics Strip with 1-line explanations
      const hero = h('div', { class: 'studio-hero panel' },
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: 'Conjugation Compatibility' }),
          h('span', { class: 'sh-val ' + (handleMatch ? 't-green' : 't-amber'), text: handleMatch ? 'Direct Coupling' : 'Linker Spacer Needed' }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${handleMatch ? 100 : 50}%;background:${handleMatch ? 'var(--emerald)' : 'var(--amber)'}` })),
          h('span', { class: 'sh-desc', text: 'Linker reactive handle pairing with payload functional group.' })),
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: 'Tumor / Normal Selectivity' }),
          h('span', { class: 'sh-val', text: `+${tgt.selectivity.toFixed(1)} log2FC` }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${Math.min(100, tgt.selectivity * 16)}%;background:var(--accent)` })),
          h('span', { class: 'sh-desc', text: 'Fold-change in target expression on tumor vs. healthy normal organs.' })),
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: 'Bystander Killing Effect' }),
          h('span', { class: 'sh-val', text: bystander ? 'Active Diffusion' : 'Cell-Autonomous' }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${bystander ? 92 : 30}%;background:${bystander ? 'var(--accent)' : 'var(--dim)'}` })),
          h('span', { class: 'sh-desc', text: 'Payload membrane permeability to kill adjacent antigen-negative tumor cells.' })),
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: 'Plasma Linker Stability' }),
          h('span', { class: 'sh-val', text: `${stabilityScore}% Intact` }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${stabilityScore}%;background:var(--emerald)` })),
          h('span', { class: 'sh-desc', text: 'Resistance to premature systemic payload deconjugation in circulation.' })));

      // 3. Organ & Tissue Expression Grid
      const activeOrgans = activeOrgansWithScores();
      const organsToShow = activeOrgans.length ? activeOrgans : [
        { organ: 'pulmonary', score: 0.85 }, { organ: 'hepatic', score: 0.78 },
        { organ: 'haematologic', score: 0.72 }, { organ: 'cardiovascular', score: 0.65 },
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

      const gtexRows = h('div', { class: 'expr-list' });
      tgt.tissues.forEach((t) => {
        gtexRows.append(h('div', { class: 'expr-row' },
          h('span', { class: 'ex-name', text: SHORT[t.organ] || t.organ }),
          h('span', { class: 'ex-track' }, h('i', { class: 'ex-fill', style: `width:${t.tpm}%;background:var(--accent)` })),
          h('span', { class: 'ex-val', text: `${t.tpm} nTPM` })));
      });

      const grid2 = h('div', { class: 'studio-grid-2' },
        h('section', { class: 'studio-card panel' },
          h('h3', { text: 'Simulated Patient Organ Toxicity Index' }),
          organRows,
          h('p', { class: 'dim', style: 'margin:12px 0 0;font-size:11.5px', text: fcSilenced ? 'LALA-PG Fc-silencing active: FcgammaR macrophage uptake attenuated.' : 'Wild-type IgG1: standard immune effector and macrophage uptake.' })),
        h('section', { class: 'studio-card panel' },
          h('h3', { text: `GTEx Normal Tissue Profile (${tgt.gene})` }),
          gtexRows,
          h('p', { class: 'dim', style: 'margin:12px 0 0;font-size:11.5px', text: lnk.note })));

      canvas.append(simWrap, hero, grid2);

      setTimeout(() => initParetoCanvas(cvs, sim, evalSpace, animateScan, () => {
        if (animateScan) {
          isOptimizing = false;
          const best = evalSpace.best;
          S.studio.target = best.spec.target;
          S.studio.linker = best.spec.linker;
          S.studio.payload = best.spec.payload;
          S.studio.dar = best.spec.dar;
          S.studio.fc = best.spec.fc;
          autoRationale = buildAutoOptimizeRationales(best);
          save();
          renderControls();
          renderStudioCanvas(false);
        }
      }), 0);
    }

    function initParetoCanvas(cvs, currentSim, evalSpace, animate, onComplete) {
      const rect = cvs.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const w = cvs.width = (rect.width || 600) * dpr;
      const h = cvs.height = (rect.height || 220) * dpr;
      const ctx = cvs.getContext('2d');
      if (!ctx) return;

      cancelAnimationFrame(simAnimId);
      const padL = 48 * dpr, padR = 24 * dpr, padT = 24 * dpr, padB = 36 * dpr;
      const plotW = w - padL - padR;
      const plotH = h - padT - padB;

      const toX = (val) => padL + (Math.max(0, Math.min(100, val)) / 100) * plotW;
      const toY = (val) => padT + (1 - Math.max(0, Math.min(100, val)) / 100) * plotH;

      const cands = evalSpace.cands;
      const pareto = evalSpace.pareto;
      const best = evalSpace.best;

      let startTime = performance.now();
      const duration = animate ? 1300 : 0;

      function renderFrame(now) {
        const elapsed = now - startTime;
        const progress = duration > 0 ? Math.min(1, elapsed / duration) : 1;
        ctx.clearRect(0, 0, w, h);

        // Numeric Grid lines & ticks
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.07)';
        ctx.lineWidth = 1 * dpr;
        ctx.font = `${9 * dpr}px monospace`;
        ctx.fillStyle = '#64748B';

        [0, 20, 40, 60, 80, 100].forEach((v) => {
          const gx = toX(v);
          const gy = toY(v);
          ctx.beginPath(); ctx.moveTo(gx, padT); ctx.lineTo(gx, padT + plotH); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(padL + plotW, gy); ctx.stroke();

          ctx.textAlign = 'center';
          ctx.fillText(String(v), gx, padT + plotH + 14 * dpr);
          ctx.textAlign = 'right';
          ctx.fillText(String(v), padL - 6 * dpr, gy + 3 * dpr);
        });

        // Axis Titles
        ctx.font = `600 ${9.5 * dpr}px sans-serif`;
        ctx.fillStyle = '#94A3B8';
        ctx.textAlign = 'center';
        ctx.fillText('Patient Organ Safety Score (0 - 100) ->', padL + plotW / 2, h - 6 * dpr);

        ctx.save();
        ctx.translate(12 * dpr, padT + plotH / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('Efficacy & Selectivity (0 - 100) ->', 0, 0);
        ctx.restore();

        // Legend at top
        ctx.textAlign = 'left';
        ctx.fillStyle = '#64748B';
        ctx.beginPath(); ctx.arc(padL + 4 * dpr, 12 * dpr, 3 * dpr, 0, Math.PI * 2); ctx.fill();
        ctx.fillText(`Candidate Space (${cands.length})`, padL + 10 * dpr, 15 * dpr);

        ctx.strokeStyle = '#0D9488';
        ctx.lineWidth = 2 * dpr;
        ctx.beginPath(); ctx.moveTo(padL + 120 * dpr, 12 * dpr); ctx.lineTo(padL + 135 * dpr, 12 * dpr); ctx.stroke();
        ctx.fillStyle = '#0D9488';
        ctx.fillText('Pareto Frontier', padL + 140 * dpr, 15 * dpr);

        ctx.fillStyle = '#2563EB';
        ctx.beginPath(); ctx.arc(padL + 225 * dpr, 12 * dpr, 4 * dpr, 0, Math.PI * 2); ctx.fill();
        ctx.fillText('Current Selection', padL + 233 * dpr, 15 * dpr);

        // Scanning wavefront cutoff X
        const cutoffSafety = progress * 102;
        const scanX = toX(Math.min(100, cutoffSafety));

        // Draw evaluated candidate dots up to cutoff
        cands.forEach((c) => {
          if (c.safetyScore > cutoffSafety) return;
          const cx = toX(c.safetyScore);
          const cy = toY(c.efficacyScore);
          ctx.fillStyle = c.isCompat ? 'rgba(148, 163, 184, 0.35)' : 'rgba(239, 68, 68, 0.22)';
          ctx.beginPath(); ctx.arc(cx, cy, 2.4 * dpr, 0, Math.PI * 2); ctx.fill();
        });

        // Draw progressive Pareto curve
        const visPareto = pareto.filter((p) => p.safetyScore <= cutoffSafety);
        if (visPareto.length >= 1) {
          ctx.beginPath();
          visPareto.forEach((p, idx) => {
            const px = toX(p.safetyScore);
            const py = toY(p.efficacyScore);
            if (idx === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          });
          ctx.strokeStyle = '#0D9488';
          ctx.lineWidth = 2.4 * dpr;
          ctx.stroke();

          visPareto.forEach((p) => {
            const px = toX(p.safetyScore);
            const py = toY(p.efficacyScore);
            ctx.fillStyle = '#FFFFFF';
            ctx.strokeStyle = '#0D9488';
            ctx.lineWidth = 1.6 * dpr;
            ctx.beginPath(); ctx.arc(px, py, 3.2 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
          });
        }

        // Scanning wavefront beam
        if (animate && progress < 0.99) {
          const grad = ctx.createLinearGradient(scanX - 24 * dpr, 0, scanX + 2 * dpr, 0);
          grad.addColorStop(0, 'rgba(13, 148, 136, 0)');
          grad.addColorStop(1, 'rgba(13, 148, 136, 0.3)');
          ctx.fillStyle = grad;
          ctx.fillRect(Math.max(padL, scanX - 24 * dpr), padT, 26 * dpr, plotH);

          ctx.strokeStyle = '#0D9488';
          ctx.lineWidth = 1.8 * dpr;
          ctx.beginPath(); ctx.moveTo(scanX, padT); ctx.lineTo(scanX, padT + plotH); ctx.stroke();
        }

        // Highlight optimal best candidate once reached
        if (cutoffSafety >= best.safetyScore) {
          const bx = toX(best.safetyScore);
          const by = toY(best.efficacyScore);
          ctx.fillStyle = 'rgba(13, 148, 136, 0.25)';
          ctx.beginPath(); ctx.arc(bx, by, 10 * dpr, 0, Math.PI * 2); ctx.fill();

          ctx.fillStyle = '#0D9488';
          ctx.strokeStyle = '#FFFFFF';
          ctx.lineWidth = 1.8 * dpr;
          ctx.beginPath(); ctx.arc(bx, by, 5 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();

          ctx.font = `bold ${9 * dpr}px sans-serif`;
          ctx.fillStyle = '#34D399';
          ctx.textAlign = bx > w - 140 * dpr ? 'right' : 'left';
          ctx.fillText(`Optimal: ${best.spec.target.split(' ')[0]} + ${best.spec.payload.split(' ')[0]} (DAR ${best.spec.dar})`, bx + (bx > w - 140 * dpr ? -8 * dpr : 8 * dpr), by - 6 * dpr);
        }

        // Current active selection diamond
        const curSim = animate && progress >= 0.98 ? best : currentSim;
        const sx = toX(curSim.safetyScore);
        const sy = toY(curSim.efficacyScore);
        ctx.fillStyle = '#2563EB';
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 1.8 * dpr;
        ctx.beginPath(); ctx.arc(sx, sy, 5 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();

        if (progress < 1) {
          simAnimId = requestAnimationFrame(renderFrame);
        } else if (onComplete) {
          onComplete();
        }
      }

      if (duration > 0) {
        simAnimId = requestAnimationFrame(renderFrame);
      } else {
        renderFrame(performance.now());
      }
    }

    renderControls();
    renderStudioCanvas();
    clear(barKeys);
    add(barKeys, [kbd('1-3', 'Switch Mode')]);
    return box;
  }

  // ------------------------------------------------------------------ Mode 2: Patient & Labs (Biomarker Flowsheet)
  function buildPatientLabsMode() {
    const box = h('div', { class: 's2' });
    box.append(buildWorkspaceBar(() => {
      refreshBackendData().then(() => renderFlowsheet());
    }));
    const content = h('div');
    box.append(content);

    const BIO_FIELDS = [
      { key: 'bilirubin', name: 'Total Bilirubin', unit: 'mg/dL', refLow: 0.2, refHigh: 1.2, organ: 'hepatic', defaultVal: '1.2' },
      { key: 'creatinine', name: 'Serum Creatinine', unit: 'mg/dL', refLow: 0.6, refHigh: 1.2, organ: 'renal', defaultVal: '1.0' },
      { key: 'ast', name: 'Aspartate Aminotransferase (AST)', unit: 'U/L', refLow: 10, refHigh: 40, organ: 'hepatic', defaultVal: '28' },
      { key: 'alt', name: 'Alanine Aminotransferase (ALT)', unit: 'U/L', refLow: 7, refHigh: 56, organ: 'hepatic', defaultVal: '32' },
      { key: 'platelets', name: 'Platelet Count', unit: 'x10³/µL', refLow: 150, refHigh: 450, organ: 'haematologic', defaultVal: '220' },
      { key: 'anc', name: 'Absolute Neutrophil Count (ANC)', unit: 'x10³/µL', refLow: 1.5, refHigh: 8.0, organ: 'haematologic', defaultVal: '3.5' },
      { key: 'hb', name: 'Hemoglobin (Hb)', unit: 'g/dL', refLow: 12.0, refHigh: 17.5, organ: 'haematologic', defaultVal: '13.8' },
      { key: 'lvef', name: 'Left Ventricular Ejection Fraction (LVEF)', unit: '%', refLow: 50, refHigh: 75, organ: 'cardiovascular', defaultVal: '60' },
    ];

    function renderFlowsheet() {
      clear(content);
      const wrap = h('div', { class: 'flowsheet-wrap' });
      const leftPanel = h('div', { class: 'flowsheet-panel panel' });
      const rightPanel = h('div', { class: 'organ-linkage-panel panel' });
      wrap.append(leftPanel, rightPanel);
      content.append(wrap);

      leftPanel.append(
        h('div', { class: 'flowsheet-head' },
          h('h2', { class: 'flowsheet-title', text: 'Clinical Biomarker Flowsheet' }),
          h('span', { class: 'flowsheet-sub', text: 'Values mapped against institutional reference intervals' })));

      const groupEl = h('div', { class: 'lab-card-group' });
      BIO_FIELDS.forEach((bf) => {
        const valStr = S.raw[bf.key];
        const valNum = parseFloat(valStr);
        const hasVal = !isNaN(valNum);

        let statusClass = 'empty';
        let statusText = 'Not entered';
        let needlePos = 50;

        if (hasVal) {
          const span = (bf.refHigh - bf.refLow) * 2.2;
          const minRange = Math.max(0, bf.refLow - span * 0.25);
          const maxRange = bf.refHigh + span * 0.75;
          needlePos = Math.max(3, Math.min(97, ((valNum - minRange) / (maxRange - minRange)) * 100));

          if (valNum > bf.refHigh * 1.5 || valNum < bf.refLow * 0.7) {
            statusClass = 'alarm'; statusText = 'Elevated';
          } else if (valNum > bf.refHigh || valNum < bf.refLow) {
            statusClass = 'warn'; statusText = 'Borderline';
          } else {
            statusClass = 'normal'; statusText = 'Normal';
          }
        }

        const input = h('input', {
          type: 'text', inputmode: 'decimal', placeholder: '—', value: valStr || '',
          class: statusClass !== 'normal' && statusClass !== 'empty' ? 'flagged' : '',
          oninput: (e) => {
            S.raw[bf.key] = e.target.value;
            S.presetId = null;
            save();
          },
          onblur: async () => {
            await refreshBackendData();
            renderFlowsheet();
          },
        });

        const normalLeft = 25;
        const normalWidth = 50;

        const row = h('div', { class: 'bio-row' },
          h('div', { class: 'bio-info' },
            h('span', { class: 'bio-name', text: bf.name }),
            h('span', { class: 'bio-ref', text: `Ref: ${bf.refLow} – ${bf.refHigh} ${bf.unit}` })),
          h('div', { class: 'bio-input-wrap' }, input),
          h('div', { class: 'bio-spectrum-wrap' },
            h('div', { class: 'bio-spectrum-track' },
              h('i', { class: 'bio-spectrum-normal', style: `left:${normalLeft}%;width:${normalWidth}%` }),
              hasVal ? h('i', { class: `bio-spectrum-needle ${statusClass}`, style: `left:${needlePos}%` }) : null)),
          h('span', { class: `bio-status-badge ${statusClass}`, text: statusText }));

        groupEl.append(row);
      });

      leftPanel.append(groupEl);

      // Right Linkage Panel
      rightPanel.append(h('h3', { class: 'linkage-title', text: 'AI Organ Vulnerability Linkage' }));
      const activeOrgans = activeOrgansWithScores();
      const linkageList = h('div', { class: 'linkage-list' });

      if (activeOrgans.length) {
        activeOrgans.forEach((ao) => {
          linkageList.append(h('div', { class: 'linkage-card' },
            h('div', { class: 'linkage-head' },
              h('span', { class: 'linkage-organ', text: SHORT[ao.organ] || ao.organ }),
              h('span', { class: 'linkage-source', text: `${Math.round(ao.score * 100)}% Risk Weight` })),
            h('span', { class: 'linkage-why', text: ao.condKey ? `Triggered by clinical diagnosis: ${condName(ao.condKey)}` : 'Triggered by laboratory biomarker elevation' })));
        });
      } else {
        linkageList.append(h('span', { class: 'dim', text: 'No active organ toxicity triggers detected.' }));
      }
      rightPanel.append(linkageList);
    }

    renderFlowsheet();
    return box;
  }

  // ------------------------------------------------------------------ 3D ADC Molecular Canvas Renderer
  let adcAnimId = 0;
  function init3dAdcCanvas(cvs, adcRow) {
    const rect = cvs.getBoundingClientRect();
    const w = cvs.width = (rect.width || 400) * (window.devicePixelRatio || 1);
    const h = cvs.height = (rect.height || 240) * (window.devicePixelRatio || 1);
    const ctx = cvs.getContext('2d');
    if (!ctx) return;

    cancelAnimationFrame(adcAnimId);
    const dpr = window.devicePixelRatio || 1;
    let rotY = 0.4;
    let rotX = 0.2;
    let isDragging = false;
    let lastMouseX = 0, lastMouseY = 0;

    cvs.onmousedown = (e) => { isDragging = true; lastMouseX = e.clientX; lastMouseY = e.clientY; };
    window.addEventListener('mouseup', () => { isDragging = false; });
    window.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const dx = e.clientX - lastMouseX;
      const dy = e.clientY - lastMouseY;
      lastMouseX = e.clientX; lastMouseY = e.clientY;
      rotY += dx * 0.01;
      rotX += dy * 0.01;
    });

    const m = (adcRow && MECH[adcRow.adc]) || {};
    const darCount = Math.round(parseFloat(m.dar || 4)) || 4;

    // Molecular nodes: Y-shaped IgG1 antibody + Linker/Payload spheres with fixed IDs
    const nodes = [
      // Fc stem (bottom center)
      { id: 'fc2', x: 0, y: 35, z: 0, r: 8, col: '#475569', type: 'Fc' },
      { id: 'fc1', x: 0, y: 15, z: 0, r: 7, col: '#475569', type: 'Fc' },
      // Hinge region
      { id: 'hinge', x: 0, y: -5, z: 0, r: 6, col: '#2563EB', type: 'Hinge' },
      // Fab Arm Left
      { id: 'fab_l1', x: -25, y: -25, z: 5, r: 7, col: '#334155', type: 'Fab' },
      { id: 'fab_l2', x: -45, y: -45, z: 10, r: 8, col: '#334155', type: 'Fab' },
      // Fab Arm Right
      { id: 'fab_r1', x: 25, y: -25, z: -5, r: 7, col: '#334155', type: 'Fab' },
      { id: 'fab_r2', x: 45, y: -45, z: -10, r: 8, col: '#334155', type: 'Fab' },
    ];

    // Explicit Linker-tethered payload branches
    const conjAnchors = ['hinge', 'fab_l1', 'fab_r1', 'hinge', 'fab_l2', 'fab_r2', 'fab_l1', 'fab_r1'];
    for (let k = 0; k < darCount; k++) {
      const angle = (k / darCount) * Math.PI * 2;
      const radius = 34 + (k % 2) * 10;
      const py = -10 + (k % 3) * 14;
      const anchor = conjAnchors[k % conjAnchors.length];
      nodes.push({
        id: 'pld_' + k,
        anchor,
        x: Math.cos(angle) * radius,
        y: py,
        z: Math.sin(angle) * radius,
        r: 5.5,
        col: '#0D9488',
        glow: true,
        type: 'Payload',
      });
    }

    function project(p, ry, rx) {
      // Rotate Y
      const cosY = Math.cos(ry), sinY = Math.sin(ry);
      const x1 = p.x * cosY + p.z * sinY;
      const z1 = -p.x * sinY + p.z * cosY;
      // Rotate X
      const cosX = Math.cos(rx), sinX = Math.sin(rx);
      const y2 = p.y * cosX - z1 * sinX;
      const z2 = p.y * sinX + z1 * cosX;
      // Perspective
      const fov = 260;
      const scale = fov / (fov + z2 + 80);
      return {
        id: p.id,
        anchor: p.anchor,
        x: w / 2 + x1 * scale * 1.8 * dpr,
        y: h / 2 + y2 * scale * 1.8 * dpr,
        z: z2,
        r: p.r * scale * dpr,
        col: p.col,
        glow: p.glow,
      };
    }

    function render3d() {
      if (!cvs.isConnected) return;
      if (!isDragging) rotY += 0.006;
      ctx.clearRect(0, 0, w, h);

      // Grid backdrop
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
      ctx.lineWidth = 1 * dpr;
      for (let y = h * 0.15; y < h; y += h * 0.2) {
        ctx.beginPath(); ctx.moveTo(w * 0.1, y); ctx.lineTo(w * 0.9, y); ctx.stroke();
      }

      // Map projected coordinates by node ID (prevents scrambling on Z-sort!)
      const projMap = {};
      const projList = [];
      nodes.forEach((n) => {
        const p = project(n, rotY, rotX);
        projMap[n.id] = p;
        projList.push(p);
      });

      // Draw antibody backbone lines by fixed node ID
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.5)';
      ctx.lineWidth = 2.4 * dpr;
      const pFc2 = projMap['fc2'], pFc1 = projMap['fc1'], pH = projMap['hinge'];
      const pL1 = projMap['fab_l1'], pL2 = projMap['fab_l2'];
      const pR1 = projMap['fab_r1'], pR2 = projMap['fab_r2'];

      if (pFc2 && pFc1 && pH && pL1 && pL2 && pR1 && pR2) {
        ctx.beginPath();
        ctx.moveTo(pFc2.x, pFc2.y); ctx.lineTo(pFc1.x, pFc1.y); ctx.lineTo(pH.x, pH.y);
        ctx.lineTo(pL1.x, pL1.y); ctx.lineTo(pL2.x, pL2.y);
        ctx.moveTo(pH.x, pH.y);
        ctx.lineTo(pR1.x, pR1.y); ctx.lineTo(pR2.x, pR2.y);
        ctx.stroke();
      }

      // Draw linker tether lines from conjugation anchors to payload spheres
      ctx.strokeStyle = '#F59E0B';
      ctx.lineWidth = 1.4 * dpr;
      for (let k = 0; k < darCount; k++) {
        const pNode = projMap['pld_' + k];
        if (pNode && pNode.anchor && projMap[pNode.anchor]) {
          const a = projMap[pNode.anchor];
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(pNode.x, pNode.y);
          ctx.stroke();
        }
      }

      // Sort spheres by Z-depth for 3D occlusion
      projList.sort((a, b) => b.z - a.z);

      // Draw spheres
      projList.forEach((p) => {
        if (p.glow) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.r * 1.6, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(13, 148, 136, 0.25)';
          ctx.fill();
        }
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(1, p.r), 0, Math.PI * 2);
        ctx.fillStyle = p.col;
        ctx.fill();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        ctx.lineWidth = 0.8 * dpr;
        ctx.stroke();
      });

      adcAnimId = requestAnimationFrame(render3d);
    }

    adcAnimId = requestAnimationFrame(render3d);
  }

  // ------------------------------------------------------------------ Detail Drawer
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
    ])) : h('p', { class: 'dim', text: 'No boxed or Section 5 warnings on patient\'s active organs.' }));

    const secChecks = (d.checks || []).length ? section('Pre-treatment checks', h('ul', { class: 'dash' }, d.checks.map((c) => h('li', { text: c })))) : null;
    const secMissing = (d.missing || []).length ? section('Missing inputs',
      h('ul', { class: 'dash' }, d.missing.map((m) => h('li', { text: m }))),
      h('button', { type: 'button', class: 'review-link', text: 'Enter lab values', onclick: () => { closeDrawer(); switchMode(2); } })) : null;

    // 3. Pivotal Trial Study Tab
    const t = d.trial && d.trial.trial && !d.trial.no_results ? d.trial : null;
    const trialSummaryCard = t ? h('div', { class: 'trial-summary-card' },
      h('p', { style: 'margin:0 0 6px;font-weight:800;font-size:13.5px;color:var(--ink-hi)', text: `${t.trial}${t.phase ? ' (Phase ' + t.phase + ' Registration Trial)' : ''}` }),
      h('p', { class: 'dim', style: 'margin:0 0 6px;font-size:12px', text: t.population || 'Patient cohort not specified' }),
      h('p', { style: 'margin:0 0 4px;font-size:12px;font-weight:600', text: `Treatment Arm: ${t.regimen} (n=${t.n})` }),
      t.comparator ? h('p', { class: 'dim', style: 'margin:0 0 8px;font-size:12px', text: `Control Arm: ${t.comparator.regimen} (n=${t.comparator.n})` }) : null,
      /^NCT\d{8}$/.test(t.nct || '') ? h('a', { class: 'review-link', href: 'https://clinicaltrials.gov/study/' + t.nct, target: '_blank', rel: 'noopener noreferrer', text: `ClinicalTrials.gov ${t.nct} ↗` }) : null
    ) : h('p', { class: 'dim', text: (d.trial && d.trial.no_results) || 'Single-arm registration study without comparator arm.' });

    const trialEvents = [];
    for (const o of (t && t.organs) || []) {
      for (const e of o.events || []) {
        trialEvents.push(h('div', { class: 'trial-event' },
          buildDualBar({ trial: t, organ: o.organ, ev: e }),
          h('div', { class: 'event-values', style: 'margin-top:6px' },
            h('span', null, h('b', { text: `${e.a}/${e.n}` }), ' Treatment Arm'),
            e.comp ? h('span', null, h('b', { text: `${e.comp[0]}/${e.comp[1]}` }), ' Comparator Arm') : null)));
      }
    }
    const secStudy = section('Trial context and adverse events', trialSummaryCard, ...trialEvents);

    // 4. Structure 3D Tab
    const m = MECH[row.adc];
    const kvRows = m ? [
      ['Target Antigen', m.target],
      ['Antibody Backbone', m.antibody],
      ['Chemical Linker', m.linker],
      ['Cytotoxic Payload', m.payload],
      ['Payload Class', m.payload_class],
      ['Average DAR', m.dar],
    ].filter(([, v]) => v) : ((d.payload && d.payload.rows) || []);

    const cvs3d = h('canvas', { class: 'adc-3d-canvas' });
    const wrap3d = h('div', { class: 'adc-3d-wrap' },
      cvs3d,
      h('span', { class: 'adc-3d-hint', text: 'Drag to rotate 3D structure' }));

    const secStructure3d = section('3D Conjugate Architecture (Interactive)',
      wrap3d,
      kvRows.length ? h('div', { class: 'kv3' }, kvRows.map(([k, v]) => [h('span', { class: 'k', text: k }), h('span', { text: v })])) : null,
      h('button', {
        type: 'button', class: 'review-link', style: 'margin-top:10px',
        text: 'Tune in Structure Studio →',
        onclick: () => { closeDrawer(); switchMode(1); },
      }));

    const secInd = section('FDA Approved Indications',
      d.indication ? h('ul', { class: 'ind' }, d.indication.split(/;\s*/).filter(Boolean).map((x) => h('li', { text: x }))) : null);

    const tabGroups = {
      Patient: [secRestriction, secPatientWarn, secChecks, secMissing].filter(Boolean),
      Study: [secStudy].filter(Boolean),
      'Structure 3D': [secStructure3d, secInd].filter(Boolean),
    };

    const nav = h('div', { class: 'evidence-tabs', role: 'group', 'aria-label': 'Evidence tabs' });
    const allSecs = Object.values(tabGroups).flat();

    function switchTab(name) {
      S.drawerTab = name;
      allSecs.forEach((s) => { s.hidden = !tabGroups[name].includes(s); });
      [...nav.children].forEach((b) => b.setAttribute('aria-pressed', b.dataset.view === name ? 'true' : 'false'));
      if (name === 'Structure 3D') {
        setTimeout(() => init3dAdcCanvas(cvs3d, row), 50);
      }
    }

    Object.keys(tabGroups).forEach((name) => {
      nav.append(h('button', {
        type: 'button', text: name, 'data-view': name,
        onclick: () => switchTab(name),
      }));
    });

    drawerBody.append(nav, ...allSecs);
    switchTab(S.drawerTab || 'Patient');
  }

  function saveReview(result) {
    if (!REVIEW || !REVIEW.reviewText) return;
    const text = REVIEW.reviewText(APP, condList().map(condName), rawValues(), FIELDS, result);
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
    const link = h('a', { href: url, download: 'ADCToX-review.txt' });
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // ------------------------------------------------------------------ Mode Switching & Keyboard Controls
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
    renderActiveMode(false);
    await refreshBackendData();
    renderActiveMode(false);
  }

  start();
})();
