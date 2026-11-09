/* ADCTOX v0.7.1 Architectural Daylight WebApp
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
          h('h2', { id: 'g-title', text: 'ADCTOX v0.7.1 Visual Workspace' }),
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
    { id: 'Tetrapeptide GGFG', cleavable: true, stability: 88, handle: 'amine_hydroxyl', note: 'Cathepsin B/L-cleavable tetrapeptide; self-immolative aminomethylene releases hydroxy/amine payload', note_ko: '카텝신 B/L 특이 절단형 4펩타이드; 자가 절단 아미노메틸렌으로 하이드록시/아민 페이로드 유리', popover: 'Enzymatically cleaved in lysosomes by cathepsins. High plasma stability (88%) prevents premature extracellular payload shedding.', popover_ko: '리소좀 효소(카텝신)에 의해서만 특이적으로 절단되며 높은 혈장 안정도(88%)로 체내 조기 유출을 방지합니다.' },
    { id: 'Val-Cit PABC', cleavable: true, stability: 76, handle: 'amine', note: 'Cathepsin B-cleavable dipeptide with para-aminobenzyl carbamate spacer for secondary/primary amines', note_ko: '카텝신 B 특이 절단형 디펩타이드; PABC 스페이서로 아민 페이로드 결합', popover: 'Validated dipeptide linker. Readily cleaved inside endosomes; moderate plasma carboxylesterase cleavage in rodents.', popover_ko: '엔도솜 내에서 신속히 절단되는 검증된 디펩타이드 링커입니다.' },
    { id: 'Hydrolyzable CL2A', cleavable: true, stability: 54, handle: 'hydroxyl', note: 'pH-sensitive carbonate linker; systemic and intratumoral hydrolysis releases SN-38', note_ko: 'pH 감응성 탄산염 링커; 종양 산성 미세환경에서 가수분해 방출', popover: 'Short PEGylated carbonate linker. pH-sensitive hydrolysis allows gradual release in acidic tumor microenvironments.', popover_ko: '산성 종양 미세환경에서 서서히 가수분해되어 지속 방출 효과를 냅니다.' },
    { id: 'Non-cleavable mc', cleavable: false, stability: 96, handle: 'amine', note: 'Maleimidocaproyl thioether; requires complete lysosomal proteolysis to release Cys-mc-payload', note_ko: '안정형 티오에테르 링커; 항체 완전 분해 시에만 페이로드 방출', popover: 'Ultra-stable thioether bond. Payload remains attached to cysteine; lacks membrane diffusion, preventing bystander toxicity.', popover_ko: '순환 혈액 내에서 극도로 안정하여 비표적 장기 노출을 최소화합니다.' },
    { id: 'Disulfide SPDB', cleavable: true, stability: 68, handle: 'thiol', note: 'Sterically hindered disulfide cleaved by intracellular glutathione for thiol maytansinoids', note_ko: '입체 장애 이황화결합 링커; 세포 내 글루타티온 농도에 의해 절단', popover: 'Hindered disulfide linker cleaved selectively by high intracellular glutathione concentrations.', popover_ko: '암세포 내 높은 글루타티온 농도에 의해 선택적으로 분해됩니다.' },
    { id: 'Acid Hydrazone', cleavable: true, stability: 48, handle: 'ketone', note: 'Acid-labile AcBut hydrazone hydrolyzed in endosomes/lysosomes (pH 4.5-5.0)', note_ko: '산 감응성 하이드라존 링커; 엔도솜/리소좀 내 산성 조건에서 가수분해', popover: 'Legacy acid-labile linker. Hydrolyzed in acidic lysosomes; higher spontaneous systemic release rate.', popover_ko: '리소좀 산성 환경에서 가수분해되는 초기 세대 링커입니다.' },
  ];

  const STUDIO_PAYLOADS = [
    { id: 'DXd ( Topo I )', cls: 'Topoisomerase I inhibitor', perm: true, handle: 'amine_hydroxyl', potency: 92, organs: { pulmonary: 82, haematologic: 68, gastrointestinal: 64, cardiovascular: 38 }, popover: 'Exatecan derivative with ~10x higher potency than SN-38. High membrane permeability drives potent bystander killing of neighboring antigen-negative tumor cells.' },
    { id: 'SN-38 ( Topo I )', cls: 'Topoisomerase I inhibitor (UGT1A1)', perm: true, handle: 'hydroxyl', potency: 78, organs: { haematologic: 86, gastrointestinal: 84, hepatic: 44 }, popover: 'Active metabolite of irinotecan. Hepatic clearance via UGT1A1 glucuronidation; neutropenia and severe diarrhea are primary toxicities.' },
    { id: 'MMAE ( Auristatin )', cls: 'Microtubule inhibitor (Auristatin)', perm: true, handle: 'amine', potency: 90, organs: { neurologic: 84, haematologic: 76, dermatologic: 66, hepatic: 52 }, popover: 'Synthetic dolastatin 10 antimitotic. Highly lipophilic and neutral at physiologic pH; strong bystander activity with dose-limiting peripheral neuropathy.' },
    { id: 'MMAF ( Auristatin )', cls: 'Charged Auristatin (low permeability)', perm: false, handle: 'amine', potency: 86, organs: { ocular: 92, haematologic: 64, renal: 28 }, popover: 'Carboxy-terminal phenylalanine confers negative charge, blocking passive membrane diffusion. Minimizes systemic bystander damage while accumulating in corneal epithelium.' },
    { id: 'DM4 / DM1 ( Maytansinoid )', cls: 'Microtubule inhibitor (Maytansinoid)', perm: true, handle: 'thiol', potency: 84, organs: { ocular: 74, hepatic: 72, neurologic: 62, haematologic: 58 }, popover: 'Thiol-containing tubulin inhibitor. Metabolized primarily via hepatic CYP3A4; associated with reversible transaminase elevations and thrombocytopenia.' },
    { id: 'SG3199 ( PBD Dimer )', cls: 'DNA minor-groove crosslinker', perm: true, handle: 'amine', potency: 98, organs: { haematologic: 92, hepatic: 78, pulmonary: 68, dermatologic: 62 }, popover: 'Ultra-potent DNA alkylator binding minor groove without distorting helix. Active against non-dividing cells; dose-limiting delayed myelosuppression and fluid retention.' },
  ];

  // ------------------------------------------------------------------ Internationalization (i18n)
  const ORGAN_KO = {
    pulmonary: '폐/호흡기',
    hepatic: '간/담도',
    haematologic: '혈액/골수',
    cardiovascular: '심장/심혈관',
    renal: '신장/요로',
    neurologic: '신경계',
    gastrointestinal: '위장관',
    ocular: '안구/각막',
    dermatologic: '피부/점막',
    metabolic_endocrine: '내분비/대사',
    musculoskeletal: '근골격',
    infectious_immune: '감염/면역',
    otologic: '이비인후',
  };

  const LAB_KO = {
    bilirubin: '총 빌리루빈',
    creatinine: '혈청 크레아티닌',
    ast: 'AST (간효소)',
    alt: 'ALT (간효소)',
    platelets: '혈소판 수치',
    anc: '호중구 절대수치 (ANC)',
    hb: '혈색소 (Hb)',
    lvef: '좌심실 구혈률 (LVEF)',
  };

  const TXT = {
    ko: {
      modes: ['1. ADC 매트릭스', '2. 구조 스튜디오', '3. 환자 정보'],
      brandTag: '임상 ADC 의사결정 및 3D 구조 스튜디오',
      quickDemo: '데모 증례:',
      customPatient: '개별 환자 입력',
      newPatient: '새 환자 입력',
      newPatientTitle: '입력된 질환을 초기화하고 새 환자 입력을 시작합니다',
      addCondPh: '암종 또는 기저질환 입력 (예: 유방암, 간질성 폐질환, 간경변, 당뇨병)...',
      condHelp: '질환명, 증상, 암종을 한글 또는 영문으로 자유롭게 입력하세요.',
      activeOrgans: '활성 취약 장기',
      noActiveOrgans: '활성 취약 장기 없음',
      footerText: 'ADCTOX 임상 ADC 의사결정 및 접합체 구조 설계 워크스페이스',
      keys: { modes: '1-3 모드 전환', nav: '상/하 행 이동', enter: '엔터 상세 근거', help: '? 안내' },
      secConstruct: 'ADC 약물 / 구조',
      secFit: '약물 적합도',
      secOrgans: '환자 취약 장기',
      secTrial: '허가 임상 부작용 발생률',
      matrixHead: 'FDA 승인 ADC 약물 치료군 순위',
      matrixSub: '환자의 취약 장기 및 라벨 주의사항을 종합한 임상 권고',
      rankBest: '1위 최적 적합',
      rankCand: '후보',
      fitStd: '표준 용량 투여',
      fitAdj: '모니터링 / 용량 조절',
      fitAvoid: '투여 주의 / 금기',
      tuneStudio: '구조 스튜디오에서 설계 ->',
      allGrade: '전체',
      grade3: '3등급 이상',
      primaryRec: '최우선 추천 약물',
      primaryHint: '카드를 클릭하면 3D 구조 및 FDA 임상 근거를 확인합니다',
      filterAll: '전체 승인 ADC',
      filterMatch: '암종 일치',
      filterRestricted: '라벨 주의/금기',
      exportSummary: '요약 내보내기',
      match: '일치',
      archTitle: '접합체 구조 설계 (Architecture)',
      autoOpt: '자동 최적화 (Auto Optimize)',
      scanning: '최적화 탐색 중...',
      scanSpace: '다목적 파레토 최적화 탐색 중...',
      tgtTitle: '1. 표적 항원 (Target mAb)',
      lnkTitle: '2. 화학 링커 (Chemical Linker)',
      pldTitle: '3. 세포독성 페이로드 (Cytotoxic Payload)',
      darTitle: '4. 약물-항체 접합비 (DAR)',
      fcTitle: '5. Fc 엔지니어링',
      wtFc: '야생형 IgG1 (Wild-type)',
      silFc: 'Fc 침묵화 (LALA-PG)',
      paretoTitle: '다목적 파레토 최적 경계선 (환자 장기 안전성 vs. 항암 효능)',
      paretoSafetyX: '환자 장기 안전성 점수 (0 - 100)',
      paretoEfficacyY: '항암 효능 및 선택도 (0 - 100)',
      legendCand: '후보군 공간',
      legendPareto: '파레토 최적 경계선',
      legendCur: '현재 선택',
      optimalLocked: 'AI 최적 설계 조합 잠금 완료',
      optimalCand: 'AI 추천 최적 조합:',
      peakPareto: '파레토 최적점',
      clickAutoOpt: '자동 최적화를 클릭하면 스캔 후 적용됩니다',
      shCompat: '접합 반응성 호환도',
      shCompatDirect: '직접 결합 가능',
      shCompatSpacer: '링커 스페이서 필요',
      shCompatDesc: '링커의 반응성 작용기와 페이로드 결합 부위의 화학적 짝맞춤입니다.',
      shSelect: '종양 대 정상조직 선택도',
      shSelectDesc: '정상 조직 대비 암세포의 표적 항원 발현비(log2FC)로, 높을수록 정상 장기 손상이 적습니다.',
      shBystander: '주변 암세포 동반 사멸 (Bystander)',
      shBystanderActive: '인접 세포 동반 사멸 (활성)',
      shBystanderAuto: '표적 세포만 국소 사멸 (비활성)',
      shBystanderDesc: '표적 단백질이 없는 인접 암세포까지 침투하여 함께 사멸시키는 효과입니다.',
      shStability: '혈장 내 링커 안정도',
      shStabilityIntact: '유지',
      shStabilityDesc: '혈액 순환 중 페이로드가 조기 유리되지 않고 종양까지 온전하게 전달되는 비율입니다.',
      simOrganTitle: '환자 취약 장기 모의 독성 지수',
      gtexTitle: '정상 조직 안전 기준치',
      gtexNote: '건강한 정상 장기 발현 수치(nTPM)로, 수치가 낮고 녹색일수록 표적 비특이 독성(Off-tumor) 위험이 적습니다.',
      fcLalaNote: 'LALA-PG Fc 침묵화: 대식세포 FcgammaR 흡수 억제 및 비표적 면역독성 저감',
      fcWtNote: '야생형 IgG1: 표준 FcgammaR 매개 대식세포 흡수 및 면역 이펙터 기능',
      flowTitle: '정량적 임상 바이오마커 플로우시트',
      flowSub: '기관 기준 참고치 대비 수치 매핑 및 독성 플래그 분석',
      refRange: '참고치',
      notEntered: '미입력',
      elevated: '수치 상승',
      borderline: '경계치',
      normal: '정상',
      organLinkage: 'AI 장기 취약도 연계 분석',
      riskWeight: '위험 가중치',
      triggeredDiag: '임상 진단에 의해 활성화',
      triggeredLab: '검사 수치 이상에 의해 활성화',
      noActiveTriggers: '활성화된 장기 독성 요인 없음',
      drTitle: '임상 근거 및 구조 상세',
      tabPatient: '환자 적합도',
      tabStudy: '허가 임상시험',
      tabStructure: '3D 분자 구조',
      labelRestriction: 'FDA 라벨 사용 제한',
      noLabelRestriction: '입력된 환자 수치에 해당하는 라벨 제한 사항이 없습니다.',
      patientWarnTitle: '환자 취약 장기 관련 경고',
      noPatientWarn: '환자의 취약 장기와 관련된 Boxed Warning 또는 주의사항이 없습니다.',
      preCheckTitle: '투여 전 권장 검사',
      missingInputTitle: '미입력 검사 항목',
      enterLabBtn: '검사 수치 입력하기',
      rotateHint: '드래그하여 3D 구조 회전',
      treatmentArm: '치료군',
      controlArm: '대조군',
      trialContext: '임상시험 상세 및 이상사례 발생률',
      struct3dTitle: '3D 접합체 분자 구조 (대화형)',
      appliesToAll: '모든 환자에게 적용',
      singleArmTrial: '단일군 임상시험 (대조군 없음)',
      compareTitle: '신규 최적 설계 vs. 기존 승인 ADC 비교',
      tabCompare: '설계 비교',
      tabStruct3d: '3D 분자 구조',
      tabRefStudy: '기존 허가 임상',
      deNovoCol: '신규 최적 설계 (De Novo ADC)',
      refCol: '기존 승인 약물 (Approved Benchmark)',
      clinicalDiff: '임상적 차이 및 개선 이점',
      deRiskTitle: '기존 약물 부작용 대비 임상 개선 기전 (Clinical De-Risking)',
      viewCompareBtn: '기존 승인 ADC와 비교 ↗',
      compTarget: '표적 항원',
      compLinker: '화학 링커',
      compPayload: '세포독성 페이로드',
      compDar: '약물-항체 접합비 (DAR)',
      compFc: 'Fc 엔지니어링',
      compSafety: '장기 안전성 점수',
      compEfficacy: '항암 효능 점수',
    },
    en: {
      modes: ['1. ADC Matrix', '2. Structure Studio', '3. Patient Info'],
      brandTag: 'Clinical ADC Decision & Structure Studio',
      quickDemo: 'Quick Demo:',
      customPatient: 'Custom Patient',
      newPatient: 'New Patient',
      newPatientTitle: 'Clear entered conditions and start custom patient input',
      addCondPh: 'Enter cancer or comorbidity (e.g., breast cancer, ILD, cirrhosis)...',
      condHelp: 'Type disease, symptom, or cancer in English or Korean.',
      activeOrgans: 'Active Vulnerable Organs',
      noActiveOrgans: 'No Active Vulnerable Organs',
      footerText: 'ADCTOX Clinical Decision and Conjugate Architecture Workspace',
      keys: { modes: '1-3 Mode', nav: 'Up/Down Navigate', enter: 'Enter Evidence', help: '? Guide' },
      secConstruct: 'ADC Regimen / Construct',
      secFit: 'Drug Fit',
      secOrgans: 'Vulnerable Organs',
      secTrial: 'Pivotal Trial AE Rate',
      matrixHead: 'Ranked FDA-Approved ADC Regimens',
      matrixSub: 'Synthesized from FDA label warnings, active organs, and pivotal trials',
      rankBest: '#1 Best Fit',
      rankCand: 'Candidate',
      fitStd: 'Standard dosing',
      fitAdj: 'Monitor / Adjust',
      fitAvoid: 'Avoid / Contraindicated',
      tuneStudio: 'Tune in Structure Studio ->',
      allGrade: 'All Gr',
      grade3: 'Gr >=3',
      primaryRec: 'Primary Recommendation',
      primaryHint: 'Click card for 3D architecture and FDA trial evidence',
      filterAll: 'All Approved ADCs',
      filterMatch: 'Cancer Match',
      filterRestricted: 'Label Restrictions',
      exportSummary: 'Export Summary',
      match: 'Match',
      archTitle: 'Conjugate Architecture',
      autoOpt: 'Auto Optimize',
      scanning: 'Optimizing...',
      scanSpace: 'Scanning candidate space...',
      tgtTitle: '1. Target Antigen (mAb)',
      lnkTitle: '2. Chemical Linker',
      pldTitle: '3. Cytotoxic Payload',
      darTitle: '4. Drug-to-Antibody Ratio (DAR)',
      fcTitle: '5. Fc Engineering',
      wtFc: 'Wild-type IgG1',
      silFc: 'Fc-Silenced (LALA-PG)',
      paretoTitle: 'Multi-Objective Pareto Frontier (Patient Organ Safety vs. Antitumor Efficacy)',
      paretoSafetyX: 'Patient Organ Safety Score (0 - 100)',
      paretoEfficacyY: 'Antitumor Efficacy & Selectivity (0 - 100)',
      legendCand: 'Candidate Space',
      legendPareto: 'Pareto Frontier',
      legendCur: 'Current Selection',
      optimalLocked: 'AI De Novo Optimal ADC Architecture Locked',
      optimalCand: 'AI Recommended Optimum:',
      peakPareto: 'Pareto Frontier Peak',
      clickAutoOpt: 'Click Auto Optimize to scan and apply',
      shCompat: 'Conjugation Compatibility',
      shCompatDirect: 'Direct Coupling',
      shCompatSpacer: 'Linker Spacer Needed',
      shCompatDesc: 'Linker reactive handle pairing with payload functional group.',
      shSelect: 'Tumor / Normal Selectivity',
      shSelectDesc: 'Fold-change in target expression on tumor vs. healthy normal organs.',
      shBystander: 'Bystander Tumor Killing',
      shBystanderActive: 'Active Bystander Diffusion',
      shBystanderAuto: 'Localized Killing Only',
      shBystanderDesc: 'Penetrates and kills adjacent antigen-negative tumor cells to counter heterogeneity.',
      shStability: 'Plasma Linker Stability',
      shStabilityIntact: 'Intact',
      shStabilityDesc: 'Resistance to premature systemic payload deconjugation in circulation.',
      simOrganTitle: 'Simulated Patient Organ Toxicity Index',
      gtexTitle: 'Normal Tissue Safety Baseline',
      gtexNote: 'Normal tissue expression level (nTPM). Lower values (green) represent reduced on-target off-tumor toxicity risk.',
      fcLalaNote: 'LALA-PG Fc-silencing active: FcgammaR macrophage uptake attenuated.',
      fcWtNote: 'Wild-type IgG1: standard immune effector and macrophage uptake.',
      flowTitle: 'Clinical Biomarker Flowsheet',
      flowSub: 'Values mapped against institutional reference intervals',
      refRange: 'Ref',
      notEntered: 'Not entered',
      elevated: 'Elevated',
      borderline: 'Borderline',
      normal: 'Normal',
      organLinkage: 'AI Organ Vulnerability Linkage',
      riskWeight: 'Risk Weight',
      triggeredDiag: 'Triggered by clinical diagnosis',
      triggeredLab: 'Triggered by laboratory biomarker elevation',
      noActiveTriggers: 'No active organ toxicity triggers detected.',
      drTitle: 'Clinical Evidence and Structure',
      tabPatient: 'Patient & Label Fit',
      tabStudy: 'Pivotal Trials',
      tabStructure: 'Structure 3D',
      labelRestriction: 'Label restriction',
      noLabelRestriction: 'No label restriction triggered for entered values.',
      patientWarnTitle: "Warnings on the patient's organs",
      noPatientWarn: "No boxed or Section 5 warnings on patient's active organs.",
      preCheckTitle: 'Pre-treatment checks',
      missingInputTitle: 'Missing inputs',
      enterLabBtn: 'Enter lab values',
      rotateHint: 'Drag to rotate 3D structure',
      treatmentArm: 'Treatment Arm',
      controlArm: 'Comparator Arm',
      trialContext: 'Trial context and adverse events',
      struct3dTitle: '3D Conjugate Architecture (Interactive)',
      appliesToAll: 'Applies to all patients',
      singleArmTrial: 'Single-arm trial',
      compareTitle: 'De Novo Design vs. Approved ADC Benchmark',
      tabCompare: 'Compare',
      tabStruct3d: '3D Structure',
      tabRefStudy: 'Pivotal Trial',
      deNovoCol: 'De Novo Design (Optimal)',
      refCol: 'Approved Benchmark',
      clinicalDiff: 'Clinical Difference & Advantage',
      deRiskTitle: 'Clinical De-Risking vs. Approved Drug Warnings',
      viewCompareBtn: 'Compare with Approved ADC ↗',
      compTarget: 'Target Antigen',
      compLinker: 'Chemical Linker',
      compPayload: 'Cytotoxic Payload',
      compDar: 'DAR',
      compFc: 'Fc Engineering',
      compSafety: 'Simulated Safety Score',
      compEfficacy: 'Antitumor Efficacy Score',
    },
  };
  function t(k) {
    const lang = S.lang === 'ko' ? 'ko' : 'en';
    return (TXT[lang] && TXT[lang][k]) || (TXT.en && TXT.en[k]) || k;
  }

  // ------------------------------------------------------------------ Session State
  const KEY = 'adctox.web.v071';
  function defaultState() {
    const p = PRESETS[0];
    return {
      mode: 0,
      lang: 'ko',
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
        if (d.lang) S.lang = d.lang;
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

  let langBtn = null;
  function frame() {
    document.title = 'ADCTOX';
    crumbsOl = h('ol');
    verEl = h('div', { class: 'ver', text: '' });
    scenarioDropdown = h('div', { class: 'scenario-dropdown' });
    langBtn = h('button', {
      type: 'button', class: 'lang-btn',
      'aria-label': 'Language Toggle',
      title: '한국어 / English 전환',
      text: S.lang === 'ko' ? 'KO / EN' : 'EN / KO',
      onclick: () => toggleLanguage(),
    });

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
        langBtn,
        h('button', { type: 'button', class: 'help', 'aria-label': 'How it works', title: 'How it works', text: '?', onclick: openGuide })));

    stageBox = h('main', { class: 'stage' });
    layout = h('div', { class: 'layout' }, stageBox);
    barKeys = h('div', { class: 'keys', 'aria-hidden': 'true' });
    bar = h('footer', { class: 'bar' },
      h('span', { text: t('footerText') }),
      barKeys);

    drawerTitle = h('h2', { id: 'dr-title' });
    drawerBody = h('div', { class: 'dr-body' });
    const xBtn = h('button', { class: 'x-btn', type: 'button', 'aria-label': 'Close', onclick: () => closeDrawer() }, svgClose());
    drawer = h('div', { class: 'drawer', role: 'dialog', 'aria-modal': 'false', 'aria-labelledby': 'dr-title', 'aria-hidden': 'true' },
      h('div', { class: 'dr-head' }, drawerTitle, xBtn), drawerBody);

    document.body.append(top, h('div', { class: 'shell' }, h('div', { class: 'wrap' }, layout)), bar, drawer, tipBox);
  }

  function toggleLanguage() {
    S.lang = S.lang === 'ko' ? 'en' : 'ko';
    save();
    renderHeaderControls();
    renderActiveMode(false);
  }

  function renderHeaderControls() {
    if (langBtn) langBtn.textContent = S.lang === 'ko' ? 'KO / EN' : 'EN / KO';
    if (bar && bar.firstElementChild) bar.firstElementChild.textContent = t('footerText');
    clear(crumbsOl);
    t('modes').forEach((name, i) => {
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
    h('span', { class: 'dim', text: t('quickDemo') }),
    h('strong', { class: 'scenario-current', text: S.presetId ? activePreset.title.split('/')[0].trim() : t('customPatient') }),
    sv('svg', { class: 'chevron', width: '10', height: '6', viewBox: '0 0 10 6', stroke: 'currentColor', 'stroke-width': '1.5', fill: 'none' },
      sv('path', { d: 'M1 1L5 5L9 1' })));

    const resetBtn = h('button', {
      type: 'button', class: 'reset-patient-btn', text: t('newPatient'),
      title: t('newPatientTitle'),
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
      'aria-autocomplete': 'list', 'aria-label': t('addCondPh'),
      placeholder: t('addCondPh'), autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false',
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
        const orgLabel = S.lang === 'ko' ? (ORGAN_KO[item.organ] || SHORT[item.organ] || item.organ) : (SHORT[item.organ] || item.organ);
        const btn = h('button', {
          type: 'button', class: 'organ-meter-btn' + (isPrio ? ' prio-active' : ''),
          title: item.condKey ? (S.lang === 'ko' ? `${orgLabel} 안전성 우선 평가` : 'Prioritize ' + orgLabel) : orgLabel,
          onclick: async () => {
            if (!item.condKey) return;
            S.first = S.first === item.condKey ? null : item.condKey;
            save();
            await refreshBackendData();
            if (onChanged) onChanged();
          },
        },
        h('div', { class: 'om-top' },
          h('span', { class: 'om-name', text: orgLabel }),
          h('span', { class: 'om-val', text: isPrio ? (S.lang === 'ko' ? '우선 1위' : 'Priority 1') : `${pct}%` })),
        h('div', { class: 'om-track' },
          h('i', { class: 'om-fill', style: `width:${pct}%` })));
        organsGrid.append(btn);
      });
    } else {
      organsGrid.append(h('span', { class: 'dim', text: t('noActiveOrgans') }));
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
          h('span', { class: 'horizon-label', text: `${t('activeOrgans')} (${activeOrgans.length})` }),
          h('span', { class: 'horizon-sub', text: S.first ? (S.lang === 'ko' ? '우선순위 적용됨' : 'Priority Active') : (S.lang === 'ko' ? '클릭 시 해당 장기 우선 평가' : 'Select organ to prioritize') })),
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
    const isKo = S.lang === 'ko';
    if (row.status === 'None' || row.status === 'No change') return { tone: 'clear', bars: 'clear', label: isKo ? '표준' : 'Standard', full: isKo ? '표준 용량 투여' : 'Standard dosing' };
    if (reason && reason.code === 'contraindicated') return { tone: 'avoid', bars: 'avoid', label: isKo ? '금기' : 'Contraindicated', full: isKo ? '투여 금기' : 'Contraindicated' };
    if (row.status === 'Avoid') return { tone: 'avoid', bars: 'avoid', label: isKo ? (row.sure ? '투여주의' : '주의(확인)') : (row.sure ? 'Avoid' : 'Avoid (check)'), full: isKo ? '투여 주의 / 회피' : 'Avoid use' };
    if (row.status === 'Lower dose' || (reason && reason.code === 'reduce_dose')) return { tone: 'monitor', bars: 'monitor', label: isKo ? '용량조절' : 'Dose adjust', full: isKo ? '용량 조절 권고' : 'Dose adjustment' };
    if (row.status === 'Monitor') return { tone: 'monitor', bars: 'monitor', label: isKo ? '모니터링' : 'Monitor', full: isKo ? '밀접 모니터링' : 'Close monitoring' };
    return { tone: 'limited', bars: 'limited', label: isKo ? '제한적' : 'Limited data', full: isKo ? '해당 코호트 연구 미비' : 'Not studied in cohort' };
  }

  function organStatusForRow(row, organ) {
    const isKo = S.lang === 'ko';
    const orgName = isKo ? (ORGAN_KO[organ] || SHORT[organ] || organ) : (SHORT[organ] || organ);
    const detail = row.detail || {};
    const allWarnings = [].concat(detail.warnings || [], detail.other_warnings || []);
    const found = allWarnings.find((w) => w.organ === organ);
    if (!found) return { cls: 'clear', tag: isKo ? '허용' : 'Clear', title: isKo ? (orgName + ' 라벨 경고 없음') : ('No label warning on ' + (SHORT[organ] || organ)) };
    if (String(found.mark || '').trim() === '!!') return { cls: 'boxed', tag: isKo ? '경고' : 'Warning', title: (isKo ? 'Boxed 경고: ' : 'Boxed Warning: ') + (found.text || '') };
    return { cls: 'warn', tag: isKo ? '주의' : 'Caution', title: (isKo ? 'Section 5 주의: ' : 'Section 5 Warning: ') + (found.text || '') };
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
    if (!trialHit || !trialHit.trial || !trialHit.ev) return h('span', { class: 'dim', style: 'font-size:11px', text: S.lang === 'ko' ? '단일군 임상 (대조군 없음)' : 'Single-arm trial' });
    const { trial, ev } = trialHit;
    const adcPct = (100 * (ev.a || 0)) / Math.max(1, ev.n || 1);
    const cmpPct = ev.comp && ev.comp[1] ? (100 * ev.comp[0]) / Math.max(1, ev.comp[1]) : null;
    const scaleMax = Math.max(25, adcPct, cmpPct || 0);
    const compLabel = (trial.comparator && trial.comparator.regimen) || (S.lang === 'ko' ? '대조군' : 'Control');
    const tip = `${trial.trial || ''}: ${ev.term || ''}\nADC (${trial.regimen || ''}): ${ev.a || 0}/${ev.n || 0} (${ev.pct || ''})` +
      (ev.comp ? `\n${S.lang === 'ko' ? '대조군' : 'Control'} (${compLabel}): ${ev.comp[0]}/${ev.comp[1]} (${ev.comp_pct || ''})` : '');

    return h('div', {
      class: 'dual-bar-group',
      title: tip,
    },
    h('div', { class: 'dual-bar-title' },
      h('span', { text: ev.term || '' }),
      h('span', { class: 'dim', text: trial.trial || '' })),
    h('div', { class: 'dual-bar-row' },
      h('span', { class: 'db-tag', text: 'ADC' }),
      h('span', { class: 'db-track' }, h('i', { class: 'db-fill-adc', style: `width:${Math.min(100, (adcPct / scaleMax) * 100).toFixed(1)}%` })),
      h('span', { class: 'db-pct', text: ev.pct || '' })),
    cmpPct !== null ? h('div', { class: 'dual-bar-row' },
      h('span', { class: 'db-tag', text: 'CMP' }),
      h('span', { class: 'db-track' }, h('i', { class: 'db-fill-cmp', style: `width:${Math.min(100, (cmpPct / scaleMax) * 100).toFixed(1)}%` })),
      h('span', { class: 'db-pct cmp', text: ev.comp_pct || '' })) : null);
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
            h('span', { class: 'sp-organ-name', text: S.lang === 'ko' ? (ORGAN_KO[item.organ] || SHORT[item.organ] || item.organ) : (SHORT[item.organ] || item.organ) }),
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
            h('span', { class: 'sp-metric-label', text: t('secOrgans') }),
            organBars),
          h('div', { class: 'sp-metric-box' },
            h('span', { class: 'sp-metric-label', text: t('secTrial') }),
            buildDualBar(trialHit))));

        cardEls.set(idx, card);
        spGrid.append(card);
      });

      content.append(h('section', { class: 'spotlight-section', 'aria-label': 'Top recommended ADCs' },
        h('div', { class: 'sec-bar' },
          h('span', { class: 'sec-kicker', text: t('primaryRec') }),
          h('span', { class: 'dim', style: 'font-size:11.5px', text: t('primaryHint') })),
        spGrid));

      let filter = 'all';
      const relevant = (row) => (hasCancer ? row.indicated === true : true);
      const filters = [
        ['all', t('filterAll'), rows.length, () => true],
        ['relevant', t('filterMatch'), rows.filter(relevant).length, relevant],
      ];

      const tabs = h('div', { class: 'review-filters', role: 'group', 'aria-label': 'Filter ADCs' });
      const toolbar = h('div', { class: 'review-toolbar' },
        tabs,
        h('button', { type: 'button', class: 'export-button', text: t('exportSummary'), onclick: () => saveReview(res) }));
      content.append(toolbar);

      const grid = h('div', { class: 'review-grid', role: 'grid', 'aria-label': 'ADC Cohort Matrix' },
        h('div', { class: 'review-grid-head', role: 'row' },
          h('span', { role: 'columnheader', text: '#' }),
          h('span', { role: 'columnheader', text: t('secConstruct') }),
          tipped(h('span', { role: 'columnheader', text: t('secFit') })),
          tipped(h('span', { role: 'columnheader', text: t('secOrgans') })),
          tipped(h('span', { role: 'columnheader', text: t('secTrial') }))));

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
            h('span', { text: S.lang === 'ko' ? (ORGAN_KO[item.organ] || SHORT[item.organ] || item.organ) : (SHORT[item.organ] || item.organ) }),
            h('b', null, h('i')),
            h('span', { class: 'mo-tag', text: os.cls === 'boxed' ? (S.lang === 'ko' ? '경고' : 'Warning') : os.cls === 'warn' ? (S.lang === 'ko' ? '주의' : 'Caution') : (S.lang === 'ko' ? '허용' : 'Clear') })));
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
            hasCancer && row.indicated ? h('span', { class: 'sp-match-tag', text: t('match') }) : null),
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
    const isKo = S.lang === 'ko';
    const activeOrgs = activeOrgansWithScores().map((o) => (isKo && ORGAN_KO[o.organ] ? ORGAN_KO[o.organ] : SHORT[o.organ] || o.organ));
    if (isKo) {
      return [
        ['1. 표적 항원', `${s.target} (선택도 +${bestSim.tgt.selectivity.toFixed(1)} log2FC)`, '정상 장기 발현을 최소화하고 종양 암세포에 고선택적으로 결합합니다.'],
        ['2. 화학 링커', `${s.linker} (혈장 안정도 ${bestSim.lnk.stability}%)`, `${activeOrgs.join(', ') || '주요 취약 장기'}에서 비특이적 유출을 방지하고 종양 내에서만 절단됩니다.`],
        ['3. 세포독성 페이로드', `${s.payload} (${bestSim.pld.family || bestSim.pld.cls})`, '환자 활성 취약 장기 독성 병목을 회피하면서 높은 항암 살상력을 발휘합니다.'],
        ['4. 접합비 및 Fc 설계', `DAR ${s.dar} + ${s.fc ? 'Fc 침묵화 (LALA-PG)' : '야생형 IgG1 (Wild-type)'}`, `환자 장기 안전성(${bestSim.safetyScore}점)과 종양 효능(${bestSim.efficacyScore}점)의 파레토 최적 균형점입니다.`],
      ];
    }
    return [
      ['1. Target Antigen', `${s.target} (Selectivity +${bestSim.tgt.selectivity.toFixed(1)} log2FC)`, 'Maximizes tumor selectivity margin while minimizing healthy normal tissue binding.'],
      ['2. Chemical Linker', `${s.linker} (Plasma Stability ${bestSim.lnk.stability}%)`, `Prevents premature systemic shedding on ${activeOrgs.join(', ') || 'vulnerable organs'} with lysosomal payload release.`],
      ['3. Cytotoxic Payload', `${s.payload} (${bestSim.pld.family || bestSim.pld.cls})`, 'Evades dose-limiting toxicity bottlenecks on active organs while preserving high potency.'],
      ['4. DAR & Fc Engineering', `DAR ${s.dar} + ${s.fc ? 'Fc-Silenced (LALA-PG)' : 'Wild-type IgG1'}`, `Optimal Pareto frontier balance: Safety ${bestSim.safetyScore}/100 and Efficacy ${bestSim.efficacyScore}/100.`],
    ];
  }

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

    function renderControls() {
      clear(controls);
      const headAction = h('div', { class: 'studio-head-action' },
        h('span', { class: 'sec-kicker', text: t('archTitle') }));
      controls.append(headAction);

      const makeGroup = (label, items, current, onPick, isGrid6) => {
        const pills = h('div', { class: 'studio-pills' + (isGrid6 ? ' grid-6' : '') });
        items.forEach((it) => {
          const val = typeof it === 'string' ? it : it.id;
          const popoverText = typeof it === 'object' ? (S.lang === 'ko' ? (it.popover_ko || it.popover) : it.popover) : null;
          const b = h('button', {
            type: 'button', class: 'st-pill', 'aria-pressed': val === current ? 'true' : 'false',
            text: val,
            onmouseenter: (e) => {
              if (popoverText) showMicroPopover(b, popoverText);
            },
            onmouseleave: () => hideMicroPopover(),
            onclick: () => {
              onPick(val); save(); renderControls(); renderStudioCanvas();
              openStudioCompareDrawer(computeStudioSimulation(), evaluateAllStudioCandidates());
            },
          });
          pills.append(b);
        });
        return h('div', { class: 'studio-group' }, h('span', { class: 'studio-label', text: label }), pills);
      };

      const optBtn = h('button', {
        type: 'button', class: 'btn-optimize', text: isOptimizing ? t('scanning') : t('autoOpt'),
        onclick: () => runOptimizationSimulation(),
      });

      controls.append(
        makeGroup(t('tgtTitle'), STUDIO_TARGETS, S.studio.target, (v) => { S.studio.target = v; autoRationale = null; }),
        makeGroup(t('lnkTitle'), STUDIO_LINKERS, S.studio.linker, (v) => { S.studio.linker = v; autoRationale = null; }),
        makeGroup(t('pldTitle'), STUDIO_PAYLOADS, S.studio.payload, (v) => { S.studio.payload = v; autoRationale = null; }),
        makeGroup(t('darTitle'), ['2', '3.5', '4', '6', '7.6', '8'], String(S.studio.dar), (v) => { S.studio.dar = parseFloat(v); autoRationale = null; }, true),
        makeGroup(t('fcTitle'), [t('wtFc'), t('silFc')], S.studio.fc ? t('silFc') : t('wtFc'), (v) => { S.studio.fc = v.includes('LALA') || v.includes('침묵'); autoRationale = null; }),
        optBtn
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
      const initialStatus = animateScan
        ? (S.lang === 'ko' ? '최적화 탐색 중... 0%' : 'Optimizing... 0%')
        : (S.lang === 'ko' ? `안전성 ${sim.safetyScore}점 / 항암효능 ${sim.efficacyScore}점` : `Safety ${sim.safetyScore} / Efficacy ${sim.efficacyScore}`);

      const simStatusEl = h('span', { class: 'sim-canvas-status', text: initialStatus });
      const simHead = h('div', { class: 'sim-canvas-head' },
        h('span', { class: 'sim-canvas-title', text: t('paretoTitle') }),
        simStatusEl);

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
          h('div', { style: 'display:flex;align-items:center;gap:10px;flex-wrap:wrap' },
            h('span', { text: isOptimal ? t('optimalLocked') : `${t('optimalCand')} ${evalSpace.best.spec.target} + ${evalSpace.best.spec.payload} (DAR ${evalSpace.best.spec.dar})` }),
            h('button', {
              type: 'button', class: 'btn-compare-pop',
              text: t('viewCompareBtn'),
              onclick: () => openStudioCompareDrawer(sim, evalSpace),
            })),
          h('span', { style: 'font-size:10.5px;color:var(--dim);font-weight:600', text: isOptimal ? t('peakPareto') : t('clickAutoOpt') })),
        h('div', { class: 'srb-steps' },
          activeRationale.map(([title, choice, desc]) => h('div', { class: 'srb-step' },
            h('b', { text: `${title}: ${choice}` }),
            h('span', { text: desc })))));
      simWrap.append(rBox);

      // 2. Metrics Strip with 1-line explanations
      const hero = h('div', { class: 'studio-hero panel' },
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: t('shCompat') }),
          h('span', { class: 'sh-val ' + (handleMatch ? 't-green' : 't-amber'), text: handleMatch ? t('shCompatDirect') : t('shCompatSpacer') }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${handleMatch ? 100 : 50}%;background:${handleMatch ? 'var(--emerald)' : 'var(--amber)'}` })),
          h('span', { class: 'sh-desc', text: t('shCompatDesc') })),
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: t('shSelect') }),
          h('span', { class: 'sh-val', text: `+${tgt.selectivity.toFixed(1)} log2FC` }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${Math.min(100, tgt.selectivity * 16)}%;background:var(--accent)` })),
          h('span', { class: 'sh-desc', text: t('shSelectDesc') })),
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: t('shBystander') }),
          h('span', { class: 'sh-val', text: bystander ? t('shBystanderActive') : t('shBystanderAuto') }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${bystander ? 92 : 30}%;background:${bystander ? 'var(--accent)' : 'var(--dim)'}` })),
          h('span', { class: 'sh-desc', text: t('shBystanderDesc') })),
        h('div', { class: 'sh-metric' },
          h('span', { class: 'sh-kicker', text: t('shStability') }),
          h('span', { class: 'sh-val', text: `${stabilityScore}% ${t('shStabilityIntact')}` }),
          h('div', { class: 'sh-bar' }, h('i', { style: `width:${stabilityScore}%;background:var(--emerald)` })),
          h('span', { class: 'sh-desc', text: t('shStabilityDesc') })));

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
          h('span', { class: 'ex-name', text: S.lang === 'ko' ? (ORGAN_KO[item.organ] || SHORT[item.organ] || item.organ) : (SHORT[item.organ] || item.organ) }),
          h('span', { class: 'ex-track' }, h('i', { class: 'ex-fill', style: `width:${burden}%;background:${color}` })),
          h('span', { class: 'ex-val', style: `color:${color}`, text: `${burden} idx` })));
      });

      const gtexRows = h('div', { class: 'expr-list' });
      tgt.tissues.forEach((t) => {
        const val = t.tpm;
        const color = val > 50 ? 'var(--red)' : val >= 25 ? 'var(--amber)' : 'var(--emerald)';
        const tag = val > 50 ? (S.lang === 'ko' ? '주의' : 'High') : val >= 25 ? (S.lang === 'ko' ? '보통' : 'Moderate') : (S.lang === 'ko' ? '안전' : 'Safe');
        gtexRows.append(h('div', { class: 'expr-row' },
          h('span', { class: 'ex-name', text: S.lang === 'ko' ? (ORGAN_KO[t.organ] || SHORT[t.organ] || t.organ) : (SHORT[t.organ] || t.organ) }),
          h('span', { class: 'ex-track' }, h('i', { class: 'ex-fill', style: `width:${Math.min(100, val * 1.5)}%;background:${color}` })),
          h('span', { class: 'ex-val', style: `color:${color}`, text: `${val} nTPM (${tag})` })));
      });

      const grid2 = h('div', { class: 'studio-grid-2' },
        h('section', { class: 'studio-card panel' },
          h('h3', { text: t('simOrganTitle') }),
          organRows,
          h('p', { class: 'dim', style: 'margin:12px 0 0;font-size:11.5px', text: fcSilenced ? t('fcLalaNote') : t('fcWtNote') })),
        h('section', { class: 'studio-card panel' },
          h('h3', { text: `${t('gtexTitle')} (${tgt.gene})` }),
          gtexRows,
          h('p', { class: 'dim', style: 'margin:12px 0 0;font-size:11.5px', text: t('gtexNote') })));

      canvas.append(simWrap, hero, grid2);

      const optBtn = controls.querySelector('.btn-optimize');

      setTimeout(() => initParetoCanvas(cvs, sim, evalSpace, animateScan,
        (pct) => {
          simStatusEl.textContent = S.lang === 'ko' ? `최적화 탐색 중... ${pct}%` : `Optimizing... ${pct}%`;
          if (optBtn) optBtn.textContent = S.lang === 'ko' ? `최적화 중... ${pct}%` : `Optimizing... ${pct}%`;
        },
        () => {
          if (optBtn) optBtn.textContent = S.lang === 'ko' ? '최적화 완료 (100%)' : 'Optimized (100%)';
          setTimeout(() => {
            isOptimizing = false;
            if (animateScan) {
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
              openStudioCompareDrawer(best, evalSpace);
            }
          }, 700);
        }), 0);
    }

    function initParetoCanvas(cvs, currentSim, evalSpace, animate, onProgress, onComplete) {
      const rect = cvs.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const w = cvs.width = (rect.width || 600) * dpr;
      const h = cvs.height = (rect.height || 380) * dpr;
      const ctx = cvs.getContext('2d');
      if (!ctx) return;

      cancelAnimationFrame(simAnimId);
      const padL = 52 * dpr, padR = 24 * dpr, padT = 32 * dpr, padB = 44 * dpr;
      const maxPlotW = w - padL - padR;
      const maxPlotH = h - padT - padB;

      // 1:1 aspect ratio square plot box (never distorted!)
      const plotSize = Math.max(160 * dpr, Math.min(maxPlotW, maxPlotH));
      const plotW = plotSize;
      const plotH = plotSize;
      const offsetX = padL + (maxPlotW - plotW) / 2;
      const offsetY = padT + (maxPlotH - plotH) / 2;

      const cands = evalSpace.cands;
      const pareto = evalSpace.pareto;
      const best = evalSpace.best;

      // Dynamic auto-scaling bounds to spread candidates across canvas
      const safeties = cands.map((c) => c.safetyScore);
      const efficacies = cands.map((c) => c.efficacyScore);
      const minSafetyVal = Math.min(...safeties);
      const minEfficacyVal = Math.min(...efficacies);
      const minX = Math.max(0, Math.floor((minSafetyVal - 4) / 10) * 10);
      const maxX = 100;
      const minY = Math.max(0, Math.floor((minEfficacyVal - 4) / 10) * 10);
      const maxY = 100;
      const spanX = Math.max(10, maxX - minX);
      const spanY = Math.max(10, maxY - minY);

      const toX = (val) => offsetX + ((Math.max(minX, Math.min(maxX, val)) - minX) / spanX) * plotW;
      const toY = (val) => offsetY + (1 - (Math.max(minY, Math.min(maxY, val)) - minY) / spanY) * plotH;

      // Deterministic pseudo-random shuffle for progressive sampling dots
      const shuffled = cands.slice().map((c, i) => ({
        c,
        sortKey: Math.sin(i * 12345.67) * 10000 - Math.floor(Math.sin(i * 12345.67) * 10000),
      })).sort((a, b) => a.sortKey - b.sortKey).map((item) => item.c);

      let startTime = performance.now();
      const duration = (animate && !still()) ? 3500 : 0;

      function renderFrame(now) {
        const elapsed = now - startTime;
        const progress = duration > 0 ? Math.min(1, elapsed / duration) : 1;
        const pct = Math.min(100, Math.floor(progress * 100));
        if (animate && onProgress) onProgress(pct);

        // Clean white background
        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(0, 0, w, h);

        // Optimal quadrant subtle tint
        const qX = toX(Math.max(minX, 70));
        const qY = toY(100);
        const qW = toX(100) - qX;
        const qH = toY(Math.max(minY, 80)) - qY;
        ctx.fillStyle = 'rgba(16, 185, 129, 0.05)';
        ctx.fillRect(qX, qY, qW, qH);

        // Plot bounding box
        ctx.strokeStyle = '#CBD5E1';
        ctx.lineWidth = 1 * dpr;
        ctx.strokeRect(offsetX, offsetY, plotW, plotH);

        // Numeric Grid lines & ticks
        ctx.strokeStyle = '#F1F5F9';
        ctx.lineWidth = 1 * dpr;
        ctx.font = `600 ${9 * dpr}px monospace`;
        ctx.fillStyle = '#64748B';

        const stepX = spanX <= 40 ? 10 : 20;
        const stepY = spanY <= 40 ? 10 : 20;
        const xTicks = [];
        for (let v = minX; v <= maxX; v += stepX) xTicks.push(v);
        if (xTicks[xTicks.length - 1] !== maxX) xTicks.push(maxX);

        const yTicks = [];
        for (let v = minY; v <= maxY; v += stepY) yTicks.push(v);
        if (yTicks[yTicks.length - 1] !== maxY) yTicks.push(maxY);

        xTicks.forEach((v) => {
          const gx = toX(v);
          ctx.beginPath(); ctx.moveTo(gx, offsetY); ctx.lineTo(gx, offsetY + plotH); ctx.stroke();
          ctx.textAlign = 'center';
          ctx.fillText(String(v), gx, offsetY + plotH + 14 * dpr);
        });

        yTicks.forEach((v) => {
          const gy = toY(v);
          ctx.beginPath(); ctx.moveTo(offsetX, gy); ctx.lineTo(offsetX + plotW, gy); ctx.stroke();
          ctx.textAlign = 'right';
          ctx.fillText(String(v), offsetX - 7 * dpr, gy + 3 * dpr);
        });

        // Axis Titles (clean labels with no arrow)
        ctx.font = `bold ${10.5 * dpr}px sans-serif`;
        ctx.fillStyle = '#1E293B';
        ctx.textAlign = 'center';
        ctx.fillText(t('paretoSafetyX'), offsetX + plotW / 2, offsetY + plotH + 32 * dpr);

        ctx.save();
        ctx.translate(offsetX - 28 * dpr, offsetY + plotH / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(t('paretoEfficacyY'), 0, 0);
        ctx.restore();

        // Legend at top
        ctx.textAlign = 'left';
        ctx.font = `600 ${9.5 * dpr}px sans-serif`;
        ctx.fillStyle = '#64748B';
        ctx.beginPath(); ctx.arc(offsetX + 4 * dpr, offsetY - 14 * dpr, 3 * dpr, 0, Math.PI * 2); ctx.fill();
        ctx.fillText(`${t('legendCand')} (${cands.length})`, offsetX + 11 * dpr, offsetY - 11 * dpr);

        ctx.strokeStyle = '#0D9488';
        ctx.lineWidth = 2 * dpr;
        ctx.beginPath(); ctx.moveTo(offsetX + 130 * dpr, offsetY - 14 * dpr); ctx.lineTo(offsetX + 146 * dpr, offsetY - 14 * dpr); ctx.stroke();
        ctx.fillStyle = '#0D9488';
        ctx.fillText(t('legendPareto'), offsetX + 152 * dpr, offsetY - 11 * dpr);

        ctx.fillStyle = '#2563EB';
        ctx.beginPath(); ctx.arc(offsetX + 242 * dpr, offsetY - 14 * dpr, 4 * dpr, 0, Math.PI * 2); ctx.fill();
        ctx.fillText(t('legendCur'), offsetX + 250 * dpr, offsetY - 11 * dpr);

        // Progressive dot sampling: plot dots progressively at their true positions
        const visibleCount = Math.floor(cands.length * progress);
        for (let k = 0; k < visibleCount; k++) {
          const c = shuffled[k];
          const cx = toX(c.safetyScore);
          const cy = toY(c.efficacyScore);
          ctx.fillStyle = c.isCompat ? 'rgba(100, 116, 139, 0.45)' : 'rgba(239, 68, 68, 0.28)';
          ctx.beginPath();
          ctx.arc(cx, cy, 2.4 * dpr, 0, Math.PI * 2);
          ctx.fill();
        }

        // Progressive Pareto curve
        if (progress >= 0.25) {
          const curveFactor = Math.min(1, (progress - 0.25) / 0.75);
          const visParetoCount = Math.max(1, Math.floor(pareto.length * curveFactor));
          const visPareto = pareto.slice(0, visParetoCount);

          if (visPareto.length >= 1) {
            ctx.beginPath();
            visPareto.forEach((p, idx) => {
              const px = toX(p.safetyScore);
              const py = toY(p.efficacyScore);
              if (idx === 0) ctx.moveTo(px, py);
              else ctx.lineTo(px, py);
            });
            const lastP = visPareto[visPareto.length - 1];
            const firstP = visPareto[0];
            ctx.lineTo(toX(lastP.safetyScore), offsetY + plotH);
            ctx.lineTo(toX(firstP.safetyScore), offsetY + plotH);
            ctx.closePath();
            const aGrad = ctx.createLinearGradient(0, offsetY, 0, offsetY + plotH);
            aGrad.addColorStop(0, 'rgba(13, 148, 136, 0.14)');
            aGrad.addColorStop(1, 'rgba(13, 148, 136, 0.01)');
            ctx.fillStyle = aGrad;
            ctx.fill();

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
              ctx.lineWidth = 1.8 * dpr;
              ctx.beginPath(); ctx.arc(px, py, 3.4 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
            });
          }
        }

        // Highlight optimal best candidate once reached or when static
        if (progress >= 0.95 || !animate) {
          const bx = toX(best.safetyScore);
          const by = toY(best.efficacyScore);
          ctx.fillStyle = 'rgba(13, 148, 136, 0.22)';
          ctx.beginPath(); ctx.arc(bx, by, 10 * dpr, 0, Math.PI * 2); ctx.fill();

          ctx.fillStyle = '#0D9488';
          ctx.strokeStyle = '#FFFFFF';
          ctx.lineWidth = 2 * dpr;
          ctx.beginPath(); ctx.arc(bx, by, 5 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();

          ctx.font = `bold ${9.5 * dpr}px sans-serif`;
          ctx.fillStyle = '#065F46';
          const alignRight = bx > offsetX + plotW - 130 * dpr;
          ctx.textAlign = alignRight ? 'right' : 'left';
          ctx.fillText(`${S.lang === 'ko' ? '최적설계' : 'Optimal'}: ${best.spec.target.split(' ')[0]} + ${best.spec.payload.split(' ')[0]} (DAR ${best.spec.dar})`, bx + (alignRight ? -8 * dpr : 8 * dpr), by - 6 * dpr);
        }

        // Current active selection marker
        const curSim = animate && progress >= 0.98 ? best : currentSim;
        const sx = toX(curSim.safetyScore);
        const sy = toY(curSim.efficacyScore);
        ctx.fillStyle = 'rgba(37, 99, 235, 0.2)';
        ctx.beginPath(); ctx.arc(sx, sy, 10 * dpr, 0, Math.PI * 2); ctx.fill();

        ctx.fillStyle = '#2563EB';
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 2 * dpr;
        ctx.beginPath(); ctx.arc(sx, sy, 5 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();

        ctx.font = `bold ${9.5 * dpr}px sans-serif`;
        ctx.fillStyle = '#1E40AF';
        const curAlignRight = sx > offsetX + plotW - 120 * dpr;
        ctx.textAlign = curAlignRight ? 'right' : 'left';
        ctx.fillText(`${S.lang === 'ko' ? '현재선택' : 'Current'} (${curSim.safetyScore}, ${curSim.efficacyScore})`, sx + (curAlignRight ? -8 * dpr : 8 * dpr), sy + 14 * dpr);

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
          h('h2', { class: 'flowsheet-title', text: t('flowTitle') }),
          h('span', { class: 'flowsheet-sub', text: t('flowSub') })));

      const groupEl = h('div', { class: 'lab-card-group' });
      BIO_FIELDS.forEach((bf) => {
        const valStr = S.raw[bf.key];
        const valNum = parseFloat(valStr);
        const hasVal = !isNaN(valNum);

        let statusClass = 'empty';
        let statusText = t('notEntered');
        let needlePos = 50;

        if (hasVal) {
          const span = (bf.refHigh - bf.refLow) * 2.2;
          const minRange = Math.max(0, bf.refLow - span * 0.25);
          const maxRange = bf.refHigh + span * 0.75;
          needlePos = Math.max(3, Math.min(97, ((valNum - minRange) / (maxRange - minRange)) * 100));

          if (valNum > bf.refHigh * 1.5 || valNum < bf.refLow * 0.7) {
            statusClass = 'alarm'; statusText = t('elevated');
          } else if (valNum > bf.refHigh || valNum < bf.refLow) {
            statusClass = 'warn'; statusText = t('borderline');
          } else {
            statusClass = 'normal'; statusText = t('normal');
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
        const labName = S.lang === 'ko' ? (LAB_KO[bf.key] || bf.name) : bf.name;

        const row = h('div', { class: 'bio-row' },
          h('div', { class: 'bio-info' },
            h('span', { class: 'bio-name', text: labName }),
            h('span', { class: 'bio-ref', text: `${t('refRange')}: ${bf.refLow} - ${bf.refHigh} ${bf.unit}` })),
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
      rightPanel.append(h('h3', { class: 'linkage-title', text: t('organLinkage') }));
      const activeOrgans = activeOrgansWithScores();
      const linkageList = h('div', { class: 'linkage-list' });

      if (activeOrgans.length) {
        activeOrgans.forEach((ao) => {
          const orgLabel = S.lang === 'ko' ? (ORGAN_KO[ao.organ] || SHORT[ao.organ] || ao.organ) : (SHORT[ao.organ] || ao.organ);
          linkageList.append(h('div', { class: 'linkage-card' },
            h('div', { class: 'linkage-head' },
              h('span', { class: 'linkage-organ', text: orgLabel }),
              h('span', { class: 'linkage-source', text: `${Math.round(ao.score * 100)}% ${t('riskWeight')}` })),
            h('span', { class: 'linkage-why', text: ao.condKey ? `${t('triggeredDiag')}: ${condName(ao.condKey)}` : t('triggeredLab') })));
        });
      } else {
        linkageList.append(h('span', { class: 'dim', text: t('noActiveTriggers') }));
      }
      rightPanel.append(linkageList);
    }

    renderFlowsheet();
    return box;
  }

  // ------------------------------------------------------------------ 3D ADC Molecular Canvas Renderer
  const ADC_SPECS = {
    'trastuzumab-deruxtecan': { brand: 'ENHERTU', target: 'HER2', dar: 8, payload: 'DXd', payloadClass: 'Topo I inhibitor', payloadColor: '#06B6D4', paratopeColor: '#38BDF8', linker: 'GGFG (Tetrapeptide)', linkerLength: 22, linkerType: 'cleavable' },
    'sacituzumab-govitecan': { brand: 'TRODELVY', target: 'TROP2', dar: 8, payload: 'SN-38', payloadClass: 'Topo I inhibitor', payloadColor: '#10B981', paratopeColor: '#F472B6', linker: 'CL2A (pH-sensitive)', linkerLength: 19, linkerType: 'cleavable' },
    'datopotamab-deruxtecan': { brand: 'DATO-DXd', target: 'TROP2', dar: 4, payload: 'DXd', payloadClass: 'Topo I inhibitor', payloadColor: '#06B6D4', paratopeColor: '#F472B6', linker: 'GGFG (Tetrapeptide)', linkerLength: 22, linkerType: 'cleavable' },
    'trastuzumab-emtansine': { brand: 'KADCYLA', target: 'HER2', dar: 4, payload: 'DM1', payloadClass: 'Maytansinoid', payloadColor: '#F59E0B', paratopeColor: '#38BDF8', linker: 'SMCC (Thioether)', linkerLength: 11, linkerType: 'non-cleavable' },
    'enfortumab-vedotin': { brand: 'PADCEV', target: 'Nectin-4', dar: 4, payload: 'MMAE', payloadClass: 'Auristatin', payloadColor: '#8B5CF6', paratopeColor: '#FBBF24', linker: 'vc-PABC (Protease)', linkerLength: 18, linkerType: 'cleavable' },
    'polatuzumab-vedotin': { brand: 'POLIVY', target: 'CD79b', dar: 4, payload: 'MMAE', payloadClass: 'Auristatin', payloadColor: '#8B5CF6', paratopeColor: '#34D399', linker: 'vc-PABC (Protease)', linkerLength: 18, linkerType: 'cleavable' },
    'brentuximab-vedotin': { brand: 'ADCETRIS', target: 'CD30', dar: 4, payload: 'MMAE', payloadClass: 'Auristatin', payloadColor: '#8B5CF6', paratopeColor: '#FB923C', linker: 'vc-PABC (Protease)', linkerLength: 18, linkerType: 'cleavable' },
    'tisotumab-vedotin': { brand: 'TIVDAK', target: 'Tissue Factor', dar: 4, payload: 'MMAE', payloadClass: 'Auristatin', payloadColor: '#8B5CF6', paratopeColor: '#A78BFA', linker: 'vc-PABC (Protease)', linkerLength: 18, linkerType: 'cleavable' },
    'belantamab-mafodotin': { brand: 'BLENREP', target: 'BCMA', dar: 4, payload: 'MMAF', payloadClass: 'Charged Auristatin', payloadColor: '#6366F1', paratopeColor: '#C084FC', linker: 'mc (Maleimidocaproyl)', linkerLength: 10, linkerType: 'non-cleavable' },
    'mirvetuximab-soravtansine': { brand: 'ELAHERE', target: 'FRalpha', dar: 4, payload: 'DM4', payloadClass: 'Maytansinoid', payloadColor: '#D97706', paratopeColor: '#E879F9', linker: 'sulfo-SPDB (Disulfide)', linkerLength: 16, linkerType: 'cleavable' },
    'loncastuximab-tesirine': { brand: 'ZYNLONTA', target: 'CD19', dar: 2, payload: 'SG3199', payloadClass: 'PBD Dimer', payloadColor: '#F43F5E', paratopeColor: '#2DD4BF', linker: 'val-ala-PEG8', linkerLength: 24, linkerType: 'cleavable' },
    'gemtuzumab-ozogamicin': { brand: 'MYLOTARG', target: 'CD33', dar: 3, payload: 'Calicheamicin', payloadClass: 'DNA Cleaver', payloadColor: '#E11D48', paratopeColor: '#F87171', linker: 'AcBut Hydrazone', linkerLength: 15, linkerType: 'cleavable' },
    'inotuzumab-ozogamicin': { brand: 'BESPONSA', target: 'CD22', dar: 6, payload: 'Calicheamicin', payloadClass: 'DNA Cleaver', payloadColor: '#E11D48', paratopeColor: '#818CF8', linker: 'AcBut Hydrazone', linkerLength: 15, linkerType: 'cleavable' },
  };

  let adcAnimId = 0;
  function init3dAdcCanvas(cvs, adcRow) {
    const rect = cvs.getBoundingClientRect();
    const w = cvs.width = (rect.width || 400) * (window.devicePixelRatio || 1);
    const h = cvs.height = (rect.height || 240) * (window.devicePixelRatio || 1);
    const ctx = cvs.getContext('2d');
    if (!ctx) return;

    cancelAnimationFrame(adcAnimId);
    const dpr = window.devicePixelRatio || 1;
    let rotY = 0.45;
    let rotX = 0.22;
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

    const adcId = (adcRow && (adcRow.adc || adcRow.id)) || '';
    const m = (adcRow && MECH[adcId]) || {};
    const spec = ADC_SPECS[adcId] || {};

    const drugName = (adcRow && (adcRow.name || adcRow.drug || m.brand || adcId)) || 'Antibody-Drug Conjugate';
    const brand = spec.brand || m.brand || (adcRow && adcRow.brand) || '';
    const target = spec.target || m.target || (adcRow && adcRow.target) || 'HER2';
    const payload = spec.payload || m.payload || (adcRow && adcRow.payload) || 'Payload';
    const payloadClass = spec.payloadClass || m.payload_family || 'Cytotoxin';
    const linker = spec.linker || m.linker || (adcRow && adcRow.linker) || 'Linker';
    const darCount = Math.max(1, Math.min(8, Math.round(parseFloat(spec.dar || m.dar || (adcRow && adcRow.dar) || 4))));
    const payloadColor = (adcRow && adcRow.payloadColor) || spec.payloadColor || '#10B981';
    const paratopeColor = (adcRow && adcRow.paratopeColor) || spec.paratopeColor || '#38BDF8';
    const isCleavable = adcRow && adcRow.linkerType ? adcRow.linkerType === 'cleavable' : (spec.linkerType !== 'non-cleavable' && m.linker_cleavable !== 'False');
    const linkerLength = (adcRow && adcRow.linkerLength) || spec.linkerLength || (isCleavable ? 18 : 11);

    // Molecular nodes: Y-shaped IgG1 antibody + Linker/Payload spheres with fixed IDs
    const nodes = [
      // Fc stem (bottom center)
      { id: 'fc2', x: 0, y: 35, z: 0, r: 8, col: '#475569', type: 'Fc' },
      { id: 'fc1', x: 0, y: 15, z: 0, r: 7.2, col: '#475569', type: 'Fc' },
      // Hinge region
      { id: 'hinge', x: 0, y: -5, z: 0, r: 6.2, col: '#2563EB', type: 'Hinge' },
      // Fab Arm Left
      { id: 'fab_l1', x: -24, y: -24, z: 5, r: 7, col: '#334155', type: 'Fab' },
      { id: 'fab_l2', x: -44, y: -44, z: 10, r: 7.8, col: '#334155', type: 'Fab' },
      { id: 'para_l', x: -55, y: -55, z: 12, r: 5.4, col: paratopeColor, type: 'Paratope' },
      // Fab Arm Right
      { id: 'fab_r1', x: 24, y: -24, z: -5, r: 7, col: '#334155', type: 'Fab' },
      { id: 'fab_r2', x: 44, y: -44, z: -10, r: 7.8, col: '#334155', type: 'Fab' },
      { id: 'para_r', x: 55, y: -55, z: -12, r: 5.4, col: paratopeColor, type: 'Paratope' },
    ];

    // Explicit Linker-tethered payload branches based on true DAR
    const conjAnchors = ['hinge', 'fab_l1', 'fab_r1', 'hinge', 'fab_l2', 'fab_r2', 'fab_l1', 'fab_r1'];
    for (let k = 0; k < darCount; k++) {
      const angle = (k / darCount) * Math.PI * 2;
      const radius = 28 + (k % 2) * 8 + (linkerLength * 0.4);
      const py = -10 + (k % 3) * 14;
      const anchor = conjAnchors[k % conjAnchors.length];
      const pldRadius = payloadClass.includes('PBD') || payloadClass.includes('DNA') ? 6.8 : (payloadClass.includes('Topo') ? 6.0 : 5.4);
      nodes.push({
        id: 'pld_' + k,
        anchor,
        x: Math.cos(angle) * radius,
        y: py,
        z: Math.sin(angle) * radius,
        r: pldRadius,
        col: payloadColor,
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
        y: h / 2 + y2 * scale * 1.8 * dpr + 4 * dpr,
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
        ctx.beginPath(); ctx.moveTo(w * 0.08, y); ctx.lineTo(w * 0.92, y); ctx.stroke();
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
      const pL1 = projMap['fab_l1'], pL2 = projMap['fab_l2'], pParaL = projMap['para_l'];
      const pR1 = projMap['fab_r1'], pR2 = projMap['fab_r2'], pParaR = projMap['para_r'];

      if (pFc2 && pFc1 && pH && pL1 && pL2 && pParaL && pR1 && pR2 && pParaR) {
        ctx.beginPath();
        ctx.moveTo(pFc2.x, pFc2.y); ctx.lineTo(pFc1.x, pFc1.y); ctx.lineTo(pH.x, pH.y);
        ctx.lineTo(pL1.x, pL1.y); ctx.lineTo(pL2.x, pL2.y); ctx.lineTo(pParaL.x, pParaL.y);
        ctx.moveTo(pH.x, pH.y);
        ctx.lineTo(pR1.x, pR1.y); ctx.lineTo(pR2.x, pR2.y); ctx.lineTo(pParaR.x, pParaR.y);
        ctx.stroke();
      }

      // Draw linker tether lines from conjugation anchors to payload spheres
      ctx.strokeStyle = isCleavable ? '#F59E0B' : '#94A3B8';
      ctx.lineWidth = isCleavable ? 1.6 * dpr : 2.2 * dpr;
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
          ctx.fillStyle = payloadColor + '33';
          ctx.fill();
        }
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(1, p.r), 0, Math.PI * 2);
        ctx.fillStyle = p.col;
        ctx.fill();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.lineWidth = 0.9 * dpr;
        ctx.stroke();
      });

      // Top Construct Header Overlay (clean title, no collisions)
      ctx.font = `bold ${10.5 * dpr}px sans-serif`;
      ctx.fillStyle = '#F8FAFC';
      ctx.textAlign = 'left';
      ctx.fillText(brand ? `${brand} (${drugName})` : drugName, 12 * dpr, 18 * dpr);

      adcAnimId = requestAnimationFrame(render3d);
    }

    adcAnimId = requestAnimationFrame(render3d);
  }

  function build3dLegend(row) {
    const adcId = (row && (row.adc || row.id)) || '';
    const m = (row && MECH[adcId]) || {};
    const spec = ADC_SPECS[adcId] || {};
    const target = (row && row.target) || spec.target || m.target || 'HER2';
    const payload = (row && row.payload) || spec.payload || m.payload || 'Payload';
    const darCount = Math.max(1, Math.min(8, Math.round(parseFloat((row && row.dar) || spec.dar || m.dar || 4))));
    const payloadColor = (row && row.payloadColor) || spec.payloadColor || '#10B981';
    const paratopeColor = (row && row.paratopeColor) || spec.paratopeColor || '#38BDF8';
    const isCleavable = row && row.linkerType ? row.linkerType === 'cleavable' : (spec.linkerType !== 'non-cleavable' && m.linker_cleavable !== 'False');

    const items = [
      ['#334155', 'IgG1 Backbone'],
      [paratopeColor, `Paratope (${target})`],
      [isCleavable ? '#F59E0B' : '#94A3B8', `Linker (${isCleavable ? 'Cleavable' : 'Direct'})`],
      [payloadColor, `${payload} (x${darCount})`],
    ];

    return h('div', { class: 'adc-3d-legend' },
      items.map(([col, txt]) => h('span', { class: 'adc-3d-legend-item' },
        h('i', { class: 'adc-3d-legend-dot', style: `background:${col}` }),
        h('span', { text: txt }))));
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
      return b === '-' ? t('appliesToAll') : b;
    };
    const secRestriction = section(t('labelRestriction'), rs.length ? h('div', { class: 'rsl' }, rs.map((r) => h('div', { class: 'rr' },
      h('div', { class: 'rh' },
        h('span', { class: 'k', text: S.lang === 'ko' ? (ORGAN_KO[r.organ] || SHORT[r.organ] || r.organ) : (SHORT[r.organ] || r.organ) }),
        h('span', { class: `s t-${TONE[r.code] || 'dim'}`, text: r.status })),
      h('div', { class: 'pl' },
        r.patient ? [h('span', { class: 'pk', text: S.lang === 'ko' ? '환자 상태' : 'Patient' }), h('span', { class: 'pv', text: r.patient })] : null,
        h('span', { class: 'pk', text: S.lang === 'ko' ? 'FDA 기준' : 'FDA Rule' }), h('span', { class: 'lv2', text: ruleText(r) })))))
      : h('p', { class: 'dim', text: t('noLabelRestriction') }));

    // 2. Warnings on Patient's Active Organs
    const ws = d.warnings || [];
    const secPatientWarn = section(t('patientWarnTitle'), ws.length ? h('div', { class: 'wl' }, ws.map((w) => [
      h('span', { class: 'k', text: S.lang === 'ko' ? (ORGAN_KO[w.organ] || SHORT[w.organ] || w.organ) : (SHORT[w.organ] || w.organ) }),
      h('span', { class: 'm ' + ((w.mark || '').trim() === '!!' ? 't-red' : 't-amber'), text: (w.mark || '').trim() }),
      h('span', { text: (w.text || '').replace(/;\s*/g, ', ') }),
    ])) : h('p', { class: 'dim', text: t('noPatientWarn') }));

    const secChecks = (d.checks || []).length ? section(t('preCheckTitle'), h('ul', { class: 'dash' }, d.checks.map((c) => h('li', { text: c })))) : null;
    const secMissing = (d.missing || []).length ? section(t('missingInputTitle'),
      h('ul', { class: 'dash' }, d.missing.map((m) => h('li', { text: m }))),
      h('button', { type: 'button', class: 'review-link', text: t('enterLabBtn'), onclick: () => { closeDrawer(); switchMode(2); } })) : null;

    // 3. Pivotal Trial Study Tab
    const tr = d.trial && d.trial.trial && !d.trial.no_results ? d.trial : null;
    const compReg = (tr && tr.comparator && tr.comparator.regimen) || (S.lang === 'ko' ? '대조군' : 'Control');
    const compN = tr && tr.comparator && tr.comparator.n ? ` (n=${tr.comparator.n})` : '';
    const trialSummaryCard = tr ? h('div', { class: 'trial-summary-card' },
      h('p', { style: 'margin:0 0 6px;font-weight:800;font-size:13.5px;color:var(--ink-hi)', text: `${tr.trial}${tr.phase ? ' (Phase ' + tr.phase + ' Registration Trial)' : ''}` }),
      h('p', { class: 'dim', style: 'margin:0 0 6px;font-size:12px', text: tr.population || 'Patient cohort not specified' }),
      h('p', { style: 'margin:0 0 4px;font-size:12px;font-weight:600', text: `${t('treatmentArm')}: ${tr.regimen || ''} (n=${tr.n || 0})` }),
      tr.comparator ? h('p', { class: 'dim', style: 'margin:0 0 8px;font-size:12px', text: `${t('controlArm')}: ${compReg}${compN}` }) : null,
      /^NCT\d{8}$/.test(tr.nct || '') ? h('a', { class: 'review-link', href: 'https://clinicaltrials.gov/study/' + tr.nct, target: '_blank', rel: 'noopener noreferrer', text: `ClinicalTrials.gov ${tr.nct} ↗` }) : null
    ) : h('p', { class: 'dim', text: (d.trial && d.trial.no_results) || t('singleArmTrial') });

    const trialEvents = [];
    for (const o of (tr && tr.organs) || []) {
      for (const e of o.events || []) {
        trialEvents.push(h('div', { class: 'trial-event' },
          buildDualBar({ trial: tr, organ: o.organ, ev: e }),
          h('div', { class: 'event-values', style: 'margin-top:6px' },
            h('span', null, h('b', { text: `${e.a}/${e.n}` }), ' ' + t('treatmentArm')),
            e.comp ? h('span', null, h('b', { text: `${e.comp[0]}/${e.comp[1]}` }), ' ' + t('controlArm')) : null)));
      }
    }
    const secStudy = section(t('trialContext'), trialSummaryCard, ...trialEvents);

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
      h('span', { class: 'adc-3d-hint', text: t('rotateHint') }));

    const secStructure3d = section(t('struct3dTitle'),
      wrap3d,
      build3dLegend(row),
      kvRows.length ? h('div', { class: 'kv3' }, kvRows.map(([k, v]) => [h('span', { class: 'k', text: k }), h('span', { text: v })])) : null,
      h('button', {
        type: 'button', class: 'review-link', style: 'margin-top:10px',
        text: t('tuneStudio'),
        onclick: () => { closeDrawer(); switchMode(1); },
      }));

    const secInd = section('FDA Approved Indications',
      d.indication ? h('ul', { class: 'ind' }, d.indication.split(/;\s*/).filter(Boolean).map((x) => h('li', { text: x }))) : null);

    const tabDefs = [
      { id: 'Patient', label: t('tabPatient'), secs: [secRestriction, secPatientWarn, secChecks, secMissing].filter(Boolean) },
      { id: 'Study', label: t('tabStudy'), secs: [secStudy].filter(Boolean) },
      { id: 'Structure', label: t('tabStructure'), secs: [secStructure3d, secInd].filter(Boolean) },
    ];

    const nav = h('div', { class: 'evidence-tabs', role: 'group', 'aria-label': 'Evidence tabs' });
    const allSecs = tabDefs.flatMap((td) => td.secs);

    function switchTab(id) {
      S.drawerTab = id;
      tabDefs.forEach((td) => {
        const active = td.id === id;
        td.secs.forEach((s) => { s.hidden = !active; });
      });
      [...nav.children].forEach((b) => b.setAttribute('aria-pressed', b.dataset.tabId === id ? 'true' : 'false'));
      if (id === 'Structure') {
        setTimeout(() => init3dAdcCanvas(cvs3d, row), 50);
      }
    }

    tabDefs.forEach((td) => {
      nav.append(h('button', {
        type: 'button', text: td.label, 'data-tab-id': td.id,
        onclick: () => switchTab(td.id),
      }));
    });

    drawerBody.append(nav, ...allSecs);
    const initialTab = ['Patient', 'Study', 'Structure'].includes(S.drawerTab) ? S.drawerTab : 'Patient';
    switchTab(initialTab);
  }

  const CLINICAL_DERISK_DB = {
    'HER2 (ERBB2)': {
      ko: [
        {
          title: '간질성 폐질환(ILD) 및 폐렴 완화 (Boxed Warning 극복)',
          desc: '엔허투(Enhertu)의 가장 치명적인 부작용인 ILD(발생률 ~10-15%, 5등급 사망 사례 보고)는 높은 DAR 8과 미침묵 Fc의 폐포 대식세포 비특이적 흡수가 주요 기전입니다. 본 신규 설계는 DAR 3.5~4 최적화와 LALA-PG Fc 침묵화를 적용하여 대식세포 비특이 섭취를 차단하고 폐 독성을 획기적으로 낮춥니다.',
        },
        {
          title: '심실 박출률(LVEF) 감소 및 심근 독성 예방',
          desc: 'HER2 심근 미세 발현에 따른 표적 의존성 및 비표적 페이로드 노출을 혈장 고안정성 GGFG 링커(88% 유지)를 통해 차단하여 심부전 위험을 예방합니다.',
        },
      ],
      en: [
        {
          title: 'Interstitial Lung Disease (ILD) / Pneumonitis Mitigation',
          desc: 'Enhertu boxed warning ILD (10-15% incidence with fatal cases) is driven by high DAR 8 aggregation and Fc-gamma receptor uptake by alveolar macrophages. De Novo DAR optimization and LALA-PG Fc silencing suppress macrophage uptake while preserving active bystander tumor killing.',
        },
        {
          title: 'Cardiotoxicity / LVEF Ejection Fraction Protection',
          desc: 'Restricts off-target systemic free DXd exposure on cardiac myocytes via 88% intact tetrapeptide plasma linker stability.',
        },
      ],
    },
    'TROP2 (TACSTD2)': {
      ko: [
        {
          title: '중증 호중구감소증 및 골수억제 완화 (Boxed Warning 극복)',
          desc: '트로델비(Trodelvy)의 3/4등급 호중구감소증(51%)은 pH-민감성 CL2A 링커의 빠른 혈장 가수분해(체내 조기 해리)로 인한 유리 SN-38 노출 때문입니다. 신규 설계의 GGFG 링커는 혈장 안정도 88%로 순환 중 누출을 막고 종양 리소좀 내에서만 선택 분해됩니다.',
        },
        {
          title: '중증 설사 및 위장관 독성 감소',
          desc: '혈중 비특이적 유리 페이로드 방출을 최소화하여 장점막 상피세포 파괴와 조기 분비성 설사 위험을 대폭 줄였습니다.',
        },
      ],
      en: [
        {
          title: 'Severe Neutropenia & Myelosuppression Mitigation',
          desc: 'Trodelvy boxed warning neutropenia (grade 3/4 ~51%) stems from premature CL2A linker hydrolysis releasing free SN-38 in circulation. De Novo stable GGFG tetrapeptide linker (88% intact) prevents premature shedding.',
        },
        {
          title: 'Severe Diarrhea & GI Mucosal Sparing',
          desc: 'Minimizes circulating free topoisomerase-1 inhibitor exposure, sparing intestinal epithelium and reducing severe diarrhea.',
        },
      ],
    },
    'Nectin-4': {
      ko: [
        {
          title: '중증 피부 부작용(SCAR, SJS/TEN) 완화',
          desc: '패드셉(Padcev)의 박스 경고인 스티븐스-존슨 증후군(SJS/TEN) 등 치명적 표피 괴사는 높은 유리 MMAE 피부 축적에서 기인합니다. 최적화된 효소 절단 제어와 제어된 접합비로 표피 세포 독성을 경감합니다.',
        },
        {
          title: '고혈당증 및 말초신경병증 감소',
          desc: '정상 췌장/말초신경으로의 비표적 축적을 억제하여 전신 부작용 프로파일을 개선했습니다.',
        },
      ],
      en: [
        {
          title: 'Severe Cutaneous Adverse Reactions (SCAR) / SJS Mitigation',
          desc: 'Padcev boxed warning for SJS/TEN and severe skin reactions is attenuated by reducing circulating free auristatin burden.',
        },
        {
          title: 'Peripheral Neuropathy Reduction',
          desc: 'Reduces cumulative axonal microtubule disruption by tuning payload burden.',
        },
      ],
    },
    'CD79b': {
      ko: [
        {
          title: '말초 감각 및 운동 신경병증(Peripheral Neuropathy) 완화',
          desc: '폴라이비(Polivy)의 주된 용량 제한 독성인 말초신경병증을 DAR 조절과 미세소관 억제제 누출 방지를 통해 완화합니다.',
        },
        {
          title: '혈소판감소증 및 혈액학적 안전성 확보',
          desc: '골수 조혈모세포에 대한 비표적 세포독성을 억제하여 혈구 수치 급감 위험을 방지합니다.',
        },
      ],
      en: [
        {
          title: 'Peripheral Neuropathy De-Risking',
          desc: 'Polivy dose-limiting peripheral neuropathy is mitigated through optimized payload conjugation ratio and stable cleavage kinetics.',
        },
        {
          title: 'Hematologic Stability',
          desc: 'Prevents bone marrow suppression and severe thrombocytopenia in vulnerable patients.',
        },
      ],
    },
    'BCMA (TNFRSF17)': {
      ko: [
        {
          title: '각막 미세낭종 상피 각막병증(Ocular Keratopathy) 회피 (Boxed Warning 극복)',
          desc: '블렌렙(Blenrep)의 시력 손상 박스 경고는 비절단성 mc 링커와 야생형 Fc가 각막 상피세포에 대식작용으로 유입되어 발생합니다. LALA-PG Fc 침묵화와 절단성 링커 설계를 통해 각막 세포 축적을 원천 차단합니다.',
        },
      ],
      en: [
        {
          title: 'Corneal Microcystic Epithelial Keratopathy Mitigation',
          desc: 'Blenrep boxed warning for visual acuity loss is driven by non-cleavable MMAF macropinocytosis in corneal epithelium. Fc silencing and enzymatic linker prevent ocular tissue entrapment.',
        },
      ],
    },
    'FRalpha (FOLR1)': {
      ko: [
        {
          title: '각막 독성 및 간질성 폐렴 발생 억제',
          desc: '엘라히어(Elahere)의 메이탄시노이드 DM4 각막 침착 및 폐 독성을 정밀 절단성 링커와 최적화된 DAR 설계를 통해 완화합니다.',
        },
      ],
      en: [
        {
          title: 'Ocular Keratopathy & Pneumonitis De-Risking',
          desc: 'Prevents corneal epithelial deposition of maytansinoid payload and suppresses pulmonary macrophage inflammation.',
        },
      ],
    },
  };

  function fillStudioCompareDrawer(simInput, evalSpaceInput) {
    const sim = simInput || computeStudioSimulation();
    const isKo = S.lang === 'ko';

    const tgt = sim.tgt || STUDIO_TARGETS[0];
    const lnk = sim.lnk || STUDIO_LINKERS[0];
    const pld = sim.pld || STUDIO_PAYLOADS[0];
    const dar = Number(sim.dar || (sim.spec && sim.spec.dar) || 4);
    const fcSilenced = Boolean(sim.fcSilenced !== undefined ? sim.fcSilenced : (sim.spec && sim.spec.fc));

    const refAdcId = (tgt && tgt.refAdc) || 'trastuzumab-deruxtecan';
    const refSpec = ADC_SPECS[refAdcId] || {};
    const refMech = MECH[refAdcId] || {};
    const refRow = (S.result && S.result.data && S.result.data.rows && S.result.data.rows.find((r) => r.adc === refAdcId)) || null;

    const refBrand = (refRow && refRow.brand) || refSpec.brand || refMech.brand || refAdcId;
    const refName = (refRow && refRow.name) || (refSpec.brand ? `${refSpec.brand} (${refAdcId})` : refAdcId);
    const deNovoName = `De Novo ${tgt.gene || tgt.id.split(' ')[0]}-${pld.id.split(' ')[0]}`;
    const deNovoSub = `DAR ${dar} / ${fcSilenced ? (isKo ? 'Fc 침묵화 (LALA-PG)' : 'Fc-Silenced (LALA-PG)') : (isKo ? '야생형 IgG1' : 'Wild-type IgG1')}`;

    drawerTitle.textContent = isKo
      ? `신규 최적설계 vs 기존 승인 약물 (${refBrand})`
      : `De Novo Design vs Approved (${refBrand})`;
    clear(drawerBody);
    drawerBody.scrollTop = 0;

    // 1. Hero Comparison Cards
    const secCompareHero = h('div', { class: 'compare-hero' },
      h('div', { class: 'compare-hero-col denovo' },
        h('span', { class: 'ch-badge', text: isKo ? 'AI 신규 최적 설계' : 'AI De Novo Design' }),
        h('span', { class: 'ch-name', text: deNovoName }),
        h('span', { class: 'ch-sub', text: deNovoSub }),
        h('span', { class: 'ch-score', text: isKo ? `안전성 ${sim.safetyScore}점 / 효능 ${sim.efficacyScore}점` : `Safety ${sim.safetyScore} / Efficacy ${sim.efficacyScore}` })),
      h('div', { class: 'compare-hero-col' },
        h('span', { class: 'ch-badge', text: isKo ? '기존 FDA 승인 벤치마크' : 'Approved FDA Benchmark' }),
        h('span', { class: 'ch-name', text: refBrand || refName }),
        h('span', { class: 'ch-sub', text: `${refSpec.linker || refMech.linker || 'Linker'} / DAR ${refSpec.dar || refMech.dar || 4}` }),
        h('span', { class: 'ch-score', style: 'color:var(--dim)', text: refMech.boxed_warnings ? (isKo ? `주요 경고: ${refMech.boxed_warnings}` : `Boxed: ${refMech.boxed_warnings}`) : (isKo ? 'FDA 허가 임상 승인' : 'Standard of Care') })));

    // 2. Structured Side-by-side Spec Table
    const tableRows = [
      [
        t('compTarget'),
        `${tgt.id} (선택도 +${tgt.selectivity.toFixed(1)} log2FC)`,
        refSpec.target || refMech.target || tgt.id,
        isKo ? '정상조직 비특이 결합 최소화' : 'Maximizes tumor selectivity margin',
      ],
      [
        t('compLinker'),
        `${lnk.id} (${lnk.cleavable ? (isKo ? '효소절단형' : 'Cleavable') : (isKo ? '비절단형' : 'Non-cleavable')}, 안정도 ${lnk.stability}%)`,
        refSpec.linker || refMech.linker || 'Standard Linker',
        isKo ? '혈장 내 조기 분해 누출 방지 (88% 유지)' : 'High plasma stability prevents shedding',
      ],
      [
        t('compPayload'),
        `${pld.id} (${pld.family || pld.cls})`,
        refSpec.payload || refMech.payload || 'Cytotoxin',
        isKo ? (sim.bystander ? '활성 동반 사멸로 인접 암세포 침투' : '강력한 세포독성') : 'Potent tumoricidal bystander killing',
      ],
      [
        t('compDar'),
        `DAR ${dar}`,
        `DAR ${refSpec.dar || refMech.dar || 4}`,
        isKo ? '친수성 최적화로 간/폐 대식세포 급속 소실 방지' : 'Balanced DAR avoids aggregation and rapid clearance',
      ],
      [
        t('compFc'),
        fcSilenced ? (isKo ? 'Fc 침묵화 (LALA-PG)' : 'Fc-Silenced (LALA-PG)') : (isKo ? '야생형 IgG1 (Wild-type)' : 'Wild-type IgG1'),
        isKo ? '야생형 IgG1 (Wild-type)' : 'Wild-type IgG1',
        isKo ? 'FcγR 매개 폐포/각막 대식세포 침착 억제' : 'Abolishes Fc-gamma-R macrophage uptake',
      ],
      [
        t('compSafety'),
        `${sim.safetyScore} / 100`,
        `~${Math.max(25, Math.min(80, sim.safetyScore - 18))} / 100`,
        isKo ? '환자 취약 활성 장기 독성 위험 대폭 경감' : 'Significant organ toxicity reduction',
      ],
      [
        t('compEfficacy'),
        `${sim.efficacyScore} / 100`,
        `~${Math.max(30, Math.min(95, sim.efficacyScore - 5))} / 100`,
        isKo ? '종양 내 유효 농도 유지 및 지속 사멸' : 'High tumor potency maintained',
      ],
    ];

    const tblEl = h('table', { class: 'compare-table' },
      h('thead', null,
        h('tr', null,
          h('th', { class: 'c-param', text: isKo ? '비교 항목' : 'Parameter' }),
          h('th', { class: 'c-denovo', text: isKo ? '신규 최적 설계 (De Novo)' : 'De Novo Design' }),
          h('th', { class: 'c-ref', text: isKo ? `기존 승인 (${refBrand || 'Benchmark'})` : `Approved (${refBrand || 'Ref'})` }),
          h('th', { text: isKo ? '임상 개선 이점' : 'Clinical Advantage' }))),
      h('tbody', null,
        tableRows.map(([param, denovo, refVal, diff]) => h('tr', null,
          h('td', { class: 'c-param', text: param }),
          h('td', { class: 'c-denovo', text: denovo }),
          h('td', { class: 'c-ref', text: refVal }),
          h('td', { text: diff })))));

    const secCompareTable = section(t('tabCompare'), tblEl);

    // 3. Clinical De-risking Points
    const deriskItems = (CLINICAL_DERISK_DB[tgt.id] && CLINICAL_DERISK_DB[tgt.id][isKo ? 'ko' : 'en']) || [
      {
        title: isKo ? '표적 장기 안전성 최적화' : 'Organ Safety Optimization',
        desc: isKo ? '최적화된 링커 안정도와 DAR 제어로 비특이적 전신 독성을 최소화합니다.' : 'Minimizes off-target toxicity through tuned DAR and linker chemistry.',
      },
    ];

    const deRiskEl = h('div', { class: 'derisk-list' },
      deriskItems.map((item) => h('div', { class: 'derisk-item' },
        h('b', { text: item.title }),
        h('span', { text: item.desc }))));

    const secDeRisk = section(t('deRiskTitle'), deRiskEl);

    // 4. 3D Structure Tab
    const cvs3d = h('canvas', { class: 'adc-3d-canvas' });
    const wrap3d = h('div', { class: 'adc-3d-wrap' },
      cvs3d,
      h('span', { class: 'adc-3d-hint', text: t('rotateHint') }));

    const deNovoConstruct = {
      name: deNovoName,
      brand: isKo ? 'AI 최적설계' : 'AI De Novo',
      target: tgt.gene || tgt.id,
      payload: pld.id,
      linker: lnk.id,
      dar: dar,
      darCount: Math.max(1, Math.min(8, Math.round(dar))),
      linkerType: lnk.cleavable ? 'cleavable' : 'non-cleavable',
      payloadColor: '#10B981',
      paratopeColor: '#38BDF8',
    };

    let active3dModel = deNovoConstruct;
    const legend3dBox = h('div');
    const updateLegend = (model) => {
      clear(legend3dBox);
      legend3dBox.append(build3dLegend(model));
    };
    updateLegend(deNovoConstruct);

    const btnToggleDeNovo = h('button', {
      type: 'button', class: 'st-pill', 'aria-pressed': 'true',
      text: isKo ? '신규 De Novo 설계 구조' : 'De Novo Construct',
      onclick: () => {
        active3dModel = deNovoConstruct;
        btnToggleDeNovo.setAttribute('aria-pressed', 'true');
        btnToggleRef.setAttribute('aria-pressed', 'false');
        updateLegend(active3dModel);
        init3dAdcCanvas(cvs3d, active3dModel);
      },
    });

    const btnToggleRef = h('button', {
      type: 'button', class: 'st-pill', 'aria-pressed': 'false',
      text: isKo ? `기존 승인약물 구조 (${refBrand})` : `Approved ADC (${refBrand})`,
      onclick: () => {
        active3dModel = refRow || { adc: refAdcId, name: refName, brand: refBrand };
        btnToggleDeNovo.setAttribute('aria-pressed', 'false');
        btnToggleRef.setAttribute('aria-pressed', 'true');
        updateLegend(active3dModel);
        init3dAdcCanvas(cvs3d, active3dModel);
      },
    });

    const switcher3d = h('div', { class: 'studio-pills', style: 'margin-bottom:12px' }, btnToggleDeNovo, btnToggleRef);

    const sec3D = section(t('tabStruct3d'),
      switcher3d,
      wrap3d,
      legend3dBox,
      h('div', { class: 'kv3', style: 'margin-top:12px' }, [
        [isKo ? '표적 항원' : 'Target', tgt.id],
        [isKo ? '접합비 (DAR)' : 'Conjugation (DAR)', `DAR ${dar}`],
        [isKo ? '화학 링커' : 'Linker Chemistry', `${lnk.id} (${lnk.cleavable ? 'Cleavable' : 'Direct'})`],
        [isKo ? '세포독성 페이로드' : 'Cytotoxic Payload', `${pld.id} (${pld.family || pld.cls})`],
        [isKo ? 'Fc 침묵화 엔지니어링' : 'Fc Engineering', fcSilenced ? (isKo ? 'LALA-PG (폐/각막 대식세포 흡수 차단)' : 'LALA-PG (Fc-gamma-R Silenced)') : (isKo ? '야생형 IgG1' : 'Wild-type IgG1')],
      ].map(([k, v]) => [h('span', { class: 'k', text: k }), h('span', { text: v })])));

    // 5. Pivotal Trial Study Tab
    const tr = refRow && refRow.detail && refRow.detail.trial && refRow.detail.trial.trial && !refRow.detail.trial.no_results ? refRow.detail.trial : null;
    const compReg = (tr && tr.comparator && tr.comparator.regimen) || (isKo ? '대조군' : 'Control');
    const compN = tr && tr.comparator && tr.comparator.n ? ` (n=${tr.comparator.n})` : '';
    const trialSummaryCard = tr ? h('div', { class: 'trial-summary-card' },
      h('p', { style: 'margin:0 0 6px;font-weight:800;font-size:13.5px;color:var(--ink-hi)', text: `${refBrand} - ${tr.trial}${tr.phase ? ' (Phase ' + tr.phase + ' Registration Trial)' : ''}` }),
      h('p', { class: 'dim', style: 'margin:0 0 6px;font-size:12px', text: tr.population || 'Patient cohort not specified' }),
      h('p', { style: 'margin:0 0 4px;font-size:12px;font-weight:600', text: `${t('treatmentArm')}: ${tr.regimen || ''} (n=${tr.n || 0})` }),
      tr.comparator ? h('p', { class: 'dim', style: 'margin:0 0 8px;font-size:12px', text: `${t('controlArm')}: ${compReg}${compN}` }) : null,
      /^NCT\d{8}$/.test(tr.nct || '') ? h('a', { class: 'review-link', href: 'https://clinicaltrials.gov/study/' + tr.nct, target: '_blank', rel: 'noopener noreferrer', text: `ClinicalTrials.gov ${tr.nct} ↗` }) : null
    ) : h('p', { class: 'dim', text: isKo ? `기존 승인 약물 (${refBrand}) 허가 임상시험 정보` : `Approved benchmark trial information for ${refBrand}` });

    const trialEvents = [];
    for (const o of (tr && tr.organs) || []) {
      for (const e of o.events || []) {
        trialEvents.push(h('div', { class: 'trial-event' },
          buildDualBar({ trial: tr, organ: o.organ, ev: e }),
          h('div', { class: 'event-values', style: 'margin-top:6px' },
            h('span', null, h('b', { text: `${e.a}/${e.n}` }), ' ' + t('treatmentArm')),
            e.comp ? h('span', null, h('b', { text: `${e.comp[0]}/${e.comp[1]}` }), ' ' + t('controlArm')) : null)));
      }
    }
    const secRefStudy = section(t('tabRefStudy'), trialSummaryCard, ...trialEvents);

    // Tab switcher
    const tabDefs = [
      { id: 'Compare', label: t('tabCompare'), secs: [secCompareHero, secCompareTable, secDeRisk].filter(Boolean) },
      { id: 'Structure', label: t('tabStruct3d'), secs: [sec3D].filter(Boolean) },
      { id: 'Study', label: t('tabRefStudy'), secs: [secRefStudy].filter(Boolean) },
    ];

    const nav = h('div', { class: 'evidence-tabs', role: 'group', 'aria-label': 'Comparison tabs' });
    const allSecs = tabDefs.flatMap((td) => td.secs);

    function switchCompareTab(id) {
      tabDefs.forEach((td) => {
        const active = td.id === id;
        td.secs.forEach((s) => { s.hidden = !active; });
      });
      [...nav.children].forEach((b) => b.setAttribute('aria-pressed', b.dataset.tabId === id ? 'true' : 'false'));
      if (id === 'Structure') {
        setTimeout(() => init3dAdcCanvas(cvs3d, active3dModel), 50);
      }
    }

    tabDefs.forEach((td) => {
      nav.append(h('button', {
        type: 'button', text: td.label, 'data-tab-id': td.id,
        onclick: () => switchCompareTab(td.id),
      }));
    });

    drawerBody.append(nav, ...allSecs);
    switchCompareTab('Compare');
  }

  function openStudioCompareDrawer(simInput, evalSpaceInput) {
    const sim = simInput || computeStudioSimulation();
    const evalSpace = evalSpaceInput || evaluateAllStudioCandidates();
    fillStudioCompareDrawer(sim, evalSpace);
    showDrawer();
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
    (APP.mechanisms || []).forEach((m) => {
      if (m) {
        const id = m.adc || m.adc_id;
        if (id) MECH[id] = m;
      }
    });
    verEl.textContent = 'v' + (APP.version || '0.7.1');

    restore();
    renderHeaderControls();
    renderActiveMode(false);
    await refreshBackendData();
    renderActiveMode(false);
  }

  start();
})();
