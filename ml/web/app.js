/* ADCTOX v0.7.9 Architectural Daylight WebApp
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
  function svgSearch() {
    return sv('svg', { width: '13', height: '13', viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'round', style: 'color:var(--dim);flex-shrink:0' },
      sv('circle', { cx: '7', cy: '7', r: '4.5' }),
      sv('path', { d: 'M10.5 10.5L14 14' }));
  }
  const clear = (el) => { while (el && el.firstChild) el.firstChild.remove(); return el; };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const kbd = (k, label) => h('span', null, h('kbd', { text: k }), ({
    add: 'Add', choose: 'Choose', remove: 'Remove', move: 'Move',
    back: 'Back', next: 'Next', select: 'Select', details: 'Evidence',
  })[label] || label);

  // ------------------------------------------------------------------ Tooltips & Guide
  const TIPS = {
    'Drug Fit': ['Dosing and eligibility guidance for this patient profile.', [
      ['1 bar', 'Standard dosing: no use restriction triggered'],
      ['2 bars', 'Monitor or Dose Adjust: check organ lab thresholds'],
      ['3 bars', 'Avoid or Contraindicated: use not advised'],
    ]],
    'Vulnerable Organs': ['Possible effects on the patient\'s vulnerable organs.', [
      ['Emerald bar', 'Clear: no warning on this organ'],
      ['Amber bar', 'Caution on this organ'],
      ['Crimson bar', 'Major warning on this organ'],
    ]],
    'Clinical Trial Cases': ['Adverse event incidence in registration clinical trials.', [
      ['Tx', 'Treatment group incidence (%)'],
      ['Ctrl', 'Control group incidence (%)'],
    ]],
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
    const isKo = S.lang === 'ko';
    const ver = (APP && APP.version) ? APP.version : '0.7.9';
    const stepItems = isKo
      ? [
          ['환자 정보', '한글 또는 영문으로 암종, 기저질환을 검색하고 검진 정보를 입력하여 AI 질환-장기 취약도 연계 결과를 확인합니다.'],
          ['ADC 매트릭스', '입력된 환자의 암종, 기저질환, 검진 수치를 기반으로 FDA 승인 ADC 약물의 적합도를 평가합니다. 상단 활성 취약 장기는 위험도(%) 내림차순으로 정렬되며, 특정 장기를 클릭하면 해당 장기 보호를 우선 반영해 순위를 재산출합니다.'],
          ['ADC 신규 설계', '표적 항원, 화학 링커, 세포독성 페이로드, DAR, Fc 엔지니어링(LALA-PG)을 조합하여 [ADC 수동 설계] 또는 [ADC 자동 설계]로 환자 맞춤형 접합체를 설계합니다.'],
        ]
      : [
          ['Patient Info', 'Search cancers or comorbidities in English or Korean, enter lab values, and review AI condition-organ associations.'],
          ['ADC Matrix', 'Ranks FDA-approved ADCs from patient comorbidities and lab values. Active vulnerable organs sort by severity (% descending); click any organ to prioritize its protection.'],
          ['De Novo ADC Design', 'Combine Target Antigen, Linker, Payload, DAR, and Fc-Silencing (LALA-PG) via Manual ADC Design or Auto-design ADC to evaluate patient-tailored conjugates.'],
        ];
    guide = h('div', { class: 'guide-scrim', onclick: (e) => { if (e.target === guide) closeGuide(); } },
      h('div', { class: 'guide', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'g-title' },
        h('div', { class: 'g-head' },
          h('h2', { id: 'g-title', text: isKo ? `ADCTOX v${ver} 워크스페이스 안내` : `ADCTOX v${ver} Workspace Guide` }),
          h('button', { type: 'button', class: 'x-btn', 'aria-label': 'Close', onclick: closeGuide }, svgClose())),
        h('div', { class: 'g-steps-list' },
          stepItems.map(([title, desc], idx) => h('div', { class: 'g-step-item' },
            h('span', { class: 'g-step-num', text: String(idx + 1) }),
            h('div', { class: 'g-step-body' },
              h('b', { text: title }),
              h('span', { text: desc }))))),
        h('h3', { text: isKo ? '시각 지표 안내' : 'Visual Encodings' }),
        h('div', { class: 'g-keys' },
          h('span', { class: 'sp-status-badge clear', text: isKo ? '표준 용량 투여' : 'Standard' }),
          h('span', { class: 'g-key-desc', text: isKo ? '입력된 환자 프로필 기준 용량 제한 없음' : 'No drug use restriction triggered for entered profile' }),
          h('span', { class: 'sp-status-badge monitor', text: isKo ? '모니터링 / 용량 조절' : 'Monitor / Adjust' }),
          h('span', { class: 'g-key-desc', text: isKo ? '밀접 모니터링 또는 용량 감량 권고' : 'Close clinical monitoring or dose modification advised' }),
          h('span', { class: 'sp-status-badge avoid', text: isKo ? '투여 주의 / 금기' : 'Avoid' }),
          h('span', { class: 'g-key-desc', text: isKo ? '투여 회피 또는 금기 권고' : 'Advises against use or contraindicated' }),
          h('span', { class: 'sp-status-badge trial-cmp', text: isKo ? '치료군 vs 대조군' : 'Treatment vs Control' }),
          h('span', { class: 'g-key-desc', text: isKo ? '등록 임상시험 치료군 대 대조군 이상사례 발생률 비교' : 'Clinical trial treatment group vs control group comparison' })),
        h('div', { class: 'g-foot' },
          h('button', { type: 'button', class: 'ok', text: isKo ? '닫기' : 'Close', onclick: closeGuide }))));
    document.body.append(guide);
  }

  // ------------------------------------------------------------------ App Data
  let APP = null, AX = [], SHORT = {}, REG = {}, REG_I = {}, FIELDS = [], MECH = {};
  const TONE = { contraindicated: 'red', avoid: 'red', insufficient_data: 'ink', no_statement: 'ink', reduce_dose: 'amber', monitor: 'amber', no_adjustment: 'green' };
  const MODES = ['Patient Info', 'ADC Matrix', 'De Novo ADC Design'];

  // ------------------------------------------------------------------ Structure Studio Knowledge Base
  const STUDIO_TARGETS = [
    { id: 'HER2 (ERBB2)', gene: 'ERBB2', refAdc: 'trastuzumab-deruxtecan', selectivity: 4.8,
      tumorKeys: ['breast', 'gastric', 'stomach', 'nsclc', 'lung', 'colorectal', 'colon', 'bladder', 'urothelial', '유방', '위암', '폐암', '대장', '방광'],
      tissues: [
        { organ: 'pulmonary', name: 'Lung alveolar', tpm: 48 },
        { organ: 'cardiovascular', name: 'Cardiomyocyte', tpm: 36 },
        { organ: 'gastrointestinal', name: 'GI mucosa', tpm: 42 },
      ],
      popover: 'Receptor tyrosine kinase amplified in breast, gastric, and NSCLC tumors. Baseline expression in lung alveolar epithelium and cardiomyocytes requires monitoring for ILD and LVEF decline.',
      popover_ko: '유방암, 위암, 비소세포폐암에서 증폭되는 수용체 티로신 키나아제입니다. 폐포 상피세포와 심근세포에 기저 발현이 존재하여 간질성 폐질환(ILD) 및 좌심실 구혈률(LVEF) 감시가 필요합니다.' },
    { id: 'TROP2 (TACSTD2)', gene: 'TACSTD2', refAdc: 'sacituzumab-govitecan', selectivity: 4.4,
      tumorKeys: ['breast', 'tnbc', 'nsclc', 'lung', 'urothelial', 'bladder', 'cervical', 'endometrial', 'ovarian', '유방', '삼중음성', '폐암', '요로상피', '방광', '자궁', '난소'],
      tissues: [
        { organ: 'gastrointestinal', name: 'Colonic epithelium', tpm: 68 },
        { organ: 'dermatologic', name: 'Stratified skin', tpm: 62 },
        { organ: 'pulmonary', name: 'Bronchial epithelium', tpm: 39 },
      ],
      popover: 'Transmembrane glycoprotein broadly overexpressed across epithelial carcinomas; baseline expression in GI mucosa and stratified skin keratinocytes mediates mucosal and cutaneous sensitivity.',
      popover_ko: '상피성 고형암 전반에 과발현되는 막관통 당단백질입니다. 대장 점막 및 피부 각질형성세포에 기저 발현이 있어 구내염, 설사 및 피부 발진 민감도와 연관됩니다.' },
    { id: 'Nectin-4', gene: 'NECTIN4', refAdc: 'enfortumab-vedotin', selectivity: 4.3,
      tumorKeys: ['urothelial', 'bladder', 'breast', 'nsclc', 'cervical', '요로상피', '방광', '유방', '자궁경부'],
      tissues: [
        { organ: 'dermatologic', name: 'Epidermal keratinocyte', tpm: 84 },
        { organ: 'metabolic_endocrine', name: 'Salivary / Sweat gland', tpm: 45 },
        { organ: 'ocular', name: 'Corneal epithelium', tpm: 34 },
      ],
      popover: 'Cell adhesion molecule highly enriched in urothelial carcinoma; strong physiological expression in epidermal keratinocytes and sweat glands mediates on-target cutaneous toxicity.',
      popover_ko: '요로상피암(방광암)에서 고밀도로 발현되는 세포 접착 분자입니다. 정상 표피 각질세포와 땀샘에도 발현량이 높아 표적 매개 피부 발진, 건조증에 대한 관리가 중요합니다.' },
    { id: 'CD79b', gene: 'CD79B', refAdc: 'polatuzumab-vedotin', selectivity: 5.4,
      tumorKeys: ['lymphoma', 'dlbcl', 'b-cell', 'leukemia', '림프종', '백혈병', '미만성'],
      tissues: [
        { organ: 'haematologic', name: 'B-lineage lymphoid', tpm: 72 },
        { organ: 'infectious_immune', name: 'Spleen / Lymph node', tpm: 58 },
        { organ: 'hepatic', name: 'Hepatic sinusoid', tpm: 12 },
      ],
      popover: 'B-cell receptor signaling subunit restricted to B-lineage lymphomas; rapidly internalized upon cross-linking with high selectivity outside lymphoid and marrow compartments.',
      popover_ko: 'B세포 계열 림프종에 선택적으로 발현되는 B세포 수용체 신호전달 소단위입니다. 결합 시 신속히 내재화되며 골수, 림프 조직 외 고형 장기 발현은 매우 낮습니다.' },
    { id: 'BCMA (TNFRSF17)', gene: 'TNFRSF17', refAdc: 'belantamab-mafodotin', selectivity: 5.8,
      tumorKeys: ['myeloma', 'plasma', '골수종', '형질세포'],
      tissues: [
        { organ: 'haematologic', name: 'Plasma cell niche', tpm: 66 },
        { organ: 'ocular', name: 'Corneal macropinocytosis', tpm: 49 },
        { organ: 'renal', name: 'Renal tubular', tpm: 14 },
      ],
      popover: 'Lineage-restricted receptor on mature plasma cells in multiple myeloma; corneal epithelial changes arise via off-target macropinocytosis of the conjugate.',
      popover_ko: '다발성 골수종 형질세포에 특이적으로 발현되는 성숙 항원입니다. 정상 고형 장기 발현은 극히 낮으나 각막 상피의 비특이적 거대음세포작용(macropinocytosis)을 통한 안구 독성이 주요 감시 대상입니다.' },
    { id: 'FRalpha (FOLR1)', gene: 'FOLR1', refAdc: 'mirvetuximab-soravtansine', selectivity: 4.6,
      tumorKeys: ['ovarian', 'endometrial', 'fallopian', 'peritoneal', 'nsclc', '난소', '자궁내막', '나팔관', '복막'],
      tissues: [
        { organ: 'ocular', name: 'Ocular epithelium', tpm: 54 },
        { organ: 'pulmonary', name: 'Type II pneumocyte', tpm: 44 },
        { organ: 'renal', name: 'Proximal kidney tubule', tpm: 51 },
      ],
      popover: 'GPI-anchored folate receptor overexpressed in ovarian and endometrial carcinomas; apical expression in corneal epithelium and renal tubules requires ocular prophylaxis.',
      popover_ko: '난소암, 자궁내막암에서 과발현되는 엽산 수용체 알파입니다. 각막 상피와 신장 근위세뇨관에 기저 발현이 있어 점안제 예방 등 안과적 관리가 권장됩니다.' },
  ];

  const STUDIO_LINKERS = [
    { id: 'Tetrapeptide GGFG', cleavable: true, stability: 88, hydro: 0.20, handle: 'amine_hydroxyl',
      prefPayloads: { 'DXd ( Topo I )': 1.0, 'SN-38 ( Topo I )': 0.72, 'MMAE ( Auristatin )': 0.65, 'MMAF ( Auristatin )': 0.55, 'SG3199 ( PBD Dimer )': 0.60 },
      note: 'Cathepsin B/L-cleavable tetrapeptide; self-immolative aminomethylene releases hydroxy/amine payload',
      note_ko: '카텝신 B/L 특이 절단형 4펩타이드; 자가 절단 아미노메틸렌으로 하이드록시/아민 페이로드 유리',
      popover: 'Hydrophilic glycine-phenylalanine tetrapeptide cleaved selectively by lysosomal cathepsins B/L. High plasma stability (88%) and low hydrophobicity enable homogeneous DAR 8 loading without hepatic aggregation.',
      popover_ko: '리소좀 효소(카텝신 B/L)에 의해 선택적으로 절단되는 친수성 테트라펩타이드 링커입니다. 높은 혈장 안정도(88%)와 낮은 소수성으로 DAR 8 고밀도 접합 시에도 간 응집과 체내 조기 유출을 억제합니다.' },
    { id: 'Val-Cit PABC', cleavable: true, stability: 76, hydro: 0.58, handle: 'amine',
      prefPayloads: { 'MMAE ( Auristatin )': 1.0, 'SG3199 ( PBD Dimer )': 0.94, 'DXd ( Topo I )': 0.70, 'MMAF ( Auristatin )': 0.68 },
      note: 'Cathepsin B-cleavable dipeptide with para-aminobenzyl carbamate spacer for secondary/primary amines',
      note_ko: '카텝신 B 특이 절단형 디펩타이드; PABC 스페이서로 아민 페이로드 결합',
      popover: 'Gold-standard cathepsin B-cleavable dipeptide linker with self-immolative PABC spacer. Releases membrane-permeable amine payloads (MMAE, PBD) cleanly inside tumor lysosomes, optimal at DAR 2–4.',
      popover_ko: '카텝신 B 절단 후 자가소멸 스페이서(PABC)를 통해 유리 약물을 방출하는 표준 디펩타이드 링커입니다. 아민계 페이로드(MMAE, PBD) 방출 효율이 뛰어나며 DAR 2~4 구간에서 최적의 혈중 안정성을 보입니다.' },
    { id: 'Hydrolyzable CL2A', cleavable: true, stability: 54, hydro: 0.32, handle: 'hydroxyl',
      prefPayloads: { 'SN-38 ( Topo I )': 1.0, 'DXd ( Topo I )': 0.78 },
      note: 'pH-sensitive carbonate linker; systemic and intratumoral hydrolysis releases SN-38',
      note_ko: 'pH 감응성 탄산염 링커; 종양 산성 미세환경에서 가수분해 방출',
      popover: 'PEGylated pH-sensitive carbonate linker engineered for camptothecins (SN-38). Gradual hydrolysis in the acidic tumor microenvironment and lysosomes drives strong bystander killing at DAR 7.6–8.',
      popover_ko: 'PEG 사슬이 도입된 pH 감응성 탄산염 링커로 SN-38 전달에 최적화되어 있습니다. 산성 종양 미세환경과 리소좀에서 약물을 방출해 이질적 종양에서도 강력한 주변 암세포 동반 사멸 효과를 냅니다.' },
    { id: 'Non-cleavable mc', cleavable: false, stability: 96, hydro: 0.42, handle: 'amine',
      prefPayloads: { 'MMAF ( Auristatin )': 1.0, 'MMAE ( Auristatin )': 0.52, 'DXd ( Topo I )': 0.48 },
      note: 'Maleimidocaproyl thioether; requires complete lysosomal proteolysis to release Cys-mc-payload',
      note_ko: '안정형 티오에테르 링커; 항체 완전 분해 시에만 페이로드 방출',
      popover: 'Ultra-stable thioether bond (96% plasma stability) requiring full lysosomal antibody proteolysis. Releases charged Cys-mc-MMAF that stays trapped inside target cells, minimizing systemic bystander toxicity.',
      popover_ko: '혈중 안정도가 96%에 달하는 비절단형 티오에테르 링커로 항체가 리소좀에서 완전 분해될 때만 약물이 방출됩니다. 전하를 띤 아미노산 결합체(Cys-mc-MMAF)를 형성해 전신 누출과 비표적 장기 손상을 최소화합니다.' },
    { id: 'Disulfide SPDB', cleavable: true, stability: 68, hydro: 0.52, handle: 'thiol',
      prefPayloads: { 'DM4 / DM1 ( Maytansinoid )': 1.0 },
      note: 'Sterically hindered disulfide cleaved by intracellular glutathione for thiol maytansinoids',
      note_ko: '입체 장애 이황화결합 링커; 세포 내 글루타티온 농도에 의해 절단',
      popover: 'Sterically hindered disulfide bond stable in oxidized plasma but reduced by high intracellular glutathione (GSH) in tumor cells to release thiol maytansinoids (DM4/DM1).',
      popover_ko: '혈중 산화 환경에서는 안정하고 암세포 내 고농도 글루타티온(GSH)에 의해 선택적으로 환원 절단되는 입체장애 이황화 링커입니다. 티올기(-SH)를 가진 메이탄시노이드(DM4/DM1)와 화학적 짝을 이룹니다.' },
    { id: 'Acid Hydrazone', cleavable: true, stability: 48, hydro: 0.55, handle: 'ketone',
      prefPayloads: {},
      note: 'Acid-labile AcBut hydrazone hydrolyzed in endosomes/lysosomes (pH 4.5-5.0)',
      note_ko: '산 감응성 하이드라존 링커; 엔도솜/리소좀 내 산성 조건에서 가수분해',
      popover: 'First-generation acid-labile hydrazone linker hydrolyzed at endosomal/lysosomal pH (4.5–5.0); requires a ketone handle (e.g., calicheamicin derivatives) and exhibits higher systemic deconjugation.',
      popover_ko: '엔도솜, 리소좀 산성 환경(pH 4.5~5.0)에서 가수분해되는 1세대 산 감응성 하이드라존 링커입니다. 케톤 작용기 페이로드가 필요하며 혈중 자발적 가수분해율이 상대적으로 높습니다.' },
  ];

  const STUDIO_PAYLOADS = [
    { id: 'DXd ( Topo I )', cls: 'Topoisomerase I inhibitor', perm: true, handle: 'amine_hydroxyl', potency: 92, optDar: 8, maxSafeDar: 8, hydro: 0.28,
      organs: { pulmonary: 82, haematologic: 68, gastrointestinal: 64, cardiovascular: 38, hepatic: 30 },
      popover: 'Membrane-permeable exatecan derivative (~10x higher Topo I potency than SN-38) with a short systemic half-life (~1.6 h). Supports homogeneous DAR 8 loading; alveolar macrophage uptake makes ILD the primary risk.',
      popover_ko: 'SN-38 대비 약 10배 높은 효력을 지닌 막 투과성 토포이소머라제 I 저해제입니다. 혈중 반감기가 짧아 전신 축적이 적고 DAR 8 고밀도 접합이 가능하나, 폐포 대식세포 흡수에 따른 간질성 폐질환(ILD) 주의가 필요합니다.' },
    { id: 'SN-38 ( Topo I )', cls: 'Topoisomerase I inhibitor (UGT1A1)', perm: true, handle: 'hydroxyl', potency: 82, optDar: 7.6, maxSafeDar: 8, hydro: 0.34,
      organs: { haematologic: 86, gastrointestinal: 84, hepatic: 44, pulmonary: 22 },
      popover: 'Active metabolite of irinotecan detoxified via hepatic UGT1A1 glucuronidation. Effective at high DAR (7.6–8) with CL2A linker; primary dose-limiting toxicities are neutropenia and secretory diarrhea.',
      popover_ko: '이리노테칸의 활성 대사체로 간의 UGT1A1 효소에 의해 해독됩니다. CL2A 링커와 결합해 높은 DAR(7.6~8)에서 강력한 항암 효능을 발휘하며, 주요 감시 독성은 호중구감소증과 중증 설사입니다.' },
    { id: 'MMAE ( Auristatin )', cls: 'Microtubule inhibitor (Auristatin)', perm: true, handle: 'amine', potency: 90, optDar: 4, maxSafeDar: 4, hydro: 0.82,
      organs: { neurologic: 84, haematologic: 76, dermatologic: 66, hepatic: 52 },
      popover: 'Potent lipophilic tubulin polymerization inhibitor with strong bystander killing. Optimal at DAR 3.5–4; loading above DAR 4 accelerates hepatic Kupffer-cell clearance and cumulative peripheral neuropathy.',
      popover_ko: '세포막 투과성과 주변 암세포 동반 사멸 효과가 우수한 미세소관 중합 저해제입니다. DAR 3.5~4에서 치료 지수가 최적이며, DAR 4 초과 시 소수성 응집으로 간 조기 포획과 말초신경병증 위험이 급증합니다.' },
    { id: 'MMAF ( Auristatin )', cls: 'Charged Auristatin (low permeability)', perm: false, handle: 'amine', potency: 86, optDar: 4, maxSafeDar: 4, hydro: 0.50,
      organs: { ocular: 92, haematologic: 64, renal: 28, hepatic: 32, neurologic: 20 },
      popover: 'C-terminal charged phenylalanine auristatin unable to diffuse across cell membranes after release. Spares peripheral nerves and marrow compared to MMAE, but concentrates in corneal epithelium via macropinocytosis.',
      popover_ko: '말단 음전하로 인해 세포 밖 수동 확산이 차단된 오리스타틴 유도체입니다. MMAE 대비 말초신경병증과 골수 억제는 현저히 낮으나, 각막 상피 내 축적에 따른 각막병증 관리가 핵심입니다.' },
    { id: 'DM4 / DM1 ( Maytansinoid )', cls: 'Microtubule inhibitor (Maytansinoid)', perm: true, handle: 'thiol', potency: 85, optDar: 3.5, maxSafeDar: 4, hydro: 0.68,
      organs: { ocular: 74, hepatic: 72, neurologic: 62, haematologic: 58 },
      popover: 'Thiol-bearing maytansinoid tubulin inhibitor conjugated at DAR 3.5–4. Intracellular reduction yields S-methyl-DM4 with bystander activity; associated with reversible corneal keratopathy and transaminase elevation.',
      popover_ko: '티올(-SH) 결합 부위를 지닌 메이탄시노이드계 미세소관 저해제로 주로 DAR 3.5~4에서 사용됩니다. 간 CYP3A4 대사 및 거핵구 영향으로 간효소(AST/ALT) 상승, 혈소판감소증, 가역적 각막병증과 연관됩니다.' },
    { id: 'SG3199 ( PBD Dimer )', cls: 'DNA minor-groove crosslinker', perm: true, handle: 'amine', potency: 98, optDar: 2, maxSafeDar: 2, hydro: 1.15,
      organs: { haematologic: 92, hepatic: 78, pulmonary: 68, dermatologic: 62, renal: 54 },
      popover: 'Picomolar-potency pyrrolobenzodiazepine interstrand DNA crosslinker active against both dividing and quiescent tumor cells. Strictly restricted to DAR 2 due to delayed myelosuppression and capillary leak.',
      popover_ko: '피코몰(pM) 농도에서 비분열 암세포까지 사멸시키는 초고효능 DNA 작은홈 가교제입니다. 지연성 골수 억제 및 체액 저류, 간 동모양혈관 독성을 예방하기 위해 임상적으로 DAR 2 저밀도 접합에 한해 사용됩니다.' },
  ];

  const STUDIO_DAR_ITEMS = [
    { id: '2', popover: 'DAR 2: Site-specific low drug loading. Minimizes hydrophobic aggregation and preserves antibody half-life; mandatory for ultra-potent DNA crosslinkers (PBD dimers) or fragile multi-organ cohorts.',
      popover_ko: 'DAR 2: 항체 1분자당 약물 2개를 결합한 저밀도 정밀 설계입니다. 소수성 응집을 최소화하고 혈중 반감기를 길게 유지하며, 초고효능 페이로드(PBD 이합체)나 다장기 취약 환자의 안전역 확보에 필수적입니다.' },
    { id: '3.5', popover: 'DAR 3.5: Validated average loading for Polivy (CD79b-MMAE), Kadcyla (HER2-DM1), and Elahere (FRα-DM4). Balances intracellular payload delivery against hepatic sinusoidal uptake.',
      popover_ko: 'DAR 3.5: 폴라이비(Polivy), 캐싸일라(Kadcyla), 엘라히어(Elahere) 등 승인 ADC에서 검증된 접합비입니다. 세포 내 약물 전달량과 간 쿠퍼세포 비특이 포획 사이의 균형이 우수합니다.' },
    { id: '4', popover: 'DAR 4: Standard interchain cysteine conjugation (Padcev, Blenrep, Dato-DXd). Optimal therapeutic index for hydrophobic auristatins (MMAE/MMAF) without triggering rapid clearance.',
      popover_ko: 'DAR 4: 사슬 간 시스테인 결합을 통한 표준 접합비(파드셉, 블렌렙, 다토포타맙 데룩스테칸 등)입니다. 소수성 오리스타틴 계열에서 간 조기 배설 없이 높은 치료 지수를 달성합니다.' },
    { id: '6', popover: 'DAR 6: Intermediate-high loading. Increases cytotoxic payload concentration per internalized receptor in tumors with moderate antigen density; requires moderately hydrophilic linkers.',
      popover_ko: 'DAR 6: 중등도 항원 발현 종양에서도 내재화당 충분한 약물 농도를 확보하기 위한 중고밀도 설계입니다. 혈중 응집 방지를 위해 친수성 스페이서 또는 안정형 링커가 권장됩니다.' },
    { id: '7.6', popover: 'DAR 7.6: High-density loading validated in Trodelvy (sacituzumab govitecan, CL2A-SN-38). Delivers high payload copy numbers per receptor when paired with PEGylated linkers.',
      popover_ko: 'DAR 7.6: 트로델비(Trodelvy, CL2A-SN-38)에 적용된 고밀도 접합비입니다. PEG가 도입된 친수성 링커와 결합해 수용체 1개당 약물 전달 효율을 극대화합니다.' },
    { id: '8', popover: 'DAR 8: Homogeneous full interchain cysteine loading (Enhertu, GGFG-DXd). Maximizes efficacy in heterogeneous or low-antigen tumors, but causes severe hepatic aggregation if used with hydrophobic payloads.',
      popover_ko: 'DAR 8: 8개 사슬 간 시스테인 전체에 약물을 균일하게 결합한 최대 밀도 설계(엔허투 등)입니다. 친수성 링커(GGFG)+Topo I 페이로드에서는 최고의 약효를 내지만, 소수성 약물에 적용 시 급격한 간 응집, 독성을 유발합니다.' },
  ];

  const STUDIO_FC_ITEMS = [
    { key: 'wt', isSilenced: false,
      popover: 'Wild-Type IgG1: Retains FcγRIIIa binding on NK cells and macrophages to support ADCC effector killing, but permits FcγR-mediated non-specific uptake into alveolar macrophages, liver, and bone marrow.',
      popover_ko: '야생형 IgG1: NK세포, 대식세포의 Fcγ 수용체 결합력을 유지해 항체 의존성 세포독성(ADCC)을 돕지만, 폐포 대식세포, 간, 골수로의 FcγR 매개 비특이적 유입이 함께 일어날 수 있습니다.' },
    { key: 'sil', isSilenced: true,
      popover: 'Fc-Silenced (LALA-PG): L234A/L235A/P329G mutation ablates FcγR and C1q complement binding while preserving FcRn half-life recycling, blocking macrophage uptake in lung, liver, and marrow.',
      popover_ko: 'Fc 침묵화 (LALA-PG): FcRn 반감기 유지 기능은 보존하면서 대식세포 FcγR 및 보체 결합만 선택적으로 제거한 변이입니다. 폐포 대식세포, 간, 안구로의 비특이 흡수를 차단해 취약 장기 안전도를 높입니다.' },
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

  // an organ shown in the page's language: ORGAN_KO is keyed by organ id, the label rows carry the short English name
  const organKo = (x) => {
    if (S.lang !== 'ko') return SHORT[x] || x;
    if (ORGAN_KO[x]) return ORGAN_KO[x];
    const key = Object.keys(SHORT).find((k) => SHORT[k] === x);
    return (key && ORGAN_KO[key]) || SHORT[x] || x;
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
      modes: ['환자 정보', 'ADC 매트릭스', 'ADC 신규 설계'],
      brandTag: '임상 ADC 의사결정 및 신규 설계 워크스페이스',
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
      secTrial: '임상시험 사례',
      matrixHead: 'FDA 승인 ADC 약물 치료군 순위',
      matrixSub: '환자의 취약 장기와 약물별 주의사항을 종합한 권고',
      rankBest: '1위 최적 적합',
      rankCand: '후보',
      fitStd: '표준 용량 투여',
      fitAdj: '모니터링 / 용량 조절',
      fitAvoid: '투여 주의 / 금기',
      tuneStudio: 'ADC 신규 설계에서 설계 ↗',
      allGrade: '전체',
      grade3: '3등급 이상',
      primaryRec: '최우선 추천 약물',
      primaryHint: '',
      filterAll: '전체 승인 ADC',
      filterMatch: '암종 일치',
      filterRestricted: '약물 사용 제한',
      exportSummary: '요약 내보내기',
      match: '일치',
      archTitle: '접합체 구조 설계',
      manualOpt: 'ADC 수동 설계',
      autoOpt: 'ADC 자동 설계',
      scanning: '최적화 탐색 중...',
      scanSpace: '설계 조합 탐색 중...',
      tgtTitle: '1. 표적 항원',
      lnkTitle: '2. 화학 링커',
      pldTitle: '3. 세포독성 페이로드',
      darTitle: '4. 약물-항체 접합비 DAR',
      fcTitle: '5. Fc 엔지니어링',
      wtFc: '야생형 IgG1',
      silFc: 'Fc 침묵화 (LALA-PG)',
      designTitle: '환자 맞춤형 ADC 설계',
      axisSafety: '예상 장기 안전도 (높을수록 안전)',
      axisEfficacy: '예상 항암 효능 (높을수록 강력)',
      legendCand: '설계 조합',
      legendBad: '접합 불가 조합',
      legendCur: '현재 선택',
      legendBest: '추천 설계',
      optimalLocked: '현재 설계가 이 환자에게 가장 균형 잡힌 조합입니다',
      optimalCand: '이 환자에게 추천하는 설계:',
      bestDesign: '환자 맞춤 추천 설계',
      clickAutoOpt: 'ADC 자동 설계를 누르면 이 환자에게 맞는 조합을 찾습니다',
      explainTitle: '점수 계산식',
      explainBody: [
        '안전도 (X, 0~100) = 100 − (0.55 × 최대 취약장기 위험도 + 0.45 × 평균 취약장기 위험도) × 100',
        '장기 위험도 p(o) = 1 − exp(−0.48 × [페이로드 장기독성 + 0.6 × 정상조직 표적발현] × 약물부하[DAR, 링커안정도, 응집도] × Fc계수 × 환자장기가중치)',
        '항암 효능 (Y, 0~100) = 100 × 적응증일치도 × 표적선택도^0.35 × 페이로드효력^0.50 × 링커보존율^0.55 × 방출효율^0.48 × DAR전달곡선^0.52 × 화학적상보성^0.32 × 동반사멸계수',
      ],
      shCompat: '접합 반응성 호환도',
      shCompatDirect: '직접 결합 가능',
      shCompatSpacer: '링커 스페이서 필요',
      shCompatDesc: '링커의 반응성 작용기와 페이로드 결합 부위의 화학적 짝맞춤입니다.',
      shSelect: '종양 대 정상조직 선택도',
      shSelectDesc: '정상 조직 대비 암세포의 표적 항원 발현비(log2FC)로, 높을수록 정상 장기 손상이 적습니다.',
      shBystander: '주변 암세포 동반 사멸',
      shBystanderActive: '동반 사멸 가능',
      shBystanderAuto: '표적 세포만 사멸',
      shBystanderDesc: '표적 단백질이 없는 인접 암세포까지 침투하여 함께 사멸시키는 효과입니다.',
      shStability: '혈장 내 링커 안정도',
      shStabilityIntact: '유지',
      shStabilityDesc: '혈액 순환 중 페이로드가 조기 유리되지 않고 종양까지 온전하게 전달되는 비율입니다.',
      simOrganTitle: '취약 장기별 예상 독성 위험',
      gtexTitle: '정상 장기의 표적 발현량',
      gtexNote: '단백질이 정상 장기에서 많이 발현될수록 암세포가 아닌 정상 조직도 함께 손상될 위험이 커집니다. 숫자는 발현량(nTPM)이며 낮을수록 안전합니다.',
      fcLalaNote: 'Fc 침묵화(LALA-PG)로 대식세포의 FcγR 결합이 줄어 폐, 간, 안구 등으로의 비특이 흡수가 감소했습니다.',
      fcWtNote: '야생형 IgG1은 대식세포의 FcγR에 결합하므로 폐, 간, 안구로의 비특이 흡수가 일어날 수 있습니다.',
      flowTitle: '검진 정보',
      flowSub: '',
      refRange: '참고치',
      notEntered: '미입력',
      elevated: '수치 상승',
      lowVal: '수치 저하',
      borderline: '경계치',
      normal: '정상',
      organLinkage: 'AI 장기 취약도 연계 분석',
      riskWeight: '위험 가중치',
      triggeredDiag: '임상 진단에 의해 활성화',
      triggeredLab: '검사 수치 이상에 의해 활성화',
      noActiveTriggers: '활성화된 장기 독성 요인 없음',
      drTitle: '임상 근거 및 구조 상세',
      tabPatient: '환자 적합도',
      tabStudy: '임상시험 사례',
      tabStructure: '분자 구조',
      labelRestriction: '약물 사용 제한 여부',
      noLabelRestriction: '입력된 환자의 수치를 고려하였을 때, 약물 사용에 제한 사항은 없습니다.',
      patientWarnTitle: '취약 장기 영향 가능성',
      noPatientWarn: '환자의 취약 장기를 고려하였을 때, 약물 사용에 제한 사항은 없습니다.',
      preCheckTitle: '투여 전 권장 검사',
      missingInputTitle: '미입력 검사 항목',
      enterLabBtn: '검사 수치 입력하기',
      treatmentArm: '치료군',
      controlArm: '대조군',
      trialContext: '이상사례 발생률 비교',
      struct3dTitle: '분자 구조',
      appliesToAll: '모든 환자에게 적용',
      singleArmTrial: '단일군 임상시험 (대조군 없음)',
      compareTitle: '맞춤 설계 vs. 기존 승인 약물 비교',
      tabCompare: '설계 비교',
      tabStruct3d: '분자 구조',
      tabRefStudy: '임상시험 사례',
      deNovoCol: '이 환자 맞춤 설계',
      refCol: '기존 승인 약물',
      clinicalDiff: '임상적 차이 및 개선 이점',
      deRiskTitle: '기존 약물 부작용 대비 임상 개선 기전',
      viewCompareBtn: '기존 승인 ADC와 비교 ↗',
      compTarget: '표적 항원',
      compLinker: '화학 링커',
      compPayload: '세포독성 페이로드',
      compDar: '약물-항체 접합비 DAR',
      compFc: 'Fc 엔지니어링',
      compSafety: '예상 장기 안전도',
      compEfficacy: '예상 항암 효능',
    },
    en: {
      modes: ['Patient Info', 'ADC Matrix', 'De Novo ADC Design'],
      brandTag: 'Clinical ADC Decision & De Novo Design',
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
      secTrial: 'Clinical Trial Cases',
      matrixHead: 'Ranked FDA-Approved ADC Regimens',
      matrixSub: 'Synthesized from drug warnings, active organs, and clinical trials',
      rankBest: '#1 Best Fit',
      rankCand: 'Candidate',
      fitStd: 'Standard dosing',
      fitAdj: 'Monitor / Adjust',
      fitAvoid: 'Avoid / Contraindicated',
      tuneStudio: 'Open in De Novo ADC Design ↗',
      allGrade: 'All Gr',
      grade3: 'Gr >=3',
      primaryRec: 'Primary Recommendation',
      primaryHint: '',
      filterAll: 'All Approved ADCs',
      filterMatch: 'Cancer Match',
      filterRestricted: 'Use Restrictions',
      exportSummary: 'Export Summary',
      match: 'Match',
      archTitle: 'Conjugate Architecture',
      manualOpt: 'Manual ADC Design',
      autoOpt: 'Auto-design ADC',
      scanning: 'Optimizing...',
      scanSpace: 'Scanning candidate space...',
      tgtTitle: '1. Target Antigen (mAb)',
      lnkTitle: '2. Chemical Linker',
      pldTitle: '3. Cytotoxic Payload',
      darTitle: '4. Drug-to-Antibody Ratio (DAR)',
      fcTitle: '5. Fc Engineering',
      wtFc: 'Wild-type IgG1',
      silFc: 'Fc-Silenced (LALA-PG)',
      designTitle: 'Patient-Tailored ADC Design',
      axisSafety: 'Expected organ safety (higher is safer)',
      axisEfficacy: 'Expected antitumor efficacy (higher is stronger)',
      legendCand: 'Design combinations',
      legendBad: 'Cannot be conjugated',
      legendCur: 'Current selection',
      legendBest: 'Recommended design',
      optimalLocked: 'The current design is the most balanced choice for this patient',
      optimalCand: 'Recommended design for this patient:',
      bestDesign: 'Recommended for this patient',
      clickAutoOpt: 'Press Auto-design ADC to find the best combination for this patient',
      explainTitle: 'Scoring Formula',
      explainBody: [
        'Safety (X, 0–100) = 100 − (0.55 × Peak Organ Risk + 0.45 × Mean Organ Risk) × 100',
        'Organ Risk p(o) = 1 − exp(−0.48 × [Payload Organ Tox + 0.6 × Normal Target Expr] × Drug Load[DAR, Stability, Aggregation] × Fc Factor × Patient Organ Weight)',
        'Efficacy (Y, 0–100) = 100 × Indication Match × Selectivity^0.35 × Potency^0.50 × Linker Retention^0.55 × Release^0.48 × DAR Curve^0.52 × Compatibility^0.32 × Bystander',
      ],
      shCompat: 'Conjugation Compatibility',
      shCompatDirect: 'Direct Coupling',
      shCompatSpacer: 'Linker Spacer Needed',
      shCompatDesc: 'Linker reactive handle pairing with payload functional group.',
      shSelect: 'Tumor / Normal Selectivity',
      shSelectDesc: 'Fold-change in target expression on tumor vs. healthy normal organs.',
      shBystander: 'Bystander Tumor Killing',
      shBystanderActive: 'Active Bystander',
      shBystanderAuto: 'Localized Killing Only',
      shBystanderDesc: 'Penetrates and kills adjacent antigen-negative tumor cells to counter heterogeneity.',
      shStability: 'Plasma Linker Stability',
      shStabilityIntact: 'Intact',
      shStabilityDesc: 'Resistance to premature systemic payload deconjugation in circulation.',
      simOrganTitle: 'Expected toxicity risk by vulnerable organ',
      gtexTitle: 'Target expression in normal organs',
      gtexNote: 'The more this protein is expressed in normal organs, the more healthy tissue can be hit together with the tumor. Numbers are expression levels (nTPM); lower is safer.',
      fcLalaNote: 'Fc silencing (LALA-PG) reduces FcγR binding on macrophages, lowering non-specific uptake in lung, liver and eye.',
      fcWtNote: 'Wild-type IgG1 binds FcγR on macrophages, so non-specific uptake in lung, liver and eye can occur.',
      flowTitle: 'Lab Values',
      flowSub: '',
      refRange: 'Ref',
      notEntered: 'Not entered',
      elevated: 'Elevated',
      lowVal: 'Low',
      borderline: 'Borderline',
      normal: 'Normal',
      organLinkage: 'AI Organ Vulnerability Linkage',
      riskWeight: 'Risk Weight',
      triggeredDiag: 'Triggered by clinical diagnosis',
      triggeredLab: 'Triggered by laboratory biomarker elevation',
      noActiveTriggers: 'No active organ toxicity triggers detected.',
      drTitle: 'Clinical Evidence and Structure',
      tabPatient: 'Patient & Label Fit',
      tabStudy: 'Trial Cases',
      tabStructure: 'Molecular Structure',
      labelRestriction: 'Restrictions on using this drug',
      noLabelRestriction: 'Given the entered patient values, there are no restrictions on using this drug.',
      patientWarnTitle: 'Possible effects on vulnerable organs',
      noPatientWarn: "Given the patient's vulnerable organs, there are no restrictions on using this drug.",
      preCheckTitle: 'Pre-treatment checks',
      missingInputTitle: 'Missing inputs',
      enterLabBtn: 'Enter lab values',
      treatmentArm: 'Treatment Arm',
      controlArm: 'Comparator Arm',
      trialContext: 'Adverse event comparison',
      struct3dTitle: 'Molecular Structure',
      appliesToAll: 'Applies to all patients',
      singleArmTrial: 'Single-arm trial',
      compareTitle: 'Tailored Design vs. Approved Drug',
      tabCompare: 'Compare',
      tabStruct3d: 'Molecular Structure',
      tabRefStudy: 'Trial Cases',
      deNovoCol: 'Tailored Design',
      refCol: 'Approved Drug',
      clinicalDiff: 'Clinical Difference & Advantage',
      deRiskTitle: 'How this design lowers the approved drug\'s side effects',
      viewCompareBtn: 'Compare with Approved ADC ↗',
      compTarget: 'Target Antigen',
      compLinker: 'Chemical Linker',
      compPayload: 'Cytotoxic Payload',
      compDar: 'DAR',
      compFc: 'Fc Engineering',
      compSafety: 'Expected organ safety score',
      compEfficacy: 'Expected antitumor efficacy score',
    },
  };
  function t(k) {
    const lang = S.lang === 'ko' ? 'ko' : 'en';
    return (TXT[lang] && TXT[lang][k]) || (TXT.en && TXT.en[k]) || k;
  }

  // ------------------------------------------------------------------ Session State
  const KEY = 'adctox.web.v079';
  const DEFAULT_SIM_WEIGHTS = {
    wSafety: 0.56,
    wPeak: 0.58,
    wExpr: 0.38,
    leakSens: 1.00,
    hydroSens: 1.00,
    fcProtect: 0.34,
    wSelect: 0.30,
    wBystander: 0.28,
  };
  const SIM_WEIGHT_PRESETS = [
    {
      id: 'balanced',
      ko: '기본 균형 (Balanced TI)',
      en: 'Balanced TI (Default)',
      weights: { wSafety: 0.56, wPeak: 0.58, wExpr: 0.38, leakSens: 1.00, hydroSens: 1.00, fcProtect: 0.34, wSelect: 0.30, wBystander: 0.28 },
    },
    {
      id: 'organ_sparing',
      ko: '다장기 보호 최우선',
      en: 'Organ-Sparing Safety',
      weights: { wSafety: 0.78, wPeak: 0.80, wExpr: 0.52, leakSens: 1.45, hydroSens: 1.55, fcProtect: 0.52, wSelect: 0.38, wBystander: 0.14 },
    },
    {
      id: 'bystander_tumor',
      ko: '이질성 고형암 동반사멸',
      en: 'Heterogeneous Solid Tumor',
      weights: { wSafety: 0.42, wPeak: 0.45, wExpr: 0.28, leakSens: 0.75, hydroSens: 0.80, fcProtect: 0.28, wSelect: 0.22, wBystander: 0.54 },
    },
    {
      id: 'high_selectivity',
      ko: '고선택성 표적 / 간-골수 보호',
      en: 'High-Selectivity / Hepatic-Sparing',
      weights: { wSafety: 0.66, wPeak: 0.68, wExpr: 0.72, leakSens: 1.25, hydroSens: 1.75, fcProtect: 0.44, wSelect: 0.52, wBystander: 0.18 },
    },
  ];
  function defaultState() {
    return {
      mode: 0,
      lang: 'en',
      presetId: null,
      conds: [],
      raw: {},
      labs: null,
      meanings: {},
      first: null,
      prioOrgan: null,
      studioDesignMode: 'idle',
      studioNeedInputWarn: false,
      studioHistory: [],
      simWeights: Object.assign({}, DEFAULT_SIM_WEIGHTS),
      simPreset: 'balanced',
      formulaOpen: false,
      analysis: null,
      result: null,
      sel: 0,
      reviewAdc: null,
      drawer: false,
      drawerTab: 'Patient',
      studio: { target: 'HER2 (ERBB2)', linker: 'Tetrapeptide GGFG', payload: 'DXd ( Topo I )', dar: 4, fc: false },
    };
  }
  let S = defaultState();
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* ignore */ }
  }
  function restore() {
    try {
      const d = JSON.parse(sessionStorage.getItem(KEY) || 'null');
      if (d && typeof d === 'object' && Array.isArray(d.conds)) {
        S = Object.assign(defaultState(), d);
        S.simWeights = Object.assign({}, DEFAULT_SIM_WEIGHTS, d.simWeights || {});
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
  function hasPatientProfile() {
    return S.conds.length > 0 || Object.keys(rawValues()).length > 0 || activeOrgansWithScores().length > 0;
  }

  const CANCER_ORGAN_RULES = [
    { re: /leukemia|myeloid|lymphoid|aml|all|cll|cml|myeloma|lymphoma|dlbcl|hodgkin|myelodysplastic|waldenstrom|백혈병|골수종|림프종|골수이형성/i,
      organs: [['haematologic', 0.84], ['infectious_immune', 0.68]] },
    { re: /lung|nsclc|sclc|bronch|pulmonary|pleural|mesothelioma|폐암|기관지암|흉막/i,
      organs: [['pulmonary', 0.82]] },
    { re: /breast|mammary|tnbc|유방암|삼중음성/i,
      organs: [['cardiovascular', 0.64], ['pulmonary', 0.58], ['haematologic', 0.54]] },
    { re: /liver|hepatocellular|hcc|cholangio|biliary|gallbladder|간암|간세포암|담도암|담관암|담낭암/i,
      organs: [['hepatic', 0.84], ['gastrointestinal', 0.60]] },
    { re: /gastric|stomach|colorectal|colon|rectal|esophageal|intestinal|duodenal|위암|대장암|결장암|직장암|식도암|장암/i,
      organs: [['gastrointestinal', 0.78], ['haematologic', 0.54]] },
    { re: /pancrea|췌장암/i,
      organs: [['gastrointestinal', 0.74], ['hepatic', 0.68], ['metabolic_endocrine', 0.60]] },
    { re: /renal|kidney|urothelial|bladder|ureter|신장암|신세포암|방광암|요로상피암/i,
      organs: [['renal', 0.78], ['dermatologic', 0.52]] },
    { re: /brain|glioma|glioblastoma|astrocytoma|meningioma|cns|neuroblastoma|뇌종양|교모세포종|신경모세포종/i,
      organs: [['neurologic', 0.82]] },
    { re: /ovarian|fallopian|peritoneal|cervical|endometrial|uterine|난소암|나팔관암|복막암|자궁경부암|자궁내막암|자궁암/i,
      organs: [['haematologic', 0.62], ['gastrointestinal', 0.58], ['ocular', 0.52]] },
    { re: /prostate|testicular|전립선암|고환암/i,
      organs: [['haematologic', 0.58], ['renal', 0.55]] },
    { re: /melanoma|cutaneous|skin cancer|basal cell|squamous cell skin|흑색종|피부암/i,
      organs: [['dermatologic', 0.76]] },
    { re: /thyroid|adrenal|neuroendocrine|갑상선암|부신암|신경내분비/i,
      organs: [['metabolic_endocrine', 0.72]] },
    { re: /head and neck|nasopharyngeal|oropharyngeal|laryngeal|oral|두경부암|비인두암|후두암|구강암/i,
      organs: [['gastrointestinal', 0.66], ['pulmonary', 0.58]] },
    { re: /sarcoma|bone|osteosarcoma|육종|골육종/i,
      organs: [['musculoskeletal', 0.74], ['haematologic', 0.60]] },
  ];

  function mergeOrganScore(map, organ, score, condKey) {
    if (!organ) return;
    const prev = map.get(organ);
    if (!prev) {
      map.set(organ, { organ, score: Math.min(0.96, score), condKey: condKey || null });
    } else {
      // Probabilistic compounding when multiple conditions burden the same organ
      const hi = Math.max(prev.score, score);
      const lo = Math.min(prev.score, score);
      const combined = Math.min(0.96, 1 - (1 - hi) * (1 - 0.32 * lo));
      map.set(organ, {
        organ,
        score: combined,
        condKey: score >= prev.score ? (condKey || prev.condKey) : prev.condKey,
      });
    }
  }

  function inferConditionOrgansFallback(text, condKey, map) {
    const s = String(text || '').trim();
    if (!s) return;
    for (const rule of CANCER_ORGAN_RULES) {
      if (rule.re.test(s)) {
        for (const [org, sc] of rule.organs) {
          mergeOrganScore(map, org, sc, condKey);
        }
      }
    }
  }

  function activeOrgansWithScores() {
    const map = new Map();
    if (S.analysis && S.analysis.state === 'done') {
      for (const r of S.analysis.reports || []) {
        const used = r.organs || [];
        const pMap = r.p || {};
        if (used.length) {
          for (const o of used) {
            const sc = typeof pMap[o] === 'number' && pMap[o] > 0 ? pMap[o] : 0.85;
            mergeOrganScore(map, o, sc, r.condition);
          }
        } else if (r.source === 'Cancer' || (r.cancers && r.cancers.length)) {
          const searchTxt = [r.condition, r.name, r.shown].concat(r.cancers || []).join(' ');
          inferConditionOrgansFallback(searchTxt, r.condition, map);
        }
      }
    }
    const P = (S.result && S.result.data && S.result.data.patient) || {};
    if (P.organ_levels && typeof P.organ_levels === 'object') {
      for (const [org, lvl] of Object.entries(P.organ_levels)) {
        const sc = typeof lvl === 'number' ? lvl : 0.80;
        mergeOrganScore(map, org, sc, null);
      }
    }
    for (const c of (P.cancers || [])) {
      const searchTxt = [c.condition, c.name].concat(c.cancers || []).join(' ');
      inferConditionOrgansFallback(searchTxt, c.condition, map);
    }
    for (const c of S.conds) {
      if (c.kind === 'reg' && REG[c.value] && (REG[c.value].organs || []).length) {
        for (const o of REG[c.value].organs || []) {
          mergeOrganScore(map, o, 0.88, c.value);
        }
      } else {
        inferConditionOrgansFallback(`${c.label || ''} ${c.value || ''}`, c.value || c.label, map);
      }
    }
    for (const fl of (S.labs && S.labs.flags) || []) {
      if (String(S.raw[fl.key] || '').trim()) {
        mergeOrganScore(map, fl.organ, 0.82, null);
      }
    }
    return AX.filter((a) => map.has(a)).map((a) => map.get(a)).sort((a, b) => b.score - a.score);
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

  function svgBrandLogo() {
    const parser = new DOMParser();
    const svgStr = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 218 42" width="182" height="35" fill="none" class="adctox-pictorial-logo" aria-hidden="true">
      <g transform="translate(2, 2)">
        <path d="M11 3 H23 M14 3 V11 L4 33 C3.2 34.6 4.4 36 6.2 36 H27.8 C29.6 36 30.8 34.6 30 33 L20 11 V3" stroke="#0891B2" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M7.2 26.5 H26.8 L29.2 32.5 C29.6 33.4 29 34.4 27.8 34.4 H6.2 C5 34.4 4.4 33.4 4.8 32.5 L7.2 26.5 Z" fill="#F59E0B"/>
        <circle cx="14" cy="21" r="1.7" fill="#F59E0B"/>
        <circle cx="19.5" cy="17.5" r="1.4" fill="#FBBF24"/>
        <circle cx="16.5" cy="13.5" r="1.2" fill="#FDE68A"/>
      </g>
      <g transform="translate(38, 2)">
        <path d="M4 4 H16 C23.5 4 28 9.5 28 19.5 C28 29.5 23.5 35 16 35 H4 Z" stroke="#0891B2" stroke-width="3.4" stroke-linejoin="round" fill="rgba(8,145,178,0.08)"/>
        <path d="M10 10 V29" stroke="#0891B2" stroke-width="2.2" stroke-linecap="round" opacity="0.45"/>
      </g>
      <g transform="translate(72, 2)">
        <path d="M26 9.5 C23.2 5.8 19.2 4 14.5 4 C7.2 4 3 9.8 3 19.5 C3 29.2 7.2 35 14.5 35 C19.2 35 23.2 33.2 26 29.5" stroke="#0891B2" stroke-width="3.6" stroke-linecap="round"/>
      </g>
      <g transform="translate(106, 2)">
        <path d="M3 4 H29 M16 4 V10 M9 10 H23" stroke="#E11D48" stroke-width="3.0" stroke-linecap="round"/>
        <rect x="10" y="10" width="12" height="19" rx="1.8" stroke="#E11D48" stroke-width="2.6" fill="rgba(225,29,72,0.06)"/>
        <rect x="11.6" y="16.5" width="8.8" height="11.2" fill="#F59E0B"/>
        <path d="M10 14.5 H14.5 M10 19 H15.5 M10 23.5 H14.5" stroke="#E11D48" stroke-width="1.7" stroke-linecap="round"/>
        <path d="M13.5 29 H18.5 L17.2 32.5 H14.8 Z" fill="#E11D48"/>
        <path d="M16 32.5 V37.5" stroke="#E11D48" stroke-width="2.2" stroke-linecap="round"/>
      </g>
      <g transform="translate(141, 2)">
        <path d="M14 7 C14 7 4 19.2 4 26.2 C4 31.8 8.5 35.8 14 35.8 C19.5 35.8 24 31.8 24 26.2 C24 19.2 14 7 14 7 Z" fill="#E11D48"/>
        <ellipse cx="10.2" cy="24.5" rx="2.2" ry="3.4" transform="rotate(-18 10.2 24.5)" fill="#FFE4E6"/>
      </g>
      <g transform="translate(174, 2)">
        <path d="M6 7 L30 32" stroke="#E11D48" stroke-width="4.2" stroke-linecap="round"/>
        <circle cx="4.8" cy="8.2" r="2.9" fill="#E11D48"/>
        <circle cx="8.2" cy="4.8" r="2.9" fill="#E11D48"/>
        <circle cx="28.8" cy="33.8" r="2.9" fill="#E11D48"/>
        <circle cx="32.2" cy="30.4" r="2.9" fill="#E11D48"/>
        <path d="M30 7 L6 32" stroke="#E11D48" stroke-width="4.2" stroke-linecap="round"/>
        <circle cx="28.8" cy="4.8" r="2.9" fill="#E11D48"/>
        <circle cx="32.2" cy="8.2" r="2.9" fill="#E11D48"/>
        <circle cx="4.8" cy="30.4" r="2.9" fill="#E11D48"/>
        <circle cx="8.2" cy="33.8" r="2.9" fill="#E11D48"/>
      </g>
    </svg>`;
    return parser.parseFromString(svgStr, 'image/svg+xml').documentElement;
  }
    const brandWrap = h('div', { class: 'brand-wrap' },
      h('div', { class: 'brand', title: 'ADCToX — Antibody-Drug Conjugate Toxicity & Design' },
        h('span', { class: 'brand-logo-svg' }, svgBrandLogo()),
        h('span', { class: 'sr-only', text: 'ADCToX' })),
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
    if (S.mode === 2 && S.drawer && drawer && drawer.classList.contains('open')) {
      fillStudioCompareDrawer(computeStudioSimulation(), evaluateAllStudioCandidates());
    }
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
    scenarioDropdown.append(h('button', {
      type: 'button', class: 'reset-patient-btn', text: t('newPatient'),
      title: t('newPatientTitle'),
      onclick: () => resetPatient(),
    }));
  }

  function resetPatient() {
    S.presetId = null;
    S.conds = [];
    S.raw = {};
    S.meanings = {};
    S.first = null;
    S.prioOrgan = null;
    S.studioDesignMode = 'idle';
    S.studioNeedInputWarn = false;
    S.studioHistory = [];
    S.analysis = null;
    S.result = null;
    S.sel = 0;
    save();
    renderHeaderControls();
    refreshBackendData().then(() => renderActiveMode(true));
  }

  // ------------------------------------------------------------------ Background Data Sync
  // The bar above the condition box follows the real steps of the work: lab values read, drugs ranked, then the analysis
  // job on the server (queued, running, the organ judge, done). It moves only when one of those steps reports in.
  const PROG = { pct: 0, text: '', on: false, hide: 0 };
  let progNode = null;
  function paintProgress() {
    const nodes = document.querySelectorAll('.model-progress');
    const list = nodes.length ? [...nodes] : (progNode ? [progNode] : []);
    list.forEach((node) => {
      node.classList.toggle('on', PROG.on);
      const fill = node.querySelector('.mp-fill');
      if (fill) fill.style.width = PROG.pct + '%';
      const txt = node.querySelector('.mp-text');
      if (txt) txt.textContent = PROG.on ? `${PROG.text} ${Math.round(PROG.pct)}%` : '';
      node.setAttribute('aria-valuenow', String(Math.round(PROG.pct)));
    });
  }
  function buildProgressBar() {
    progNode = h('div', { class: 'model-progress', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': '0', 'aria-label': 'Analysis progress' },
      h('div', { class: 'mp-track' }, h('i', { class: 'mp-fill' })),
      h('span', { class: 'mp-text' }));
    paintProgress();
    return progNode;
  }
  const PROG_TEXT = {
    ko: {
      searching: '미등록 질환 의미 매핑 및 AI 모델 탐색 중',
      start: '환자 정보 확인 중',
      labs: '검사 수치 해석 중',
      rank: '약물 순위 계산 중',
      queued: '백그라운드 질환-장기 모델 대기 중',
      running: '백그라운드 질환-장기 독성 모델 추론 중',
      judging: '질환별 취약 장기 정밀 판정 중',
      done: '분석 완료',
    },
    en: {
      searching: 'Mapping condition via clinical AI model',
      start: 'Reading patient information',
      labs: 'Interpreting lab values',
      rank: 'Ranking drugs',
      queued: 'Background condition-organ model queued',
      running: 'Running condition-organ toxicity model',
      judging: 'Judging vulnerable organs',
      done: 'Analysis complete',
    },
  };
  function setProgress(pct, key) {
    clearTimeout(PROG.hide);
    if (!PROG.on) PROG.pct = 0;
    PROG.on = true;
    PROG.pct = Math.max(PROG.pct, pct);
    if (key) PROG.text = (PROG_TEXT[S.lang === 'ko' ? 'ko' : 'en'])[key] || key;
    paintProgress();
  }
  function endProgress() {
    if (!PROG.on) return;
    setProgress(100, 'done');
    PROG.hide = setTimeout(() => { PROG.on = false; paintProgress(); PROG.pct = 0; }, 900);
  }

  let syncSeq = 0;
  async function refreshBackendData() {
    const seq = ++syncSeq;
    PROG.on = false;
    setProgress(4, 'start');
    try {
      const labsRes = await API.labs(rawValues());
      if (seq !== syncSeq) return;
      S.labs = labsRes;
    } catch (e) { /* keep existing */ }
    setProgress(25, 'labs');

    try {
      const labRaw = (S.labs && S.labs.raw) || rawValues();
      let recRes;
      try {
        recRes = await API.recommend({
          conditions: condList(),
          raw: labRaw,
          choice: allChoice(),
          first: S.first,
        });
      } catch (errFirst) {
        if (S.first) {
          S.first = null;
          recRes = await API.recommend({
            conditions: condList(),
            raw: labRaw,
            choice: allChoice(),
            first: null,
          });
        } else {
          throw errFirst;
        }
      }
      if (seq !== syncSeq) return;
      S.result = { sig: resultSig(), data: recRes };
      save();
    } catch (e) { /* ignore */ }
    setProgress(55, 'rank');

    runBackgroundAnalysis(seq).then(() => { if (seq === syncSeq) endProgress(); });
  }

  async function runBackgroundAnalysis(seq) {
    const sig = JSON.stringify([condList(), pickChoice()]);
    if (S.analysis && S.analysis.sig === sig && S.analysis.state === 'done') return;
    if (!condList().length) return;
    try {
      const start = await API.analyze(condList(), pickChoice());
      if (seq !== syncSeq) return;
      setProgress(60, 'queued');
      const job = start.job;
      for (let k = 0; k < 600; k++) {
        await sleep(200);
        if (seq !== syncSeq) return;
        const r = await API.job(job);
        if (r.state === 'done' || r.state === 'error') {
          S.analysis = {
            sig, state: r.state, error: r.error || null,
            reports: r.reports || [], ambiguous: r.ambiguous || [], unresolved: r.unresolved || [],
          };
          save();
          renderActiveMode(false);
          return;
        }
        if (r.step === 'judging') {
          const nextP = Math.min(96, Math.max(82, PROG.pct + 1.4));
          setProgress(nextP, 'judging');
        } else if (r.state === 'running') {
          const nextP = Math.min(84, Math.max(64, PROG.pct + 1.6));
          setProgress(nextP, 'running');
        } else {
          const nextP = Math.min(68, Math.max(58, PROG.pct + 0.8));
          setProgress(nextP, 'queued');
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
      S.studioNeedInputWarn = false;
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
      if (!hasPatientProfile()) S.studioDesignMode = 'idle';
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
          text: labBadges.join('  /  '), onclick: () => switchMode(0),
        }));
      }
    }

    function renderSugg() {
      clear(sugg);
      const show = st.items.length > 0 && st.q.trim() !== '';
      sugg.hidden = !show;
      input.setAttribute('aria-expanded', show ? 'true' : 'false');
      if (!show) return;
      const isKo = S.lang === 'ko';
      st.items.slice(0, 7).forEach((it, i) => {
        const isActive = i === st.cur;
        const li = h('li', {
          class: 'opt' + (isActive ? ' is-active' : ''),
          role: 'option',
          'aria-selected': isActive ? 'true' : 'false',
        },
        h('span', { class: 'nm' },
          h('span', { class: 'opt-dot', 'aria-hidden': 'true' }),
          h('span', { class: 'main', text: it.kind === 'raw' ? (isKo ? `+ "${it.text}" 직접 추가 (AI 모델 분석)` : `+ Add "${it.text}" (AI Model)`) : it.s.text }),
          it.s && it.s.sub ? h('span', { class: 'sub', text: it.s.sub }) : null),
        h('span', { class: 'opt-pick-pill', text: isKo ? '선택 ↵' : 'Select ↵' }));
        li.addEventListener('mouseenter', () => {
          st.cur = i;
          [...sugg.children].forEach((elChild, idx) => {
            const act = idx === i;
            elChild.classList.toggle('is-active', act);
            elChild.setAttribute('aria-selected', act ? 'true' : 'false');
          });
        });
        li.addEventListener('mousedown', (e) => {
          e.preventDefault();
          li.classList.add('is-picking');
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
        const r = await API.suggest(q, pickedList(), false);
        if (seq !== st.seq) return;
        const out = [];
        for (const s of r.names || []) out.push({ kind: 's', s });
        for (const s of r.symptoms || []) out.push({ kind: 'sym', s });
        out.push({ kind: 'raw', text: q });
        st.items = out;
        st.cur = 0;
        renderSugg();

        // If fast dictionary lookup did not find a direct match, run AI semantic suggest with live top progress bar
        if (out.length <= 1 && q.length >= 2) {
          PROG.on = false;
          setProgress(22, 'searching');
          const progTimer = setInterval(() => {
            if (seq !== st.seq || !PROG.on) { clearInterval(progTimer); return; }
            setProgress(Math.min(88, PROG.pct + 12), 'searching');
          }, 180);
          try {
            const aiRes = await API.suggest(q, pickedList(), true);
            clearInterval(progTimer);
            if (seq !== st.seq) return;
            const aiOut = [];
            for (const s of aiRes.names || []) aiOut.push({ kind: 's', s });
            for (const s of aiRes.symptoms || []) aiOut.push({ kind: 'sym', s });
            aiOut.push({ kind: 'raw', text: q });
            st.items = aiOut;
            st.cur = 0;
            renderSugg();
            endProgress();
          } catch (eAi) {
            clearInterval(progTimer);
            endProgress();
          }
        }
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
    const horizonSubEl = h('span', { class: 'horizon-sub' });

    function updateHorizonSub() {
      const prioOrg = S.prioOrgan || (S.first && activeOrgans.find((x) => x.condKey === S.first)?.organ) || null;
      if (prioOrg) {
        const pLabel = S.lang === 'ko' ? (ORGAN_KO[prioOrg] || SHORT[prioOrg] || prioOrg) : (SHORT[prioOrg] || prioOrg);
        horizonSubEl.textContent = S.lang === 'ko' ? `${pLabel} 우선 평가 적용 중 (재클릭 시 해제)` : `Prioritizing ${pLabel} (click to clear)`;
        horizonSubEl.classList.add('prio-sub-active');
      } else {
        horizonSubEl.textContent = S.lang === 'ko' ? '클릭 시 해당 장기 우선 평가' : 'Select organ to prioritize';
        horizonSubEl.classList.remove('prio-sub-active');
      }
    }

    function renderOrgansGrid() {
      clear(organsGrid);
      updateHorizonSub();
      if (activeOrgans.length) {
        activeOrgans.forEach((item) => {
          const pct = Math.round(Math.max(15, Math.min(100, item.score * 100)));
          const isPrio = (S.prioOrgan === item.organ) || (!S.prioOrgan && item.condKey && S.first === item.condKey);
          const orgLabel = S.lang === 'ko' ? (ORGAN_KO[item.organ] || SHORT[item.organ] || item.organ) : (SHORT[item.organ] || item.organ);
          const btn = h('button', {
            type: 'button',
            class: 'organ-meter-btn' + (isPrio ? ' prio-active' : ''),
            'aria-pressed': isPrio ? 'true' : 'false',
            title: S.lang === 'ko' ? `${orgLabel} (${pct}%) 우선 평가 토글` : `Toggle priority for ${orgLabel} (${pct}%)`,
            onclick: async () => {
              const turningOff = isPrio;
              S.prioOrgan = turningOff ? null : item.organ;
              if (item.condKey && condList().length >= 2) {
                S.first = turningOff ? null : item.condKey;
              } else {
                S.first = null;
              }
              save();
              renderOrgansGrid();
              await refreshBackendData();
              if (onChanged) onChanged();
            },
          },
          h('div', { class: 'om-top' },
            h('span', { class: 'om-name', text: orgLabel }),
            h('span', { class: 'om-val', text: `${pct}%` })),
          h('div', { class: 'om-track' },
            h('i', { class: 'om-fill', style: `width:${pct}%` })));
          organsGrid.append(btn);
        });
      } else {
        organsGrid.append(h('span', { class: 'dim', text: t('noActiveOrgans') }));
      }
    }
    renderOrgansGrid();

    return h('section', { class: 'workspace-bar', 'aria-label': 'Patient and active organ profile' },
      h('div', { class: 'wb-left' },
        buildProgressBar(),
        h('div', { class: 'wb-search-row' },
          h('div', { class: 'wb-input-wrap' },
            svgSearch(),
            input),
          sugg),
        chipsWrap),
      h('div', { class: 'wb-right' },
        h('div', { class: 'horizon-head' },
          h('span', { class: 'horizon-label', text: `${t('activeOrgans')} (${activeOrgans.length})` }),
          horizonSubEl),
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
    if (!found) return { cls: 'clear', tag: isKo ? '허용' : 'Clear', title: isKo ? (orgName + ' 특이 주의사항 없음') : ('No warning on ' + (SHORT[organ] || organ)) };
    if (String(found.mark || '').trim() === '!!') return { cls: 'boxed', tag: isKo ? '경고' : 'Warning', title: (isKo ? '중증 주의사항: ' : 'Major warning: ') + (found.text || '') };
    return { cls: 'warn', tag: isKo ? '주의' : 'Caution', title: (isKo ? '주의사항: ' : 'Caution: ') + (found.text || '') };
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
    const isKo = S.lang === 'ko';
    if (!trialHit || !trialHit.trial || !trialHit.ev) return h('span', { class: 'dim', style: 'font-size:11px', text: isKo ? '단일군 임상 (대조군 없음)' : 'Single-arm trial' });
    const { trial, ev } = trialHit;
    const adcPct = (100 * (ev.a || 0)) / Math.max(1, ev.n || 1);
    const cmpPct = ev.comp && ev.comp[1] ? (100 * ev.comp[0]) / Math.max(1, ev.comp[1]) : null;
    const scaleMax = Math.max(25, adcPct, cmpPct || 0);
    const compLabel = (trial.comparator && trial.comparator.regimen) || (isKo ? '대조군' : 'Control');
    const txLabel = isKo ? '치료군' : 'Tx';
    const ctrlLabel = isKo ? '대조군' : 'Ctrl';
    const tip = `${trial.trial || ''}: ${ev.term || ''}\n${isKo ? '치료군' : 'Treatment'} (${trial.regimen || ''}): ${adcPct.toFixed(1)}%` +
      (cmpPct !== null ? `\n${isKo ? '대조군' : 'Control'} (${compLabel}): ${cmpPct.toFixed(1)}%` : '');

    return h('div', {
      class: 'dual-bar-group',
      title: tip,
    },
    h('div', { class: 'dual-bar-row' },
      h('span', { class: 'db-tag', text: txLabel }),
      h('span', { class: 'db-track' }, h('i', { class: 'db-fill-adc', style: `width:${Math.min(100, (adcPct / scaleMax) * 100).toFixed(1)}%` })),
      h('span', { class: 'db-pct', text: `${adcPct.toFixed(1)}%` })),
    cmpPct !== null ? h('div', { class: 'dual-bar-row' },
      h('span', { class: 'db-tag', text: ctrlLabel }),
      h('span', { class: 'db-track' }, h('i', { class: 'db-fill-cmp', style: `width:${Math.min(100, (cmpPct / scaleMax) * 100).toFixed(1)}%` })),
      h('span', { class: 'db-pct cmp', text: `${cmpPct.toFixed(1)}%` })) : null,
    h('div', { class: 'dual-bar-title' },
      h('span', { text: ev.term || '' }),
      h('span', { class: 'dim', text: trial.trial || '' })));
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
      const activeOrgans = activeOrgansWithScores();
      let rows = res.rows.slice();
      if (S.prioOrgan) {
        const pk = S.prioOrgan;
        const penOf = (r) => {
          const os = organStatusForRow(r, pk);
          return os.cls === 'boxed' ? 2 : (os.cls === 'warn' ? 1 : 0);
        };
        rows.sort((a, b) => (penOf(a) - penOf(b)) || (a.rank - b.rank));
        rows = rows.map((r, idx) => Object.assign({}, r, { rank: idx + 1 }));
      }

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
              h('span', { class: 'sp-rank', text: `TOP #${row.rank}` })),
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
          h('span', { class: 'sec-kicker', text: t('primaryRec') })),
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
      keepRow = () => { if (S.mode === 1 && trs[S.sel] && trs[S.sel].isConnected) trs[S.sel].scrollIntoView({ block: 'nearest' }); };

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

  // ------------------------------------------------------------------ Mode 1: Structure & Combination Studio
  let simAnimId = 0;
  let studioChartRO = null;

  // The score model behind the dots. Both scores are smooth, bounded transforms of published properties (no hard caps),
  // so combinations spread out instead of piling up on a line.
  const FC_SENSITIVE = ['pulmonary', 'haematologic', 'ocular', 'hepatic'];
  const FALLBACK_ORGANS = [
    { organ: 'pulmonary', score: 0.8 }, { organ: 'hepatic', score: 0.8 },
    { organ: 'haematologic', score: 0.8 }, { organ: 'cardiovascular', score: 0.7 },
  ];
  // the approved drug of each target, written in the studio's own parts so it is scored by the same formula
  const REF_STUDIO = {
    'HER2 (ERBB2)': { linker: 'Tetrapeptide GGFG', payload: 'DXd ( Topo I )', dar: 8, fc: false },
    'TROP2 (TACSTD2)': { linker: 'Hydrolyzable CL2A', payload: 'SN-38 ( Topo I )', dar: 7.6, fc: false },
    'Nectin-4': { linker: 'Val-Cit PABC', payload: 'MMAE ( Auristatin )', dar: 4, fc: false },
    'CD79b': { linker: 'Val-Cit PABC', payload: 'MMAE ( Auristatin )', dar: 3.5, fc: false },
    'BCMA (TNFRSF17)': { linker: 'Non-cleavable mc', payload: 'MMAF ( Auristatin )', dar: 4, fc: false },
    'FRalpha (FOLR1)': { linker: 'Disulfide SPDB', payload: 'DM4 / DM1 ( Maytansinoid )', dar: 3.5, fc: false },
  };
  const plainName = (id) => String(id || '').replace(/\s*\(.*?\)\s*/g, ' ').replace(/\s+/g, ' ').trim();

  function patientCancerMatchesTarget(tgt) {
    const P = (S.result && S.result.data && S.result.data.patient) || {};
    const cancerTexts = []
      .concat((P.cancers || []).map((c) => `${c.condition || ''} ${c.label || ''}`))
      .concat(S.conds.map((c) => `${c.label || ''} ${c.value || ''}`))
      .join(' ')
      .toLowerCase();
    if (!cancerTexts.trim()) return null;
    const hasAnyTumorKeyword = /cancer|carcinoma|tumor|lymphoma|myeloma|leukemia|sarcoma|암|종양|림프종|골수종|백혈병/.test(cancerTexts);
    if (!hasAnyTumorKeyword) return null;
    return (tgt.tumorKeys || []).some((k) => cancerTexts.includes(k.toLowerCase()));
  }

  function computeStudioSimulation(specInput, organsInput) {
    const W = Object.assign({}, DEFAULT_SIM_WEIGHTS, S.simWeights || {});
    const spec = specInput || S.studio;
    const tgt = STUDIO_TARGETS.find((x) => x.id === spec.target) || STUDIO_TARGETS[0];
    const lnk = STUDIO_LINKERS.find((x) => x.id === spec.linker) || STUDIO_LINKERS[0];
    const pld = STUDIO_PAYLOADS.find((x) => x.id === spec.payload) || STUDIO_PAYLOADS[0];
    const dar = Number(spec.dar) || 4;
    const fcSilenced = Boolean(spec.fc);

    const real = organsInput || activeOrgansWithScores();
    const baseOrgans = real.slice();
    const organSet = new Set(baseOrgans.map((o) => o.organ));
    for (const tis of (tgt.tissues || [])) {
      if (!organSet.has(tis.organ)) {
        baseOrgans.push({ organ: tis.organ, score: 0.44, condKey: null, baselineTissue: true });
        organSet.add(tis.organ);
      }
    }
    const isCompat = lnk.handle === pld.handle || lnk.handle.includes(pld.handle) || pld.handle.includes(lnk.handle);

    // Chemical linker-payload pairing affinity (clinically validated pair = 1.0)
    const pairAffinity = isCompat ? ((lnk.prefPayloads && lnk.prefPayloads[pld.id]) || 0.72) : 0.35;

    // 1. Two-Pathway Mechanistic Organ Hazard:
    //    (a) Off-Target (Antigen-Independent): Plasma linker deconjugation + Hydrophobic DAR Kupffer aggregation + FcgammaR uptake
    //    (b) On-Target / Off-Tumor (Antigen-Dependent): Normal tissue GTEx expression * receptor-mediated payload internalization
    const maxSafeDar = pld.maxSafeDar || 4;
    const darExcess = Math.max(0, dar - maxSafeDar);
    const hydroFactor = (pld.hydro || 0.5) * (0.55 + (lnk.hydro || 0.4) * 0.9);
    const leakMult = 1 + W.leakSens * 2.15 * Math.pow(1 - lnk.stability / 100, 1.15);
    const aggMult = 1 + W.hydroSens * (0.38 * darExcess * hydroFactor + 0.09 * Math.pow(dar / 4, 1.75) * hydroFactor);
    const darScale = Math.pow(dar / 4, 0.72);
    const chemPenalty = 1 + (1 - pairAffinity) * 0.42;
    const wOnTarget = Math.max(0.10, Math.min(0.85, W.wExpr));

    const allOrganRisks = baseOrgans.map((ao) => {
      const payloadTox = (pld.organs[ao.organ] != null ? pld.organs[ao.organ] : 20) / 100;
      const expr = ((tgt.tissues.find((x) => x.organ === ao.organ) || { tpm: 6 }).tpm) / 100;
      const fcMult = fcSilenced && FC_SENSITIVE.includes(ao.organ) ? Math.max(0.25, 1 - W.fcProtect) : 1.0;
      const prioMult = (S.prioOrgan && S.prioOrgan === ao.organ) ? 1.45 : 1.0;
      const vulnWeight = (ao.baselineTissue ? 0.46 : (0.58 + 0.42 * Math.min(1, ao.score || 0.8))) * prioMult;

      const offTargetHazard = payloadTox * darScale * leakMult * aggMult * fcMult;
      const onTargetHazard = expr * (0.45 + 0.55 * payloadTox) * (dar / 4) * (0.75 + 0.25 * fcMult);
      const combinedHazard = ((1 - wOnTarget) * offTargetHazard + wOnTarget * 1.65 * onTargetHazard) * chemPenalty * vulnWeight;
      return { organ: ao.organ, p: 1 - Math.exp(-0.56 * combinedHazard), baselineTissue: Boolean(ao.baselineTissue) };
    });

    const organRisks = real.length ? allOrganRisks.filter((r) => !r.baselineTissue) : allOrganRisks;
    const meanRisk = allOrganRisks.length ? allOrganRisks.reduce((a, r) => a + r.p, 0) / allOrganRisks.length : 0;
    const worstRisk = allOrganRisks.length ? Math.max(...allOrganRisks.map((r) => r.p)) : 0;
    const wPeak = Math.max(0.15, Math.min(0.90, W.wPeak));
    const safetyRaw = Math.max(2, Math.min(98, 100 * (1 - (wPeak * worstRisk + (1 - wPeak) * meanRisk))));
    const safetyScore = Math.round(safetyRaw);

    // 2. Competing Multi-Mechanism Antitumor Efficacy (Normalized Convex Combination + Biophysical Couplings)
    const bystander = lnk.cleavable && pld.perm;
    const indMatch = patientCancerMatchesTarget(tgt);
    const indFactor = indMatch === null ? 1.0 : (indMatch ? 1.06 : 0.68);

    // Normalized sub-scores in [0, 1] that compete when weights change:
    // S_select: tumor-to-normal expression margin (TCGA vs GTEx log2FC)
    const sSelect = Math.max(0.18, Math.min(0.98, (tgt.selectivity - 2.4) / 3.6));
    // S_pot: intrinsic payload cytotoxicity & optimal DAR stoichiometry minus hydrophobic hepatic clearance loss
    const optDar = pld.optDar || 4;
    const darDeviation = Math.abs(dar - optDar);
    const pkClearanceLoss = Math.max(0.32, 1 - W.hydroSens * (0.14 * darExcess * hydroFactor + 0.04 * Math.max(0, dar - 4) * hydroFactor));
    const sPotency = Math.max(0.15, Math.min(0.99, Math.pow(pld.potency / 100, 1.35) * (1 - Math.exp(-dar / 2.8)) * Math.exp(-0.045 * darDeviation * darDeviation) * pkClearanceLoss));
    // S_deliv: intact plasma delivery to tumor + intracellular lysosomal cleavage efficiency
    const plasmaIntact = Math.max(0.20, 1 - W.leakSens * 0.68 * (1 - lnk.stability / 100));
    const releaseEff = lnk.cleavable ? 0.96 : (pld.perm === false ? 0.90 : 0.62);
    const sDeliv = Math.max(0.15, Math.min(0.98, plasmaIntact * releaseEff));
    // S_bys: bystander killing diffusion across antigen-heterogeneous tumor beds
    const sBystander = bystander ? (0.84 + 0.14 * (dar / 8)) : (lnk.cleavable ? 0.42 : (pld.perm ? 0.34 : 0.14));

    const rawWSelect = Math.max(0.05, W.wSelect);
    const rawWBys = Math.max(0.05, W.wBystander);
    const rawWCore = Math.max(0.20, 1.0 - 0.55 * (rawWSelect + rawWBys));
    const wSum = rawWSelect + rawWBys + rawWCore;
    const nwSel = rawWSelect / wSum;
    const nwBys = rawWBys / wSum;
    const nwPot = (rawWCore * 0.56) / wSum;
    const nwDel = (rawWCore * 0.44) / wSum;

    const convexEff = nwSel * sSelect + nwPot * sPotency + nwDel * sDeliv + nwBys * sBystander;
    const eff = convexEff * Math.pow(pairAffinity, 0.36) * indFactor * (isCompat ? 1.0 : 0.48);
    const efficacyRaw = Math.max(2, Math.min(98, eff * 100));
    const efficacyScore = Math.round(efficacyRaw);

    return { spec, tgt, lnk, pld, dar, fcSilenced, safetyScore, efficacyScore, safetyRaw, efficacyRaw, isCompat, organRisks, meanRisk, bystander, nwSel, nwPot, nwDel, nwBys };
  }

  function evaluateAllStudioCandidates() {
    const W = Object.assign({}, DEFAULT_SIM_WEIGHTS, S.simWeights || {});
    const real = activeOrgansWithScores();
    const cands = [];
    const dars = [2, 3.5, 4, 6, 7.6, 8];
    STUDIO_TARGETS.forEach((t) => {
      STUDIO_LINKERS.forEach((l) => {
        STUDIO_PAYLOADS.forEach((p) => {
          dars.forEach((d) => {
            [false, true].forEach((fc) => {
              cands.push(computeStudioSimulation({ target: t.id, linker: l.id, payload: p.id, dar: d, fc }, real));
            });
          });
        });
      });
    });

    // User-tunable Therapeutic Index Safety Priority (lambda_safe), lightly modulated by multi-organ burden
    const organShift = real.length > 2 ? Math.min(0.08, (real.length - 2) * 0.02) : 0;
    const wSafety = Math.max(0.15, Math.min(0.88, W.wSafety + organShift));
    let best = null;
    let top = -1;
    cands.forEach((c) => {
      if (!c.isCompat) return;
      const util = wSafety * c.safetyRaw + (1 - wSafety) * c.efficacyRaw;
      c.utilScore = util;
      if (util > top) { top = util; best = c; }
    });
    return { cands, best: best || cands[0], wSafety };
  }

  function buildAutoOptimizeRationales(bestSim) {
    const s = bestSim.spec;
    const isKo = S.lang === 'ko';
    const activeOrgs = activeOrgansWithScores().map((o) => (isKo && ORGAN_KO[o.organ] ? ORGAN_KO[o.organ] : SHORT[o.organ] || o.organ));
    const tgtName = plainName(s.target);
    const plName = plainName(s.payload);
    if (isKo) {
      return [
        ['1. 표적 항원', `${tgtName}, 선택도 +${bestSim.tgt.selectivity.toFixed(1)} log2FC`, '정상 장기에는 적고 종양에 많은 표적이라 정상 조직 손상을 줄입니다.'],
        ['2. 화학 링커', `${s.linker}, 혈장 안정도 ${bestSim.lnk.stability}%`, `${activeOrgs.join(', ') || '주요 장기'}로 약물이 미리 새어 나가는 것을 줄이고 종양 안에서 풀리도록 합니다.`],
        ['3. 세포독성 페이로드', `${plName}, ${bestSim.pld.cls}`, '이 환자의 취약 장기에 대한 독성이 상대적으로 낮으면서 항암 효력은 유지합니다.'],
        ['4. 접합비와 Fc', `DAR ${s.dar}, ${s.fc ? 'Fc 침묵화' : '야생형 IgG1'}`, `예상 장기 안전도 ${bestSim.safetyScore}점, 예상 항암 효능 ${bestSim.efficacyScore}점으로 두 지표의 균형이 가장 좋은 조합입니다.`],
      ];
    }
    return [
      ['1. Target antigen', `${tgtName}, selectivity +${bestSim.tgt.selectivity.toFixed(1)} log2FC`, 'Low in normal organs and high in the tumor, so healthy tissue is spared.'],
      ['2. Chemical linker', `${s.linker}, plasma stability ${bestSim.lnk.stability}%`, `Keeps drug from leaking into ${activeOrgs.join(', ') || 'major organs'} and releases it inside the tumor.`],
      ['3. Cytotoxic payload', `${plName}, ${bestSim.pld.cls}`, 'Relatively low toxicity on this patient\'s vulnerable organs while keeping antitumor potency.'],
      ['4. DAR and Fc', `DAR ${s.dar}, ${s.fc ? 'Fc silenced' : 'wild-type IgG1'}`, `Expected organ safety ${bestSim.safetyScore} and antitumor efficacy ${bestSim.efficacyScore}: the best balance of the two.`],
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
    let optBtn = null;

    // A pace that speeds up, stalls and speeds up again like real work, instead of one constant crawl.
    const PACE = [[0, 0], [0.1, 0.06], [0.24, 0.31], [0.36, 0.38], [0.58, 0.77], [0.7, 0.81], [0.88, 0.97], [1, 1]];
    function pace(f) {
      for (let i = 1; i < PACE.length; i++) {
        if (f <= PACE[i][0]) {
          const [t0, p0] = PACE[i - 1];
          const [t1, p1] = PACE[i];
          const u = (f - t0) / (t1 - t0);
          return p0 + (p1 - p0) * (u * u * (3 - 2 * u));
        }
      }
      return 1;
    }

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
              hideMicroPopover();
              onPick(val);
              if (!hasPatientProfile()) {
                S.studioDesignMode = 'idle';
              } else {
                if (S.studioDesignMode === 'auto') S.studioDesignMode = 'manual';
                if (S.studioDesignMode === 'manual') pushManualHistory();
              }
              save();
              renderControls();
              renderStudioCanvas(false);
              if (S.studioDesignMode !== 'idle' && hasPatientProfile()) {
                openStudioCompareDrawer(computeStudioSimulation(), evaluateAllStudioCandidates());
              }
            },
          });
          pills.append(b);
        });
        return h('div', { class: 'studio-group' }, h('span', { class: 'studio-label', text: label }), pills);
      };

      const fcItems = STUDIO_FC_ITEMS.map((item) => ({
        id: item.isSilenced ? t('silFc') : t('wtFc'),
        popover: item.popover,
        popover_ko: item.popover_ko,
      }));

      const manualBtn = h('button', {
        type: 'button',
        class: 'btn-manual-design' + (S.studioDesignMode === 'manual' ? ' is-active' : ''),
        text: t('manualOpt'),
        onclick: () => runManualSimulation(),
      });

      optBtn = h('button', {
        type: 'button',
        class: 'btn-optimize' + (isOptimizing ? ' is-running' : '') + (S.studioDesignMode === 'auto' && !isOptimizing ? ' is-optimal' : ''),
        text: t('autoOpt'),
        'aria-busy': isOptimizing ? 'true' : 'false',
        onclick: () => runOptimizationSimulation(),
      });

      const actionBtnRow = h('div', { class: 'studio-btn-row' }, manualBtn, optBtn);

      controls.append(
        makeGroup(t('tgtTitle'), STUDIO_TARGETS, S.studio.target, (v) => { S.studio.target = v; autoRationale = null; }),
        makeGroup(t('lnkTitle'), STUDIO_LINKERS, S.studio.linker, (v) => { S.studio.linker = v; autoRationale = null; }),
        makeGroup(t('pldTitle'), STUDIO_PAYLOADS, S.studio.payload, (v) => { S.studio.payload = v; autoRationale = null; }),
        makeGroup(t('darTitle'), STUDIO_DAR_ITEMS, String(S.studio.dar), (v) => { S.studio.dar = parseFloat(v); autoRationale = null; }, true),
        makeGroup(t('fcTitle'), fcItems, S.studio.fc ? t('silFc') : t('wtFc'), (v) => { S.studio.fc = v.includes('LALA') || v.includes('침묵'); autoRationale = null; }),
        actionBtnRow
      );
    }

    let popoverEl = null;
    function showMicroPopover(targetBtn, text) {
      hideMicroPopover();
      popoverEl = h('div', { class: 'micro-popover', text });
      document.body.append(popoverEl);
      const r = targetBtn.getBoundingClientRect();
      const pw = popoverEl.offsetWidth || 270;
      const ph = popoverEl.offsetHeight || 72;
      const margin = 10;
      let left = r.left + r.width / 2 - pw / 2;
      left = Math.max(margin, Math.min(window.innerWidth - pw - margin, left));
      let top = r.top - ph - 8;
      if (top < margin) top = r.bottom + 8;
      popoverEl.style.left = Math.round(left) + 'px';
      popoverEl.style.top = Math.round(top) + 'px';
    }
    function hideMicroPopover() {
      if (popoverEl) { popoverEl.remove(); popoverEl = null; }
    }

    function pushManualHistory() {
      if (!Array.isArray(S.studioHistory)) S.studioHistory = [];
      const curSpec = Object.assign({}, S.studio);
      const key = `${curSpec.target}|${curSpec.linker}|${curSpec.payload}|${curSpec.dar}|${curSpec.fc}`;
      S.studioHistory = S.studioHistory.filter((item) => `${item.target}|${item.linker}|${item.payload}|${item.dar}|${item.fc}` !== key);
      S.studioHistory.push(curSpec);
      if (S.studioHistory.length > 6) S.studioHistory.shift();
    }

    function requirePatientProfile() {
      if (hasPatientProfile()) {
        S.studioNeedInputWarn = false;
        return true;
      }
      S.studioDesignMode = 'idle';
      S.studioNeedInputWarn = true;
      save();
      renderControls();
      renderStudioCanvas(false);
      const searchInput = box.querySelector('.wb-input-wrap input');
      if (searchInput) searchInput.focus();
      return false;
    }

    function runManualSimulation() {
      if (isOptimizing) return;
      hideMicroPopover();
      if (!requirePatientProfile()) return;
      S.studioDesignMode = 'manual';
      pushManualHistory();
      save();
      renderControls();
      renderStudioCanvas(false);
    }

    function runOptimizationSimulation() {
      if (isOptimizing) return;
      hideMicroPopover();
      if (!requirePatientProfile()) return;
      isOptimizing = true;
      S.studioDesignMode = 'auto';
      save();
      closeDrawer();
      renderControls();
      renderStudioCanvas(true);
    }

    const riskLevel = (pct) => {
      const ko = S.lang === 'ko';
      return pct >= 60 ? (ko ? '높음' : 'High') : pct >= 35 ? (ko ? '보통' : 'Moderate') : (ko ? '낮음' : 'Low');
    };
    const riskColor = (pct) => (pct >= 60 ? 'var(--red)' : pct >= 35 ? 'var(--amber)' : 'var(--emerald)');

    function renderStudioCanvas(animateScan) {
      clear(canvas);
      const isKo = S.lang === 'ko';
      const sim = computeStudioSimulation();
      const evalSpace = evaluateAllStudioCandidates();
      const tgt = sim.tgt;
      const lnk = sim.lnk;
      const dar = sim.dar;
      const fcSilenced = sim.fcSilenced;
      const handleMatch = sim.isCompat;
      const bystander = sim.bystander;
      const stabilityScore = Math.max(25, Math.min(98, Math.round(lnk.stability - (dar > 4 ? (dar - 4) * 2.5 : 0))));

      // 1. The chart of every design combination for this patient
      if (!hasPatientProfile() && S.studioDesignMode !== 'idle') {
        S.studioDesignMode = 'idle';
      }
      const simWrap = h('section', { class: 'sim-canvas-panel panel' });
      const total = evalSpace.cands.length;
      const designMode = S.studioDesignMode || 'idle';
      const initialStatus = animateScan
        ? (isKo ? `설계 조합 0 / ${total.toLocaleString()}개 계산 중` : `Scoring 0 / ${total.toLocaleString()} combinations`)
        : !hasPatientProfile()
          ? (isKo ? '환자 정보 미입력 (질환 또는 검진 수치를 먼저 입력하세요)' : 'Patient info required (Enter conditions or lab values first)')
          : designMode === 'idle'
            ? (isKo ? '설계 대기 중 (수동 설계 또는 자동 설계를 실행하세요)' : 'Ready (Click Manual ADC Design or Auto-design ADC)')
            : (isKo ? `안전도 ${sim.safetyScore}점 / 항암 효능 ${sim.efficacyScore}점` : `Safety ${sim.safetyScore} / Efficacy ${sim.efficacyScore}`);

      const simStatusEl = h('span', {
        class: 'sim-canvas-status' + (S.studioNeedInputWarn && !hasPatientProfile() ? ' is-warn' : ''),
        text: initialStatus,
      });
      const simHead = h('div', { class: 'sim-canvas-head' },
        h('span', { class: 'sim-canvas-title', text: t('designTitle') }),
        simStatusEl);

      const chartWrap = h('div', { class: 'sim-chart-wrap' });
      const cvs = h('canvas', { class: 'sim-canvas' });
      chartWrap.append(cvs);
      if (S.studioNeedInputWarn && !hasPatientProfile()) {
        chartWrap.append(h('div', { class: 'sim-need-patient-banner' },
          h('span', {
            text: isKo
              ? '환자 맞춤형 설계를 실행하려면 먼저 암종, 기저질환 또는 검진 수치를 입력해야 합니다.'
              : 'Enter patient conditions or lab values first to run patient-tailored ADC design.',
          }),
          h('button', {
            type: 'button',
            class: 'btn-goto-patient',
            text: isKo ? '1. 환자 정보 탭으로 이동 →' : 'Go to 1. Patient Info →',
            onclick: () => switchMode(0),
          })));
      }

      const eqGrid = h('div', { class: 'sim-eq-grid' });
      const summaryMeta = h('span', { class: 'sim-summary-meta' });
      const rBox = h('div', { class: 'sim-rationale-box' });
      const organRows = h('div', { class: 'expr-list' });

      function updateOrganRowsDom(curSim) {
        clear(organRows);
        curSim.organRisks.forEach((item) => {
          const pct = Math.round(item.p * 100);
          const color = riskColor(pct);
          organRows.append(h('div', { class: 'expr-row' },
            h('span', { class: 'ex-name', text: organKo(item.organ) }),
            h('span', { class: 'ex-track' }, h('i', { class: 'ex-fill', style: `width:${Math.max(4, pct)}%;background:${color}` })),
            h('span', { class: 'ex-val', style: `color:${color}`, text: `${riskLevel(pct)} ${pct}%` })));
        });
      }

      function updateRationaleDom(curSim, curSpace) {
        clear(rBox);
        const bestC = curSpace.best;
        const activeRat = buildAutoOptimizeRationales(bestC);
        const isOpt = (
          S.studio.target === bestC.spec.target &&
          S.studio.linker === bestC.spec.linker &&
          S.studio.payload === bestC.spec.payload &&
          Number(S.studio.dar) === Number(bestC.spec.dar) &&
          Boolean(S.studio.fc) === Boolean(bestC.spec.fc)
        );
        rBox.append(
          h('div', { class: 'srb-title' },
            h('span', { class: 'srb-main-text', text: isOpt ? t('optimalLocked') : `${t('optimalCand')} ${plainName(bestC.spec.target)} + ${plainName(bestC.spec.payload)}, DAR ${bestC.spec.dar}` }),
            h('button', {
              type: 'button', class: 'btn-compare-pop',
              text: t('viewCompareBtn'),
              onclick: () => openStudioCompareDrawer(curSim, curSpace),
            })),
          h('div', { class: 'srb-steps' },
            activeRat.map(([title, choice, desc]) => h('div', { class: 'srb-step' },
              h('b', { text: `${title}: ${choice}` }),
              h('span', { text: desc }))))
        );
      }

      function updateFormulaLines(curSim, curSpace) {
        const w = Object.assign({}, DEFAULT_SIM_WEIGHTS, S.simWeights || {});
        const sNow = curSim || sim;
        const spNow = curSpace || evalSpace;
        const wSafeEff = spNow.wSafety != null ? spNow.wSafety : w.wSafety;
        const wEffComp = Math.max(0, 1 - wSafeEff);
        const wMean = Math.max(0, 1 - w.wPeak);
        const wOff = Math.max(0, 1 - w.wExpr);
        const utilVal = (wSafeEff * sNow.safetyRaw + wEffComp * sNow.efficacyRaw).toFixed(1);

        const activePresetObj = SIM_WEIGHT_PRESETS.find((p) => p.id === S.simPreset);
        const presetLabel = activePresetObj ? (isKo ? activePresetObj.ko : activePresetObj.en) : (isKo ? '사용자 정의 계수' : 'Custom Weights');
        summaryMeta.textContent = isKo
          ? `${presetLabel} | 치료지수 U = ${utilVal}`
          : `${presetLabel} | Utility U = ${utilVal}`;

        clear(eqGrid);
        const cards = isKo
          ? [
              {
                tag: '1. 치료지수 목적함수 (Therapeutic Index)',
                sym: 'U_TI',
                eq: `U = ${wSafeEff.toFixed(2)} * X_safe + ${wEffComp.toFixed(2)} * Y_eff`,
                desc: `파레토 프론티어 상에서 장기 보존 안전도(X)와 항암 효능(Y)의 최적 균형점(Best = ${plainName(spNow.best.spec.target)} + ${plainName(spNow.best.spec.payload)}, DAR ${spNow.best.spec.dar})을 결정합니다.`,
              },
              {
                tag: '2. 이중 경로 장기 안전도 (Two-Pathway PK/PD Safety)',
                sym: 'X_safe',
                eq: `X = 100 * [1 - (${w.wPeak.toFixed(2)} * p_max + ${wMean.toFixed(2)} * p_mean)],  p(o) = 1 - exp(-0.56 * H_o)`,
                desc: `H_o = V_o * [${wOff.toFixed(2)} * OffTarget(누출:${w.leakSens.toFixed(2)}, 응집:${w.hydroSens.toFixed(2)}, Fc보호:${Math.round(w.fcProtect * 100)}%) + ${w.wExpr.toFixed(2)} * OnTarget(GTEx * DAR/4)]`,
              },
              {
                tag: '3. 다중 기전 항암 효능 (Normalized Convex Efficacy)',
                sym: 'Y_eff',
                eq: `Y = 100 * Ind * Pair * [${(sNow.nwSel || 0.25).toFixed(2)}*S_sel + ${(sNow.nwPot || 0.30).toFixed(2)}*S_pot + ${(sNow.nwDel || 0.23).toFixed(2)}*S_deliv + ${(sNow.nwBys || 0.22).toFixed(2)}*S_bys]`,
                desc: '종양 발현 선택도(S_sel), 페이로드-DAR 세포독성(S_pot), 혈장 전달률(S_deliv), 주변세포 동반사멸(S_bys)의 정규화 볼록 결합입니다.',
              },
            ]
          : [
              {
                tag: '1. Therapeutic Index Utility Objective',
                sym: 'U_TI',
                eq: `U = ${wSafeEff.toFixed(2)} * X_safe + ${wEffComp.toFixed(2)} * Y_eff`,
                desc: `Selects the Pareto-optimal construct (Best = ${plainName(spNow.best.spec.target)} + ${plainName(spNow.best.spec.payload)}, DAR ${spNow.best.spec.dar}) balancing organ safety and antitumor potency.`,
              },
              {
                tag: '2. Two-Pathway Organ Safety (Off-Target vs. On-Target)',
                sym: 'X_safe',
                eq: `X = 100 * [1 - (${w.wPeak.toFixed(2)} * p_max + ${wMean.toFixed(2)} * p_mean)],  p(o) = 1 - exp(-0.56 * H_o)`,
                desc: `H_o = V_o * [${wOff.toFixed(2)} * OffTarget(Leak:${w.leakSens.toFixed(2)}, Agg:${w.hydroSens.toFixed(2)}, Fc:${Math.round(w.fcProtect * 100)}%) + ${w.wExpr.toFixed(2)} * OnTarget(GTEx * DAR/4)]`,
              },
              {
                tag: '3. Multi-Mechanism Antitumor Efficacy (Convex Combination)',
                sym: 'Y_eff',
                eq: `Y = 100 * Ind * Pair * [${(sNow.nwSel || 0.25).toFixed(2)}*S_sel + ${(sNow.nwPot || 0.30).toFixed(2)}*S_pot + ${(sNow.nwDel || 0.23).toFixed(2)}*S_deliv + ${(sNow.nwBys || 0.22).toFixed(2)}*S_bys]`,
                desc: 'Normalized convex combination of TCGA/GTEx selectivity (S_sel), payload-DAR potency (S_pot), intact delivery (S_deliv), and bystander diffusion (S_bys).',
              },
            ];

        cards.forEach((c) => {
          eqGrid.append(h('div', { class: 'sim-eq-card' },
            h('div', { class: 'sim-eq-card-head' },
              h('span', { class: 'sim-eq-tag', text: c.tag }),
              h('code', { class: 'sim-eq-sym', text: c.sym })),
            h('div', { class: 'sim-eq-math', text: c.eq }),
            h('div', { class: 'sim-eq-desc', text: c.desc })));
        });
      }
      updateFormulaLines(sim, evalSpace);

      const PARAM_DEFS = [
        { key: 'wSafety', sym: 'λ_safe', col: 'left', min: 0.15, max: 0.85, step: 0.02,
          ko: '치료지수 안전도 가중치', en: 'TI Safety Priority',
          subKo: '파레토 최적 조합 선택 시 안전도(X) 대 효능(Y) 비중', subEn: 'Pareto trade-off weight between Organ Safety and Efficacy' },
        { key: 'wPeak', sym: 'ω_peak', col: 'left', min: 0.15, max: 0.90, step: 0.05,
          ko: '최대 위험장기 집중도', en: 'Worst-Organ Dominance',
          subKo: '단일 치명적 취약장기(Peak) 대 다장기 평균 위험 비중', subEn: 'Peak vulnerable organ hazard vs. multi-organ mean risk' },
        { key: 'wExpr', sym: 'α_on', col: 'left', min: 0.10, max: 0.85, step: 0.05,
          ko: '온타깃 정상조직 발현 비중', en: 'On-Target GTEx Weight',
          subKo: '정상 상피 항원 발현(GTEx) 대 비표적 페이로드 독성 비율', subEn: 'Antigen-mediated normal tissue toxicity vs. off-target payload risk' },
        { key: 'leakSens', sym: 'β_leak', col: 'left', min: 0.20, max: 2.20, step: 0.05,
          ko: '링커 조기절단 민감도', en: 'Linker Instability Penalty',
          subKo: '혈중 비특이 가수분해 및 유리 페이로드 전신 누출 페널티', subEn: 'Systemic free-payload leakage from plasma linker deconjugation' },
        { key: 'hydroSens', sym: 'γ_agg', col: 'right', min: 0.20, max: 2.20, step: 0.05,
          ko: '소수성 고DAR 응집 페널티', en: 'Hydrophobic DAR Penalty',
          subKo: '고밀도 접합 시 간 쿠퍼세포 포획 및 약동학 청소 손실', subEn: 'Hepatic Kupffer-cell uptake and PK clearance at high DAR' },
        { key: 'fcProtect', sym: 'φ_Fc', col: 'right', min: 0.05, max: 0.65, step: 0.02,
          ko: 'Fc 침묵화(LALA-PG) 보호율', en: 'Fc-Silencing Protection',
          subKo: '폐포 대식세포, 간, 골수의 FcγR 비특이 흡수 차단율', subEn: 'Attenuation of FcγR macrophage uptake in lung, liver, and marrow' },
        { key: 'wSelect', sym: 'w_sel', col: 'right', min: 0.10, max: 0.70, step: 0.02,
          ko: '항원 종양선택도 효능 비중', en: 'Target Selectivity Weight',
          subKo: 'TCGA 종양 과발현 배수(log2FC)의 항암 효능 기여도', subEn: 'Contribution of tumor-to-normal log2FC margin to efficacy' },
        { key: 'wBystander', sym: 'w_bys', col: 'right', min: 0.05, max: 0.65, step: 0.02,
          ko: '주변세포 동반사멸 비중', en: 'Bystander Killing Weight',
          subKo: '절단형 링커 + 막투과성 약물의 이질성 종양 확산 효과', subEn: 'Membrane-permeable payload diffusion in heterogeneous tumors' },
      ];

      const colLeft = h('div', { class: 'sim-param-col' },
        h('div', { class: 'sim-col-header', text: isKo ? 'I. 치료지수 및 전신 독성 경로 계수' : 'I. Therapeutic Index & Toxicity Pathway Weights' }));
      const colRight = h('div', { class: 'sim-param-col' },
        h('div', { class: 'sim-col-header', text: isKo ? 'II. 접합 생물물리 및 항암 효능 계수' : 'II. Conjugation Biophysics & Antitumor Efficacy Weights' }));

      const inputRefs = {};
      function syncSliderFill(rangeEl, val, min, max) {
        const pct = Math.max(0, Math.min(100, ((val - min) / Math.max(0.0001, max - min)) * 100));
        rangeEl.style.setProperty('--pct', `${pct.toFixed(1)}%`);
      }

      function refreshLiveFormulaState() {
        let newSpace = evaluateAllStudioCandidates();
        if (S.studioDesignMode === 'auto' && hasPatientProfile()) {
          const b = newSpace.best;
          S.studio.target = b.spec.target;
          S.studio.linker = b.spec.linker;
          S.studio.payload = b.spec.payload;
          S.studio.dar = b.spec.dar;
          S.studio.fc = b.spec.fc;
          renderControls();
        }
        const newSim = computeStudioSimulation();
        updateFormulaLines(newSim, newSpace);
        updateOrganRowsDom(newSim);
        updateRationaleDom(newSim, newSpace);
        if (S.studioDesignMode !== 'idle' && hasPatientProfile()) {
          simStatusEl.textContent = isKo
            ? `안전도 ${newSim.safetyScore}점 / 항암 효능 ${newSim.efficacyScore}점`
            : `Safety ${newSim.safetyScore} / Efficacy ${newSim.efficacyScore}`;
        }
        initDesignChart(cvs, newSim, newSpace, false);
      }

      PARAM_DEFS.forEach((pd) => {
        const curVal = Number((S.simWeights && S.simWeights[pd.key]) ?? DEFAULT_SIM_WEIGHTS[pd.key]);
        const numInput = h('input', {
          type: 'number',
          class: 'sim-param-num',
          min: String(pd.min),
          max: String(pd.max),
          step: String(pd.step),
          value: curVal.toFixed(2),
        });
        const rangeInput = h('input', {
          type: 'range',
          class: 'sim-param-range',
          min: String(pd.min),
          max: String(pd.max),
          step: String(pd.step),
          value: String(curVal),
        });
        syncSliderFill(rangeInput, curVal, pd.min, pd.max);
        inputRefs[pd.key] = { numInput, rangeInput, pd };

        function applyWeight(rawV) {
          const parsed = parseFloat(rawV);
          if (isNaN(parsed)) return;
          const clamped = Math.max(pd.min, Math.min(pd.max, Math.round(parsed * 100) / 100));
          if (!S.simWeights) S.simWeights = Object.assign({}, DEFAULT_SIM_WEIGHTS);
          S.simWeights[pd.key] = clamped;
          S.simPreset = 'custom';
          presetBtns.forEach((b) => b.classList.toggle('is-active', false));
          numInput.value = clamped.toFixed(2);
          rangeInput.value = String(clamped);
          syncSliderFill(rangeInput, clamped, pd.min, pd.max);
          save();
          refreshLiveFormulaState();
        }
        rangeInput.addEventListener('input', (e) => applyWeight(e.target.value));
        numInput.addEventListener('change', (e) => applyWeight(e.target.value));

        const card = h('div', { class: 'sim-param-card' },
          h('div', { class: 'sim-param-top' },
            h('div', { class: 'sim-param-title-wrap' },
              h('code', { class: 'sim-param-sym', text: pd.sym }),
              h('span', { class: 'sim-param-label', text: isKo ? pd.ko : pd.en })),
            numInput),
          h('div', { class: 'sim-param-sub', text: isKo ? pd.subKo : pd.subEn }),
          rangeInput);

        if (pd.col === 'left') colLeft.append(card);
        else colRight.append(card);
      });

      const presetBtns = [];
      const presetGroup = h('div', { class: 'sim-preset-group' });
      SIM_WEIGHT_PRESETS.forEach((pr) => {
        const pb = h('button', {
          type: 'button',
          class: 'sim-preset-btn' + ((S.simPreset || 'balanced') === pr.id ? ' is-active' : ''),
          text: isKo ? pr.ko : pr.en,
          onclick: () => {
            S.simPreset = pr.id;
            S.simWeights = Object.assign({}, DEFAULT_SIM_WEIGHTS, pr.weights);
            presetBtns.forEach((b) => b.classList.toggle('is-active', b === pb));
            Object.keys(inputRefs).forEach((k) => {
              const ref = inputRefs[k];
              const v = S.simWeights[k];
              ref.numInput.value = v.toFixed(2);
              ref.rangeInput.value = String(v);
              syncSliderFill(ref.rangeInput, v, ref.pd.min, ref.pd.max);
            });
            save();
            refreshLiveFormulaState();
          },
        });
        presetBtns.push(pb);
        presetGroup.append(pb);
      });

      const explainToolbar = h('div', { class: 'sim-param-toolbar' },
        h('div', { class: 'sim-preset-wrap' },
          h('span', { class: 'sim-param-hint', text: isKo ? '임상 시나리오 프리셋' : 'Clinical Scenario Presets' }),
          presetGroup),
        h('button', {
          type: 'button',
          class: 'sim-param-reset',
          text: isKo ? '기본값 복원' : 'Reset Defaults',
          onclick: () => {
            S.simPreset = 'balanced';
            S.simWeights = Object.assign({}, DEFAULT_SIM_WEIGHTS);
            presetBtns.forEach((b, idx) => b.classList.toggle('is-active', idx === 0));
            Object.keys(inputRefs).forEach((k) => {
              const ref = inputRefs[k];
              const v = S.simWeights[k];
              ref.numInput.value = v.toFixed(2);
              ref.rangeInput.value = String(v);
              syncSliderFill(ref.rangeInput, v, ref.pd.min, ref.pd.max);
            });
            save();
            refreshLiveFormulaState();
          },
        }));

      const paramColumns = h('div', { class: 'sim-param-columns' }, colLeft, colRight);

      const explain = h('details', {
        class: 'sim-explain',
        open: S.formulaOpen ? '' : null,
        ontoggle: (e) => { S.formulaOpen = e.currentTarget.open; save(); },
      },
      h('summary', null,
        h('span', { class: 'sim-summary-title', text: t('explainTitle') }),
        summaryMeta),
      explainToolbar,
      eqGrid,
      paramColumns);
      simWrap.append(simHead, chartWrap, explain);

      // Recommended design and why
      updateRationaleDom(sim, evalSpace);
      if (designMode !== 'idle') simWrap.append(rBox);

      // 2. Metrics strip
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

      // 3. Organ risk and normal-tissue expression
      updateOrganRowsDom(sim);

      const gtexRows = h('div', { class: 'expr-list' });
      tgt.tissues.forEach((tis) => {
        const val = tis.tpm;
        const color = val > 50 ? 'var(--red)' : val >= 25 ? 'var(--amber)' : 'var(--emerald)';
        const level = val > 50 ? (isKo ? '높음' : 'High') : val >= 25 ? (isKo ? '보통' : 'Moderate') : (isKo ? '낮음' : 'Low');
        gtexRows.append(h('div', { class: 'expr-row' },
          h('span', { class: 'ex-name', text: organKo(tis.organ) }),
          h('span', { class: 'ex-track' }, h('i', { class: 'ex-fill', style: `width:${Math.min(100, val * 1.5)}%;background:${color}` })),
          h('span', { class: 'ex-val', style: `color:${color}`, text: `${level} ${val}` })));
      });

      const grid2 = h('div', { class: 'studio-grid-2' },
        h('section', { class: 'studio-card panel' },
          h('h3', { text: t('simOrganTitle') }),
          organRows,
          h('p', { class: 'dim', style: 'margin:12px 0 0', text: isKo
            ? `이 설계가 환자의 취약 장기에 독성을 일으킬 가능성을 모델로 환산한 값입니다. 막대가 짧고 녹색일수록 안전합니다. ${fcSilenced ? t('fcLalaNote') : t('fcWtNote')}`
            : `Modeled chance that this design harms each vulnerable organ; a shorter green bar is safer. ${fcSilenced ? t('fcLalaNote') : t('fcWtNote')}` })),
        h('section', { class: 'studio-card panel' },
          h('h3', { text: t('gtexTitle') }),
          gtexRows,
          h('p', { class: 'dim', style: 'margin:12px 0 0', text: `${tgt.gene} ${t('gtexNote')}` })));

      canvas.append(simWrap, hero, grid2);

      setTimeout(() => initDesignChart(cvs, sim, evalSpace, animateScan,
        (f, shown) => {
          simStatusEl.textContent = isKo
            ? `설계 조합 ${shown.toLocaleString()} / ${total.toLocaleString()}개 계산 중`
            : `Scoring ${shown.toLocaleString()} / ${total.toLocaleString()} combinations`;
          if (optBtn) optBtn.style.setProperty('--p', (f * 100).toFixed(1) + '%');
        },
        () => {
          if (!animateScan) return;
          if (optBtn) optBtn.style.setProperty('--p', '100%');
          setTimeout(() => {
            isOptimizing = false;
            const best = evalSpace.best;
            S.studio.target = best.spec.target;
            S.studio.linker = best.spec.linker;
            S.studio.payload = best.spec.payload;
            S.studio.dar = best.spec.dar;
            S.studio.fc = best.spec.fc;
            autoRationale = buildAutoOptimizeRationales(best);
            save();
            if (S.mode !== 2) return;
            renderControls();
            renderStudioCanvas(false);
            setTimeout(() => { if (S.mode === 2) openStudioCompareDrawer(best, evalSpace); }, 600);
          }, 700);
        }), 0);
    }

    function initDesignChart(cvs, currentSim, evalSpace, animate, onProgress, onComplete) {
      const ctx = cvs.getContext('2d');
      if (!ctx) return;

      cancelAnimationFrame(simAnimId);
      if (studioChartRO) {
        studioChartRO.disconnect();
        studioChartRO = null;
      }

      const cands = evalSpace.cands;
      const best = evalSpace.best;

      // Fixed 0-100 clinical coordinate frame so parameter adjustments visibly translate and separate candidate clusters
      const minX = 0;
      const maxX = 100;
      const minY = 0;
      const maxY = 100;
      const spanX = 100;
      const spanY = 100;

      // fixed pseudo-random order, so the dots appear scattered rather than sweeping across
      const shuffled = cands.slice().map((c, i) => ({
        c,
        sortKey: Math.sin(i * 12345.67) * 10000 - Math.floor(Math.sin(i * 12345.67) * 10000),
      })).sort((a, b) => a.sortKey - b.sortKey).map((item) => item.c);

      const startTime = performance.now();
      const duration = (animate && !still()) ? 4200 : 0;
      let completed = false;

      // Compute Pareto frontier points (non-dominated compatible candidates)
      const compatCands = cands.filter((c) => c.isCompat).slice().sort((a, b) => (b.safetyRaw - a.safetyRaw) || (b.efficacyRaw - a.efficacyRaw));
      const paretoFront = [];
      let maxEffSeen = -1;
      for (const c of compatCands) {
        if (c.efficacyRaw > maxEffSeen + 0.2) {
          paretoFront.push(c);
          maxEffSeen = c.efficacyRaw;
        }
      }

      function drawCalloutLabel(text, dotX, dotY, preferAbove, offsetX, offsetY, plotW, plotH, dpr, color, avoidBox) {
        ctx.font = `bold ${10 * dpr}px sans-serif`;
        const textW = ctx.measureText(text).width;
        const boxH = 14 * dpr;
        const gap = 9 * dpr;
        let tx = dotX + gap;
        if (tx + textW > offsetX + plotW - 6 * dpr) {
          tx = dotX - gap - textW;
        }
        tx = Math.max(offsetX + 6 * dpr, Math.min(offsetX + plotW - textW - 6 * dpr, tx));
        let ty = preferAbove ? (dotY - 9 * dpr) : (dotY + 16 * dpr);
        if (ty - 11 * dpr < offsetY + 4 * dpr) ty = dotY + 16 * dpr;
        if (ty > offsetY + plotH - 6 * dpr) ty = dotY - 9 * dpr;

        const box = { x: tx - 4 * dpr, y: ty - 11 * dpr, w: textW + 8 * dpr, h: boxH };
        if (avoidBox) {
          const overlapsX = box.x < avoidBox.x + avoidBox.w + 4 * dpr && box.x + box.w + 4 * dpr > avoidBox.x;
          const overlapsY = box.y < avoidBox.y + avoidBox.h + 2 * dpr && box.y + box.h + 2 * dpr > avoidBox.y;
          if (overlapsX && overlapsY) {
            const downY = avoidBox.y + avoidBox.h + 14 * dpr;
            const upY = avoidBox.y - 6 * dpr;
            if (downY <= offsetY + plotH - 5 * dpr) ty = downY;
            else if (upY - 11 * dpr >= offsetY + 4 * dpr) ty = upY;
            box.y = ty - 11 * dpr;
          }
        }

        ctx.textAlign = 'left';
        ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
        ctx.fillRect(box.x, box.y, box.w, box.h);
        ctx.strokeStyle = 'rgba(203, 213, 225, 0.85)';
        ctx.lineWidth = 1 * dpr;
        ctx.strokeRect(box.x, box.y, box.w, box.h);
        ctx.fillStyle = color;
        ctx.fillText(text, tx, ty);
        return box;
      }

      function renderFrame(now) {
        if (!cvs.isConnected) return;
        const rect = cvs.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const w = Math.max(260 * dpr, Math.round((rect.width || 600) * dpr));
        const h = Math.max(240 * dpr, Math.round((rect.height || 380) * dpr));
        if (cvs.width !== w || cvs.height !== h) {
          cvs.width = w;
          cvs.height = h;
        }

        const isKo = S.lang === 'ko';
        const modeNow = animate ? 'auto' : (S.studioDesignMode || 'idle');
        const legend = modeNow === 'idle'
          ? []
          : modeNow === 'manual'
            ? [
                ['#2563EB', 4.5, t('legendCur')],
                ['#D97706', 4.0, isKo ? '동일 표적 승인 약물' : 'Approved Ref ADC'],
                ['rgba(100, 116, 139, 0.55)', 3.2, isKo ? '동일 표적 후보군' : 'Same-Target Pool'],
              ]
            : [
                ['rgba(100, 116, 139, 0.75)', 3, `${t('legendCand')} ${cands.length.toLocaleString()}`],
                ['rgba(239, 68, 68, 0.6)', 3, t('legendBad')],
                ['#0D9488', 4.5, t('legendBest')],
                ['#2563EB', 4.5, t('legendCur')],
              ];
        ctx.font = `600 ${10 * dpr}px sans-serif`;
        const padL = 52 * dpr, padR = 24 * dpr, padB = 42 * dpr, padT = 44 * dpr;
        const maxPlotW = Math.max(140 * dpr, w - padL - padR);
        const maxPlotH = Math.max(140 * dpr, h - padT - padB);

        // square plot box so the two axes are never stretched differently
        const plotSize = Math.max(140 * dpr, Math.min(maxPlotW, maxPlotH));
        const plotW = plotSize;
        const plotH = plotSize;
        const offsetX = padL + (maxPlotW - plotW) / 2;
        const offsetY = padT + (maxPlotH - plotH) / 2;

        const toX = (val) => offsetX + ((Math.max(minX, Math.min(maxX, val)) - minX) / spanX) * plotW;
        const toY = (val) => offsetY + (1 - (Math.max(minY, Math.min(maxY, val)) - minY) / spanY) * plotH;

        const tfrac = duration > 0 ? Math.min(1, (now - startTime) / duration) : 1;
        const f = duration > 0 ? pace(tfrac) : 1;
        const shown = Math.floor(cands.length * f);
        if (animate && onProgress && !completed) onProgress(f, shown);

        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(0, 0, w, h);

        ctx.strokeStyle = '#CBD5E1';
        ctx.lineWidth = 1 * dpr;
        ctx.strokeRect(offsetX, offsetY, plotW, plotH);

        ctx.strokeStyle = '#F1F5F9';
        ctx.lineWidth = 1 * dpr;
        ctx.font = `600 ${10 * dpr}px sans-serif`;
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

        ctx.font = `bold ${11 * dpr}px sans-serif`;
        ctx.fillStyle = '#1E293B';
        ctx.textAlign = 'center';
        ctx.fillText(t('axisSafety'), offsetX + plotW / 2, offsetY + plotH + 31 * dpr);
        ctx.save();
        ctx.translate(offsetX - 34 * dpr, offsetY + plotH / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(t('axisEfficacy'), 0, 0);
        ctx.restore();

        // Single-row compact legend above the plot
        if (legend.length) {
          ctx.textAlign = 'left';
          ctx.font = `600 ${9.5 * dpr}px sans-serif`;
          let lx = offsetX;
          const ly = offsetY - 14 * dpr;
          legend.forEach(([col, rad, label]) => {
            const need = (rad * 2 + 5) * dpr + ctx.measureText(label).width + 11 * dpr;
            ctx.fillStyle = col;
            ctx.beginPath(); ctx.arc(lx + rad * dpr, ly, rad * dpr, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = '#64748B';
            ctx.fillText(label, lx + (rad * 2 + 5) * dpr, ly + 3.2 * dpr);
            lx += need;
          });
        }

        if (modeNow === 'idle') {
          ctx.fillStyle = 'rgba(248, 250, 252, 0.72)';
          ctx.fillRect(offsetX + 1 * dpr, offsetY + 1 * dpr, plotW - 2 * dpr, plotH - 2 * dpr);
          ctx.fillStyle = '#475569';
          ctx.font = `bold ${11.5 * dpr}px sans-serif`;
          ctx.textAlign = 'center';
          const idleMsg = !hasPatientProfile()
            ? (isKo
                ? '먼저 암종, 기저질환 또는 검진 정보를 입력한 뒤 설계를 실행하세요'
                : 'Enter patient conditions or lab values first, then run design simulation')
            : (isKo
                ? '왼쪽에서 [ADC 수동 설계] 또는 [ADC 자동 설계] 버튼을 눌러 시뮬레이션을 실행하세요'
                : 'Click [Manual ADC Design] or [Auto-design ADC] on the left to plot results');
          ctx.fillText(idleMsg, offsetX + plotW / 2, offsetY + plotH / 2 + 4 * dpr);
          return;
        }

        if (modeNow === 'auto') {
          // dots appear at their true continuous positions
          for (let k = 0; k < shown; k++) {
            const c = shuffled[k];
            const isSameTgt = c.spec.target === best.spec.target;
            ctx.fillStyle = !c.isCompat
              ? 'rgba(239, 68, 68, 0.25)'
              : isSameTgt
                ? 'rgba(13, 148, 136, 0.55)'
                : 'rgba(100, 116, 139, 0.36)';
            ctx.beginPath();
            ctx.arc(toX(c.safetyRaw), toY(c.efficacyRaw), (isSameTgt && c.isCompat ? 2.7 : 2.2) * dpr, 0, Math.PI * 2);
            ctx.fill();
          }

          // Draw Pareto Frontier curve once scan completes
          if ((f >= 0.97 || !animate) && paretoFront.length >= 2) {
            ctx.save();
            ctx.strokeStyle = 'rgba(13, 148, 136, 0.55)';
            ctx.lineWidth = 1.8 * dpr;
            ctx.setLineDash([4 * dpr, 3 * dpr]);
            ctx.beginPath();
            paretoFront.forEach((p, idx) => {
              const px = toX(p.safetyRaw), py = toY(p.efficacyRaw);
              if (idx === 0) ctx.moveTo(px, py);
              else ctx.lineTo(px, py);
            });
            ctx.stroke();
            ctx.restore();
          }
        } else if (modeNow === 'manual') {
          // In manual mode: show the active target's compatible sub-cloud lightly so the user sees the local landscape,
          // plus the Reference Approved ADC for this target, plus previous manual attempts!
          const sameTargetCands = cands.filter((c) => c.spec.target === currentSim.spec.target && c.isCompat);
          sameTargetCands.forEach((c) => {
            ctx.fillStyle = 'rgba(148, 163, 184, 0.35)';
            ctx.beginPath();
            ctx.arc(toX(c.safetyRaw), toY(c.efficacyRaw), 2.3 * dpr, 0, Math.PI * 2);
            ctx.fill();
          });

          // Reference Approved ADC for the selected target
          const refBase = REF_STUDIO[currentSim.spec.target];
          let refBox = null;
          if (refBase) {
            const refSim = computeStudioSimulation(Object.assign({ target: currentSim.spec.target }, refBase));
            const rx = toX(refSim.safetyRaw), ry = toY(refSim.efficacyRaw);
            const sxNow = toX(currentSim.safetyRaw), syNow = toY(currentSim.efficacyRaw);

            // Dashed comparison vector from Approved Ref ADC to Current Manual Design
            if (Math.hypot(rx - sxNow, ry - syNow) > 6 * dpr) {
              ctx.save();
              ctx.strokeStyle = 'rgba(217, 119, 6, 0.65)';
              ctx.lineWidth = 1.5 * dpr;
              ctx.setLineDash([4 * dpr, 3 * dpr]);
              ctx.beginPath();
              ctx.moveTo(rx, ry);
              ctx.lineTo(sxNow, syNow);
              ctx.stroke();
              ctx.restore();
            }

            ctx.fillStyle = 'rgba(217, 119, 6, 0.18)';
            ctx.beginPath(); ctx.arc(rx, ry, 8.5 * dpr, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = '#D97706';
            ctx.strokeStyle = '#FFFFFF';
            ctx.lineWidth = 1.8 * dpr;
            ctx.beginPath(); ctx.arc(rx, ry, 4.5 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();

            if (Math.hypot(rx - sxNow, ry - syNow) > 8 * dpr) {
              const refAdcId = currentSim.tgt.refAdc || '';
              const refBrand = (ADC_SPECS[refAdcId] && ADC_SPECS[refAdcId].brand) || (isKo ? '승인 약물' : 'Approved');
              const refLbl = `${refBrand} (${refSim.safetyScore}, ${refSim.efficacyScore})`;
              refBox = drawCalloutLabel(refLbl, rx, ry, true, offsetX, offsetY, plotW, plotH, dpr, '#B45309', null);
            }
          }

          // Previous manual history trail
          const hist = Array.isArray(S.studioHistory) ? S.studioHistory : [];
          if (hist.length >= 2) {
            ctx.save();
            ctx.strokeStyle = 'rgba(37, 99, 235, 0.35)';
            ctx.lineWidth = 1.4 * dpr;
            ctx.beginPath();
            hist.forEach((hSpec, idx) => {
              const hSim = computeStudioSimulation(hSpec);
              const hx = toX(hSim.safetyRaw), hy = toY(hSim.efficacyRaw);
              if (idx === 0) ctx.moveTo(hx, hy);
              else ctx.lineTo(hx, hy);
              if (idx < hist.length - 1) {
                ctx.fillStyle = 'rgba(37, 99, 235, 0.40)';
                ctx.beginPath(); ctx.arc(hx, hy, 3.2 * dpr, 0, Math.PI * 2); ctx.fill();
              }
            });
            ctx.stroke();
            ctx.restore();
          }

          const sx = toX(currentSim.safetyRaw);
          const sy = toY(currentSim.efficacyRaw);
          ctx.fillStyle = 'rgba(37, 99, 235, 0.22)';
          ctx.beginPath(); ctx.arc(sx, sy, 10 * dpr, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = '#2563EB';
          ctx.strokeStyle = '#FFFFFF';
          ctx.lineWidth = 2 * dpr;
          ctx.beginPath(); ctx.arc(sx, sy, 5.2 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();

          const curLabel = `${plainName(currentSim.spec.target)} + ${plainName(currentSim.spec.payload)}, DAR ${currentSim.spec.dar} (${currentSim.safetyScore}, ${currentSim.efficacyScore})`;
          drawCalloutLabel(curLabel, sx, sy, false, offsetX, offsetY, plotW, plotH, dpr, '#1E40AF', refBox);
          return;
        }

        const bx = toX(best.safetyRaw);
        const by = toY(best.efficacyRaw);
        const sx = toX(currentSim.safetyRaw);
        const sy = toY(currentSim.efficacyRaw);
        const sameSpot = Math.hypot(bx - sx, by - sy) < 8 * dpr;

        // recommended design, once every combination has been scored in auto mode
        if (f >= 0.97 || !animate) {
          ctx.fillStyle = 'rgba(13, 148, 136, 0.22)';
          ctx.beginPath(); ctx.arc(bx, by, 10.5 * dpr, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = '#0D9488';
          ctx.strokeStyle = '#FFFFFF';
          ctx.lineWidth = 2 * dpr;
          ctx.beginPath(); ctx.arc(bx, by, 5.2 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        }

        // current selection
        if (!sameSpot || (f < 0.97 && animate)) {
          ctx.fillStyle = 'rgba(37, 99, 235, 0.2)';
          ctx.beginPath(); ctx.arc(sx, sy, 10 * dpr, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = '#2563EB';
          ctx.strokeStyle = '#FFFFFF';
          ctx.lineWidth = 2 * dpr;
          ctx.beginPath(); ctx.arc(sx, sy, 5 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        }

        if (f >= 0.97 || !animate) {
          if (sameSpot) {
            const unifiedLabel = `${t('legendBest')} / ${t('legendCur')}: ${plainName(best.spec.target)} + ${plainName(best.spec.payload)}, DAR ${best.spec.dar} (${best.safetyScore}, ${best.efficacyScore})`;
            drawCalloutLabel(unifiedLabel, bx, by, true, offsetX, offsetY, plotW, plotH, dpr, '#065F46', null);
          } else {
            const bestLabel = `${t('legendBest')}: ${plainName(best.spec.target)} + ${plainName(best.spec.payload)}, DAR ${best.spec.dar}`;
            const bestBox = drawCalloutLabel(bestLabel, bx, by, true, offsetX, offsetY, plotW, plotH, dpr, '#065F46', null);
            const curLabel = `${t('legendCur')} (${currentSim.safetyScore}, ${currentSim.efficacyScore})`;
            drawCalloutLabel(curLabel, sx, sy, false, offsetX, offsetY, plotW, plotH, dpr, '#1E40AF', bestBox);
          }
        } else {
          const curLabel = `${t('legendCur')} (${currentSim.safetyScore}, ${currentSim.efficacyScore})`;
          drawCalloutLabel(curLabel, sx, sy, false, offsetX, offsetY, plotW, plotH, dpr, '#1E40AF', null);
        }

        if (tfrac < 1) {
          simAnimId = requestAnimationFrame(renderFrame);
        } else if (animate && onComplete && !completed) {
          completed = true;
          onComplete();
        }
      }

      if (typeof ResizeObserver !== 'undefined' && cvs.parentElement) {
        studioChartRO = new ResizeObserver(() => {
          if (!cvs.isConnected) return;
          renderFrame(performance.now());
        });
        studioChartRO.observe(cvs.parentElement);
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
      { key: 'bilirubin', name: 'Total Bilirubin', unit: 'mg/dL', refLow: 0.2, refHigh: 1.2, scaleMin: 0, scaleMax: 3.0, organ: 'hepatic', defaultVal: '1.2' },
      { key: 'creatinine', name: 'Serum Creatinine', unit: 'mg/dL', refLow: 0.6, refHigh: 1.2, scaleMin: 0, scaleMax: 3.0, organ: 'renal', defaultVal: '1.0' },
      { key: 'ast', name: 'AST (Aminotransferase)', unit: 'U/L', refLow: 10, refHigh: 40, scaleMin: 0, scaleMax: 120, organ: 'hepatic', defaultVal: '28' },
      { key: 'alt', name: 'ALT (Aminotransferase)', unit: 'U/L', refLow: 7, refHigh: 56, scaleMin: 0, scaleMax: 160, organ: 'hepatic', defaultVal: '32' },
      { key: 'platelets', name: 'Platelet Count', unit: 'x10³/µL', refLow: 150, refHigh: 450, scaleMin: 0, scaleMax: 600, organ: 'haematologic', defaultVal: '220' },
      { key: 'anc', name: 'Neutrophil Count (ANC)', unit: 'x10³/µL', refLow: 1.5, refHigh: 8.0, scaleMin: 0, scaleMax: 12.0, organ: 'haematologic', defaultVal: '3.5' },
      { key: 'hb', name: 'Hemoglobin (Hb)', unit: 'g/dL', refLow: 12.0, refHigh: 17.5, scaleMin: 6.0, scaleMax: 21.0, organ: 'haematologic', defaultVal: '13.8' },
      { key: 'lvef', name: 'Ejection Fraction (LVEF)', unit: '%', refLow: 50, refHigh: 75, scaleMin: 20, scaleMax: 90, organ: 'cardiovascular', defaultVal: '60' },
    ];

    function computeBioRowMetrics(bf, rawValStr) {
      const valNum = parseFloat(rawValStr);
      const hasVal = rawValStr !== undefined && String(rawValStr).trim() !== '' && !isNaN(valNum);
      const span = Math.max(0.001, bf.scaleMax - bf.scaleMin);
      const normalLeft = Math.max(0, Math.min(95, ((bf.refLow - bf.scaleMin) / span) * 100));
      const normalRight = Math.max(normalLeft + 4, Math.min(100, ((bf.refHigh - bf.scaleMin) / span) * 100));
      const normalWidth = normalRight - normalLeft;

      let statusClass = 'empty';
      let statusText = t('notEntered');
      let needlePos = normalLeft + normalWidth / 2;

      if (hasVal) {
        needlePos = Math.max(1.5, Math.min(98.5, ((valNum - bf.scaleMin) / span) * 100));
        if (valNum > bf.refHigh * 1.5) {
          statusClass = 'alarm'; statusText = t('elevated');
        } else if (valNum < bf.refLow * 0.75) {
          statusClass = 'alarm'; statusText = t('lowVal');
        } else if (valNum > bf.refHigh || valNum < bf.refLow) {
          statusClass = 'warn'; statusText = t('borderline');
        } else {
          statusClass = 'normal'; statusText = t('normal');
        }
      }
      return { hasVal, valNum, normalLeft, normalWidth, normalRight, statusClass, statusText, needlePos };
    }

    function renderFlowsheet() {
      clear(content);
      const wrap = h('div', { class: 'flowsheet-wrap' });
      const leftPanel = h('div', { class: 'flowsheet-panel panel' });
      const rightPanel = h('div', { class: 'organ-linkage-panel panel' });
      wrap.append(leftPanel, rightPanel);
      content.append(wrap);

      leftPanel.append(
        h('div', { class: 'flowsheet-head' },
          h('h2', { class: 'flowsheet-title', text: t('flowTitle') })));

      const groupEl = h('div', { class: 'lab-card-group' });
      BIO_FIELDS.forEach((bf) => {
        const valStr = S.raw[bf.key];
        const m = computeBioRowMetrics(bf, valStr);

        const trackEl = h('div', { class: 'bio-spectrum-track' },
          h('i', {
            class: 'bio-spectrum-normal',
            style: `left:${m.normalLeft.toFixed(1)}%;width:${m.normalWidth.toFixed(1)}%`,
            title: `${t('refRange')}: ${bf.refLow} – ${bf.refHigh} ${bf.unit}`,
          }));
        const needleEl = h('i', {
          class: `bio-spectrum-needle ${m.statusClass}`,
          style: `left:${m.needlePos.toFixed(1)}%;display:${m.hasVal ? 'block' : 'none'}`,
        });
        trackEl.append(needleEl);

        const ticksEl = h('div', { class: 'bio-spectrum-ticks' },
          h('span', { class: 'bio-tick', style: `left:${m.normalLeft.toFixed(1)}%`, text: String(bf.refLow) }),
          h('span', { class: 'bio-tick', style: `left:${m.normalRight.toFixed(1)}%`, text: String(bf.refHigh) }));

        const statusBadgeEl = h('span', { class: `bio-status-badge ${m.statusClass}`, text: m.statusText });

        const input = h('input', {
          type: 'text', inputmode: 'decimal', placeholder: '—', value: valStr || '',
          class: m.statusClass !== 'normal' && m.statusClass !== 'empty' ? 'flagged' : '',
          oninput: (e) => {
            S.raw[bf.key] = e.target.value;
            S.presetId = null;
            if (String(e.target.value).trim()) S.studioNeedInputWarn = false;
            else if (!hasPatientProfile()) S.studioDesignMode = 'idle';
            save();
            const live = computeBioRowMetrics(bf, e.target.value);
            input.className = live.statusClass !== 'normal' && live.statusClass !== 'empty' ? 'flagged' : '';
            needleEl.className = `bio-spectrum-needle ${live.statusClass}`;
            needleEl.style.left = `${live.needlePos.toFixed(1)}%`;
            needleEl.style.display = live.hasVal ? 'block' : 'none';
            statusBadgeEl.className = `bio-status-badge ${live.statusClass}`;
            statusBadgeEl.textContent = live.statusText;
          },
          onblur: async () => {
            await refreshBackendData();
            renderFlowsheet();
          },
        });

        const labName = S.lang === 'ko' ? (LAB_KO[bf.key] || bf.name) : bf.name;

        const row = h('div', { class: 'bio-row' },
          h('div', { class: 'bio-info' },
            h('span', { class: 'bio-name', text: labName }),
            h('span', { class: 'bio-ref', text: `${t('refRange')}: ${bf.refLow} - ${bf.refHigh} ${bf.unit}` })),
          h('div', { class: 'bio-input-wrap' }, input),
          h('div', { class: 'bio-spectrum-wrap' }, trackEl, ticksEl),
          statusBadgeEl);

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
    let w = cvs.width = (rect.width || 400) * (window.devicePixelRatio || 1);
    let h = cvs.height = (rect.height || 240) * (window.devicePixelRatio || 1);
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
      const curRect = cvs.getBoundingClientRect();
      if (curRect.width > 20 && curRect.height > 20) {
        const nw = Math.round(curRect.width * dpr);
        const nh = Math.round(curRect.height * dpr);
        if (cvs.width !== nw || cvs.height !== nh) {
          w = cvs.width = nw;
          h = cvs.height = nh;
        }
      }
      if (!isDragging) rotY += 0.006;
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(0, 0, w, h);

      // Subtle bright grid backdrop
      ctx.strokeStyle = 'rgba(15, 23, 42, 0.06)';
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
      ctx.strokeStyle = 'rgba(71, 85, 105, 0.55)';
      ctx.lineWidth = 2.6 * dpr;
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
      ctx.strokeStyle = isCleavable ? '#D97706' : '#64748B';
      ctx.lineWidth = isCleavable ? 1.8 * dpr : 2.2 * dpr;
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
          ctx.arc(p.x, p.y, p.r * 1.65, 0, Math.PI * 2);
          ctx.fillStyle = payloadColor + '28';
          ctx.fill();
        }
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(1, p.r), 0, Math.PI * 2);
        ctx.fillStyle = p.col;
        ctx.fill();
        ctx.strokeStyle = 'rgba(15, 23, 42, 0.22)';
        ctx.lineWidth = 1.0 * dpr;
        ctx.stroke();
      });

      adcAnimId = requestAnimationFrame(render3d);
    }

    adcAnimId = requestAnimationFrame(render3d);
  }

  function build3dLegend(row) {
    const isKo = S.lang === 'ko';
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
      ['#334155', isKo ? '항체 골격 (IgG1)' : 'IgG1 Backbone'],
      [paratopeColor, isKo ? `항원 결합부 (${target})` : `Paratope (${target})`],
      [isCleavable ? '#D97706' : '#64748B', isKo ? `링커 (${isCleavable ? '절단형' : '비절단형'})` : `Linker (${isCleavable ? 'Cleavable' : 'Non-cleavable'})`],
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

  // ------------------------------------------------------------------ Clinical trial cases
  // Per adverse event: the treatment group beside the control group, and how much lower or higher the treatment group was.
  // Raw counts are not shown; the point is how this drug did against the earlier regimen.
  function trialCaseBlock(tr, fallbackText, heading) {
    const isKo = S.lang === 'ko';
    if (!tr) return h('p', { class: 'dim', text: fallbackText });
    const compReg = tr.comparator && tr.comparator.regimen;
    const mineOrgans = new Set(activeOrgansWithScores().map((o) => o.organ));
    const events = [];
    for (const o of tr.organs || []) {
      for (const e of o.events || []) {
        const a = (100 * (e.a || 0)) / Math.max(1, e.n || 1);
        const c = e.comp && e.comp[1] ? (100 * e.comp[0]) / Math.max(1, e.comp[1]) : null;
        events.push({ organ: o.organ, term: e.term || '', a, c, mine: mineOrgans.has(o.organ) });
      }
    }
    events.sort((x, y) => (Number(y.mine) - Number(x.mine)) || ((x.c === null ? 1e9 : x.a - x.c) - (y.c === null ? 1e9 : y.a - y.c)));

    const cmp = events.filter((e) => e.c !== null);
    const lower = cmp.filter((e) => e.a < e.c - 0.5).length;
    const higher = cmp.filter((e) => e.a > e.c + 0.5).length;
    let verdict;
    let tone = 'good';
    if (!cmp.length) {
      tone = 'neutral';
      verdict = isKo ? '대조군이 없는 시험이라 비교 결과는 없습니다. 치료군에서 나타난 이상사례 발생률만 보여 드립니다.' : 'This trial had no control group, so there is no comparison. Only the rates in the treatment group are shown.';
    } else {
      const head = isKo ? `대조군과 비교할 수 있는 이상사례 ${cmp.length}개 중 ` : `Of ${cmp.length} adverse events that can be compared with the control group, `;
      if (lower === cmp.length) verdict = head + (isKo ? '모두 치료군에서 더 적게 나타났습니다.' : 'all were less frequent in the treatment group.');
      else if (higher === cmp.length) { tone = 'bad'; verdict = head + (isKo ? '모두 치료군에서 더 많이 나타났습니다.' : 'all were more frequent in the treatment group.'); }
      else {
        if (higher > lower) tone = 'bad';
        verdict = head + (isKo ? `${lower}개는 더 적게, ${higher}개는 더 많이, 나머지는 비슷하게 나타났습니다.` : `${lower} were less frequent, ${higher} more frequent, and the rest similar.`);
      }
    }

    const info = [
      [isKo ? '대상 환자' : 'Patients', tr.population || ''],
      [isKo ? '치료군' : 'Treatment group', tr.regimen || ''],
      [isKo ? '대조군' : 'Control group', compReg || (isKo ? '없음' : 'None')],
    ].filter(([, v]) => v);

    const card = h('div', { class: 'trial-summary-card' },
      h('p', { class: 'tc-name', text: `${heading ? heading + ' ' : ''}${tr.trial}${tr.phase ? (isKo ? ` 임상 ${tr.phase}상` : ` Phase ${tr.phase}`) : ''}` }),
      h('div', { class: 'kv3 tc-info' }, info.map(([k, v]) => [h('span', { class: 'k', text: k }), h('span', { text: v })])),
      /^NCT\d{8}$/.test(tr.nct || '') ? h('a', { class: 'review-link', href: 'https://clinicaltrials.gov/study/' + tr.nct, target: '_blank', rel: 'noopener noreferrer', text: `ClinicalTrials.gov ${tr.nct} ↗` }) : null);

    const diffChip = (e) => {
      if (e.c === null) return h('span', { class: 'tc-diff neutral', text: isKo ? '대조군 없음' : 'No control' });
      const d = e.a - e.c;
      if (Math.abs(d) <= 0.5) return h('span', { class: 'tc-diff neutral', text: isKo ? '대조군과 비슷' : 'Similar to control' });
      return d < 0
        ? h('span', { class: 'tc-diff good', text: isKo ? `대조군보다 ${(-d).toFixed(1)}%p 낮음` : `${(-d).toFixed(1)} pts lower than control` })
        : h('span', { class: 'tc-diff bad', text: isKo ? `대조군보다 ${d.toFixed(1)}%p 높음` : `${d.toFixed(1)} pts higher than control` });
    };
    const barRow = (label, pct, scale, cls) => h('div', { class: 'tc-row' },
      h('span', { class: 'tc-label', text: label }),
      h('span', { class: 'tc-track' }, h('i', { class: cls, style: `width:${Math.max(2, Math.min(100, (pct / scale) * 100)).toFixed(1)}%` })),
      h('span', { class: 'tc-pct', text: `${pct.toFixed(1)}%` }));

    const list = events.slice(0, 10).map((e) => {
      const scale = Math.max(10, e.a, e.c || 0);
      return h('div', { class: 'tc-event' },
        h('div', { class: 'tc-head' },
          h('span', { class: 'tc-term', text: e.term }),
          e.mine ? h('span', { class: 'tc-mine', text: organKo(e.organ) }) : null,
          diffChip(e)),
        barRow(isKo ? '치료군' : 'Treatment', e.a, scale, 'tc-fill-tx'),
        e.c !== null ? barRow(isKo ? '대조군' : 'Control', e.c, scale, 'tc-fill-cmp') : null);
    });

    return h('div', { class: 'tc-wrap' }, card, h('p', { class: 'tc-verdict ' + tone, text: verdict }), list);
  }

  const KV_KO = {
    'Target Antigen': '표적 항원', 'Antibody Backbone': '항체', 'Chemical Linker': '링커', 'Cytotoxic Payload': '페이로드',
    'Payload Class': '페이로드 계열', 'Average DAR': '평균 DAR', Payload: '페이로드', Action: '작용 방식', Linker: '링커',
    'Bystander effect': '주변 암세포 사멸', Target: '표적',
  };

  function fillDrawer(row) {
    if (!row) return;
    const isKo = S.lang === 'ko';
    const d = row.detail || {};
    drawerTitle.textContent = row.name;
    clear(drawerBody);
    drawerBody.scrollTop = 0;

    // 1. Can the drug be used for this patient
    const CODE_KO = { contraindicated: '사용 금지', avoid: '사용 주의', reduce_dose: '용량 감량', monitor: '경과 관찰', insufficient_data: '판단 자료 부족' };
    const rs = (d.reasons || []).filter((r) => r.code !== 'no_adjustment' && r.code !== 'no_statement');
    const ruleText = (r) => {
      const b = String(r.basis || '').replace(/^if /, '');
      return b === '-' ? t('appliesToAll') : b;
    };
    const secRestriction = section(t('labelRestriction'), rs.length ? h('div', { class: 'rsl' }, rs.map((r) => h('div', { class: 'rr' },
      h('div', { class: 'rh' },
        h('span', { class: 'k', text: organKo(r.organ) }),
        h('span', { class: `s t-${TONE[r.code] || 'dim'}`, text: isKo ? (CODE_KO[r.code] || r.status) : r.status })),
      h('div', { class: 'pl' },
        r.patient ? [h('span', { class: 'pk', text: isKo ? '환자 수치' : 'Patient' }), h('span', { class: 'pv', text: r.patient })] : null,
        h('span', { class: 'pk', text: isKo ? '적용 기준' : 'Criterion' }), h('span', { class: 'lv2', text: ruleText(r) })))))
      : h('p', { class: 'dim', text: t('noLabelRestriction') }));

    // 2. Effects on the patient's vulnerable organs
    const ws = d.warnings || [];
    const secPatientWarn = section(t('patientWarnTitle'), ws.length ? h('div', { class: 'wl' }, ws.map((w) => {
      const strong = (w.mark || '').trim() === '!!';
      return [
        h('span', { class: 'k', text: organKo(w.organ) }),
        h('span', { class: 'm ' + (strong ? 't-red' : 't-amber'), text: strong ? (isKo ? '경고' : 'Warning') : (isKo ? '주의' : 'Caution') }),
        h('span', { text: (w.text || '').replace(/;\s*/g, ', ') }),
      ];
    })) : h('p', { class: 'dim', text: t('noPatientWarn') }));

    const secChecks = (d.checks || []).length ? section(t('preCheckTitle'), h('ul', { class: 'dash' }, d.checks.map((c) => h('li', { text: c })))) : null;
    const secMissing = (d.missing || []).length ? section(t('missingInputTitle'),
      h('ul', { class: 'dash' }, d.missing.map((m) => h('li', { text: m }))),
      h('button', { type: 'button', class: 'review-link', text: t('enterLabBtn'), onclick: () => { closeDrawer(); switchMode(0); } })) : null;

    // 3. Clinical trial cases
    const tr = d.trial && d.trial.trial && !d.trial.no_results ? d.trial : null;
    const secStudy = section(t('trialContext'), trialCaseBlock(tr, (d.trial && d.trial.no_results) || t('singleArmTrial')));

    // 4. Molecular structure
    const m = MECH[row.adc];
    const kvRows = (m ? [
      ['Target Antigen', m.target],
      ['Antibody Backbone', m.antibody],
      ['Chemical Linker', m.linker],
      ['Cytotoxic Payload', m.payload],
      ['Payload Class', m.payload_class],
      ['Average DAR', m.dar],
    ].filter(([, v]) => v) : ((d.payload && d.payload.rows) || [])).map(([k, v]) => [isKo ? (KV_KO[k] || k) : k, isKo && /^(yes|no)$/i.test(String(v)) ? (/^yes$/i.test(String(v)) ? '있음' : '없음') : v]);

    const cvs3d = h('canvas', { class: 'adc-3d-canvas' });
    const wrap3d = h('div', { class: 'adc-3d-wrap' }, cvs3d);

    const secStructure3d = section(null,
      wrap3d,
      build3dLegend(row),
      kvRows.length ? h('div', { class: 'kv3' }, kvRows.map(([k, v]) => [h('span', { class: 'k', text: k }), h('span', { text: v })])) : null,
      h('button', {
        type: 'button', class: 'review-link', style: 'margin-top:10px',
        text: t('tuneStudio'),
        onclick: () => { closeDrawer(); switchMode(2); },
      }));

    const tabDefs = [
      { id: 'Patient', label: t('tabPatient'), secs: [secRestriction, secPatientWarn, secChecks, secMissing].filter(Boolean) },
      { id: 'Study', label: t('tabStudy'), secs: [secStudy].filter(Boolean) },
      { id: 'Structure', label: t('tabStructure'), secs: [secStructure3d].filter(Boolean) },
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

  // ------------------------------------------------------------------ Why this design has fewer side effects than the approved drug
  // Each entry: the approved drug's problem, the biology behind it, and the "kinds" that decide how this design answers it.
  // The answer is written from the parts the user actually chose, not from a fixed text.
  const DERISK = {
    'HER2 (ERBB2)': [
      { ko: ['간질성 폐질환(ILD, 폐렴)', '엔허투는 임상시험에서 ILD와 폐렴이 약 10~15%에서 보고되었고 일부는 치명적이었습니다.', 'DXd는 세포막을 잘 통과하는 약물이고, DAR 8은 항체 한 개에 약물 8개가 붙어 물에 잘 섞이지 않아 응집되기 쉽습니다. 응집된 ADC와 Fc 부위는 폐포 대식세포의 FcγR에 붙어 비특이적으로 흡수되고, 대식세포 안에서 풀려난 DXd가 폐포 상피를 손상시키며 염증을 일으킵니다.'],
        en: ['Interstitial lung disease (pneumonitis)', 'Enhertu caused ILD or pneumonitis in about 10 to 15 percent of patients in trials, some fatal.', 'DXd crosses cell membranes easily, and DAR 8 puts eight drugs on one antibody, which makes it water-repellent and prone to clumping. Clumped ADC and the Fc region bind FcγR on alveolar macrophages and are taken up non-specifically; the DXd released inside them injures the alveolar lining and triggers inflammation.'],
        kinds: ['fc', 'dar', 'pay:pulmonary'] },
      { ko: ['심장 기능 저하(LVEF 감소)', '트라스투주맙 계열 항체는 좌심실 박출률을 떨어뜨릴 수 있습니다.', 'HER2는 심근세포에도 있어 심근의 생존 신호에 관여합니다. 항체가 이 신호를 막거나, 혈액 속에서 미리 떨어져 나온 페이로드가 심근에 닿으면 심근세포가 손상됩니다.'],
        en: ['Reduced heart function (LVEF drop)', 'Trastuzumab-type antibodies can lower left ventricular ejection fraction.', 'HER2 is also on heart muscle cells and supports their survival signaling. The antibody can block that signal, and payload that falls off in the blood can reach the heart muscle and damage it.'],
        kinds: ['target', 'linker', 'pay:cardiovascular'] },
    ],
    'TROP2 (TACSTD2)': [
      { ko: ['중증 호중구감소증', '트로델비는 3등급 이상 호중구감소증이 환자의 약 절반(51%)에서 나타났습니다.', 'CL2A 링커는 pH에 민감한 결합이라 혈액 속에서도 서서히 끊어집니다. 떨어져 나온 SN-38이 골수에서 호중구가 되는 전구세포를 직접 공격해 백혈구 수치가 떨어집니다.'],
        en: ['Severe neutropenia', 'Trodelvy caused grade 3 or higher neutropenia in about half of patients (51 percent).', 'The CL2A linker is pH-sensitive and slowly breaks even in the blood. The SN-38 that comes off attacks neutrophil precursor cells in bone marrow, so white cell counts fall.'],
        kinds: ['linker', 'pay:haematologic', 'dar'] },
      { ko: ['중증 설사', '3등급 이상 설사가 약 10%에서 보고되었습니다.', 'SN-38은 장 점막 상피세포에도 독성이 있고, 간에서 UGT1A1이 해독하지 못한 SN-38은 담즙을 따라 장으로 나와 점막을 손상시킵니다.'],
        en: ['Severe diarrhea', 'Grade 3 or higher diarrhea was reported in about 10 percent of patients.', 'SN-38 is toxic to the cells lining the gut, and SN-38 that the liver enzyme UGT1A1 does not detoxify is excreted in bile into the intestine, where it injures the lining.'],
        kinds: ['linker', 'pay:gastrointestinal'] },
    ],
    'Nectin-4': [
      { ko: ['중증 피부 반응', '파드셉은 스티븐스-존슨 증후군, 독성표피괴사융해증(SJS/TEN) 같은 중증 피부 반응에 대한 경고가 있습니다.', 'Nectin-4는 정상 피부의 표피 각질세포에 많이 발현합니다. 약물이 표적을 따라 피부에 모이면 MMAE가 각질세포를 죽여 피부가 벗겨집니다.'],
        en: ['Severe skin reactions', 'Padcev carries a warning for severe skin reactions such as Stevens-Johnson syndrome and toxic epidermal necrolysis.', 'Nectin-4 is abundant on keratinocytes in normal skin. When the drug gathers in skin by following its target, MMAE kills keratinocytes and the skin peels.'],
        kinds: ['target', 'pay:dermatologic', 'linker'] },
      { ko: ['말초신경병증', '손발 저림과 근력 저하 같은 말초 감각 및 운동 신경병증이 흔하게 나타납니다.', 'MMAE는 미세소관을 억제하는 약물이라, 분열하지 않는 신경 축삭 안의 물질 수송까지 방해합니다. 혈액 속으로 새어 나온 MMAE가 많을수록 신경 손상이 쌓입니다.'],
        en: ['Peripheral neuropathy', 'Numbness, tingling and weakness in the hands and feet are common.', 'MMAE blocks microtubules, which also carry cargo along non-dividing nerve axons. The more MMAE leaks into the blood, the more nerve damage builds up.'],
        kinds: ['linker', 'pay:neurologic', 'dar'] },
    ],
    'CD79b': [
      { ko: ['말초신경병증', '말초신경병증은 폴라이비의 용량을 제한하는 대표적인 독성입니다.', 'MMAE는 미세소관을 억제하는 약물이라, 분열하지 않는 신경 축삭 안의 물질 수송까지 방해합니다. 혈액 속으로 새어 나온 MMAE가 많을수록 신경 손상이 쌓입니다.'],
        en: ['Peripheral neuropathy', 'Neuropathy is the main dose-limiting toxicity of Polivy.', 'MMAE blocks microtubules, which also carry cargo along non-dividing nerve axons. The more MMAE leaks into the blood, the more nerve damage builds up.'],
        kinds: ['linker', 'pay:neurologic', 'dar'] },
      { ko: ['호중구와 혈소판 감소', '호중구감소증과 혈소판감소증이 흔하게 나타납니다.', 'CD79b는 B세포에 있지만 MMAE는 분열이 빠른 모든 세포를 공격합니다. 혈액 속에서 풀려난 MMAE는 골수의 조혈 전구세포 분열을 막아 혈구 수가 줄어듭니다.'],
        en: ['Low neutrophils and platelets', 'Neutropenia and thrombocytopenia are common.', 'CD79b sits on B cells, but MMAE attacks any fast-dividing cell. MMAE freed in the blood stops hematopoietic precursors in bone marrow from dividing, so blood counts fall.'],
        kinds: ['linker', 'pay:haematologic', 'dar'] },
    ],
    'BCMA (TNFRSF17)': [
      { ko: ['각막 병증(시력 저하)', '블렌렙은 각막 상피 병증이 환자의 약 70% 이상에서 보고되어 별도의 안과 관리가 필요합니다.', '각막 상피세포는 거대음세포작용으로 혈액 속 ADC를 비특이적으로 삼킵니다. 비절단형 링커는 세포 안에서 항체가 완전히 분해될 때까지 MMAF를 붙들고 있어, 분해 산물이 각막 상피에 쌓이며 미세낭종이 생깁니다.'],
        en: ['Corneal damage (vision loss)', 'Blenrep caused corneal epithelial changes in roughly 70 percent or more of patients and needs eye monitoring.', 'Corneal epithelial cells take up ADC from the blood non-specifically by macropinocytosis. A non-cleavable linker holds MMAF until the antibody is fully broken down, so the breakdown product piles up in the corneal lining and forms microcysts.'],
        kinds: ['fc', 'linker', 'pay:ocular'] },
    ],
    'FRalpha (FOLR1)': [
      { ko: ['각막 병증(시력 저하)', '엘라히어는 각막 병증과 시력 저하에 대한 경고가 있습니다.', '엽산 수용체 알파는 각막 상피에도 있고, 메이탄시노이드(DM4)는 각막 상피세포의 분열을 막아 상피가 손상됩니다.'],
        en: ['Corneal damage (vision loss)', 'Elahere carries a warning for corneal disease and vision loss.', 'Folate receptor alpha is also present in the corneal lining, and the maytansinoid DM4 stops corneal epithelial cells from dividing, so the lining is damaged.'],
        kinds: ['target', 'pay:ocular', 'linker'] },
      { ko: ['간질성 폐질환', '드물지만 간질성 폐질환이 보고되었습니다.', 'ADC가 폐포 대식세포에 비특이적으로 흡수되면 폐 안에서 페이로드가 풀려나 염증이 생깁니다.'],
        en: ['Interstitial lung disease', 'Interstitial lung disease was reported, though rarely.', 'When ADC is taken up non-specifically by alveolar macrophages, the payload is released inside the lung and causes inflammation.'],
        kinds: ['fc', 'pay:pulmonary'] },
    ],
  };

  // one sentence per kind: tone better / same / worse than the approved drug, for the parts the user chose
  function deriskAnswer(kind, sim, refSim, isKo) {
    const L = (ko, en) => (isKo ? ko : en);
    if (kind === 'fc') {
      if (sim.fcSilenced) return { tone: 'better', text: L('Fc 침묵화(LALA-PG)로 대식세포의 FcγR 결합이 거의 사라져 비특이 흡수 경로가 막혀 있습니다.', 'Fc silencing (LALA-PG) removes most FcγR binding on macrophages, so the non-specific uptake route is blocked.') };
      return { tone: 'same', text: L('Fc가 야생형이라 대식세포를 통한 비특이 흡수 경로가 기존 약물처럼 남아 있습니다.', 'The Fc is wild-type, so the macrophage uptake route remains, as in the approved drug.') };
    }
    if (kind === 'dar') {
      if (sim.dar < refSim.dar) return { tone: 'better', text: L(`DAR이 ${refSim.dar}에서 ${sim.dar}로 낮아 약물 부하와 응집 위험이 줄었습니다.`, `DAR is lower, ${refSim.dar} to ${sim.dar}, so drug load and clumping risk are reduced.`) };
      if (sim.dar > refSim.dar) return { tone: 'worse', text: L(`DAR이 ${refSim.dar}에서 ${sim.dar}로 높아져 약물 부하와 응집 위험이 커졌습니다.`, `DAR is higher, ${refSim.dar} to ${sim.dar}, so drug load and clumping risk are greater.`) };
      return { tone: 'same', text: L(`DAR ${sim.dar}로 기존 약물과 같아 약물 부하는 줄지 않았습니다.`, `DAR ${sim.dar} is the same as the approved drug, so drug load is not reduced.`) };
    }
    if (kind === 'linker') {
      const a = refSim.lnk.stability;
      const b = sim.lnk.stability;
      if (sim.lnk.id === refSim.lnk.id) return { tone: 'same', text: L(`같은 링커라서 혈장 안정도(${b}%)가 기존 약물과 같습니다.`, `Same linker, so plasma stability (${b}%) is the same as the approved drug.`) };
      if (!sim.lnk.cleavable && refSim.lnk.cleavable) return { tone: b > a ? 'better' : 'worse', text: L(`비절단형 링커로 혈장 안정도가 ${a}%에서 ${b}%로 바뀌어 혈액 속 조기 방출이 줄지만, 항체가 완전히 분해되어야 약물이 풀립니다.`, `A non-cleavable linker changes plasma stability from ${a}% to ${b}%, so early release in blood drops, but the antibody must be fully broken down to free the drug.`) };
      if (b > a) return { tone: 'better', text: L(`링커 혈장 안정도가 ${a}%에서 ${b}%로 높아져 혈액 속에서 미리 떨어져 나가는 약물이 줄었습니다.`, `Plasma stability rises from ${a}% to ${b}%, so less drug falls off in the blood.`) };
      if (b < a) return { tone: 'worse', text: L(`링커 혈장 안정도가 ${a}%에서 ${b}%로 낮아 혈액 속 조기 방출이 늘 수 있습니다.`, `Plasma stability falls from ${a}% to ${b}%, so early release in the blood may increase.`) };
      return { tone: 'same', text: L(`링커 혈장 안정도는 ${b}%로 기존과 같습니다.`, `Plasma stability is ${b}%, the same as before.`) };
    }
    if (kind === 'target') {
      return { tone: 'same', text: L('표적이 기존 약물과 같아서 정상 장기에 표적이 있어서 생기는 독성은 그대로입니다.', 'The target is the same as the approved drug, so toxicity caused by the target being present in normal organs stays.') };
    }
    if (kind.startsWith('pay:')) {
      const organ = kind.slice(4);
      const mine = sim.pld.organs[organ] != null ? sim.pld.organs[organ] : 22;
      const ref = refSim.pld.organs[organ] != null ? refSim.pld.organs[organ] : 22;
      const name = organKo(organ);
      if (sim.pld.id === refSim.pld.id) return { tone: 'same', text: L(`같은 페이로드라서 ${name}에 대한 독성도 같습니다.`, `Same payload, so its toxicity on ${name} is the same.`) };
      if (mine < ref - 8) return { tone: 'better', text: L(`${plainName(sim.pld.id)}는 ${name}에 대한 독성이 ${plainName(refSim.pld.id)}보다 낮습니다.`, `${plainName(sim.pld.id)} is less toxic to ${name} than ${plainName(refSim.pld.id)}.`) };
      if (mine > ref + 8) return { tone: 'worse', text: L(`${plainName(sim.pld.id)}는 ${name}에 대한 독성이 ${plainName(refSim.pld.id)}보다 높습니다.`, `${plainName(sim.pld.id)} is more toxic to ${name} than ${plainName(refSim.pld.id)}.`) };
      return { tone: 'same', text: L(`${name}에 대한 페이로드 독성은 기존 약물과 비슷합니다.`, `Payload toxicity on ${name} is similar to the approved drug.`) };
    }
    return { tone: 'same', text: '' };
  }

  function fillStudioCompareDrawer(simInput) {
    const sim = simInput || computeStudioSimulation();
    const isKo = S.lang === 'ko';
    const L = (ko, en) => (isKo ? ko : en);

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
    // the approved drug scored by the same formula on the same patient
    const refSim = computeStudioSimulation(Object.assign({ target: tgt.id }, REF_STUDIO[tgt.id] || { linker: lnk.id, payload: pld.id, dar: 4, fc: false }), sim.organRisks ? sim.organRisks.map((r) => ({ organ: r.organ, score: 0.8 })) : null);

    const tgtName = plainName(tgt.id);
    const designName = `${tgtName}-${plainName(pld.id)}`;
    const designSub = `${lnk.id}, DAR ${dar}, ${fcSilenced ? L('Fc 침묵화', 'Fc silenced') : L('야생형 IgG1', 'wild-type IgG1')}`;

    // no title: the two cards below already say what is being compared
    drawerTitle.textContent = '';
    clear(drawerBody);
    drawerBody.scrollTop = 0;

    // 1. The two designs side by side
    const secCompareHero = h('div', { class: 'compare-hero' },
      h('div', { class: 'compare-hero-col denovo' },
        h('span', { class: 'ch-badge', text: L('이 환자 맞춤 설계', 'Tailored to this patient') }),
        h('span', { class: 'ch-name', text: designName }),
        h('span', { class: 'ch-sub', text: designSub }),
        h('span', { class: 'ch-score', text: L(`안전도 ${sim.safetyScore}점 / 효능 ${sim.efficacyScore}점`, `Safety ${sim.safetyScore} / Efficacy ${sim.efficacyScore}`) })),
      h('div', { class: 'compare-hero-col' },
        h('span', { class: 'ch-badge', text: L('기존 승인 약물', 'Approved drug') }),
        h('span', { class: 'ch-name', text: refBrand || refName }),
        h('span', { class: 'ch-sub', text: `${refSpec.linker || refSim.lnk.id}, DAR ${refSim.dar}, ${L('야생형 IgG1', 'wild-type IgG1')}` }),
        h('span', { class: 'ch-score', style: 'color:var(--dim)', text: L(`안전도 ${refSim.safetyScore}점 / 효능 ${refSim.efficacyScore}점`, `Safety ${refSim.safetyScore} / Efficacy ${refSim.efficacyScore}`) })));

    // 2. Part by part, with what it means clinically
    const burden = (p) => sim.organRisks.reduce((a, r) => a + (p.organs[r.organ] != null ? p.organs[r.organ] : 22), 0) / Math.max(1, sim.organRisks.length);
    const dSafety = sim.safetyScore - refSim.safetyScore;
    const dEff = sim.efficacyScore - refSim.efficacyScore;
    const toneOf = (d) => (d >= 3 ? 'better' : d <= -3 ? 'worse' : 'same');

    const linkerGain = deriskAnswer('linker', sim, refSim, isKo);
    const darGain = deriskAnswer('dar', sim, refSim, isKo);
    const fcGain = sim.fcSilenced
      ? { tone: 'better', text: L('Fc 침묵화로 대식세포 FcγR을 통한 비특이 흡수가 줄어, 폐, 간, 안구 독성 위험이 낮아집니다.', 'Fc silencing lowers non-specific uptake through macrophage FcγR, reducing lung, liver and eye toxicity risk.') }
      : { tone: 'same', text: L('기존 약물과 같은 야생형 IgG1이라 차이가 없습니다.', 'Same wild-type IgG1 as the approved drug, so no difference.') };
    let payGain;
    if (pld.id === refSim.pld.id) payGain = { tone: 'same', text: L('같은 페이로드를 사용하므로 항암 효력과 독성 특성이 같습니다.', 'The same payload is used, so potency and toxicity profile are the same.') };
    else {
      const a = burden(refSim.pld);
      const b = burden(pld);
      const pct = a ? Math.round(Math.abs(1 - b / a) * 100) : 0;
      const tox = b < a - 3 ? L(`환자의 취약 장기에 대한 독성이 약 ${pct}% 낮고`, `toxicity on the patient's vulnerable organs is about ${pct}% lower, `)
        : b > a + 3 ? L(`환자의 취약 장기에 대한 독성이 약 ${pct}% 높고`, `toxicity on the patient's vulnerable organs is about ${pct}% higher, `)
          : L('환자의 취약 장기에 대한 독성은 비슷하고', 'toxicity on the patient\'s vulnerable organs is similar, ');
      const pot = pld.potency > refSim.pld.potency + 3 ? L(' 항암 효력은 더 강합니다.', 'and potency is stronger.')
        : pld.potency < refSim.pld.potency - 3 ? L(' 항암 효력은 더 약합니다.', 'and potency is weaker.') : L(' 항암 효력은 비슷합니다.', 'and potency is similar.');
      payGain = { tone: b < a - 3 ? 'better' : b > a + 3 ? 'worse' : 'same', text: tox + pot };
    }

    const rows = [
      [t('compTarget'), tgtName, plainName(refSim.tgt.id),
        { tone: 'same', text: L(`같은 ${tgtName} 표적이라 종양 선택도(+${tgt.selectivity.toFixed(1)} log2FC)는 같습니다. 차이는 아래 항목에서 생깁니다.`, `Same ${tgtName} target, so tumor selectivity (+${tgt.selectivity.toFixed(1)} log2FC) is the same. The differences come from the parts below.`) }],
      [t('compLinker'), `${lnk.id}, ${lnk.cleavable ? L('절단형', 'cleavable') : L('비절단형', 'non-cleavable')}`, refSpec.linker || refSim.lnk.id, linkerGain],
      [t('compPayload'), plainName(pld.id), plainName(refSim.pld.id), payGain],
      [t('compDar'), `DAR ${dar}`, `DAR ${refSim.dar}`, darGain],
      [t('compFc'), fcSilenced ? L('Fc 침묵화 (LALA-PG)', 'Fc silenced (LALA-PG)') : L('야생형 IgG1', 'Wild-type IgG1'), L('야생형 IgG1', 'Wild-type IgG1'), fcGain],
      [t('compSafety'), L(`${sim.safetyScore}점`, `${sim.safetyScore}`), L(`${refSim.safetyScore}점`, `${refSim.safetyScore}`),
        { tone: toneOf(dSafety), text: dSafety >= 3 ? L(`같은 환자 기준으로 기존 약물보다 ${dSafety}점 높아, 취약 장기 독성 위험이 낮습니다.`, `${dSafety} points higher than the approved drug for this patient, so risk to vulnerable organs is lower.`)
          : dSafety <= -3 ? L(`기존 약물보다 ${-dSafety}점 낮습니다. 효능을 위해 안전도를 일부 양보한 조합입니다.`, `${-dSafety} points lower than the approved drug; some safety is traded for efficacy.`) : L('기존 약물과 비슷한 수준입니다.', 'Similar to the approved drug.') }],
      [t('compEfficacy'), L(`${sim.efficacyScore}점`, `${sim.efficacyScore}`), L(`${refSim.efficacyScore}점`, `${refSim.efficacyScore}`),
        { tone: toneOf(dEff), text: dEff >= 3 ? L(`기존 약물보다 ${dEff}점 높아, 종양에 더 강하게 작용할 것으로 예상됩니다.`, `${dEff} points higher than the approved drug, so a stronger effect on the tumor is expected.`)
          : dEff <= -3 ? L(`기존 약물보다 ${-dEff}점 낮아 항암 효능은 다소 떨어질 수 있습니다.`, `${-dEff} points lower than the approved drug, so antitumor effect may be somewhat weaker.`) : L('기존 약물과 비슷한 수준입니다.', 'Similar to the approved drug.') }],
    ];

    const chipText = { better: L('개선', 'Better'), same: L('동일', 'Same'), worse: L('감소', 'Trade-off') };
    const cmpList = h('div', { class: 'cmp-list' }, rows.map(([param, mine, ref, gain]) => h('div', { class: 'cmp-item' },
      h('div', { class: 'cmp-param', text: param }),
      h('div', { class: 'cmp-pair' },
        h('div', { class: 'cmp-side mine' }, h('span', { class: 'cmp-tag', text: L('맞춤 설계', 'Tailored') }), h('span', { class: 'cmp-val', text: mine })),
        h('div', { class: 'cmp-side' }, h('span', { class: 'cmp-tag', text: refBrand }), h('span', { class: 'cmp-val', text: ref }))),
      h('div', { class: 'cmp-gain ' + gain.tone },
        h('span', { class: 'cmp-chip ' + gain.tone, text: chipText[gain.tone] }),
        h('span', { class: 'cmp-gain-text', text: gain.text })))));

    const secCompareTable = section(L('설계 비교와 임상 개선 이점', 'Comparison and clinical advantage'), cmpList);

    // 3. Why the approved drug's side effects are lower with this design
    const deriskDefs = DERISK[tgt.id] || [];
    const deRiskEl = h('div', { class: 'derisk-list' }, deriskDefs.map((def) => {
      const [title, problem, cause] = def[isKo ? 'ko' : 'en'];
      const answers = def.kinds.map((k) => deriskAnswer(k, sim, refSim, isKo)).filter((a) => a.text);
      return h('div', { class: 'derisk-item' },
        h('b', { text: title }),
        h('div', { class: 'dr-block' }, h('span', { class: 'dr-label', text: L(`${refBrand}의 문제`, `Problem with ${refBrand}`) }), h('span', { text: problem })),
        h('div', { class: 'dr-block' }, h('span', { class: 'dr-label', text: L('발생 기전', 'Why it happens') }), h('span', { text: cause })),
        h('div', { class: 'dr-block' }, h('span', { class: 'dr-label', text: L('이 설계의 대응', 'What this design does') }),
          h('ul', { class: 'dr-answers' }, answers.map((a) => h('li', null, h('span', { class: 'cmp-chip ' + a.tone, text: chipText[a.tone] }), h('span', { text: a.text }))))));
    }));
    const secDeRisk = deriskDefs.length ? section(t('deRiskTitle'), deRiskEl) : null;

    // 4. Molecular structure of both
    const cvs3d = h('canvas', { class: 'adc-3d-canvas' });
    const wrap3d = h('div', { class: 'adc-3d-wrap' }, cvs3d);

    const designConstruct = {
      name: designName,
      brand: '',
      target: tgt.gene || tgt.id,
      payload: plainName(pld.id),
      linker: lnk.id,
      dar: dar,
      darCount: Math.max(1, Math.min(8, Math.round(dar))),
      linkerType: lnk.cleavable ? 'cleavable' : 'non-cleavable',
      payloadColor: '#10B981',
      paratopeColor: '#38BDF8',
    };

    let active3dModel = designConstruct;
    const legend3dBox = h('div');
    const updateLegend = (model) => {
      clear(legend3dBox);
      legend3dBox.append(build3dLegend(model));
    };
    updateLegend(designConstruct);

    const btnToggleDesign = h('button', {
      type: 'button', class: 'st-pill', 'aria-pressed': 'true',
      text: L('맞춤 설계 구조', 'Tailored design'),
      onclick: () => {
        active3dModel = designConstruct;
        btnToggleDesign.setAttribute('aria-pressed', 'true');
        btnToggleRef.setAttribute('aria-pressed', 'false');
        updateLegend(active3dModel);
        init3dAdcCanvas(cvs3d, active3dModel);
      },
    });

    const btnToggleRef = h('button', {
      type: 'button', class: 'st-pill', 'aria-pressed': 'false',
      text: L(`${refBrand} 구조`, `${refBrand} structure`),
      onclick: () => {
        active3dModel = refRow || { adc: refAdcId, name: refName, brand: refBrand };
        btnToggleDesign.setAttribute('aria-pressed', 'false');
        btnToggleRef.setAttribute('aria-pressed', 'true');
        updateLegend(active3dModel);
        init3dAdcCanvas(cvs3d, active3dModel);
      },
    });

    const switcher3d = h('div', { class: 'studio-pills', style: 'margin-bottom:12px' }, btnToggleDesign, btnToggleRef);

    const sec3D = section(null,
      switcher3d,
      wrap3d,
      legend3dBox,
      h('div', { class: 'kv3', style: 'margin-top:12px' }, [
        [L('표적 항원', 'Target'), tgtName],
        [L('접합비 DAR', 'DAR'), `DAR ${dar}`],
        [L('화학 링커', 'Linker'), `${lnk.id}, ${lnk.cleavable ? L('절단형', 'cleavable') : L('비절단형', 'non-cleavable')}`],
        [L('세포독성 페이로드', 'Payload'), `${plainName(pld.id)}, ${pld.cls}`],
        [L('Fc', 'Fc'), fcSilenced ? L('LALA-PG로 침묵화해 대식세포 흡수를 줄임', 'Silenced with LALA-PG to cut macrophage uptake') : L('야생형 IgG1', 'Wild-type IgG1')],
      ].map(([k, v]) => [h('span', { class: 'k', text: k }), h('span', { text: v })])));

    // 5. Clinical trial cases of the approved drug
    const tr = refRow && refRow.detail && refRow.detail.trial && refRow.detail.trial.trial && !refRow.detail.trial.no_results ? refRow.detail.trial : null;
    const secRefStudy = section(null, trialCaseBlock(tr, L(`${refBrand}의 임상시험 정보가 없습니다.`, `No clinical trial information for ${refBrand}.`), refBrand));

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


  function openStudioCompareDrawer(simInput) {
    const sim = simInput || computeStudioSimulation();
    fillStudioCompareDrawer(sim);
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
    const builder = [buildPatientLabsMode, buildAdcMatrixMode, buildStructureStudioMode][S.mode] || buildPatientLabsMode;
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
    if (!inInput && ['1', '2', '3'].includes(e.key)) {
      e.preventDefault();
      switchMode(Number(e.key) - 1);
      return;
    }
    if (!inInput && S.mode === 1 && resultKeys && ['ArrowDown', 'ArrowUp', 'Enter'].includes(e.key)) {
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
    verEl.textContent = 'v' + (APP.version || '0.7.9');

    restore();
    renderHeaderControls();
    renderActiveMode(false);
    await refreshBackendData();
    renderActiveMode(false);
  }

  start();
})();
