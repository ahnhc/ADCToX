/* ADCTOX v0.8.3 Architectural Daylight WebApp
   Active-Organ Matrix + 368,640-Construct Studio + Deep Research (GPU/CPU) + Biomarker Flowsheet
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
        if (url === '/api/analyze' || url === '/api/studio/deep-research') throw e;
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
    studioCatalog: () => call('GET', '/api/studio/catalog'),
    studioGpuStatus: () => call('GET', '/api/studio/gpu-status'),
    studioEvaluate: (body) => call('POST', '/api/studio/evaluate', body),
    studioDeepResearch: (body) => call('POST', '/api/studio/deep-research', body),
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
    const ver = (APP && APP.version) ? APP.version : '0.8.3';
    const stepItems = isKo
      ? [
          ['환자 정보', '한글 또는 영문으로 암종과 기저질환을 검색하고 활성 취약 장기를 확인합니다. 검진 정보의 [필수 입력]과 [선택 입력] 토글을 펼쳐 환자 수치를 입력할 수 있습니다.'],
          ['ADC 매트릭스', '입력된 환자의 암종, 기저질환, 검진 수치를 기반으로 FDA 승인 ADC 약물의 적합도를 평가합니다. 상단 활성 취약 장기는 위험도(%) 내림차순으로 정렬되며, 특정 장기를 클릭하면 해당 장기 보호를 우선 반영해 순위를 재산출합니다.'],
          ['ADC 신규 설계', '36종 표적 항원, 16종 링커, 20종 페이로드, 8단계 DAR, 4종 항체 골격(368,640개 조합)에서 [ADC 자동 설계]로 초대규모 행렬 탐색을 수행하거나, 우측 화살표 메뉴에서 [Deep Research]를 켜 ADCSurrogateNet v2를 실시간 구동합니다.'],
        ]
      : [
          ['Patient Info', 'Search cancers or comorbidities in English or Korean and review active vulnerable organs. Toggle Required or Optional lab sections below to enter patient biomarkers.'],
          ['ADC Matrix', 'Ranks FDA-approved ADCs from patient comorbidities and lab values. Active vulnerable organs sort by severity (% descending); click any organ to prioritize its protection.'],
          ['De Novo ADC Design', 'Explore 368,640 constructs (36 targets, 16 linkers, 20 payloads, 8 DARs, 4 Fc formats) via server matrix Auto-design or toggle Deep Research from the split-button menu for live 5-fold ADCSurrogateNet v2 inference.'],
        ];
    guide = h('div', { class: 'guide-scrim', onclick: (e) => { if (e.target === guide) closeGuide(); } },
      h('div', { class: 'guide', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'g-title' },
        h('div', { class: 'g-head' },
          h('h2', { id: 'g-title', text: isKo ? 'ADCTOX 안내' : 'ADCTOX Guide' }),
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
  let STUDIO_TARGETS = [
    {
      "id": "HER2 (ERBB2)",
      "gene": "ERBB2",
      "group": "breast_gyn",
      "refAdc": "trastuzumab-deruxtecan",
      "selectivity": 4.9,
      "tumor_tpm": 280.0,
      "tumorKeys": [
        "breast",
        "gastric",
        "stomach",
        "nsclc",
        "lung",
        "colorectal",
        "colon",
        "bladder",
        "urothelial",
        "biliary",
        "유방",
        "위암",
        "폐암",
        "대장",
        "방광",
        "담도"
      ],
      "tissues": [
        {
          "organ": "pulmonary",
          "tpm": 48
        },
        {
          "organ": "cardiovascular",
          "tpm": 36
        },
        {
          "organ": "gastrointestinal",
          "tpm": 42
        }
      ],
      "popover": "Receptor tyrosine kinase amplified in breast, gastric, and NSCLC tumors. Baseline expression in lung alveolar epithelium and cardiomyocytes requires monitoring for ILD and LVEF decline.",
      "popover_ko": "유방암, 위암, 비소세포폐암에서 증폭되는 수용체 티로신 키나아제입니다. 폐포 상피세포와 심근세포에 기저 발현이 존재하여 간질성 폐질환(ILD) 및 좌심실 구혈률(LVEF) 감시가 필요합니다."
    },
    {
      "id": "TROP2 (TACSTD2)",
      "gene": "TACSTD2",
      "group": "breast_gyn",
      "refAdc": "sacituzumab-govitecan",
      "selectivity": 4.4,
      "tumor_tpm": 310.0,
      "tumorKeys": [
        "breast",
        "tnbc",
        "nsclc",
        "lung",
        "urothelial",
        "bladder",
        "cervical",
        "endometrial",
        "ovarian",
        "유방",
        "삼중음성",
        "폐암",
        "요로상피",
        "방광",
        "자궁",
        "난소"
      ],
      "tissues": [
        {
          "organ": "gastrointestinal",
          "tpm": 68
        },
        {
          "organ": "dermatologic",
          "tpm": 62
        },
        {
          "organ": "pulmonary",
          "tpm": 39
        }
      ],
      "popover": "Transmembrane glycoprotein broadly overexpressed across epithelial carcinomas; baseline expression in GI mucosa and stratified skin keratinocytes mediates mucosal and cutaneous sensitivity.",
      "popover_ko": "상피성 고형암 전반에 과발현되는 막관통 당단백질입니다. 대장 점막 및 피부 각질형성세포에 기저 발현이 있어 구내염, 설사 및 피부 발진 민감도와 연관됩니다."
    },
    {
      "id": "FRalpha (FOLR1)",
      "gene": "FOLR1",
      "group": "breast_gyn",
      "refAdc": "mirvetuximab-soravtansine",
      "selectivity": 4.6,
      "tumor_tpm": 210.0,
      "tumorKeys": [
        "ovarian",
        "endometrial",
        "fallopian",
        "peritoneal",
        "nsclc",
        "난소",
        "자궁내막",
        "나팔관",
        "복막"
      ],
      "tissues": [
        {
          "organ": "ocular",
          "tpm": 54
        },
        {
          "organ": "pulmonary",
          "tpm": 44
        },
        {
          "organ": "renal",
          "tpm": 51
        }
      ],
      "popover": "GPI-anchored folate receptor overexpressed in ovarian and endometrial carcinomas; apical expression in corneal epithelium and renal tubules requires ocular monitoring.",
      "popover_ko": "난소암, 자궁내막암에서 과발현되는 엽산 수용체 알파입니다. 각막 상피와 신장 근위세뇨관에 기저 발현이 있어 점안제 예방 등 안과적 관리가 권장됩니다."
    },
    {
      "id": "Tissue Factor (F3)",
      "gene": "F3",
      "group": "breast_gyn",
      "refAdc": "tisotumab-vedotin",
      "selectivity": 4.2,
      "tumor_tpm": 195.0,
      "tumorKeys": [
        "cervical",
        "ovarian",
        "head and neck",
        "pancreatic",
        "자궁경부",
        "난소",
        "두경부",
        "췌장"
      ],
      "tissues": [
        {
          "organ": "ocular",
          "tpm": 58
        },
        {
          "organ": "dermatologic",
          "tpm": 46
        },
        {
          "organ": "pulmonary",
          "tpm": 35
        }
      ],
      "popover": "Coagulation initiator receptor highly expressed in cervical and squamous carcinomas; conjunctival and mucosal expression drives ocular surface and epistaxis risk.",
      "popover_ko": "자궁경부암 및 편평상피암에서 고발현되는 응고 개시 수용체입니다. 결막 및 비강 점막 상피 발현으로 인해 결막염, 안구건조 및 비출혈 관리가 중요합니다."
    },
    {
      "id": "HER3 (ERBB3)",
      "gene": "ERBB3",
      "group": "breast_gyn",
      "refAdc": "trastuzumab-deruxtecan",
      "selectivity": 4.5,
      "tumor_tpm": 230.0,
      "tumorKeys": [
        "breast",
        "nsclc",
        "lung",
        "egfr",
        "colorectal",
        "ovarian",
        "유방",
        "폐암",
        "대장",
        "난소"
      ],
      "tissues": [
        {
          "organ": "gastrointestinal",
          "tpm": 48
        },
        {
          "organ": "dermatologic",
          "tpm": 36
        },
        {
          "organ": "hepatic",
          "tpm": 28
        }
      ],
      "popover": "Pseudokinase receptor driving EGFR-TKI resistance in NSCLC and luminal/HER2 breast cancers (Patritumab deruxtecan target) with rapid clathrin internalization.",
      "popover_ko": "EGFR 표적치료 내성 비소세포폐암과 유방암에서 과발현되는 수용체(파트리투맙 데룩스테칸 표적)로, 내재화 속도가 빠르고 심근 기저 발현이 HER2보다 낮습니다."
    },
    {
      "id": "LIV-1 (SLC39A6)",
      "gene": "SLC39A6",
      "group": "breast_gyn",
      "refAdc": "sacituzumab-govitecan",
      "selectivity": 4.7,
      "tumor_tpm": 245.0,
      "tumorKeys": [
        "breast",
        "tnbc",
        "prostate",
        "melanoma",
        "cervical",
        "유방",
        "삼중음성",
        "전립선",
        "흑색종"
      ],
      "tissues": [
        {
          "organ": "metabolic_endocrine",
          "tpm": 42
        },
        {
          "organ": "gastrointestinal",
          "tpm": 22
        },
        {
          "organ": "dermatologic",
          "tpm": 18
        }
      ],
      "popover": "Zinc transporter protein enriched across hormone-positive and triple-negative breast cancers (Ladiratuzumab target) with low visceral organ expression.",
      "popover_ko": "호르몬 양성 및 삼중음성 유방암 전반에 고발현되는 아연 수송체 막단백질(라디라투주맙 표적)로, 주요 실질 장기 내 기저 발현이 낮습니다."
    },
    {
      "id": "NaPi2b (SLC34A2)",
      "gene": "SLC34A2",
      "group": "breast_gyn",
      "refAdc": "mirvetuximab-soravtansine",
      "selectivity": 3.8,
      "tumor_tpm": 265.0,
      "tumorKeys": [
        "ovarian",
        "nsclc",
        "lung",
        "endometrial",
        "thyroid",
        "난소",
        "폐암",
        "자궁내막",
        "갑상선"
      ],
      "tissues": [
        {
          "organ": "pulmonary",
          "tpm": 88
        },
        {
          "organ": "gastrointestinal",
          "tpm": 24
        },
        {
          "organ": "renal",
          "tpm": 18
        }
      ],
      "popover": "Sodium-dependent phosphate transporter overexpressed in high-grade serous ovarian cancer and NSCLC; physiological surfactant pneumocyte expression warrants pulmonary caution.",
      "popover_ko": "고등급 장액성 난소암과 비소세포폐암에서 발현되는 인산 수송체입니다. 정상 제2형 폐포 상피세포의 발현량이 높아 폐 독성 회피 설계가 필수적입니다."
    },
    {
      "id": "EGFR",
      "gene": "EGFR",
      "group": "lung_gi",
      "refAdc": "enfortumab-vedotin",
      "selectivity": 3.9,
      "tumor_tpm": 290.0,
      "tumorKeys": [
        "nsclc",
        "lung",
        "head and neck",
        "colorectal",
        "colon",
        "glioblastoma",
        "glioma",
        "폐암",
        "두경부",
        "대장",
        "교모세포종",
        "뇌종양"
      ],
      "tissues": [
        {
          "organ": "dermatologic",
          "tpm": 92
        },
        {
          "organ": "gastrointestinal",
          "tpm": 54
        },
        {
          "organ": "ocular",
          "tpm": 45
        }
      ],
      "popover": "Epidermal growth factor receptor amplified in NSCLC, HNSCC, colorectal, and glioblastoma; abundant basal keratinocyte and corneal expression drives rash and keratitis.",
      "popover_ko": "비소세포폐암, 두경부암, 대장암, 교모세포종에서 증폭되는 표피성장인자 수용체입니다. 피부 기저 각질세포와 각막 상피 발현이 높아 피부 및 안구 독성 제어가 핵심입니다."
    },
    {
      "id": "c-MET (MET)",
      "gene": "MET",
      "group": "lung_gi",
      "refAdc": "enfortumab-vedotin",
      "selectivity": 4.4,
      "tumor_tpm": 215.0,
      "tumorKeys": [
        "nsclc",
        "lung",
        "gastric",
        "stomach",
        "colorectal",
        "colon",
        "renal",
        "hepatocellular",
        "liver",
        "폐암",
        "위암",
        "대장",
        "신장암",
        "간암"
      ],
      "tissues": [
        {
          "organ": "hepatic",
          "tpm": 46
        },
        {
          "organ": "gastrointestinal",
          "tpm": 38
        },
        {
          "organ": "renal",
          "tpm": 34
        }
      ],
      "popover": "Hepatocyte growth factor receptor overexpressed in MET-amplified NSCLC, gastric, and colorectal cancers (Telisotuzumab vedotin target).",
      "popover_ko": "비소세포폐암, 위암, 대장암에서 증폭되는 간세포성장인자 수용체(텔리소투주맙 베도틴 표적)로, 간세포 및 위장관 상피 기저 발현을 고려해 설계합니다."
    },
    {
      "id": "CEACAM5",
      "gene": "CEACAM5",
      "group": "lung_gi",
      "refAdc": "sacituzumab-govitecan",
      "selectivity": 4.8,
      "tumor_tpm": 350.0,
      "tumorKeys": [
        "colorectal",
        "colon",
        "rectal",
        "gastric",
        "stomach",
        "nsclc",
        "lung",
        "pancreatic",
        "대장",
        "결장",
        "직장",
        "위암",
        "폐암",
        "췌장"
      ],
      "tissues": [
        {
          "organ": "gastrointestinal",
          "tpm": 86
        },
        {
          "organ": "pulmonary",
          "tpm": 18
        },
        {
          "organ": "hepatic",
          "tpm": 8
        }
      ],
      "popover": "Carcinoembryonic antigen densely expressed on colorectal, gastric, pancreatic, and non-squamous NSCLC tumors (Tusamitamab / Precemtabart target).",
      "popover_ko": "대장암, 위암, 췌장암, 비편평 비소세포폐암에서 고밀도로 발현되는 암배아항원(투사미타맙, 프레셈타바트 표적)입니다. 정상 대장 점막 외 전신 장기 발현이 낮습니다."
    },
    {
      "id": "CLDN18.2 (CLDN18)",
      "gene": "CLDN18",
      "group": "lung_gi",
      "refAdc": "trastuzumab-deruxtecan",
      "selectivity": 5.1,
      "tumor_tpm": 260.0,
      "tumorKeys": [
        "gastric",
        "stomach",
        "esophageal",
        "pancreatic",
        "biliary",
        "cholangio",
        "위암",
        "식도암",
        "췌장",
        "담도",
        "담관"
      ],
      "tissues": [
        {
          "organ": "gastrointestinal",
          "tpm": 90
        },
        {
          "organ": "pulmonary",
          "tpm": 22
        },
        {
          "organ": "hepatic",
          "tpm": 4
        }
      ],
      "popover": "Tight-junction isoform buried in healthy gastric pits but exposed on gastric, GEJ, and pancreatic adenocarcinoma surfaces, yielding high tumor selectivity outside gastric mucosa.",
      "popover_ko": "정상 위 점막에서는 세포 간 밀착연접 내부에 숨겨져 있다가 위암, 식도위접합부암, 췌장암에서 표면으로 노출되는 고선택성 표적입니다."
    },
    {
      "id": "B7-H3 (CD276)",
      "gene": "CD276",
      "group": "lung_gi",
      "refAdc": "trastuzumab-deruxtecan",
      "selectivity": 5.2,
      "tumor_tpm": 240.0,
      "tumorKeys": [
        "sclc",
        "nsclc",
        "lung",
        "prostate",
        "esophageal",
        "head and neck",
        "sarcoma",
        "neuroblastoma",
        "폐암",
        "소세포",
        "전립선",
        "식도암",
        "육종",
        "두경부"
      ],
      "tissues": [
        {
          "organ": "metabolic_endocrine",
          "tpm": 18
        },
        {
          "organ": "pulmonary",
          "tpm": 16
        },
        {
          "organ": "cardiovascular",
          "tpm": 14
        }
      ],
      "popover": "Immune checkpoint ligand overexpressed across SCLC, prostate, esophageal, and pediatric solid tumors (Ifinatamab deruxtecan target) with restricted normal organ translation.",
      "popover_ko": "소세포폐암, 전립선암, 식도암, 육종 등 고형암 전반에 과발현되는 면역관문 단백질(이피나타맙 데룩스테칸 표적)로 정상 장기 발현이 낮아 치료지수가 넓습니다."
    },
    {
      "id": "DLL3",
      "gene": "DLL3",
      "group": "lung_gi",
      "refAdc": "loncastuximab-tesirine",
      "selectivity": 5.9,
      "tumor_tpm": 185.0,
      "tumorKeys": [
        "sclc",
        "neuroendocrine",
        "lung",
        "prostate",
        "glioma",
        "소세포폐암",
        "폐암",
        "신경내분비"
      ],
      "tissues": [
        {
          "organ": "neurologic",
          "tpm": 22
        },
        {
          "organ": "metabolic_endocrine",
          "tpm": 11
        },
        {
          "organ": "pulmonary",
          "tpm": 4
        }
      ],
      "popover": "Inhibitory Notch ligand selectively expressed on small-cell lung cancer (SCLC) and neuroendocrine carcinomas with virtually absent surface expression in adult normal organs.",
      "popover_ko": "소세포폐암(SCLC) 및 신경내분비 종양 표면에 특이적으로 발현되는 Notch 리간드로, 성인 정상 조직의 세포막 표면 발현이 극히 낮습니다."
    },
    {
      "id": "Mesothelin (MSLN)",
      "gene": "MSLN",
      "group": "lung_gi",
      "refAdc": "mirvetuximab-soravtansine",
      "selectivity": 4.5,
      "tumor_tpm": 255.0,
      "tumorKeys": [
        "mesothelioma",
        "ovarian",
        "pancreatic",
        "nsclc",
        "lung",
        "중피종",
        "흉막",
        "난소",
        "췌장",
        "폐암"
      ],
      "tissues": [
        {
          "organ": "pulmonary",
          "tpm": 48
        },
        {
          "organ": "cardiovascular",
          "tpm": 30
        },
        {
          "organ": "gastrointestinal",
          "tpm": 14
        }
      ],
      "popover": "GPI-anchored glycoprotein overexpressed in mesothelioma, pancreatic, and ovarian cancers (Anetumab target); normal expression is confined to pleural/pericardial/peritoneal serosa.",
      "popover_ko": "악성 중피종, 췌장암, 난소암에서 과발현되는 막단백질(아네투맙 표적)입니다. 정상 발현이 흉막, 심낭, 복막 중피세포에 국한되어 장막염 감시가 필요합니다."
    },
    {
      "id": "EpCAM",
      "gene": "EPCAM",
      "group": "lung_gi",
      "refAdc": "sacituzumab-govitecan",
      "selectivity": 3.7,
      "tumor_tpm": 330.0,
      "tumorKeys": [
        "colorectal",
        "colon",
        "gastric",
        "breast",
        "pancreatic",
        "ovarian",
        "대장",
        "위암",
        "유방",
        "췌장",
        "난소"
      ],
      "tissues": [
        {
          "organ": "gastrointestinal",
          "tpm": 94
        },
        {
          "organ": "pulmonary",
          "tpm": 46
        },
        {
          "organ": "renal",
          "tpm": 38
        }
      ],
      "popover": "Pan-epithelial cell adhesion molecule with very high copy density across GI and breast carcinomas; basolateral expression in normal gut and biliary epithelium requires stable linkers.",
      "popover_ko": "위장관암, 유방암 등 상피성 암종에서 매우 높은 밀도로 발현되나 정상 장 점막 및 담관 상피에도 발현되어 고안정성 링커 조합이 요구됩니다."
    },
    {
      "id": "FGFR2",
      "gene": "FGFR2",
      "group": "lung_gi",
      "refAdc": "enfortumab-vedotin",
      "selectivity": 4.3,
      "tumor_tpm": 205.0,
      "tumorKeys": [
        "gastric",
        "stomach",
        "cholangio",
        "biliary",
        "breast",
        "endometrial",
        "위암",
        "담관",
        "담도",
        "유방",
        "자궁내막"
      ],
      "tissues": [
        {
          "organ": "dermatologic",
          "tpm": 58
        },
        {
          "organ": "ocular",
          "tpm": 46
        },
        {
          "organ": "gastrointestinal",
          "tpm": 36
        }
      ],
      "popover": "Fibroblast growth factor receptor 2b/2 amplified in diffuse gastric cancer and intrahepatic cholangiocarcinoma (Aprutumab target); corneal and nail-bed expression warrants ocular care.",
      "popover_ko": "미만성 위암과 담관암에서 유전자 증폭이 흔한 수용체(아프루투맙 표적)이며, 각막 및 피부 부속기 기저 발현을 고려해야 합니다."
    },
    {
      "id": "Integrin beta-6 (ITGB6)",
      "gene": "ITGB6",
      "group": "lung_gi",
      "refAdc": "enfortumab-vedotin",
      "selectivity": 4.8,
      "tumor_tpm": 225.0,
      "tumorKeys": [
        "nsclc",
        "lung",
        "head and neck",
        "esophageal",
        "pancreatic",
        "breast",
        "폐암",
        "두경부",
        "식도암",
        "췌장",
        "유방"
      ],
      "tissues": [
        {
          "organ": "pulmonary",
          "tpm": 36
        },
        {
          "organ": "gastrointestinal",
          "tpm": 28
        },
        {
          "organ": "dermatologic",
          "tpm": 24
        }
      ],
      "popover": "Epithelial-restricted alpha-v-beta-6 integrin upregulated during carcinoma invasion in NSCLC, HNSCC, and esophageal cancer (Sigvotatug vedotin target).",
      "popover_ko": "비소세포폐암, 두경부암, 식도암의 침윤 과정에서 특이적으로 유도되는 인테그린(시그보타투그 베도틴 표적)으로 정상 성체 조직 발현이 낮습니다."
    },
    {
      "id": "Nectin-4",
      "gene": "NECTIN4",
      "group": "gu_solid",
      "refAdc": "enfortumab-vedotin",
      "selectivity": 4.3,
      "tumor_tpm": 190.0,
      "tumorKeys": [
        "urothelial",
        "bladder",
        "breast",
        "nsclc",
        "cervical",
        "요로상피",
        "방광",
        "유방",
        "자궁경부"
      ],
      "tissues": [
        {
          "organ": "dermatologic",
          "tpm": 84
        },
        {
          "organ": "metabolic_endocrine",
          "tpm": 45
        },
        {
          "organ": "ocular",
          "tpm": 34
        }
      ],
      "popover": "Cell adhesion molecule highly enriched in urothelial carcinoma; physiological expression in epidermal keratinocytes and sweat glands mediates cutaneous toxicity.",
      "popover_ko": "요로상피암(방광암)에서 고밀도로 발현되는 세포 접착 분자입니다. 정상 표피 각질세포와 땀샘에도 발현량이 높아 표적 매개 피부 발진, 건조증에 대한 관리가 중요합니다."
    },
    {
      "id": "PSMA (FOLH1)",
      "gene": "FOLH1",
      "group": "gu_solid",
      "refAdc": "enfortumab-vedotin",
      "selectivity": 5.3,
      "tumor_tpm": 295.0,
      "tumorKeys": [
        "prostate",
        "renal",
        "kidney",
        "전립선",
        "신장암"
      ],
      "tissues": [
        {
          "organ": "renal",
          "tpm": 52
        },
        {
          "organ": "gastrointestinal",
          "tpm": 28
        },
        {
          "organ": "neurologic",
          "tpm": 19
        }
      ],
      "popover": "Prostate-specific membrane antigen densely expressed in metastatic castration-resistant prostate cancer and tumor neovasculature, with proximal renal tubule and salivary expression.",
      "popover_ko": "전이성 거세저항성 전립선암과 종양 신생혈관에 고발현되는 막항원입니다. 신장 근위세뇨관 및 침샘의 기저 발현을 고려해 페이로드를 선택합니다."
    },
    {
      "id": "STEAP1",
      "gene": "STEAP1",
      "group": "gu_solid",
      "refAdc": "enfortumab-vedotin",
      "selectivity": 5.4,
      "tumor_tpm": 240.0,
      "tumorKeys": [
        "prostate",
        "sarcoma",
        "ewing",
        "bladder",
        "전립선",
        "육종",
        "방광"
      ],
      "tissues": [
        {
          "organ": "metabolic_endocrine",
          "tpm": 25
        },
        {
          "organ": "renal",
          "tpm": 14
        },
        {
          "organ": "pulmonary",
          "tpm": 12
        }
      ],
      "popover": "Six-transmembrane epithelial antigen of the prostate (Vandortuzumab target) overexpressed in >85% of prostate cancers and Ewing sarcoma with minimal normal visceral expression.",
      "popover_ko": "전립선암의 85% 이상과 유윙 육종에서 과발현되는 6막관통 단백질(반도르투주맙 표적)로 정상 실질 장기의 기저 발현이 매우 낮습니다."
    },
    {
      "id": "CDH6",
      "gene": "CDH6",
      "group": "gu_solid",
      "refAdc": "trastuzumab-deruxtecan",
      "selectivity": 5.0,
      "tumor_tpm": 235.0,
      "tumorKeys": [
        "ovarian",
        "renal",
        "kidney",
        "endometrial",
        "cholangio",
        "난소",
        "신장암",
        "신세포암",
        "자궁내막"
      ],
      "tissues": [
        {
          "organ": "renal",
          "tpm": 68
        },
        {
          "organ": "neurologic",
          "tpm": 16
        },
        {
          "organ": "cardiovascular",
          "tpm": 8
        }
      ],
      "popover": "Cadherin-6 cell adhesion receptor overexpressed in ovarian and clear-cell renal cell carcinoma (Raludotatug deruxtecan target); normal expression is mainly renal proximal tubules.",
      "popover_ko": "난소암 및 투명세포 신세포암에서 고발현되는 카드헤린-6(랄루도타투그 데룩스테칸 표적)로, 정상 조직 발현은 신장 근위세뇨관에 제한됩니다."
    },
    {
      "id": "ENPP3",
      "gene": "ENPP3",
      "group": "gu_solid",
      "refAdc": "belantamab-mafodotin",
      "selectivity": 5.1,
      "tumor_tpm": 220.0,
      "tumorKeys": [
        "renal",
        "kidney",
        "hepatocellular",
        "liver",
        "신장암",
        "신세포암",
        "간암"
      ],
      "tissues": [
        {
          "organ": "renal",
          "tpm": 44
        },
        {
          "organ": "gastrointestinal",
          "tpm": 32
        },
        {
          "organ": "hepatic",
          "tpm": 18
        }
      ],
      "popover": "Ectonucleotide pyrophosphatase (CD203c, AGS-16C3F target) expressed in >90% of clear-cell and papillary renal cell carcinomas with low systemic background.",
      "popover_ko": "투명세포 및 유두상 신세포암의 90% 이상에서 과발현되는 효소 수용체(AGS-16C3F 표적)로 비표적 장기 기저 발현이 낮습니다."
    },
    {
      "id": "AXL",
      "gene": "AXL",
      "group": "gu_solid",
      "refAdc": "tisotumab-vedotin",
      "selectivity": 4.4,
      "tumor_tpm": 205.0,
      "tumorKeys": [
        "nsclc",
        "lung",
        "sarcoma",
        "melanoma",
        "pancreatic",
        "renal",
        "aml",
        "폐암",
        "육종",
        "흑색종",
        "췌장",
        "신장암"
      ],
      "tissues": [
        {
          "organ": "pulmonary",
          "tpm": 34
        },
        {
          "organ": "cardiovascular",
          "tpm": 26
        },
        {
          "organ": "musculoskeletal",
          "tpm": 22
        }
      ],
      "popover": "TAM-family receptor tyrosine kinase enriched in mesenchymal/EMT drug-resistant NSCLC, sarcoma, and melanoma (Enapotamab / Mecbotamab target).",
      "popover_ko": "상피-중간엽 전이(EMT) 및 치료 저항성 비소세포폐암, 육종, 흑색종에서 발현이 증가하는 수용체(에나포타맙, 멕보타맙 표적)입니다."
    },
    {
      "id": "PTK7",
      "gene": "PTK7",
      "group": "gu_solid",
      "refAdc": "sacituzumab-govitecan",
      "selectivity": 4.7,
      "tumor_tpm": 225.0,
      "tumorKeys": [
        "ovarian",
        "nsclc",
        "lung",
        "tnbc",
        "breast",
        "esophageal",
        "난소",
        "폐암",
        "유방",
        "삼중음성",
        "식도암"
      ],
      "tissues": [
        {
          "organ": "gastrointestinal",
          "tpm": 32
        },
        {
          "organ": "pulmonary",
          "tpm": 24
        },
        {
          "organ": "dermatologic",
          "tpm": 22
        }
      ],
      "popover": "Wnt-pathway pseudokinase receptor enriched on tumor-initiating cells in ovarian cancer, TNBC, and NSCLC (Cofetuzumab pelidotin target).",
      "popover_ko": "난소암, 삼중음성 유방암, 비소세포폐암의 암줄기세포 분획에서 과발현되는 Wnt 경로 수용체(코페투주맙 표적)입니다."
    },
    {
      "id": "P-Cadherin (CDH3)",
      "gene": "CDH3",
      "group": "gu_solid",
      "refAdc": "enfortumab-vedotin",
      "selectivity": 4.3,
      "tumor_tpm": 240.0,
      "tumorKeys": [
        "head and neck",
        "breast",
        "tnbc",
        "pancreatic",
        "gastric",
        "colorectal",
        "두경부",
        "유방",
        "삼중음성",
        "췌장",
        "위암",
        "대장"
      ],
      "tissues": [
        {
          "organ": "dermatologic",
          "tpm": 64
        },
        {
          "organ": "gastrointestinal",
          "tpm": 34
        },
        {
          "organ": "ocular",
          "tpm": 22
        }
      ],
      "popover": "Placental cadherin upregulated in basal-like breast, HNSCC, pancreatic, and gastric carcinomas (PCA062 target); basal epidermal expression parallels Nectin-4.",
      "popover_ko": "기저유사 유방암, 두경부암, 췌장암, 위암에서 발현되는 태반성 카드헤린으로, 피부 기저층 발현이 있어 피부 독성 감시가 권장됩니다."
    },
    {
      "id": "GPNMB",
      "gene": "GPNMB",
      "group": "gu_solid",
      "refAdc": "enfortumab-vedotin",
      "selectivity": 4.6,
      "tumor_tpm": 230.0,
      "tumorKeys": [
        "melanoma",
        "breast",
        "tnbc",
        "osteosarcoma",
        "sarcoma",
        "glioma",
        "흑색종",
        "피부암",
        "유방",
        "삼중음성",
        "골육종",
        "육종"
      ],
      "tissues": [
        {
          "organ": "dermatologic",
          "tpm": 45
        },
        {
          "organ": "musculoskeletal",
          "tpm": 18
        },
        {
          "organ": "pulmonary",
          "tpm": 16
        }
      ],
      "popover": "Osteoactivin transmembrane glycoprotein overexpressed in melanoma, TNBC, and osteosarcoma (Glembatumumab vedotin target); melanocyte expression links to rash.",
      "popover_ko": "흑색종, 삼중음성 유방암, 골육종에서 과발현되는 막관통 당단백질(글렘바투무맙 베도틴 표적)로 피부 멜라닌세포 발현과 연관됩니다."
    },
    {
      "id": "ROR1",
      "gene": "ROR1",
      "group": "gu_solid",
      "refAdc": "polatuzumab-vedotin",
      "selectivity": 5.5,
      "tumor_tpm": 195.0,
      "tumorKeys": [
        "lymphoma",
        "cll",
        "leukemia",
        "tnbc",
        "breast",
        "nsclc",
        "ovarian",
        "림프종",
        "백혈병",
        "유방",
        "삼중음성",
        "폐암",
        "난소"
      ],
      "tissues": [
        {
          "organ": "cardiovascular",
          "tpm": 11
        },
        {
          "organ": "neurologic",
          "tpm": 9
        },
        {
          "organ": "pulmonary",
          "tpm": 8
        }
      ],
      "popover": "Oncofetal receptor expressed across mantle-cell/DLBCL lymphomas, CLL, TNBC, and NSCLC (Zilovertamab vedotin target) with minimal adult tissue expression.",
      "popover_ko": "외투세포 및 미만성 거대 B세포 림프종과 삼중음성 유방암, 폐암에 발현되는 태아성 종양항원(질로버타맙 베도틴 표적)으로 성인 정상 조직 발현이 매우 낮습니다."
    },
    {
      "id": "CD79b",
      "gene": "CD79B",
      "group": "heme",
      "refAdc": "polatuzumab-vedotin",
      "selectivity": 5.4,
      "tumor_tpm": 240.0,
      "tumorKeys": [
        "lymphoma",
        "dlbcl",
        "b-cell",
        "leukemia",
        "림프종",
        "백혈병",
        "미만성"
      ],
      "tissues": [
        {
          "organ": "haematologic",
          "tpm": 72
        },
        {
          "organ": "infectious_immune",
          "tpm": 58
        },
        {
          "organ": "hepatic",
          "tpm": 12
        }
      ],
      "popover": "B-cell receptor signaling subunit restricted to B-lineage lymphomas; rapidly internalized upon cross-linking with high selectivity outside lymphoid compartments.",
      "popover_ko": "B세포 계열 림프종에 선택적으로 발현되는 B세포 수용체 신호전달 소단위입니다. 결합 시 신속히 내재화되며 골수, 림프 조직 외 고형 장기 발현은 매우 낮습니다."
    },
    {
      "id": "BCMA (TNFRSF17)",
      "gene": "TNFRSF17",
      "group": "heme",
      "refAdc": "belantamab-mafodotin",
      "selectivity": 5.8,
      "tumor_tpm": 260.0,
      "tumorKeys": [
        "myeloma",
        "plasma",
        "waldenstrom",
        "골수종",
        "형질세포"
      ],
      "tissues": [
        {
          "organ": "haematologic",
          "tpm": 66
        },
        {
          "organ": "ocular",
          "tpm": 49
        },
        {
          "organ": "renal",
          "tpm": 14
        }
      ],
      "popover": "Lineage-restricted receptor on mature plasma cells in multiple myeloma; corneal epithelial changes arise via off-target macropinocytosis of charged conjugates.",
      "popover_ko": "다발성 골수종 형질세포에 특이적으로 발현되는 성숙 항원입니다. 정상 고형 장기 발현은 극히 낮으나 각막 상피의 비특이적 거대음세포작용을 통한 안구 독성이 주요 감시 대상입니다."
    },
    {
      "id": "CD19",
      "gene": "CD19",
      "group": "heme",
      "refAdc": "loncastuximab-tesirine",
      "selectivity": 5.5,
      "tumor_tpm": 250.0,
      "tumorKeys": [
        "lymphoma",
        "dlbcl",
        "all",
        "cll",
        "leukemia",
        "b-cell",
        "림프종",
        "백혈병"
      ],
      "tissues": [
        {
          "organ": "haematologic",
          "tpm": 68
        },
        {
          "organ": "infectious_immune",
          "tpm": 62
        },
        {
          "organ": "hepatic",
          "tpm": 10
        }
      ],
      "popover": "Pan-B-lineage co-receptor expressed from pre-B ALL through DLBCL (Loncastuximab tesirine target) with zero expression on non-hematopoietic solid parenchyma.",
      "popover_ko": "급성 림프구성 백혈병부터 미만성 거대 B세포 림프종까지 폭넓게 발현되는 B세포 공수용체(론카스툭시맙 테시린 표적)로 비조혈계 고형 장기 발현이 없습니다."
    },
    {
      "id": "CD22",
      "gene": "CD22",
      "group": "heme",
      "refAdc": "inotuzumab-ozogamicin",
      "selectivity": 5.4,
      "tumor_tpm": 235.0,
      "tumorKeys": [
        "all",
        "leukemia",
        "lymphoma",
        "b-cell",
        "백혈병",
        "림프종"
      ],
      "tissues": [
        {
          "organ": "haematologic",
          "tpm": 64
        },
        {
          "organ": "infectious_immune",
          "tpm": 54
        },
        {
          "organ": "hepatic",
          "tpm": 16
        }
      ],
      "popover": "Sialic-acid binding Ig-like lectin (Siglec-2) rapidly endocytosed on B-cell ALL and NHL blasts (Inotuzumab ozogamicin target); hepatic VOD risk comes from calicheamicin payload.",
      "popover_ko": "B세포 급성 림프구성 백혈병에서 빠르게 내재화되는 시알산 결합 수용체(이노투주맙 오조가마이신 표적)입니다. 간 정맥폐쇄성 질환 위험은 주로 칼리키아마이신 페이로드에서 기인합니다."
    },
    {
      "id": "CD30 (TNFRSF8)",
      "gene": "TNFRSF8",
      "group": "heme",
      "refAdc": "brentuximab-vedotin",
      "selectivity": 5.9,
      "tumor_tpm": 275.0,
      "tumorKeys": [
        "hodgkin",
        "lymphoma",
        "alcl",
        "t-cell",
        "호지킨",
        "림프종"
      ],
      "tissues": [
        {
          "organ": "infectious_immune",
          "tpm": 34
        },
        {
          "organ": "haematologic",
          "tpm": 28
        },
        {
          "organ": "pulmonary",
          "tpm": 8
        }
      ],
      "popover": "TNF-receptor family member densely expressed on Hodgkin Reed-Sternberg cells and ALCL (Brentuximab vedotin target), restricted to small activated lymphocyte subsets in health.",
      "popover_ko": "호지킨 림프종과 역형성 거대세포 림프종에서 선택적으로 고발현되는 수용체(브렌툭시맙 베도틴 표적)로 정상 조직 내 기저 발현이 극히 제한적입니다."
    },
    {
      "id": "CD33",
      "gene": "CD33",
      "group": "heme",
      "refAdc": "gemtuzumab-ozogamicin",
      "selectivity": 4.9,
      "tumor_tpm": 245.0,
      "tumorKeys": [
        "aml",
        "myeloid",
        "leukemia",
        "myelodysplastic",
        "백혈병",
        "골수성",
        "골수이형성"
      ],
      "tissues": [
        {
          "organ": "haematologic",
          "tpm": 78
        },
        {
          "organ": "hepatic",
          "tpm": 34
        },
        {
          "organ": "infectious_immune",
          "tpm": 42
        }
      ],
      "popover": "Myeloid Siglec-3 receptor expressed on ~90% of AML blasts (Gemtuzumab ozogamicin target); shared expression on myeloid progenitors and hepatic Kupffer cells drives cytopenia and VOD.",
      "popover_ko": "급성 골수성 백혈병(AML) 모세포의 약 90%에 발현되는 골수계 항원(겜투주맙 오조가마이신 표적)으로 골수 전구세포와 간 쿠퍼세포 발현에 따른 혈구감소 및 간독성 관리가 핵심입니다."
    },
    {
      "id": "CD123 (IL3RA)",
      "gene": "IL3RA",
      "group": "heme",
      "refAdc": "gemtuzumab-ozogamicin",
      "selectivity": 5.3,
      "tumor_tpm": 215.0,
      "tumorKeys": [
        "aml",
        "bpdcen",
        "myeloid",
        "leukemia",
        "myelodysplastic",
        "백혈병",
        "골수성",
        "골수이형성"
      ],
      "tissues": [
        {
          "organ": "haematologic",
          "tpm": 58
        },
        {
          "organ": "infectious_immune",
          "tpm": 36
        },
        {
          "organ": "cardiovascular",
          "tpm": 18
        }
      ],
      "popover": "Interleukin-3 receptor alpha chain enriched on leukemic stem cells in AML and BPDCN (Pivekimab sunirine target) with lower expression on normal HSCs than CD33.",
      "popover_ko": "급성 골수성 백혈병 줄기세포와 모세포성 형질세포양 수지상세포 종양에서 과발현되는 수용체(피베키맙 수니린 표적)로 CD33 대비 정상 조혈모세포 발현이 낮습니다."
    },
    {
      "id": "CD70",
      "gene": "CD70",
      "group": "heme",
      "refAdc": "brentuximab-vedotin",
      "selectivity": 5.6,
      "tumor_tpm": 230.0,
      "tumorKeys": [
        "renal",
        "kidney",
        "lymphoma",
        "aml",
        "leukemia",
        "nasopharyngeal",
        "신장암",
        "림프종",
        "백혈병",
        "비인두암"
      ],
      "tissues": [
        {
          "organ": "infectious_immune",
          "tpm": 28
        },
        {
          "organ": "haematologic",
          "tpm": 22
        },
        {
          "organ": "renal",
          "tpm": 10
        }
      ],
      "popover": "CD27 ligand transiently expressed only on antigen-activated lymphocytes in health, but constitutively overexpressed in clear-cell RCC, NHL, and AML.",
      "popover_ko": "정상 상태에서는 활성화된 림프구에만 일시 발현되나 투명세포 신세포암, 림프종, 급성 골수성 백혈병에서 지속적으로 고발현되는 고선택성 표적입니다."
    },
    {
      "id": "CD25 (IL2RA)",
      "gene": "IL2RA",
      "group": "heme",
      "refAdc": "brentuximab-vedotin",
      "selectivity": 5.4,
      "tumor_tpm": 220.0,
      "tumorKeys": [
        "hodgkin",
        "lymphoma",
        "t-cell",
        "leukemia",
        "호지킨",
        "림프종",
        "백혈병"
      ],
      "tissues": [
        {
          "organ": "infectious_immune",
          "tpm": 48
        },
        {
          "organ": "haematologic",
          "tpm": 35
        },
        {
          "organ": "dermatologic",
          "tpm": 12
        }
      ],
      "popover": "IL-2 receptor alpha chain expressed on Hodgkin/T-cell lymphomas and intratumoral immunosuppressive Treg cells (Camidanlumab tesirine target).",
      "popover_ko": "호지킨 및 T세포 림프종 세포와 종양 미세환경 내 면역억제 조절 T세포(Treg)에 고발현되는 수용체(카미단루맙 테시린 표적)입니다."
    }
  ];

  let STUDIO_LINKERS = [
    {
      "id": "Tetrapeptide GGFG",
      "group": "protease",
      "cleavable": true,
      "stability": 88,
      "hydro": 0.2,
      "handle": "amine_hydroxyl",
      "popover": "Hydrophilic glycine-phenylalanine tetrapeptide cleaved selectively by lysosomal cathepsins B/L. High plasma stability (88%) and low hydrophobicity enable homogeneous DAR 8 loading.",
      "popover_ko": "리소좀 효소(카텝신 B/L)에 의해 선택적으로 절단되는 친수성 테트라펩타이드 링커입니다. 높은 혈장 안정도(88%)와 낮은 소수성으로 DAR 8 고밀도 접합에서도 간 응집을 억제합니다."
    },
    {
      "id": "GGFG-Cyclopropyl",
      "group": "protease",
      "cleavable": true,
      "stability": 92,
      "hydro": 0.24,
      "handle": "amine_hydroxyl",
      "popover": "Cyclopropyl-shielded GGFG aminomethylene linker (SHR-A1811 / Rezetecan class) that slows premature plasma esterase/protease cleavage while preserving lysosomal Topo I release.",
      "popover_ko": "아미노메틸렌 자가절단 부위에 사이클로프로필 입체 보호기를 도입한 차세대 GGFG 링커(SHR-A1811 계열)로 혈중 조기 유출을 더욱 낮춥니다."
    },
    {
      "id": "Val-Cit PABC",
      "group": "protease",
      "cleavable": true,
      "stability": 76,
      "hydro": 0.58,
      "handle": "amine",
      "popover": "Standard cathepsin B-cleavable dipeptide linker with self-immolative 1,6-PABC spacer. Releases amine payloads cleanly inside tumor lysosomes, optimal at DAR 2-4.",
      "popover_ko": "카텝신 B 절단 후 자가소멸 스페이서(PABC)를 통해 유리 약물을 방출하는 표준 디펩타이드 링커입니다. 아민계 페이로드 방출 효율이 뛰어나며 DAR 2-4 구간에 적합합니다."
    },
    {
      "id": "Val-Ala PABC",
      "group": "protease",
      "cleavable": true,
      "stability": 80,
      "hydro": 0.44,
      "handle": "amine",
      "popover": "Less hydrophobic Val-Ala dipeptide with PABC spacer; reduces high-DAR aggregation relative to Val-Cit while maintaining rapid cathepsin cleavage.",
      "popover_ko": "Val-Cit 대비 소수성과 응집 경향을 낮춘 Val-Ala 디펩타이드 PABC 링커로 리소좀 카텝신 절단 속도와 용해도의 균형이 우수합니다."
    },
    {
      "id": "Glu-Val-Cit PABC",
      "group": "protease",
      "cleavable": true,
      "stability": 91,
      "hydro": 0.28,
      "handle": "amine",
      "popover": "Anionic Glu-Val-Cit tripeptide PABC linker engineered to block extracellular neutrophil-elastase cleavage in bone marrow and lungs while retaining full lysosomal cathepsin B release.",
      "popover_ko": "음전하 글루탐산(Glu)을 도입해 골수 및 폐 호중구 엘라스타아제에 의한 세포 외 조기 절단(호중구감소증 유발 경로)을 차단한 고안정성 트리펩타이드 링커입니다."
    },
    {
      "id": "Legumain Asn-Pro-Val",
      "group": "protease",
      "cleavable": true,
      "stability": 93,
      "hydro": 0.34,
      "handle": "amine_hydroxyl",
      "popover": "Tumor-associated legumain (asparaginyl endopeptidase) cleavable tripeptide linker with high stability in normal human plasma and myeloid progenitors.",
      "popover_ko": "종양 리소좀에 과발현되는 레구메인 효소에 의해서만 절단되는 Asn-Pro-Val 링커로 정상 혈장 및 조혈모세포 내 안정성이 매우 높습니다."
    },
    {
      "id": "PEG8-Val-Ala PABC",
      "group": "hydrophilic",
      "cleavable": true,
      "stability": 84,
      "hydro": 0.18,
      "handle": "amine",
      "popover": "Discrete PEG8-shielded Val-Ala PABC linker (Zynlonta / Tesirine architecture) that masks lipophilic warheads from hepatic Kupffer-cell uptake.",
      "popover_ko": "단분산 PEG8 친수성 사슬로 소수성 페이로드를 차폐한 Val-Ala PABC 링커(진론타 구조)로 간 쿠퍼세포의 비특이 포획을 줄입니다."
    },
    {
      "id": "Beta-Glucuronide PEG8",
      "group": "hydrophilic",
      "cleavable": true,
      "stability": 90,
      "hydro": 0.14,
      "handle": "amine_hydroxyl",
      "popover": "Polyhydroxylated beta-glucuronide + PEG8 linker cleaved strictly by lysosomal beta-glucuronidase; ultra-low hydrophobicity prevents DAR 8 aggregation.",
      "popover_ko": "리소좀 베타-글루쿠로니다아제에 의해서만 절단되는 초친수성 글루쿠로나이드-PEG8 링커로 고밀도 DAR 접합에서도 응집과 조기 유출을 크게 낮춥니다."
    },
    {
      "id": "Pyrimidine-TMT PEG8",
      "group": "hydrophilic",
      "cleavable": true,
      "stability": 86,
      "hydro": 0.22,
      "handle": "amine_hydroxyl",
      "popover": "Methylsulfonyl-pyrimidine irreversible thiol conjugation handle with PEG8 spacer (Sacituzumab tirumotecan / SKB264 class), eliminating retro-Michael maleimide deconjugation in plasma.",
      "popover_ko": "말레이미드의 역-마이클 혈장 탈접합 반응을 원천 차단하는 메틸설포닐 피리미딘 결합부 + PEG8 링커(사시투주맙 티루모테칸 계열)입니다."
    },
    {
      "id": "Pyrophosphate Phos",
      "group": "hydrophilic",
      "cleavable": true,
      "stability": 91,
      "hydro": 0.1,
      "handle": "hydroxyl_amine_hydroxyl",
      "popover": "Di-anionic pyrophosphate diester linker cleaved sequentially by lysosomal acid pyrophosphatase and acid phosphatase; imparts high water solubility.",
      "popover_ko": "이중 음전하 피로인산 에스테르 링커로 혈중에서는 완전한 수용성을 유지하고 리소좀 산성 포스파타아제에 의해 선택적으로 절단됩니다."
    },
    {
      "id": "Hydrolyzable CL2A",
      "group": "ph_redox",
      "cleavable": true,
      "stability": 54,
      "hydro": 0.32,
      "handle": "hydroxyl",
      "popover": "PEGylated pH-sensitive benzyl carbonate linker engineered for camptothecins (SN-38). Intratumoral extracellular + lysosomal hydrolysis drives broad bystander activity at DAR 7.6-8.",
      "popover_ko": "PEG 사슬이 도입된 pH 감응성 탄산염 링커(트로델비 구조)로 산성 종양 미세환경과 리소좀에서 약물을 방출해 강한 주변 암세포 사멸 효과를 유도합니다."
    },
    {
      "id": "Disulfide SPDB",
      "group": "ph_redox",
      "cleavable": true,
      "stability": 68,
      "hydro": 0.52,
      "handle": "thiol",
      "popover": "Sterically hindered gem-dimethyl disulfide bond reduced selectively by high intracellular tumor glutathione (GSH) to release thiol maytansinoids.",
      "popover_ko": "입체장애 이황화 결합으로 혈중 산화 환경에서는 안정하고 암세포 내 고농도 글루타티온(GSH)에 의해 환원되어 티올계 메이탄시노이드를 방출합니다."
    },
    {
      "id": "Sulfo-SPDB",
      "group": "ph_redox",
      "cleavable": true,
      "stability": 74,
      "hydro": 0.26,
      "handle": "thiol",
      "popover": "Charged sulfonated hindered disulfide linker (Mirvetuximab soravtansine / Elahere) that suppresses multidrug-resistance (MDR1) efflux and hepatic aggregation of DM4 conjugates.",
      "popover_ko": "설폰산 음전하기를 도입한 이황화 링커(엘라히어 구조)로 소수성 응집과 다제내성 수송체(MDR1) 약물 유출을 동시에 억제합니다."
    },
    {
      "id": "Acid Hydrazone",
      "group": "ph_redox",
      "cleavable": true,
      "stability": 48,
      "hydro": 0.55,
      "handle": "ketone",
      "popover": "Acid-labile AcBut hydrazone linker hydrolyzed at endosomal/lysosomal pH 4.5-5.0; pairs with ketone-bearing enediynes (calicheamicin) with higher plasma deconjugation.",
      "popover_ko": "엔도솜 및 리소좀 산성 환경(pH 4.5-5.0)에서 가수분해되는 하이드라존 링커로 케톤 작용기 페이로드(칼리키아마이신)와 결합합니다."
    },
    {
      "id": "Non-cleavable mc",
      "group": "non_cleavable",
      "cleavable": false,
      "stability": 96,
      "hydro": 0.42,
      "handle": "amine",
      "popover": "Ultra-stable maleimidocaproyl thioether bond (96% plasma stability) requiring complete lysosomal antibody proteolysis to release charged Cys-mc-payload.",
      "popover_ko": "혈중 안정도 96%의 비절단형 티오에테르 링커로 항체가 리소좀에서 완전 분해될 때만 전하성 아미노산-페이로드 결합체를 방출해 전신 누출을 최소화합니다."
    },
    {
      "id": "Non-cleavable SMCC",
      "group": "non_cleavable",
      "cleavable": false,
      "stability": 95,
      "hydro": 0.46,
      "handle": "thiol_amine",
      "popover": "Rigid cyclohexanecarboxylate thioether linker (Trastuzumab emtansine / Kadcyla architecture) releasing Lys-SMCC-DM1 exclusively after full lysosomal catabolism.",
      "popover_ko": "사이클로헥산 고리를 포함한 고강성 비절단형 티오에테르 링커(캐싸일라 구조)로 리소좀 내 완전 단백질 분해 후에만 약물이 방출됩니다."
    }
  ];

  let STUDIO_PAYLOADS = [
    {
      "id": "DXd ( Topo I )",
      "group": "topo1",
      "cls": "Topoisomerase I inhibitor",
      "perm": true,
      "handle": "amine_hydroxyl",
      "potency": 92,
      "optDar": 8,
      "maxSafeDar": 8,
      "hydro": 0.28,
      "organs": {
        "pulmonary": 82,
        "haematologic": 68,
        "gastrointestinal": 64,
        "cardiovascular": 38,
        "hepatic": 30
      },
      "popover": "Membrane-permeable exatecan hydroxyacetamide derivative (~10x higher Topo I potency than SN-38) with short systemic half-life (~1.6 h); supports DAR 8 loading.",
      "popover_ko": "SN-38 대비 약 10배 높은 효력과 짧은 전신 반감기(약 1.6시간)를 지닌 막투과성 토포이소머라제 I 저해제로 DAR 8 고밀도 접합이 가능합니다."
    },
    {
      "id": "Exatecan ( Topo I )",
      "group": "topo1",
      "cls": "Topoisomerase I inhibitor (PGP-evading)",
      "perm": true,
      "handle": "amine",
      "potency": 94,
      "optDar": 6,
      "maxSafeDar": 8,
      "hydro": 0.36,
      "organs": {
        "haematologic": 78,
        "gastrointestinal": 68,
        "pulmonary": 72,
        "hepatic": 34
      },
      "popover": "Unmodified primary-amine exatecan warhead that evades P-gp/BCRP multidrug efflux pumps and delivers potent bystander killing in Topo I-refractory tumors.",
      "popover_ko": "다제내성 약물유출 펌프(P-gp, BCRP)를 회피하는 1차 아민 엑사테칸 페이로드로 내성 고형암에서 높은 세포독성과 동반 사멸 효능을 보입니다."
    },
    {
      "id": "SN-38 ( Topo I )",
      "group": "topo1",
      "cls": "Topoisomerase I inhibitor (UGT1A1)",
      "perm": true,
      "handle": "hydroxyl",
      "potency": 82,
      "optDar": 7.6,
      "maxSafeDar": 8,
      "hydro": 0.34,
      "organs": {
        "haematologic": 86,
        "gastrointestinal": 84,
        "hepatic": 44,
        "pulmonary": 22
      },
      "popover": "Active metabolite of irinotecan cleared via hepatic UGT1A1 glucuronidation; lower interstitial lung toxicity than DXd, with neutropenia and diarrhea as main DLTs.",
      "popover_ko": "이리노테칸 활성 대사체로 간 UGT1A1 대사를 거치며, DXd 계열 대비 간질성 폐질환 빈도가 낮고 주요 감시 항목은 호중구감소증과 설사입니다."
    },
    {
      "id": "Belotecan KL610023 ( Topo I )",
      "group": "topo1",
      "cls": "Water-soluble Topo I inhibitor",
      "perm": true,
      "handle": "amine_hydroxyl",
      "potency": 89,
      "optDar": 7.6,
      "maxSafeDar": 8,
      "hydro": 0.24,
      "organs": {
        "haematologic": 74,
        "gastrointestinal": 58,
        "pulmonary": 34,
        "hepatic": 32
      },
      "popover": "Belotecan-derived hydrophilic camptothecin warhead (Sacituzumab tirumotecan / SKB264) supporting homogeneous DAR 7.6-8 with low pulmonary and GI mucosal accumulation.",
      "popover_ko": "벨로테칸 유래 친수성 캠프토테신 페이로드(사시투주맙 티루모테칸 적용)로 DAR 7.6-8 고밀도 결합에서도 폐 및 장 점막 축적이 적습니다."
    },
    {
      "id": "Rezetecan SHR9265 ( Topo I )",
      "group": "topo1",
      "cls": "Cyclopropyl-shielded Topo I inhibitor",
      "perm": true,
      "handle": "amine_hydroxyl",
      "potency": 93,
      "optDar": 6,
      "maxSafeDar": 8,
      "hydro": 0.31,
      "organs": {
        "haematologic": 70,
        "pulmonary": 56,
        "gastrointestinal": 56,
        "hepatic": 30
      },
      "popover": "Chiral cyclopropyl-hydroxyamide exatecan analog (Trastuzumab rezetecan / SHR-A1811) balancing membrane bystander permeability with reduced alveolar macrophage retention.",
      "popover_ko": "사이클로프로필 입체 구조를 도입한 엑사테칸 유도체(트라스투주맙 레제테칸 적용)로 주변 암세포 투과도와 폐포 대식세포 안전성 균형을 개선한 약물입니다."
    },
    {
      "id": "AZD8205 Top1i ( Topo I )",
      "group": "topo1",
      "cls": "Next-gen Polar Topo I inhibitor",
      "perm": true,
      "handle": "amine_hydroxyl",
      "potency": 90,
      "optDar": 8,
      "maxSafeDar": 8,
      "hydro": 0.22,
      "organs": {
        "haematologic": 66,
        "pulmonary": 48,
        "gastrointestinal": 52,
        "renal": 28,
        "hepatic": 26
      },
      "popover": "Polar aminomethyl-camptothecin Topo I payload (AZ14170132 / Puxitatug samrotecan class) designed for rapid renal clearance of free payload and DAR 8 homogeneity.",
      "popover_ko": "극성 아미노메틸 치환체를 도입해 유리 약물의 신속한 신장 배설과 DAR 8 균일 접합을 구현한 차세대 토포이소머라제 I 저해제입니다."
    },
    {
      "id": "MMAE ( Auristatin )",
      "group": "tubulin",
      "cls": "Microtubule inhibitor (Auristatin)",
      "perm": true,
      "handle": "amine",
      "potency": 90,
      "optDar": 4,
      "maxSafeDar": 4,
      "hydro": 0.82,
      "organs": {
        "neurologic": 84,
        "haematologic": 76,
        "dermatologic": 66,
        "hepatic": 52
      },
      "popover": "Lipophilic tubulin polymerization inhibitor with strong bystander killing; optimal at DAR 3.5-4, whereas higher DAR accelerates Kupffer clearance and neuropathy.",
      "popover_ko": "막투과성과 동반 사멸 효과가 우수한 미세소관 중합 저해제입니다. DAR 3.5-4에서 치료지수가 최적이며 고DAR에서는 간 포획과 말초신경병증이 증가합니다."
    },
    {
      "id": "MMAF ( Auristatin )",
      "group": "tubulin",
      "cls": "Charged Auristatin (low permeability)",
      "perm": false,
      "handle": "amine",
      "potency": 86,
      "optDar": 4,
      "maxSafeDar": 6,
      "hydro": 0.5,
      "organs": {
        "ocular": 92,
        "haematologic": 64,
        "renal": 28,
        "hepatic": 32,
        "neurologic": 20
      },
      "popover": "C-terminal carboxylate auristatin trapped inside target cells after release; spares peripheral nerves and marrow vs MMAE, with corneal keratopathy as primary risk.",
      "popover_ko": "말단 음전하로 세포 밖 수동 확산이 제한된 오리스타틴입니다. MMAE 대비 신경병증과 골수 억제는 낮으나 각막 상피 축적 관리가 중요합니다."
    },
    {
      "id": "AS269 ( Auristatin )",
      "group": "tubulin",
      "cls": "Site-specific Non-permeable Auristatin",
      "perm": false,
      "handle": "amine_hydroxyl",
      "potency": 88,
      "optDar": 2,
      "maxSafeDar": 4,
      "hydro": 0.44,
      "organs": {
        "ocular": 68,
        "pulmonary": 52,
        "haematologic": 28,
        "neurologic": 18,
        "hepatic": 34
      },
      "popover": "Para-acetylphenylalanine-coupled polar auristatin (ARX788 Amberstatin) yielding ultra-low systemic free payload (<1% deconjugation) and minimal myelosuppression.",
      "popover_ko": "위치 특이적 결합용 극성 오리스타틴(ARX788 앰버스타틴)으로 혈중 유리 약물 농도가 극히 낮아 골수 억제와 신경 독성이 적습니다."
    },
    {
      "id": "Duostatin-5 ( Auristatin )",
      "group": "tubulin",
      "cls": "Morpholine Auristatin",
      "perm": true,
      "handle": "amine",
      "potency": 89,
      "optDar": 3.5,
      "maxSafeDar": 4,
      "hydro": 0.72,
      "organs": {
        "neurologic": 68,
        "haematologic": 66,
        "ocular": 54,
        "hepatic": 44
      },
      "popover": "C-terminal morpholinamide auristatin balancing moderate bystander permeability with lower lipophilicity than MMAE.",
      "popover_ko": "말단 모르폴린 구조를 통해 MMAE보다 친유성을 낮추면서 종양 내 동반 사멸 활성을 유지한 오리스타틴 유도체입니다."
    },
    {
      "id": "DM4 / DM1 ( Maytansinoid )",
      "group": "tubulin",
      "cls": "Microtubule inhibitor (Maytansinoid)",
      "perm": true,
      "handle": "thiol",
      "potency": 85,
      "optDar": 3.5,
      "maxSafeDar": 4,
      "hydro": 0.68,
      "organs": {
        "ocular": 74,
        "hepatic": 72,
        "neurologic": 62,
        "haematologic": 58
      },
      "popover": "Sterically hindered thiol maytansinoid (Ravtansine / Soravtansine) yielding S-methyl-DM4 bystander catabolites; linked to reversible keratopathy and transaminase elevation.",
      "popover_ko": "입체장애 티올기를 지닌 메이탄시노이드(소라브탄신/라브탄신)로 S-메틸 대사체를 통해 동반 사멸을 유도하며 간효소 상승과 가역적 각막병증을 감시합니다."
    },
    {
      "id": "DM1 Mertansine ( Maytansinoid )",
      "group": "tubulin",
      "cls": "Thioether Maytansinoid",
      "perm": false,
      "handle": "thiol",
      "potency": 83,
      "optDar": 3.5,
      "maxSafeDar": 4,
      "hydro": 0.62,
      "organs": {
        "hepatic": 76,
        "haematologic": 64,
        "neurologic": 48,
        "cardiovascular": 34
      },
      "popover": "Mertansine warhead optimized for non-cleavable SMCC conjugation (Kadcyla); releases membrane-impermeable Lys-SMCC-DM1, with thrombocytopenia and AST/ALT rise as main DLTs.",
      "popover_ko": "비절단형 SMCC 링커(캐싸일라)에 최적화된 메르탄신 페이로드로 막비투과성 대사체를 형성하며 혈소판감소증 및 AST/ALT 상승이 주요 감시 항목입니다."
    },
    {
      "id": "Eribulin ( Halichondrin )",
      "group": "tubulin",
      "cls": "Microtubule dynamics inhibitor",
      "perm": true,
      "handle": "amine",
      "potency": 87,
      "optDar": 4,
      "maxSafeDar": 6,
      "hydro": 0.38,
      "organs": {
        "haematologic": 72,
        "pulmonary": 46,
        "neurologic": 44,
        "hepatic": 30
      },
      "popover": "Macrocyclic halichondrin B analog (Farletuzumab ecteribulin / MORAb-202) that inhibits microtubule plus-end growth with lower hydrophobicity and lower neuropathy than MMAE.",
      "popover_ko": "할리콘드린 B 거대고리 유도체(파를레투주맙 엑테리불린 적용)로 친수성이 높고 MMAE 대비 말초신경 손상 빈도가 낮습니다."
    },
    {
      "id": "Tubulysin M ( Tubulysin )",
      "group": "tubulin",
      "cls": "Vinca-domain Tubulin depolymerizer",
      "perm": true,
      "handle": "amine_hydroxyl",
      "potency": 93,
      "optDar": 2,
      "maxSafeDar": 4,
      "hydro": 0.64,
      "organs": {
        "haematologic": 78,
        "hepatic": 64,
        "neurologic": 62,
        "gastrointestinal": 52
      },
      "popover": "Sub-nanomolar tetrapeptide tubulin depolymerizer resistant to P-gp efflux pumps; effective at low DAR (2-3.5) in low-antigen-density tumors.",
      "popover_ko": "P-gp 약물유출 펌프 내성을 극복하는 고효력 튜불리신 페이로드로 저발현 종양에서도 DAR 2-3.5 저밀도 접합으로 강한 세포사멸을 유도합니다."
    },
    {
      "id": "SG3199 ( PBD Dimer )",
      "group": "dna",
      "cls": "DNA minor-groove crosslinker",
      "perm": true,
      "handle": "amine",
      "potency": 98,
      "optDar": 2,
      "maxSafeDar": 2,
      "hydro": 1.15,
      "organs": {
        "haematologic": 92,
        "hepatic": 78,
        "pulmonary": 68,
        "dermatologic": 62,
        "renal": 54
      },
      "popover": "Picomolar pyrrolobenzodiazepine interstrand DNA crosslinker active against quiescent stem-like cells; restricted to DAR 1-2 due to delayed myelosuppression and edema.",
      "popover_ko": "비분열 암줄기세포까지 사멸시키는 피코몰 효력의 DNA 가교제(테시린 페이로드)로 지연성 골수 억제 및 부종 예방을 위해 DAR 1-2 저밀도 설계에 사용됩니다."
    },
    {
      "id": "DGN549 Sunirine ( IGN )",
      "group": "dna",
      "cls": "Mono-imine DNA alkylator (IGN)",
      "perm": true,
      "handle": "amine_thiol",
      "potency": 95,
      "optDar": 2,
      "maxSafeDar": 3.5,
      "hydro": 0.86,
      "organs": {
        "haematologic": 72,
        "hepatic": 54,
        "pulmonary": 42,
        "dermatologic": 46,
        "renal": 38
      },
      "popover": "Indolinobenzodiazepine mono-imine warhead (Pivekimab sunirine) that mono-alkylates DNA without interstrand crosslinking, markedly reducing prolonged marrow aplasia vs PBD dimers.",
      "popover_ko": "가교 대신 단일 알킬화를 유도하도록 개량된 인돌리노벤조디아제핀(수니린 페이로드)으로 PBD 이합체 대비 장기 지속형 골수 억제와 간독성을 크게 완화합니다."
    },
    {
      "id": "seco-DUBA ( Duocarmycin )",
      "group": "dna",
      "cls": "DNA minor-groove AT-alkylator",
      "perm": true,
      "handle": "amine_hydroxyl",
      "potency": 94,
      "optDar": 2,
      "maxSafeDar": 4,
      "hydro": 0.88,
      "organs": {
        "ocular": 76,
        "pulmonary": 64,
        "haematologic": 58,
        "dermatologic": 52,
        "hepatic": 46
      },
      "popover": "Seco-duocarmycin hydroxybenzamide-azaindole prodrug (Trastuzumab duocarmazine / SYD985) killing dividing and non-dividing cells via Spiro-cyclopropyldienone DNA alkylation.",
      "popover_ko": "분열 및 비분열 종양세포의 DNA 작은홈 아데닌을 알킬화하는 듀오카마이신 전구약물(SYD985 페이로드)로 결막 및 폐 독성 감시가 필요합니다."
    },
    {
      "id": "Calicheamicin ( Enediyne )",
      "group": "dna",
      "cls": "DNA double-strand cleaver",
      "perm": true,
      "handle": "ketone_thiol",
      "potency": 96,
      "optDar": 2,
      "maxSafeDar": 4,
      "hydro": 0.76,
      "organs": {
        "hepatic": 90,
        "haematologic": 88,
        "infectious_immune": 64,
        "gastrointestinal": 48
      },
      "popover": "Enediyne diradical DNA double-strand cleaver (Mylotarg / Besponsa); highly potent in acute leukemias, with hepatic sinusoidal obstruction syndrome (VOD/SOS) as key risk.",
      "popover_ko": "DNA 이중가닥 절단을 유도하는 엔다이인계 고효력 페이로드(마일로탁, 베스폰사)로 급성 백혈병에 효과적이나 간 정맥폐쇄성 질환(VOD) 위험이 높습니다."
    },
    {
      "id": "Filanesib KSPi ( Kinesin )",
      "group": "targeted",
      "cls": "Kinesin Spindle Protein (Eg5) inhibitor",
      "perm": false,
      "handle": "amine_hydroxyl",
      "potency": 85,
      "optDar": 4,
      "maxSafeDar": 8,
      "hydro": 0.35,
      "organs": {
        "haematologic": 74,
        "gastrointestinal": 48,
        "hepatic": 24,
        "neurologic": 12
      },
      "popover": "Mitotic kinesin Eg5 inhibitor (VIP943 class) selective strictly for dividing cells; completely spares post-mitotic peripheral neurons (zero axonal neuropathy) and hepatocytes.",
      "popover_ko": "세포분열 방추사 키네신(Eg5)만 선택적으로 저해하는 페이로드로 비분열 말초신경 축삭과 간세포를 손상시키지 않아 신경병증을 원천 회피합니다."
    },
    {
      "id": "STING Agonist ( Immune )",
      "group": "targeted",
      "cls": "Innate Immune STING Agonist (iADC)",
      "perm": false,
      "handle": "amine_hydroxyl",
      "potency": 81,
      "optDar": 4,
      "maxSafeDar": 6,
      "hydro": 0.16,
      "organs": {
        "infectious_immune": 68,
        "hepatic": 34,
        "cardiovascular": 32,
        "haematologic": 28,
        "neurologic": 12
      },
      "popover": "Immunostimulatory STING agonist payload activating intratumoral type-I interferon signaling without direct DNA/tubulin cytotoxicity; avoids classic myelosuppression and neuropathy.",
      "popover_ko": "종양 미세환경 내 제1형 인터페론 선천면역을 활성화하는 면역자극 페이로드(iADC)로 전통적 세포독성 약물의 골수 억제와 신경독성을 피할 수 있습니다."
    }
  ];

  let STUDIO_DAR_ITEMS = [
    {
      "id": "1",
      "val": 1.0,
      "popover": "DAR 1: Ultra-low site-specific single-drug loading for picomolar DNA warheads (PBD/IGN/Calicheamicin) or severe multi-organ fragility.",
      "popover_ko": "DAR 1: 초고효력 DNA 작용 페이로드(PBD, IGN, 칼리키아마이신) 또는 중증 다장기 기능저하 환자의 안전역 확보를 위한 초저밀도 단일 접합 설계입니다."
    },
    {
      "id": "2",
      "val": 2.0,
      "popover": "DAR 2: Site-specific low drug loading. Minimizes hydrophobic aggregation and preserves antibody half-life; standard for PBD/IGN/AS269 conjugates.",
      "popover_ko": "DAR 2: 위치 특이적 저밀도 설계로 소수성 응집을 최소화하고 항체 반감기를 보존하며 고효력 페이로드의 표준 접합비입니다."
    },
    {
      "id": "3.5",
      "val": 3.5,
      "popover": "DAR 3.5: Validated clinical loading for Polivy, Kadcyla, and Elahere. Balances intracellular delivery against hepatic sinusoidal uptake.",
      "popover_ko": "DAR 3.5: 폴라이비, 캐싸일라, 엘라히어 등 승인 약물에서 검증된 접합비로 세포 내 전달량과 간 비특이 포획 사이의 균형이 우수합니다."
    },
    {
      "id": "4",
      "val": 4.0,
      "popover": "DAR 4: Standard interchain cysteine/engineered-site loading (Padcev, Blenrep, Dato-DXd). Optimal therapeutic index for auristatins and Topo I.",
      "popover_ko": "DAR 4: 파드셉, 블렌렙, 다토포타맙 데룩스테칸에 적용된 표준 접합비로 오리스타틴 및 Topo I 계열 전반에서 안정적인 약동학을 보입니다."
    },
    {
      "id": "5",
      "val": 5.0,
      "popover": "DAR 5: Intermediate engineered loading boosting receptor-limited tumor killing while keeping HIC retention below hepatic clearance thresholds.",
      "popover_ko": "DAR 5: 중등도 항원 발현 종양에서 수용체당 약물 전달량을 높이면서도 간 쿠퍼세포 청소 임계치 이하로 소수성을 유지하는 설계입니다."
    },
    {
      "id": "6",
      "val": 6.0,
      "popover": "DAR 6: High-intermediate homogeneous loading (Trastuzumab rezetecan / SHR-A1811 class) pairing shielded GGFG/PEG linkers with Topo I warheads.",
      "popover_ko": "DAR 6: 트라스투주맙 레제테칸(SHR-A1811) 등에 채택된 중고밀도 균일 접합비로 친수성 링커와 결합해 효능과 폐/골수 안전성의 균형을 잡습니다."
    },
    {
      "id": "7.6",
      "val": 7.6,
      "popover": "DAR 7.6: High-density loading validated in Trodelvy and SKB264 when paired with PEGylated linkers.",
      "popover_ko": "DAR 7.6: 트로델비 및 사시투주맙 티루모테칸에 적용된 고밀도 접합비로 PEG 친수성 링커와 결합해 높은 종양 내 농도를 형성합니다."
    },
    {
      "id": "8",
      "val": 8.0,
      "popover": "DAR 8: Full interchain cysteine loading (Enhertu). Maximizes efficacy with hydrophilic Topo I linkers, but accelerates hepatic aggregation with lipophilic payloads.",
      "popover_ko": "DAR 8: 사슬 간 시스테인 8곳 전체에 결합하는 최대 밀도 설계(엔허투)로 친수성 Topo I 조합에서 최고 효능을 내나 소수성 약물에서는 간 응집을 유발합니다."
    }
  ];

  let STUDIO_FC_ITEMS = [
    {
      "id": "igg1_wt",
      "ko": "야생형 IgG1",
      "en": "Wild-type IgG1",
      "isotype": "IgG1",
      "isSilenced": false,
      "fcActivity": 1.0,
      "adcc": 1.015,
      "popover": "Wild-Type IgG1: Retains FcgammaRIIIa binding on NK cells and macrophages for ADCC effector support, but permits FcgammaR-mediated uptake in lung, liver, and marrow.",
      "popover_ko": "야생형 IgG1: NK세포 및 대식세포 Fc감마 수용체 결합으로 항체 의존성 세포독성(ADCC)을 지원하나 폐포 대식세포, 간, 골수로의 비특이 흡수가 동반될 수 있습니다."
    },
    {
      "id": "igg1_lalapg",
      "ko": "Fc 침묵화 (LALA-PG)",
      "en": "Fc-Silenced (LALA-PG)",
      "isotype": "IgG1",
      "isSilenced": true,
      "fcActivity": 0.08,
      "adcc": 0.985,
      "popover": "Fc-Silenced IgG1 (L234A/L235A/P329G): Ablates FcgammaR and C1q complement binding while preserving FcRn half-life recycling, blocking macrophage uptake in lung, liver, and eye.",
      "popover_ko": "Fc 침묵화 (LALA-PG): FcRn 반감기 재순환은 유지하면서 대식세포 Fc감마 수용체 및 보체 결합만 제거해 폐, 간, 안구로의 비특이 흡수를 차단합니다."
    },
    {
      "id": "igg4_s228p",
      "ko": "IgG4 S228P (저효능기)",
      "en": "IgG4 S228P (Low Effector)",
      "isotype": "IgG4",
      "isSilenced": false,
      "fcActivity": 0.4,
      "adcc": 0.995,
      "popover": "Hinge-stabilized IgG4 S228P backbone (used clinically in Mylotarg and Besponsa): markedly lower FcgammaRIIIa & complement activation than WT IgG1 without synthetic CH2 triple mutation.",
      "popover_ko": "힌지 안정화 IgG4 S228P 골격(마일로탁, 베스폰사 채택): 야생형 IgG1 대비 Fc감마 수용체 및 보체 활성이 현저히 낮아 면역원성 부담 없이 비특이 흡수를 줄입니다."
    },
    {
      "id": "igg2_lowfc",
      "ko": "IgG2 (비결합 힌지)",
      "en": "IgG2 (Minimal FcgammaR)",
      "isotype": "IgG2",
      "isSilenced": false,
      "fcActivity": 0.35,
      "adcc": 0.992,
      "popover": "Human IgG2 backbone (PVAGP lower hinge): naturally minimal FcgammaRI/IIIa affinity (~0.35x WT) with rigid disulfide hinge geometry that shields conjugation sites.",
      "popover_ko": "인간 IgG2 골격: 선천적으로 낮은 Fc감마 수용체 결합력(야생형 IgG1의 약 35%)과 견고한 이황화 힌지 구조로 접합 부위를 입체적으로 보호합니다."
    }
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
    crcl: 'CLcr (크레아티닌 청소율)',
    esrd: '투석 / 말기신부전 여부 (Dialysis/ESRD)',
    egfr: '사구체여과율 (eGFR)',
    creatinine: '혈청 크레아티닌 (Creatinine)',
    age: '나이',
    sex: '성별',
    weight: '체중',
    bilirubin: '총 빌리루빈 (Bilirubin)',
    ast: 'AST (간효소)',
    alt: 'ALT (간효소)',
    child_pugh: 'Child-Pugh 간기능 등급',
    platelet: '혈소판 수치 (Platelets)',
    platelets: '혈소판 수치 (Platelets)',
    anc: '호중구 절대수치 (ANC)',
    hb: '혈색소 (Hb)',
    lvef: '좌심실 구혈률 (LVEF)',
    hba1c: '당화혈색소 (HbA1c)',
    ugt1a1: 'UGT1A1*28 동형접합 변이',
  };

  const MISSING_KO = {
    'CLcr (Creatinine + age, sex, weight, or eGFR)': 'CLcr (크레아티닌 청소율 — 직접 입력, eGFR, 또는 크레아티닌+나이/성별/체중)',
    'CLcr / dialysis status': 'CLcr (크레아티닌 청소율) / 투석 여부 (Dialysis/ESRD)',
    'Dialysis/ESRD': '투석 / 말기신부전 여부 (Dialysis/ESRD)',
    'Bilirubin': '총 빌리루빈 (Bilirubin)',
    'Bilirubin / AST / ALT / Child-Pugh': '총 빌리루빈 / AST / ALT / Child-Pugh 간기능 등급',
    'AST': 'AST (간효소)',
    'ALT': 'ALT (간효소)',
    'Child-Pugh': 'Child-Pugh 간기능 등급',
    'LVEF': '좌심실 구혈률 (LVEF)',
    'Platelets': '혈소판 수치 (Platelets)',
    'Platelets / ANC': '혈소판 수치 (Platelets) / 호중구 절대수치 (ANC)',
    'ANC': '호중구 절대수치 (ANC)',
    'HbA1c': '당화혈색소 (HbA1c)',
    'UGT1A1*28': 'UGT1A1*28 동형접합 변이',
  };

  const TXT = {
    ko: {
      modes: ['환자 정보', 'ADC 매트릭스', 'ADC 신규 설계'],
      brandTag: 'ADCTOX',
      newPatient: '새 환자 입력',
      newPatientTitle: '입력된 질환과 수치를 초기화하고 1번 환자 정보 탭으로 이동합니다',
      addCondPh: '암종 또는 기저질환 입력 (예: 유방암, 간질성 폐질환, 간경변, 당뇨병)...',
      condHelp: '질환명, 증상, 암종을 한글 또는 영문으로 자유롭게 입력하세요.',
      activeOrgans: '활성 취약 장기',
      noActiveOrgans: '활성 취약 장기 없음',
      footerText: 'ADCTOX',
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
      tgtTitle: '1. 표적 항원 (36)',
      lnkTitle: '2. 화학 링커 (16)',
      pldTitle: '3. 세포독성 페이로드 (20)',
      darTitle: '4. 약물-항체 접합비 DAR (8)',
      fcTitle: '5. 항체 골격 및 Fc 엔지니어링 (4)',
      wtFc: '야생형 IgG1',
      silFc: 'Fc 침묵화 (LALA-PG)',
      deepTitle: 'Deep Research',
      deepSub: 'ADCSurrogateNet v2 5-Fold 실시간 구동',
      deepRunBtn: 'Deep Research 설계',
      deepBusyBtn: 'GPU 대기 중 (4/4)',
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
      explainTitle: '신경망 점수 산출 원리 (ADC-SurrogateNet)',
      explainBody: [
        '안전도 (X, 0~100) = 100 - (최대 취약장기 위험 가중합 + 평균 취약장기 위험 가중합) * 100',
        '장기 위험도 p(o) = 1 - exp(-V_o * [OffTarget(H_leak + H_agg + H_Fc) + OnTarget(H_on)]) (ADCNet + ChEMBL v34 + 임상 13장기 AE + GTEx v8 / Tabula Sapiens 5-Fold 앙상블)',
        '항암 효능 (Y, 0~100) = 100 * 적응증일치도 * 화학접합호환도 * (w_sel*S_sel + w_pot*S_pot + w_deliv*S_deliv + w_bys*S_bys) (ESM-2 650M + ChemBERTa-2 LoRA + 3D Boltzmann Conformer)',
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
      basicTitle: '검진 정보',
      basicReqTag: '필수 입력',
      basicExpand: '필수 항목 입력 ▾',
      basicCollapse: '필수 항목 접기 ▴',
      flowTitle: '검진 정보',
      flowOptTag: '선택 입력',
      flowSub: '직접 측정한 신장 청소율, 간 기능 등급, 심장 구혈률 및 약물유전형 지표',
      flowExpand: '선택 항목 입력 ▾',
      flowCollapse: '선택 항목 접기 ▴',
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
      tabStudy: '기존 임상시험 사례',
      tabStructure: '분자 구조',
      labelRestriction: '약물 사용 제한 여부',
      noLabelRestriction: '입력된 환자의 수치를 고려하였을 때, 약물 사용에 제한 사항은 없습니다.',
      patientWarnTitle: '취약 장기 영향 가능성',
      noPatientWarn: '환자의 취약 장기를 고려하였을 때, 약물 사용에 제한 사항은 없습니다.',
      preCheckTitle: '투여 전 권장 검사',
      missingInputTitle: '미입력 검진 정보',
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
      tabRefStudy: '기존 승인 약물 임상시험 사례',
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
      footerText: 'ADCTOX',
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
      tgtTitle: '1. Target Antigen (36)',
      lnkTitle: '2. Chemical Linker (16)',
      pldTitle: '3. Cytotoxic Payload (20)',
      darTitle: '4. Drug-to-Antibody Ratio (8)',
      fcTitle: '5. Antibody & Fc Format (4)',
      wtFc: 'Wild-type IgG1',
      silFc: 'Fc-Silenced (LALA-PG)',
      deepTitle: 'Deep Research',
      deepSub: 'Live 5-Fold ADCSurrogateNet v2',
      deepRunBtn: 'Deep Research',
      deepBusyBtn: 'GPUs Busy (4/4)',
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
      explainTitle: 'Neural Scoring Model (ADC-SurrogateNet)',
      explainBody: [
        'Safety (X, 0-100) = 100 - (w_peak * Peak Organ Risk + (1 - w_peak) * Mean Organ Risk) * 100',
        'Organ Risk p(o) = 1 - exp(-V_o * [OffTarget(H_leak + H_agg + H_Fc) + OnTarget(H_on)]) (5-Fold Ensemble trained on ADCNet, ChEMBL v34, Clinical 13-Organ AE & FDA SPL, GTEx v8 / Tabula Sapiens)',
        'Efficacy (Y, 0-100) = 100 * Indication * Compatibility * (w_sel*S_sel + w_pot*S_pot + w_deliv*S_deliv + w_bys*S_bys) (ESM-2 650M + ChemBERTa-2 LoRA + 3D Boltzmann Conformer)',
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
      basicTitle: 'Lab & Clinical Info',
      basicReqTag: 'Required',
      basicExpand: 'Enter Required Labs ▾',
      basicCollapse: 'Hide Required Labs ▴',
      flowTitle: 'Lab & Clinical Info',
      flowOptTag: 'Optional',
      flowSub: 'Direct clearance, Child-Pugh grade, cardiac LVEF, and pharmacogenomic markers',
      flowExpand: 'Enter Optional Labs ▾',
      flowCollapse: 'Hide Optional Labs ▴',
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
      tabStudy: 'Prior Trial Cases',
      tabStructure: 'Molecular Structure',
      labelRestriction: 'Restrictions on using this drug',
      noLabelRestriction: 'Given the entered patient values, there are no restrictions on using this drug.',
      patientWarnTitle: 'Possible effects on vulnerable organs',
      noPatientWarn: "Given the patient's vulnerable organs, there are no restrictions on using this drug.",
      preCheckTitle: 'Pre-treatment checks',
      missingInputTitle: 'Missing Lab & Clinical Info',
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
      tabRefStudy: 'Approved Drug Trial Cases',
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

  // ------------------------------------------------------------------ Session State & Neural Surrogate Binding
  const KEY = 'adctox.web.v083';
  const LEGACY_KEY = 'adctox.web.v081';
  const SURROGATE_NET = (typeof globalThis !== 'undefined' && globalThis.ADCTOX_SURROGATE)
    ? globalThis.ADCTOX_SURROGATE
    : ((typeof window !== 'undefined' && window.ADCTOX_SURROGATE) ? window.ADCTOX_SURROGATE : null);
  const SURROGATE_ORGANS = (SURROGATE_NET && Array.isArray(SURROGATE_NET.organs) && SURROGATE_NET.organs.length === 13)
    ? SURROGATE_NET.organs
    : ['haematologic', 'hepatic', 'cardiovascular', 'pulmonary', 'renal', 'gastrointestinal', 'neurologic', 'ocular', 'dermatologic', 'metabolic_endocrine', 'musculoskeletal', 'infectious_immune', 'otologic'];
  const SURROGATE_ORGAN_IDX = {};
  SURROGATE_ORGANS.forEach((ax, idx) => { SURROGATE_ORGAN_IDX[ax] = idx; });

  const BASE_SURROGATE_WEIGHTS = Object.assign({
    wSafety: 0.56,
    wPeak: 0.58,
    wExpr: 0.36,
    leakSens: 1.00,
    hydroSens: 1.00,
    fcProtect: 0.34,
    wSelect: 0.27,
    wBystander: 0.27,
  }, (SURROGATE_NET && SURROGATE_NET.weights) || {});
  const DEFAULT_SIM_WEIGHTS = Object.assign({}, BASE_SURROGATE_WEIGHTS);
  const SIM_WEIGHT_PRESETS = [
    {
      id: 'balanced',
      ko: '균형',
      en: 'Balanced',
      weights: Object.assign({}, DEFAULT_SIM_WEIGHTS),
    },
    {
      id: 'organ_sparing',
      ko: '장기 보호 우선',
      en: 'Organ Protection Priority',
      weights: { wSafety: 0.78, wPeak: 0.80, wExpr: 0.52, leakSens: 1.45, hydroSens: 1.55, fcProtect: 0.52, wSelect: 0.38, wBystander: 0.14 },
    },
    {
      id: 'efficacy_first',
      ko: '항암 효과 우선',
      en: 'Antitumor Efficacy Priority',
      weights: { wSafety: 0.36, wPeak: 0.42, wExpr: 0.28, leakSens: 0.75, hydroSens: 0.80, fcProtect: 0.28, wSelect: 0.36, wBystander: 0.52 },
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
      basicLabsOpen: false,
      labsOpen: false,
      meanings: {},
      first: null,
      prioOrgan: null,
      studioDesignMode: 'idle',
      studioNeedInputWarn: false,
      studioHistory: [],
      deepResearchOn: false,
      deepMenuOpen: false,
      customPayloadSmiles: '',
      tgtCat: 'rec',
      tgtQuery: '',
      lnkCat: 'all',
      pldCat: 'all',
      lastRunMode: 'matrix_368k',
      simWeights: Object.assign({}, DEFAULT_SIM_WEIGHTS),
      simPreset: 'balanced',
      formulaOpen: false,
      analysis: null,
      result: null,
      sel: 0,
      reviewAdc: null,
      drawer: false,
      drawerTab: 'Patient',
      studio: { target: 'HER2 (ERBB2)', linker: 'Tetrapeptide GGFG', payload: 'DXd ( Topo I )', dar: 4, fc: false, fcFormat: 'igg1_wt' },
    };
  }
  let S = defaultState();
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* ignore */ }
  }
  function restore() {
    try {
      const rawJson = sessionStorage.getItem(KEY) || sessionStorage.getItem(LEGACY_KEY) || 'null';
      const d = JSON.parse(rawJson);
      if (d && typeof d === 'object' && Array.isArray(d.conds)) {
        S = Object.assign(defaultState(), d);
        S.studio = Object.assign(defaultState().studio, d.studio || {});
        if (!S.studio.fcFormat) S.studio.fcFormat = S.studio.fc ? 'igg1_lalapg' : 'igg1_wt';
        S.studio.fc = S.studio.fcFormat !== 'igg1_wt';
        S.deepMenuOpen = false;
        S.simWeights = Object.assign({}, DEFAULT_SIM_WEIGHTS, d.simWeights || {});
        if (S.simPreset !== 'custom' && !SIM_WEIGHT_PRESETS.some((p) => p.id === S.simPreset)) {
          S.simPreset = 'balanced';
        }
        if (S.raw && S.raw.platelets !== undefined) {
          if (S.raw.platelet === undefined) S.raw.platelet = S.raw.platelets;
          delete S.raw.platelets;
        }
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
  let crumbRefs = null;
  let resetPatientBtn = null;
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
    let relabeled = false;
    if (Array.isArray(S.conds)) {
      S.conds.forEach((c) => {
        if (c && c.ko && c.en) {
          c.label = S.lang === 'ko' ? c.ko : c.en;
          relabeled = true;
        }
      });
    }
    save();
    renderHeaderControls();
    if (relabeled) {
      refreshBackendData().then(() => {
        renderActiveMode(false);
        if (S.mode === 2 && S.drawer && drawer && drawer.classList.contains('open')) {
          fillStudioCompareDrawer(computeStudioSimulation(), evaluateAllStudioCandidates());
        }
      });
      return;
    }
    renderActiveMode(false);
    if (S.mode === 2 && S.drawer && drawer && drawer.classList.contains('open')) {
      fillStudioCompareDrawer(computeStudioSimulation(), evaluateAllStudioCandidates());
    }
  }

  function renderHeaderControls() {
    if (langBtn) langBtn.textContent = S.lang === 'ko' ? 'KO / EN' : 'EN / KO';
    if (bar && bar.firstElementChild) bar.firstElementChild.textContent = t('footerText');
    const modeNames = t('modes');
    if (!crumbRefs) {
      const items = [0, 1, 2].map((i) => {
        const labelEl = h('span', { class: 'crumb-label', text: modeNames[i] });
        const btn = h('button', {
          class: 'cb', type: 'button',
          onclick: () => switchMode(i),
        }, h('span', { class: 'step-number', 'aria-hidden': 'true', text: String(i + 1) }), labelEl);
        const wrap = h('div', { class: 'crumb' }, btn);
        return { wrap, btn, labelEl };
      });
      const clinicianGroup = h('li', { class: 'crumb-clinician-group' }, items[0].wrap, items[1].wrap);
      const researchGroup = h('li', { class: 'crumb-research-group' }, items[2].wrap);
      crumbsOl.append(clinicianGroup, researchGroup);
      crumbRefs = { items, clinicianGroup, researchGroup };
    }
    crumbRefs.items.forEach((it, i) => {
      const now = i === S.mode;
      it.labelEl.textContent = modeNames[i];
      it.wrap.classList.toggle('now', now);
      if (now) it.btn.setAttribute('aria-current', 'step');
      else it.btn.removeAttribute('aria-current');
    });
    crumbRefs.clinicianGroup.classList.toggle('is-clinician-active', S.mode === 0 || S.mode === 1);

    if (!resetPatientBtn) {
      resetPatientBtn = h('button', {
        type: 'button', class: 'reset-patient-btn',
        onclick: () => resetPatient(),
      });
      scenarioDropdown.append(resetPatientBtn);
    }
    resetPatientBtn.textContent = t('newPatient');
    resetPatientBtn.title = t('newPatientTitle');
  }

  function resetPatient() {
    closeDrawer(true);
    S.mode = 0;
    S.basicLabsOpen = false;
    S.labsOpen = false;
    S.deepMenuOpen = false;
    S.presetId = null;
    S.conds = [];
    S.raw = {};
    S.labs = null;
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
    renderActiveMode(true);
    window.scrollTo(0, 0);
    refreshBackendData().then(() => renderActiveMode(false));
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
        const isCancer = cancerConds.has(c.label) || cancerConds.has(c.value) || /carcinoma|cancer|lymphoma|myeloma|leukemia|tumor|암|종양|백혈병|림프종|골수종|육종|흑색종/i.test(c.label);
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
      if (S.raw.crcl) labBadges.push(`CLcr ${S.raw.crcl} mL/min`);
      else if (sh.crcl) labBadges.push(`CLcr ${sh.crcl} mL/min`);
      else if (S.raw.creatinine) labBadges.push(`Cr ${S.raw.creatinine} mg/dL`);
      if (S.raw.esrd === 'y' || S.raw.esrd === true) labBadges.push('Dialysis/ESRD');
      if (S.raw.bilirubin) labBadges.push(`Bili ${S.raw.bilirubin} mg/dL`);
      if (S.raw.child_pugh) labBadges.push(`Child-Pugh ${S.raw.child_pugh}`);
      if (S.raw.platelet) labBadges.push(`Plt ${S.raw.platelet}`);
      if (S.raw.anc) labBadges.push(`ANC ${S.raw.anc}`);
      if (S.raw.lvef) labBadges.push(`LVEF ${S.raw.lvef}%`);
      if (S.raw.hba1c) labBadges.push(`HbA1c ${S.raw.hba1c}%`);
      if (S.raw.ugt1a1 === 'y' || S.raw.ugt1a1 === true) labBadges.push('UGT1A1*28');

      if (labBadges.length) {
        chipsWrap.append(h('button', {
          type: 'button', class: 'p-chip lab-chip',
          title: S.lang === 'ko' ? '검진 정보 열기' : 'Open Lab & Clinical Info',
          text: labBadges.join('  /  '),
          onclick: () => {
            S.basicLabsOpen = true;
            if (S.raw.crcl || S.raw.egfr || S.raw.child_pugh || S.raw.lvef || S.raw.hba1c || S.raw.ugt1a1) S.labsOpen = true;
            save();
            switchMode(0);
          },
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
    return box;
  }

  // ------------------------------------------------------------------ Mode 1: Structure & Combination Studio
  let simAnimId = 0;
  let studioChartRO = null;
  let studioGpuPollTimer = 0;
  let studioDocClickHandler = null;

  const FC_SENSITIVE = ['pulmonary', 'haematologic', 'ocular', 'hepatic'];
  const FALLBACK_ORGANS = [
    { organ: 'pulmonary', score: 0.8 }, { organ: 'hepatic', score: 0.8 },
    { organ: 'haematologic', score: 0.8 }, { organ: 'cardiovascular', score: 0.7 },
  ];

  const REF_ADC_ARCH = {
    'trastuzumab-deruxtecan': { linker: 'Tetrapeptide GGFG', payload: 'DXd ( Topo I )', dar: 8, fc: false, fcFormat: 'igg1_wt' },
    'sacituzumab-govitecan': { linker: 'Hydrolyzable CL2A', payload: 'SN-38 ( Topo I )', dar: 7.6, fc: false, fcFormat: 'igg1_wt' },
    'mirvetuximab-soravtansine': { linker: 'Sulfo-SPDB', payload: 'DM4 / DM1 ( Maytansinoid )', dar: 3.5, fc: false, fcFormat: 'igg1_wt' },
    'tisotumab-vedotin': { linker: 'Val-Cit PABC', payload: 'MMAE ( Auristatin )', dar: 4, fc: false, fcFormat: 'igg1_wt' },
    'enfortumab-vedotin': { linker: 'Val-Cit PABC', payload: 'MMAE ( Auristatin )', dar: 4, fc: false, fcFormat: 'igg1_wt' },
    'polatuzumab-vedotin': { linker: 'Val-Cit PABC', payload: 'MMAE ( Auristatin )', dar: 3.5, fc: false, fcFormat: 'igg1_wt' },
    'brentuximab-vedotin': { linker: 'Val-Cit PABC', payload: 'MMAE ( Auristatin )', dar: 4, fc: false, fcFormat: 'igg1_wt' },
    'loncastuximab-tesirine': { linker: 'PEG8-Val-Ala PABC', payload: 'SG3199 ( PBD Dimer )', dar: 2, fc: false, fcFormat: 'igg1_wt' },
    'belantamab-mafodotin': { linker: 'Non-cleavable mc', payload: 'MMAF ( Auristatin )', dar: 4, fc: false, fcFormat: 'igg1_wt' },
    'inotuzumab-ozogamicin': { linker: 'Acid Hydrazone', payload: 'Calicheamicin ( Enediyne )', dar: 6, fc: false, fcFormat: 'igg4_s228p' },
    'gemtuzumab-ozogamicin': { linker: 'Acid Hydrazone', payload: 'Calicheamicin ( Enediyne )', dar: 3.5, fc: false, fcFormat: 'igg4_s228p' },
  };

  function getRefStudioForTarget(targetId) {
    const tgt = STUDIO_TARGETS.find((x) => x.id === targetId);
    const refId = (tgt && tgt.refAdc) || 'trastuzumab-deruxtecan';
    return REF_ADC_ARCH[refId] || REF_ADC_ARCH['trastuzumab-deruxtecan'];
  }

  function isPairCompatible(lnk, pld) {
    if (!lnk || !pld) return false;
    const lh = String(lnk.handle || '');
    const ph = String(pld.handle || '');
    if (lh === ph) return true;
    for (const tok of ['amine', 'hydroxyl', 'thiol', 'ketone']) {
      if (lh.includes(tok) && ph.includes(tok)) return true;
    }
    return false;
  }

  const plainName = (id) => String(id || '').replace(/\s*\(.*?\)\s*/g, ' ').replace(/\s+/g, ' ').trim();

  function patientCancerText() {
    const P = (S.result && S.result.data && S.result.data.patient) || {};
    return []
      .concat((P.cancers || []).map((c) => `${c.condition || ''} ${c.label || ''}`))
      .concat(S.conds.map((c) => `${c.label || ''} ${c.value || ''}`))
      .join(' ')
      .trim();
  }

  function patientCancerMatchesTarget(tgt) {
    const cancerTexts = patientCancerText().toLowerCase();
    if (!cancerTexts) return null;
    const hasAnyTumorKeyword = /cancer|carcinoma|tumor|lymphoma|myeloma|leukemia|sarcoma|glioma|melanoma|mesothelioma|암|종양|림프종|골수종|백혈병|육종|흑색종|중피종/.test(cancerTexts);
    if (!hasAnyTumorKeyword) return null;
    return (tgt.tumorKeys || []).some((k) => cancerTexts.includes(k.toLowerCase()));
  }

  function computeStudioSimulation(specInput, organsInput) {
    const activeSurrogate = SURROGATE_NET || ((typeof globalThis !== 'undefined' && globalThis.ADCTOX_SURROGATE) ? globalThis.ADCTOX_SURROGATE : ((typeof window !== 'undefined' && window.ADCTOX_SURROGATE) ? window.ADCTOX_SURROGATE : null));
    const W0 = Object.assign({}, BASE_SURROGATE_WEIGHTS, (activeSurrogate && activeSurrogate.weights) || {});
    const W = Object.assign({}, W0, S.simWeights || {});
    const rawSpec = specInput || S.studio;
    const tgt = STUDIO_TARGETS.find((x) => x.id === rawSpec.target) || STUDIO_TARGETS[0];
    const lnk = STUDIO_LINKERS.find((x) => x.id === rawSpec.linker) || STUDIO_LINKERS[0];
    const pld = STUDIO_PAYLOADS.find((x) => x.id === rawSpec.payload) || STUDIO_PAYLOADS[0];
    const dar = Number(rawSpec.dar) || 4;
    const fcFormat = rawSpec.fcFormat || (rawSpec.fc ? 'igg1_lalapg' : 'igg1_wt');
    const fcObj = STUDIO_FC_ITEMS.find((x) => x.id === fcFormat) || STUDIO_FC_ITEMS[0];
    const fcSilenced = fcFormat !== 'igg1_wt';
    const fcStrength = Math.max(0, Math.min(1, 1 - Number(fcObj && fcObj.fcActivity != null ? fcObj.fcActivity : (fcSilenced ? 0.08 : 1.0))));
    const spec = Object.assign({}, rawSpec, { target: tgt.id, linker: lnk.id, payload: pld.id, dar, fc: fcSilenced, fcFormat });

    const real = organsInput || activeOrgansWithScores();
    const baseOrgans = real.slice();
    const organSet = new Set(baseOrgans.map((o) => o.organ));
    for (const tis of (tgt.tissues || [])) {
      if (!organSet.has(tis.organ)) {
        baseOrgans.push({ organ: tis.organ, score: 0.44, condKey: null, baselineTissue: true });
        organSet.add(tis.organ);
      }
    }
    const isCompat = isPairCompatible(lnk, pld);
    const pairAffinity = isCompat ? ((lnk.prefPayloads && lnk.prefPayloads[pld.id]) || 0.84) : 0.35;
    const chemPenalty = 1 + (1 - pairAffinity) * 0.38;

    const gridKey = `${tgt.id}|${lnk.id}|${pld.id}|${dar}|${fcFormat === 'igg1_lalapg' ? 1 : 0}`;
    const node = (activeSurrogate && activeSurrogate.grid) ? activeSurrogate.grid[gridKey] : null;

    const wOnTarget = Math.max(0.10, Math.min(0.85, W.wExpr));
    const wOn0 = Math.max(0.10, Math.min(0.85, W0.wExpr));
    const onScale = wOnTarget / wOn0;
    const offScale = (1 - wOnTarget) / Math.max(0.15, 1 - wOn0);
    const leakScale = W.leakSens / Math.max(0.15, W0.leakSens);
    const aggScale = W.hydroSens / Math.max(0.15, W0.hydroSens);
    const fcSliderRatio = Math.max(0.12, (1 - W.fcProtect) / Math.max(0.15, 1 - W0.fcProtect));
    const fcSliderScale = 1.0 + fcStrength * (fcSliderRatio - 1.0);

    const organRiskMap = {};
    let allOrganRisks;
    let pIC50Pos;
    let pIC50Bys;
    let plasmaStabPct;
    let hicAgg;
    let clHep;
    let sSelect;
    let sPotency;
    let sDeliv;
    let sBystander;

    if (node && Array.isArray(node.m)) {
      pIC50Pos = Number(node.m[0]);
      pIC50Bys = Number(node.m[1]);
      plasmaStabPct = Math.max(20, Math.min(98, Math.round(Number(node.m[2]))));
      hicAgg = Number(node.m[3]);
      clHep = Number(node.m[4]);

      SURROGATE_ORGANS.forEach((ax, idx) => {
        const hb0 = (node.hb[idx] || 0) * 0.001 * leakScale;
        const ha0 = (node.ha[idx] || 0) * 0.001 * aggScale;
        const hf0 = (node.hf[idx] || 0) * 0.001 * fcSliderScale;
        const ho0 = (node.ho[idx] || 0) * 0.001;
        const hBaseOrg = (offScale * (hb0 + ha0 + hf0) + onScale * ho0) * chemPenalty;
        organRiskMap[ax] = Math.round(100 * (1 - Math.exp(-Math.max(0.005, hBaseOrg))));
      });

      allOrganRisks = baseOrgans.map((ao) => {
        const oIdx = SURROGATE_ORGAN_IDX[ao.organ] != null ? SURROGATE_ORGAN_IDX[ao.organ] : 0;
        const prioMult = (S.prioOrgan && S.prioOrgan === ao.organ) ? 1.45 : 1.0;
        const vulnWeight = (ao.baselineTissue ? 0.62 : (0.85 + 0.85 * Math.min(1, ao.score || 0.8))) * prioMult;
        const hb = (node.hb[oIdx] || 0) * 0.001 * leakScale;
        const ha = (node.ha[oIdx] || 0) * 0.001 * aggScale;
        const hf = (node.hf[oIdx] || 0) * 0.001 * fcSliderScale;
        const ho = (node.ho[oIdx] || 0) * 0.001;
        const combinedHazard = (offScale * (hb + ha + hf) + onScale * ho) * chemPenalty * vulnWeight;
        return {
          organ: ao.organ,
          p: Math.max(0.01, Math.min(0.98, 1 - Math.exp(-combinedHazard))),
          baselineTissue: Boolean(ao.baselineTissue),
        };
      });

      const hydroDelta = (W.hydroSens - W0.hydroSens) * Math.max(0, hicAgg - 1.15) * 0.12;
      const leakDelta = (W.leakSens - W0.leakSens) * (1 - plasmaStabPct / 100) * 0.24;
      sSelect = Math.max(0.12, Math.min(0.98, Number(node.m[5])));
      sPotency = Math.max(0.08, Math.min(0.99, Number(node.m[6]) * Math.exp(-hydroDelta)));
      sDeliv = Math.max(0.08, Math.min(0.98, Number(node.m[7]) * Math.exp(-leakDelta)));
      sBystander = Math.max(0.06, Math.min(0.98, Number(node.m[8])));
    } else {
      plasmaStabPct = Math.max(25, Math.min(98, Math.round(lnk.stability - (dar > 4 ? (dar - 4) * 2.5 : 0))));
      pIC50Pos = 6.2 + (pld.potency / 35) + Math.log2(Math.max(1, dar)) * 0.18;
      pIC50Bys = pld.perm && lnk.cleavable ? pIC50Pos - 0.6 : pIC50Pos - 1.8;
      hicAgg = 1.0 + 0.18 * dar * (pld.hydro || 0.5);
      clHep = 1.0 + 0.45 * (hicAgg - 1.0);
      const pldOrgs = pld.organs || {};
      SURROGATE_ORGANS.forEach((ax) => {
        organRiskMap[ax] = pldOrgs[ax] != null ? pldOrgs[ax] : 22;
      });
      allOrganRisks = baseOrgans.map((ao) => {
        const payloadTox = (pldOrgs[ao.organ] != null ? pldOrgs[ao.organ] : 20) / 100;
        const expr = (((tgt.tissues || []).find((x) => x.organ === ao.organ) || { tpm: 6 }).tpm) / 100;
        const fcMult = fcStrength > 0 && FC_SENSITIVE.includes(ao.organ) ? Math.max(0.25, 1 - fcStrength * W.fcProtect) : 1.0;
        const prioMult = (S.prioOrgan && S.prioOrgan === ao.organ) ? 1.45 : 1.0;
        const darOver = dar > (pld.maxSafeDar || 6) ? (1 + 0.14 * (dar - (pld.maxSafeDar || 6))) : 1.0;
        const vulnWeight = (ao.baselineTissue ? 0.46 : (0.58 + 0.42 * Math.min(1, ao.score || 0.8))) * prioMult;
        const hFallback = ((1 - wOnTarget) * payloadTox * fcMult * darOver + wOnTarget * 1.4 * expr) * chemPenalty * vulnWeight;
        return { organ: ao.organ, p: 1 - Math.exp(-0.56 * hFallback), baselineTissue: Boolean(ao.baselineTissue) };
      });
      sSelect = Math.max(0.18, Math.min(0.98, (tgt.selectivity - 2.4) / 3.6));
      sPotency = Math.max(0.15, Math.min(0.99, Math.pow(pld.potency / 100, 1.35) * (0.82 + 0.04 * Math.min(8, dar))));
      sDeliv = Math.max(0.15, Math.min(0.98, plasmaStabPct / 100));
      sBystander = (lnk.cleavable && pld.perm) ? 0.88 : 0.25;
    }

    const organRisks = real.length ? allOrganRisks.filter((r) => !r.baselineTissue) : allOrganRisks;
    const meanRisk = allOrganRisks.length ? allOrganRisks.reduce((a, r) => a + r.p, 0) / allOrganRisks.length : 0;
    const worstRisk = allOrganRisks.length ? Math.max(...allOrganRisks.map((r) => r.p)) : 0;
    const wPeak = Math.max(0.15, Math.min(0.90, W.wPeak));
    const safetyRaw = Math.max(2, Math.min(98, 100 * (1 - (wPeak * worstRisk + (1 - wPeak) * meanRisk))));
    const safetyScore = Math.round(safetyRaw);

    const bystander = lnk.cleavable && pld.perm;
    const indMatch = patientCancerMatchesTarget(tgt);
    const indFactor = indMatch === null ? 1.0 : (indMatch ? 1.06 : 0.68);

    const rawWSelect = Math.max(0.05, W.wSelect);
    const rawWBys = Math.max(0.05, W.wBystander);
    const rawWCore = Math.max(0.20, 1.0 - 0.55 * (rawWSelect + rawWBys));
    const wSum = rawWSelect + rawWBys + rawWCore;
    const nwSel = rawWSelect / wSum;
    const nwBys = rawWBys / wSum;
    const nwPot = (rawWCore * 0.56) / wSum;
    const nwDel = (rawWCore * 0.44) / wSum;

    const adccBoost = Number(fcObj && fcObj.adcc != null ? fcObj.adcc : (fcSilenced ? 0.985 : 1.015));
    const convexEff = (nwSel * sSelect + nwPot * sPotency + nwDel * sDeliv + nwBys * sBystander) * adccBoost;
    const eff = convexEff * Math.pow(pairAffinity, 0.34) * indFactor * (isCompat ? 1.0 : 0.48);
    const efficacyRaw = Math.max(2, Math.min(98, eff * 100));
    const efficacyScore = Math.round(efficacyRaw);

    return {
      spec, tgt, lnk, pld, dar, fcSilenced, fcFormat,
      safetyScore, efficacyScore, safetyRaw, efficacyRaw,
      isCompat, organRisks, organRiskMap, meanRisk, bystander,
      nwSel, nwPot, nwDel, nwBys,
      plasmaStabPct, pIC50Pos, pIC50Bys, hicAgg, clHep,
    };
  }

  function evaluateLocalFallbackSpace() {
    // Offline/mock fallback when running from file://?mock=1 without Python server
    const W = Object.assign({}, DEFAULT_SIM_WEIGHTS, S.simWeights || {});
    const real = activeOrgansWithScores();
    const cands = [];
    const curTgt = STUDIO_TARGETS.find((x) => x.id === S.studio.target) || STUDIO_TARGETS[0];
    const tgtSample = STUDIO_TARGETS.slice(0, 6);
    if (!tgtSample.some((t) => t.id === curTgt.id)) tgtSample.push(curTgt);
    const lnkSample = STUDIO_LINKERS.slice(0, 6);
    const pldSample = STUDIO_PAYLOADS.slice(0, 6);
    const dars = [2, 3.5, 4, 6, 7.6, 8];
    tgtSample.forEach((tObj) => {
      lnkSample.forEach((lObj) => {
        pldSample.forEach((pObj) => {
          dars.forEach((d) => {
            ['igg1_wt', 'igg1_lalapg'].forEach((fcFmt) => {
              cands.push(computeStudioSimulation({
                target: tObj.id, linker: lObj.id, payload: pObj.id,
                dar: d, fc: fcFmt !== 'igg1_wt', fcFormat: fcFmt,
              }, real));
            });
          });
        });
      });
    });

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
    return {
      isServer: false,
      mode: 'local_fallback',
      totalCombinations: STUDIO_TARGETS.length * STUDIO_LINKERS.length * STUDIO_PAYLOADS.length * STUDIO_DAR_ITEMS.length * STUDIO_FC_ITEMS.length,
      cands,
      best: best || cands[0],
      current: computeStudioSimulation(S.studio, real),
      wSafety,
    };
  }

  function hydrateServerDetail(det) {
    if (!det || !det.spec) return computeStudioSimulation();
    const spec = det.spec;
    const tgt = STUDIO_TARGETS.find((x) => x.id === spec.target) || STUDIO_TARGETS[0];
    const lnk = STUDIO_LINKERS.find((x) => x.id === spec.linker) || STUDIO_LINKERS[0];
    const basePld = STUDIO_PAYLOADS.find((x) => x.id === spec.payload) || STUDIO_PAYLOADS[0];
    const pld = spec.customPayloadLabel
      ? Object.assign({}, basePld, { id: spec.customPayloadLabel, cls: 'Custom SMILES Payload' })
      : basePld;
    const dar = Number(spec.dar) || 4;
    const fcFormat = spec.fcFormat || det.fcFormat || (spec.fc ? 'igg1_lalapg' : 'igg1_wt');
    const fcSilenced = fcFormat !== 'igg1_wt';
    return Object.assign({}, det, {
      spec: Object.assign({}, spec, { dar, fc: fcSilenced, fcFormat }),
      tgt,
      lnk,
      pld,
      dar,
      fcSilenced,
      fcFormat,
    });
  }

  function adaptServerSpace(res) {
    const current = hydrateServerDetail(res.current);
    const best = hydrateServerDetail(res.best);
    const refCurrent = res.ref_current ? hydrateServerDetail(res.ref_current) : null;
    const refBest = res.ref_best ? hydrateServerDetail(res.ref_best) : null;
    const cloud = (res.cloud || []).map((pt) => ({
      safetyRaw: pt[0],
      efficacyRaw: pt[1],
      isCompat: Boolean(pt[2] & 1),
      isBestTarget: Boolean(pt[2] & 2),
      isCurTarget: Boolean(pt[2] & 4),
    }));
    const sameTargetCloud = (res.same_target_cloud || []).map((pt) => ({
      safetyRaw: pt[0],
      efficacyRaw: pt[1],
    }));
    return {
      isServer: true,
      mode: res.mode || 'matrix_368k',
      totalCombinations: Number(res.total_combinations) || 368640,
      compatibleCombinations: Number(res.compatible_combinations) || 0,
      wSafety: Number(res.w_safety != null ? res.w_safety : S.simWeights.wSafety),
      elapsedMs: Number(res.elapsed_ms) || 0,
      current,
      best,
      refCurrent,
      refBest,
      paretoFront: res.pareto_front || [],
      topCandidates: res.top_candidates || [],
      cloud,
      sameTargetCloud,
      deepResearch: res.deep_research || null,
    };
  }

  function buildAutoOptimizeRationales(bestSim) {
    const s = bestSim.spec;
    const isKo = S.lang === 'ko';
    const activeOrgs = activeOrgansWithScores().map((o) => (isKo && ORGAN_KO[o.organ] ? ORGAN_KO[o.organ] : SHORT[o.organ] || o.organ));
    const tgtName = plainName(s.target);
    const plName = s.customPayloadLabel || plainName(s.payload);
    const stabVal = bestSim.plasmaStabPct != null ? bestSim.plasmaStabPct : bestSim.lnk.stability;
    const picVal = bestSim.pIC50Pos != null ? bestSim.pIC50Pos.toFixed(2) : null;
    const fcLbl = fcFormatLabel(s.fcFormat, s.fc, isKo);
    const doseNoteKo = bestSim.optimalDoseMgKg ? ` (${bestSim.optimalDoseMgKg} mg/kg)` : '';
    const doseNoteEn = bestSim.optimalDoseMgKg ? ` (${bestSim.optimalDoseMgKg} mg/kg)` : '';
    if (isKo) {
      return [
        ['1. 표적 항원', `${tgtName}, 선택도 +${bestSim.tgt.selectivity.toFixed(1)} log2FC`, 'GTEx/Tabula Sapiens 정상 조직 발현 대비 종양 과발현 마진이 높아 온타깃 정상 장기 손상을 억제합니다.'],
        ['2. 화학 링커', `${s.linker}, 신경망 혈장 보존율 ${stabVal}%`, `${activeOrgs.join(', ') || '주요 장기'}로 유리 페이로드가 조기 방출되는 경로를 낮추고 종양 내 절단 효율을 확보합니다.`],
        ['3. 세포독성 페이로드', `${plName}, ${bestSim.pld.cls}${picVal ? ` (pIC50 ${picVal})` : ''}`, '환자 취약 장기 독성 경로 위험도가 낮으면서 접합체 세포독성 효력을 유지합니다.'],
        ['4. 접합비와 항체 골격', `DAR ${s.dar}, ${fcLbl}${doseNoteKo}`, `예상 장기 안전도 ${bestSim.safetyScore}점, 항암 효능 ${bestSim.efficacyScore}점으로 치료지수 균형이 최적입니다.`],
      ];
    }
    return [
      ['1. Target antigen', `${tgtName}, selectivity +${bestSim.tgt.selectivity.toFixed(1)} log2FC`, 'High tumor-to-normal expression margin across GTEx and Tabula Sapiens spares healthy tissue.'],
      ['2. Chemical linker', `${s.linker}, neural plasma retention ${stabVal}%`, `Reduces systemic free-payload leakage into ${activeOrgs.join(', ') || 'major organs'} while preserving intratumoral release.`],
      ['3. Cytotoxic payload', `${plName}, ${bestSim.pld.cls}${picVal ? ` (pIC50 ${picVal})` : ''}`, 'Lowers predicted hazard on this patient\'s vulnerable organs while maintaining conjugate potency.'],
      ['4. DAR and Fc format', `DAR ${s.dar}, ${fcLbl}${doseNoteEn}`, `Neural ensemble organ safety ${bestSim.safetyScore} and antitumor efficacy ${bestSim.efficacyScore}: optimal therapeutic index.`],
    ];
  }

  function svgChevronDown() {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 12 12');
    svg.setAttribute('width', '11');
    svg.setAttribute('height', '11');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', 'M2.5 4.5L6 8L9.5 4.5');
    path.setAttribute('stroke', 'currentColor');
    path.setAttribute('stroke-width', '1.8');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(path);
    return svg;
  }

  function buildStructureStudioMode() {
    const box = h('div', { class: 's-studio' });
    box.append(buildWorkspaceBar(() => triggerServerEvaluate(false)));
    const wrap = h('div', { class: 'studio-wrap' });
    const controls = h('aside', { class: 'studio-controls panel', 'aria-label': 'Conjugate Architecture Controls' });
    const canvas = h('div', { class: 'studio-canvas' });
    wrap.append(controls, canvas);
    box.append(wrap);

    let isOptimizing = false;
    let optBtn = null;
    let serverSpace = null;
    let gpuStatus = {
      max_slots: 4,
      active_count: 0,
      free_count: 4,
      available: true,
      next_slot: 0,
      backend: 'cuda',
      slots: [0, 1, 2, 3].map((i) => ({ slot: i, busy: false, label: `GPU ${i}` })),
    };
    let gpuStatusMsg = '';
    let evalReqSeq = 0;
    let sliderDebounceTimer = 0;

    if (studioGpuPollTimer) {
      clearInterval(studioGpuPollTimer);
      studioGpuPollTimer = 0;
    }
    if (studioDocClickHandler) {
      document.removeEventListener('pointerdown', studioDocClickHandler);
      studioDocClickHandler = null;
    }

    studioDocClickHandler = (ev) => {
      if (!box.isConnected) {
        document.removeEventListener('pointerdown', studioDocClickHandler);
        studioDocClickHandler = null;
        return;
      }
      if (S.deepMenuOpen) {
        const popWrap = controls.querySelector('.split-optimize-wrap');
        if (popWrap && !popWrap.contains(ev.target)) {
          S.deepMenuOpen = false;
          renderControls();
        }
      }
    };
    document.addEventListener('pointerdown', studioDocClickHandler);

    async function pollGpuStatus(silent) {
      if (!API.studioGpuStatus) return gpuStatus;
      try {
        const st = await API.studioGpuStatus();
        if (!st || typeof st !== 'object') return gpuStatus;
        const prevAvail = Boolean(gpuStatus && gpuStatus.available);
        const prevActive = Number(gpuStatus && gpuStatus.active_count);
        gpuStatus = st;
        if (st.available && gpuStatusMsg) gpuStatusMsg = '';
        if (!silent || prevAvail !== Boolean(st.available) || prevActive !== Number(st.active_count) || S.deepMenuOpen) {
          if (box.isConnected) renderControls();
        }
      } catch (e) { /* ignore transient poll failure */ }
      return gpuStatus;
    }

    studioGpuPollTimer = setInterval(() => {
      if (!box.isConnected) {
        clearInterval(studioGpuPollTimer);
        studioGpuPollTimer = 0;
        return;
      }
      pollGpuStatus(true);
    }, 2000);
    pollGpuStatus(true);

    function buildEvalRequestBody() {
      const fcFmt = S.studio.fcFormat || (S.studio.fc ? 'igg1_lalapg' : 'igg1_wt');
      return {
        spec: {
          target: S.studio.target,
          linker: S.studio.linker,
          payload: S.studio.payload,
          dar: Number(S.studio.dar) || 4,
          fc: fcFmt !== 'igg1_wt',
          fcFormat: fcFmt,
        },
        organs: activeOrgansWithScores().map((o) => ({ organ: o.organ, score: o.score })),
        prioOrgan: S.prioOrgan || null,
        cancerText: patientCancerText(),
        simWeights: Object.assign({}, DEFAULT_SIM_WEIGHTS, S.simWeights || {}),
        customPayloadSmiles: S.deepResearchOn ? String(S.customPayloadSmiles || '').trim() : '',
      };
    }

    async function triggerServerEvaluate(openCompareAfter) {
      const seq = ++evalReqSeq;
      if (!API.studioEvaluate) {
        serverSpace = evaluateLocalFallbackSpace();
        if (box.isConnected) renderStudioCanvas(false);
        if (openCompareAfter && S.studioDesignMode !== 'idle' && hasPatientProfile()) {
          openStudioCompareDrawer(serverSpace.current, serverSpace);
        }
        return serverSpace;
      }
      try {
        const res = await API.studioEvaluate(buildEvalRequestBody());
        if (seq !== evalReqSeq || !box.isConnected) return serverSpace;
        serverSpace = adaptServerSpace(res);
        renderStudioCanvas(false);
        if (openCompareAfter && S.studioDesignMode !== 'idle' && hasPatientProfile()) {
          openStudioCompareDrawer(serverSpace.current, serverSpace);
        }
        return serverSpace;
      } catch (e) {
        serverSpace = evaluateLocalFallbackSpace();
        if (box.isConnected) renderStudioCanvas(false);
        return serverSpace;
      }
    }

    // Smooth non-uniform scan pace
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

    function filteredTargets() {
      const q = String(S.tgtQuery || '').trim().toLowerCase();
      if (q) {
        const hits = STUDIO_TARGETS.filter((it) => (
          it.id.toLowerCase().includes(q) ||
          String(it.gene || '').toLowerCase().includes(q) ||
          (it.tumorKeys || []).some((k) => k.toLowerCase().includes(q))
        ));
        return hits.length ? hits : STUDIO_TARGETS;
      }
      const cat = S.tgtCat || 'rec';
      if (cat === 'all') return STUDIO_TARGETS;
      if (cat !== 'rec') {
        const list = STUDIO_TARGETS.filter((it) => it.group === cat);
        if (!list.some((it) => it.id === S.studio.target)) {
          const cur = STUDIO_TARGETS.find((it) => it.id === S.studio.target);
          if (cur) return [cur].concat(list);
        }
        return list;
      }
      // 'rec': Cancer-matched targets first + flagship clinical targets + active selection
      const matched = STUDIO_TARGETS.filter((it) => patientCancerMatchesTarget(it) === true);
      const flagshipIds = [
        'HER2 (ERBB2)', 'TROP2 (TACSTD2)', 'Nectin-4', 'CLDN18.2 (CLDN18)',
        'HER3 (ERBB3)', 'FRalpha (FOLR1)', 'B7-H3 (CD276)', 'DLL3',
        'EGFR', 'c-MET (MET)', 'CD79b', 'BCMA (TNFRSF17)',
      ];
      const out = [];
      const seen = new Set();
      const pushUnique = (item) => {
        if (item && !seen.has(item.id)) { seen.add(item.id); out.push(item); }
      };
      pushUnique(STUDIO_TARGETS.find((it) => it.id === S.studio.target));
      matched.forEach(pushUnique);
      flagshipIds.forEach((id) => pushUnique(STUDIO_TARGETS.find((it) => it.id === id)));
      return out.slice(0, 14);
    }

    function filteredLinkers() {
      const cat = S.lnkCat || 'all';
      if (cat === 'all') return STUDIO_LINKERS;
      const list = STUDIO_LINKERS.filter((it) => it.group === cat);
      const cur = STUDIO_LINKERS.find((it) => it.id === S.studio.linker);
      if (cur && !list.some((it) => it.id === cur.id)) return [cur].concat(list);
      return list;
    }

    function filteredPayloads() {
      const cat = S.pldCat || 'all';
      if (cat === 'all') return STUDIO_PAYLOADS;
      const list = STUDIO_PAYLOADS.filter((it) => it.group === cat);
      const cur = STUDIO_PAYLOADS.find((it) => it.id === S.studio.payload);
      if (cur && !list.some((it) => it.id === cur.id)) return [cur].concat(list);
      return list;
    }

    function renderControls() {
      const activeSearch = document.activeElement && controls.contains(document.activeElement) && document.activeElement.classList.contains('studio-search-input');
      const selStart = activeSearch ? document.activeElement.selectionStart : null;
      const selEnd = activeSearch ? document.activeElement.selectionEnd : null;

      clear(controls);
      const isKo = S.lang === 'ko';
      const totalCombos = STUDIO_TARGETS.length * STUDIO_LINKERS.length * STUDIO_PAYLOADS.length * STUDIO_DAR_ITEMS.length * STUDIO_FC_ITEMS.length;

      const headAction = h('div', { class: 'studio-head-action' },
        h('span', { class: 'sec-kicker', text: t('archTitle') }),
        h('span', {
          class: 'studio-combo-badge',
          text: isKo ? `${totalCombos.toLocaleString()}개 조합` : `${totalCombos.toLocaleString()} Combos`,
        }));
      controls.append(headAction);

      const curLnkObj = STUDIO_LINKERS.find((x) => x.id === S.studio.linker) || STUDIO_LINKERS[0];
      const curPldObj = STUDIO_PAYLOADS.find((x) => x.id === S.studio.payload) || STUDIO_PAYLOADS[0];
      const curFcFormat = S.studio.fcFormat || (S.studio.fc ? 'igg1_lalapg' : 'igg1_wt');

      const onPartPicked = (mutator) => {
        hideMicroPopover();
        mutator();
        if (!hasPatientProfile()) {
          S.studioDesignMode = 'idle';
        } else {
          if (S.studioDesignMode === 'auto') S.studioDesignMode = 'manual';
          if (S.studioDesignMode === 'manual') pushManualHistory();
        }
        save();
        renderControls();
        triggerServerEvaluate(S.studioDesignMode !== 'idle' && hasPatientProfile());
      };

      const makeCatTabs = (tabs, activeId, onTab) => {
        const bar = h('div', { class: 'studio-cat-tabs', role: 'tablist' });
        tabs.forEach(([id, koLbl, enLbl]) => {
          bar.append(h('button', {
            type: 'button',
            class: 'studio-cat-tab' + (activeId === id ? ' is-active' : ''),
            onclick: () => { onTab(id); save(); renderControls(); },
            text: isKo ? koLbl : enLbl,
          }));
        });
        return bar;
      };

      const makePillsList = (items, currentVal, onPick, opts) => {
        const o = opts || {};
        const cls = 'studio-pills' + (o.grid4 ? ' grid-4' : '') + (o.scrollable ? ' is-scrollable' : '');
        const pills = h('div', { class: cls });
        items.forEach((it) => {
          const val = typeof it === 'string' ? it : it.id;
          const labelTxt = o.labelFn ? o.labelFn(it) : val;
          const popoverText = typeof it === 'object' ? (isKo ? (it.popover_ko || it.popover) : it.popover) : null;
          const extraCls = o.extraClassFn ? o.extraClassFn(it) : '';
          const b = h('button', {
            type: 'button',
            class: 'st-pill' + (extraCls ? ' ' + extraCls : ''),
            'aria-pressed': val === currentVal ? 'true' : 'false',
            text: labelTxt,
            onmouseenter: () => { if (popoverText) showMicroPopover(b, popoverText); },
            onmouseleave: () => hideMicroPopover(),
            onclick: () => onPick(val, it),
          });
          pills.append(b);
        });
        return pills;
      };

      // 1. Target Antigen (36) with category tabs + inline search
      const tgtSearch = h('input', {
        type: 'search',
        class: 'studio-search-input',
        placeholder: isKo ? '표적 또는 유전자 검색 (예: CLDN18.2, DLL3, HER3)...' : 'Search target or gene (e.g., CLDN18.2, DLL3, HER3)...',
        value: S.tgtQuery || '',
        oninput: (e) => {
          S.tgtQuery = e.target.value;
          save();
          renderControls();
        },
      });
      const tgtCatBar = makeCatTabs([
        ['rec', '주요/일치', 'Key/Match'],
        ['breast_gyn', '유방/부인', 'Breast/Gyn'],
        ['lung_gi', '폐/소화기', 'Lung/GI'],
        ['gu_solid', '비뇨/고형', 'GU/Solid'],
        ['heme', '혈액암', 'Heme'],
        ['all', '전체 36', 'All 36'],
      ], S.tgtQuery ? '' : (S.tgtCat || 'rec'), (id) => { S.tgtCat = id; S.tgtQuery = ''; });

      const tgtGroup = h('div', { class: 'studio-group' },
        h('span', { class: 'studio-label', text: t('tgtTitle') }),
        tgtCatBar,
        tgtSearch,
        makePillsList(filteredTargets(), S.studio.target, (v) => onPartPicked(() => { S.studio.target = v; }), {
          scrollable: true,
          extraClassFn: (it) => (patientCancerMatchesTarget(it) === true ? 'is-cancer-match' : ''),
        }));

      // 2. Chemical Linker (16)
      const lnkCatBar = makeCatTabs([
        ['all', '전체 16', 'All 16'],
        ['protease', '펩타이드', 'Protease'],
        ['hydrophilic', '친수성', 'Hydrophilic'],
        ['ph_redox', 'pH/환원', 'pH/Redox'],
        ['non_cleavable', '비절단', 'Non-cleav'],
      ], S.lnkCat || 'all', (id) => { S.lnkCat = id; });

      const lnkGroup = h('div', { class: 'studio-group' },
        h('span', { class: 'studio-label', text: t('lnkTitle') }),
        lnkCatBar,
        makePillsList(filteredLinkers(), S.studio.linker, (v) => onPartPicked(() => { S.studio.linker = v; }), {
          scrollable: (S.lnkCat || 'all') === 'all',
          extraClassFn: (it) => (!isPairCompatible(it, curPldObj) ? 'is-incompat' : ''),
        }));

      // 3. Cytotoxic Payload (20)
      const pldCatBar = makeCatTabs([
        ['all', '전체 20', 'All 20'],
        ['topo1', 'Topo I', 'Topo I'],
        ['tubulin', '미세소관', 'Tubulin'],
        ['dna', 'DNA', 'DNA'],
        ['targeted', '표적/면역', 'Targeted'],
      ], S.pldCat || 'all', (id) => { S.pldCat = id; });

      const pldGroup = h('div', { class: 'studio-group' },
        h('span', { class: 'studio-label', text: t('pldTitle') }),
        pldCatBar,
        makePillsList(filteredPayloads(), S.studio.payload, (v) => onPartPicked(() => { S.studio.payload = v; }), {
          scrollable: (S.pldCat || 'all') === 'all',
          extraClassFn: (it) => (!isPairCompatible(curLnkObj, it) ? 'is-incompat' : ''),
        }));

      // 4. DAR (8)
      const darGroup = h('div', { class: 'studio-group' },
        h('span', { class: 'studio-label', text: t('darTitle') }),
        makePillsList(STUDIO_DAR_ITEMS, String(S.studio.dar), (v) => onPartPicked(() => { S.studio.dar = parseFloat(v); }), {
          grid4: true,
        }));

      // 5. Antibody & Fc Format (4)
      const fcGroup = h('div', { class: 'studio-group' },
        h('span', { class: 'studio-label', text: t('fcTitle') }),
        makePillsList(STUDIO_FC_ITEMS, curFcFormat, (v) => onPartPicked(() => {
          S.studio.fcFormat = v;
          S.studio.fc = v !== 'igg1_wt';
        }), {
          labelFn: (it) => (isKo ? it.ko : it.en),
        }));

      // Manual + Split Auto-Optimize / Deep Research Action Row
      const manualBtn = h('button', {
        type: 'button',
        class: 'btn-manual-design' + (S.studioDesignMode === 'manual' ? ' is-active' : ''),
        text: t('manualOpt'),
        onclick: () => runManualSimulation(),
      });

      const slotsBusy = Boolean(gpuStatus && gpuStatus.available === false);
      const deepBlocked = Boolean(S.deepResearchOn && slotsBusy && !isOptimizing);

      const mainBtnLabel = deepBlocked
        ? t('deepBusyBtn')
        : S.deepResearchOn
          ? t('deepRunBtn')
          : t('autoOpt');

      const mainBtnClass = 'btn-optimize split-main'
        + (isOptimizing ? ' is-running' : '')
        + (S.deepResearchOn && !deepBlocked && !isOptimizing ? ' is-deep-mode' : '')
        + (!S.deepResearchOn && S.studioDesignMode === 'auto' && !isOptimizing ? ' is-optimal' : '')
        + (deepBlocked ? ' is-gpu-busy' : '');

      optBtn = h('button', {
        type: 'button',
        class: mainBtnClass,
        disabled: deepBlocked ? true : false,
        text: mainBtnLabel,
        'aria-busy': isOptimizing ? 'true' : 'false',
        onclick: () => {
          if (deepBlocked) return;
          runOptimizationSimulation(Boolean(S.deepResearchOn));
        },
      });

      const caretClass = 'btn-optimize-caret'
        + (S.deepMenuOpen ? ' is-open' : '')
        + (S.deepResearchOn && !deepBlocked ? ' is-deep-mode' : '')
        + (!S.deepResearchOn && S.studioDesignMode === 'auto' && !isOptimizing ? ' is-optimal' : '')
        + (deepBlocked ? ' is-gpu-busy' : '');

      const caretBtn = h('button', {
        type: 'button',
        class: caretClass,
        'aria-label': 'Deep Research',
        'aria-expanded': S.deepMenuOpen ? 'true' : 'false',
        title: 'Deep Research',
        onclick: (e) => {
          e.stopPropagation();
          S.deepMenuOpen = !S.deepMenuOpen;
          if (S.deepMenuOpen) pollGpuStatus(false);
          renderControls();
        },
      }, svgChevronDown());

      const splitGroup = h('div', { class: 'split-optimize-group' }, optBtn, caretBtn);
      const splitWrap = h('div', { class: 'split-optimize-wrap' }, splitGroup);

      if (S.deepMenuOpen) {
        const backendIsCuda = !gpuStatus || String(gpuStatus.backend || 'cuda').startsWith('cuda');
        const activeCnt = Number((gpuStatus && gpuStatus.active_count) || 0);
        const maxSlots = Number((gpuStatus && gpuStatus.max_slots) || 4);
        const toggleDisabled = slotsBusy && !S.deepResearchOn;

        const toggleBtn = h('button', {
          type: 'button',
          role: 'switch',
          'aria-checked': S.deepResearchOn ? 'true' : 'false',
          disabled: toggleDisabled ? true : false,
          class: 'drp-toggle-btn'
            + (S.deepResearchOn && !slotsBusy ? ' is-on' : '')
            + (slotsBusy ? ' is-gpu-busy' : ''),
          onclick: (e) => {
            e.stopPropagation();
            if (toggleDisabled) return;
            S.deepResearchOn = !S.deepResearchOn;
            save();
            renderControls();
          },
        },
        h('div', { class: 'drp-toggle-copy' },
          h('span', { class: 'drp-title', text: t('deepTitle') })),
        h('span', { class: 'drp-switch-pill' }, h('i', { class: 'drp-switch-knob' })));

        const slotMetaLabel = backendIsCuda
          ? (isKo ? `GPU 순차 할당 (0 → 3)  |  사용 ${activeCnt}/${maxSlots}` : `GPU Queue (0 → 3)  |  In Use ${activeCnt}/${maxSlots}`)
          : (isKo ? `CPU 서버 연산 모드 (0 → 3)  |  사용 ${activeCnt}/${maxSlots}` : `CPU Server Mode (0 → 3)  |  In Use ${activeCnt}/${maxSlots}`);

        const slotsGrid = h('div', { class: 'drp-slots-grid' });
        ((gpuStatus && gpuStatus.slots) || [0, 1, 2, 3].map((i) => ({ slot: i, busy: false }))).forEach((sl) => {
          const prefix = backendIsCuda ? 'GPU' : 'CPU';
          slotsGrid.append(h('div', {
            class: 'drp-slot-pill ' + (sl.busy ? 'is-busy' : 'is-free'),
            title: sl.label || `${prefix} ${sl.slot}`,
          },
          h('span', { class: 'drp-slot-id', text: `${prefix} ${sl.slot}` }),
          h('span', { class: 'drp-slot-st', text: sl.busy ? (isKo ? '사용 중' : 'Busy') : (isKo ? '대기' : 'Free') })));
        });

        const smilesRow = S.deepResearchOn
          ? h('div', { class: 'drp-smiles-box' },
              h('label', {
                class: 'drp-smiles-label',
                text: isKo ? '신규 페이로드 SMILES (선택 입력)' : 'Custom Payload SMILES (optional)',
              }),
              h('input', {
                type: 'text',
                class: 'drp-smiles-input',
                placeholder: 'CCc1c2c(nc3ccc(O)cc13)-c1cc3c(c(=O)n1C2)COC(=O)C3(O)CC',
                value: S.customPayloadSmiles || '',
                onclick: (e) => e.stopPropagation(),
                oninput: (e) => { S.customPayloadSmiles = e.target.value; save(); },
              }))
          : null;

        const popover = h('div', {
          class: 'deep-research-popover',
          onclick: (e) => e.stopPropagation(),
        },
        toggleBtn,
        smilesRow);

        splitWrap.append(popover);
      }

      const actionBtnRow = h('div', { class: 'studio-btn-row' }, manualBtn, splitWrap);

      controls.append(tgtGroup, lnkGroup, pldGroup, darGroup, fcGroup, actionBtnRow);
      if (gpuStatusMsg) {
        controls.append(h('div', { class: 'gpu-busy-notice', text: gpuStatusMsg }));
      }

      if (activeSearch) {
        const newSearch = controls.querySelector('.studio-search-input');
        if (newSearch) {
          newSearch.focus({ preventScroll: true });
          try { if (selStart !== null) newSearch.setSelectionRange(selStart, selEnd); } catch (e) { /* ignore */ }
        }
      }
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
      const key = `${curSpec.target}|${curSpec.linker}|${curSpec.payload}|${curSpec.dar}|${curSpec.fcFormat || curSpec.fc}`;
      S.studioHistory = S.studioHistory.filter((item) => `${item.target}|${item.linker}|${item.payload}|${item.dar}|${item.fcFormat || item.fc}` !== key);
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

    async function runManualSimulation() {
      if (isOptimizing) return;
      hideMicroPopover();
      S.deepMenuOpen = false;
      if (!requirePatientProfile()) return;
      S.studioDesignMode = 'manual';
      S.lastRunMode = 'matrix_368k';
      pushManualHistory();
      save();
      renderControls();
      await triggerServerEvaluate(false);
    }

    async function runOptimizationSimulation(useDeepResearch) {
      if (isOptimizing) return;
      hideMicroPopover();
      S.deepMenuOpen = false;
      if (!requirePatientProfile()) return;

      isOptimizing = true;
      gpuStatusMsg = '';
      S.studioDesignMode = 'auto';
      save();
      closeDrawer();
      renderControls();

      const isKo = S.lang === 'ko';
      if (useDeepResearch && API.studioDeepResearch) {
        // Mode 3: Real-time 5-fold ADCSurrogateNet v2 on GPU 0..3 (or CPU server fallback)
        const statusBanner = canvas.querySelector('.sim-canvas-status');
        if (statusBanner) {
          statusBanner.textContent = isKo
            ? 'Deep Research 연산 중...'
            : 'Running Deep Research...';
        }
        setTimeout(() => pollGpuStatus(false), 75);
        try {
          const res = await API.studioDeepResearch(buildEvalRequestBody());
          if (res.gpu_status) gpuStatus = res.gpu_status;
          serverSpace = adaptServerSpace(res);
          S.lastRunMode = 'deep_research_v2';
          if (!box.isConnected) { isOptimizing = false; return; }
          renderStudioCanvas(true);
        } catch (err) {
          isOptimizing = false;
          if (err && (err.status === 429 || (err.data && err.data.code === 'all_gpu_slots_busy'))) {
            if (err.data && err.data.gpu_status) gpuStatus = err.data.gpu_status;
            else gpuStatus = Object.assign({}, gpuStatus, { available: false, active_count: 4, free_count: 0 });
            gpuStatusMsg = isKo
              ? '현재 GPU 0-3 슬롯(4개)이 모두 사용 중입니다. 슬롯이 비면 버튼이 자동 활성화됩니다.'
              : 'All 4 GPU slots (0-3) are currently busy. The button re-enables automatically once a slot opens.';
            renderControls();
            renderStudioCanvas(false);
          } else {
            gpuStatusMsg = (err && err.message) || 'Deep Research error';
            renderControls();
            renderStudioCanvas(false);
          }
          pollGpuStatus(false);
        }
        return;
      }

      // Mode 2 (Default): Python Server 368,640 Matrix Search
      S.lastRunMode = 'matrix_368k';
      try {
        if (API.studioEvaluate) {
          const res = await API.studioEvaluate(buildEvalRequestBody());
          serverSpace = adaptServerSpace(res);
        } else {
          serverSpace = evaluateLocalFallbackSpace();
        }
      } catch (e) {
        serverSpace = evaluateLocalFallbackSpace();
      }
      if (!box.isConnected) { isOptimizing = false; return; }
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
      const evalSpace = serverSpace || evaluateLocalFallbackSpace();
      const sim = (evalSpace && evalSpace.current) ? evalSpace.current : computeStudioSimulation();
      const tgt = sim.tgt;
      const lnk = sim.lnk;
      const dar = sim.dar;
      const fcSilenced = sim.fcSilenced;
      const handleMatch = sim.isCompat;
      const bystander = sim.bystander;
      const stabilityScore = sim.plasmaStabPct != null
        ? sim.plasmaStabPct
        : Math.max(25, Math.min(98, Math.round(lnk.stability - (dar > 4 ? (dar - 4) * 2.5 : 0))));

      if (!hasPatientProfile() && S.studioDesignMode !== 'idle') {
        S.studioDesignMode = 'idle';
      }
      const simWrap = h('section', { class: 'sim-canvas-panel panel' });
      const total = evalSpace.totalCombinations || 368640;
      const designMode = S.studioDesignMode || 'idle';
      const isDeepResult = evalSpace.mode === 'deep_research_v2' && evalSpace.deepResearch;
      const initialStatus = animateScan
        ? (isDeepResult
            ? (isKo ? `ADCSurrogateNet v2 (${evalSpace.deepResearch.device_label}) 검증 중...` : `Verifying on ${evalSpace.deepResearch.device_label}...`)
            : (isKo ? `설계 조합 0 / ${total.toLocaleString()}개 행렬 연산 중` : `Scoring 0 / ${total.toLocaleString()} combinations`))
        : !hasPatientProfile()
          ? (isKo ? '환자 정보 미입력 (질환 또는 검진 수치를 먼저 입력하세요)' : 'Patient info required (Enter conditions or lab values first)')
          : designMode === 'idle'
            ? (isKo ? '설계 대기 중 (수동 설계 또는 자동 설계를 실행하세요)' : 'Ready (Click Manual ADC Design or Auto-design ADC)')
            : (isKo
                ? `안전도 ${sim.safetyScore}점 / 항암 효능 ${sim.efficacyScore}점`
                : `Safety ${sim.safetyScore} / Efficacy ${sim.efficacyScore}`);

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

      // Live Deep Research Telemetry Strip (shown when Mode 3 Deep Research was executed)
      let deepStrip = null;
      if (designMode !== 'idle' && isDeepResult && !animateScan) {
        const dr = evalSpace.deepResearch;
        const bSim = evalSpace.best || sim;
        const concItems = (bSim.concResponse || []).map((cr) => h('div', { class: 'dts-conc-item' },
          h('span', { class: 'dts-conc-nm', text: `${cr.concNm} nM` }),
          h('span', { class: 'dts-conc-bar' }, h('i', { style: `width:${Math.min(100, Math.max(4, cr.killPct))}%` })),
          h('span', { class: 'dts-conc-val', text: `${cr.killPct.toFixed(0)}%` })));

        deepStrip = h('div', { class: 'deep-telemetry-strip' },
          h('div', { class: 'dts-head' },
            h('span', { class: 'dts-tag', text: 'Deep Research' }),
            h('span', {
              class: 'dts-meta',
              text: isKo
                ? `최적 권장 용량 ${dr.optimal_dose_mgkg} mg/kg`
                : `Optimal Dose ${dr.optimal_dose_mgkg} mg/kg`,
            })),
          h('div', { class: 'dts-body' },
            h('div', { class: 'dts-sigma-group' },
              h('span', { class: 'dts-chip', text: isKo ? `안전도 ${bSim.safetyScore} ± ${(bSim.safetyStd || 0).toFixed(1)}` : `Safety ${bSim.safetyScore} ± ${(bSim.safetyStd || 0).toFixed(1)}` }),
              h('span', { class: 'dts-chip', text: isKo ? `효능 ${bSim.efficacyScore} ± ${(bSim.efficacyStd || 0).toFixed(1)}` : `Efficacy ${bSim.efficacyScore} ± ${(bSim.efficacyStd || 0).toFixed(1)}` }),
              h('span', { class: 'dts-chip', text: `pIC50 ${(bSim.pIC50Pos || 8).toFixed(2)} ± ${(bSim.pIC50Std || 0).toFixed(2)}` })),
            concItems.length ? h('div', { class: 'dts-conc-grid' }, concItems) : null));
      }

      const eqGrid = h('div', { class: 'sim-eq-grid' });
      const summaryMeta = h('span', { class: 'sim-summary-meta' });
      const rBox = h('div', { class: 'sim-rationale-box' });
      const organRows = h('div', { class: 'expr-list' });

      function updateOrganRowsDom(curSim) {
        clear(organRows);
        (curSim.organRisks || []).forEach((item) => {
          const pct = Math.round(item.p * 100);
          const color = riskColor(pct);
          const stdTxt = item.pStd != null ? ` (±${Math.round(item.pStd * 100)}%)` : '';
          organRows.append(h('div', { class: 'expr-row' },
            h('span', { class: 'ex-name', text: organKo(item.organ) }),
            h('span', { class: 'ex-track' }, h('i', { class: 'ex-fill', style: `width:${Math.max(4, pct)}%;background:${color}` })),
            h('span', { class: 'ex-val', style: `color:${color}`, text: `${riskLevel(pct)} ${pct}%${stdTxt}` })));
        });
      }

      function updateRationaleDom(curSim, curSpace) {
        clear(rBox);
        const bestC = curSpace.best;
        const activeRat = buildAutoOptimizeRationales(bestC);
        const curFcFmt = S.studio.fcFormat || (S.studio.fc ? 'igg1_lalapg' : 'igg1_wt');
        const bestFcFmt = bestC.spec.fcFormat || (bestC.spec.fc ? 'igg1_lalapg' : 'igg1_wt');
        const isOpt = (
          S.studio.target === bestC.spec.target &&
          S.studio.linker === bestC.spec.linker &&
          S.studio.payload === bestC.spec.payload &&
          Number(S.studio.dar) === Number(bestC.spec.dar) &&
          curFcFmt === bestFcFmt
        );
        const bestPayName = bestC.spec.customPayloadLabel || plainName(bestC.spec.payload);
        rBox.append(
          h('div', { class: 'srb-title' },
            h('span', { class: 'srb-main-text', text: isOpt ? t('optimalLocked') : `${t('optimalCand')} ${plainName(bestC.spec.target)} + ${bestPayName}, DAR ${bestC.spec.dar}` }),
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
        const totalCombTxt = (spNow.totalCombinations || 368640).toLocaleString();

        const activePresetObj = SIM_WEIGHT_PRESETS.find((p) => p.id === S.simPreset);
        const presetLabel = activePresetObj ? (isKo ? activePresetObj.ko : activePresetObj.en) : (isKo ? '사용자 정의 계수' : 'Custom Weights');
        summaryMeta.textContent = isKo
          ? `${presetLabel} | 치료지수 U = ${utilVal}`
          : `${presetLabel} | Utility U = ${utilVal}`;

        clear(eqGrid);
        const picTxt = sNow.pIC50Pos != null ? sNow.pIC50Pos.toFixed(2) : '8.00';
        const stabTxt = sNow.plasmaStabPct != null ? `${sNow.plasmaStabPct}%` : '85%';
        const mVar = (base, sub) => sub ? h('span', null, h('i', { class: 'eq-v', text: base }), h('sub', { text: sub })) : h('i', { class: 'eq-v', text: base });
        const mNum = (val) => h('span', { class: 'eq-num', text: val });
        const mOp = (op) => h('span', { class: 'eq-op', text: op });
        const mTxt = (txt) => h('span', { class: 'eq-fn', text: txt });

        const eq1Lines = [
          h('div', { class: 'sim-eq-line' },
            mVar('U', 'TI'), mOp('='),
            mNum(wSafeEff.toFixed(2)), mOp('×'), mVar('X', 'safe'),
            mOp('+'),
            mNum(wEffComp.toFixed(2)), mOp('×'), mVar('Y', 'eff')),
        ];
        const eq2Lines = [
          h('div', { class: 'sim-eq-line' },
            mVar('X', 'safe'), mOp('='), mTxt('100'), mOp('×'), mTxt('[1 − ('),
            mNum(w.wPeak.toFixed(2)), mOp('×'), mVar('p', 'max'),
            mOp('+'),
            mNum(wMean.toFixed(2)), mOp('×'), mVar('p', 'mean'),
            mTxt(')],   '),
            mVar('p', 'o'), mOp('='), mTxt('1 − exp(−'), mVar('H', 'o'), mTxt(')')),
          h('div', { class: 'sim-eq-line' },
            mVar('H', 'o'), mOp('='), mVar('V', 'o'), mOp('×'), mTxt('['),
            mNum(wOff.toFixed(2)), mOp('×'), mTxt('('),
            mNum(w.leakSens.toFixed(2)), mOp('×'), mVar('H', 'leak'),
            mOp('+'),
            mNum(w.hydroSens.toFixed(2)), mOp('×'), mVar('H', 'agg'),
            mOp('+'), mVar('H', 'Fc'), mTxt(')'),
            mOp('+'),
            mNum(w.wExpr.toFixed(2)), mOp('×'), mVar('H', 'on'), mTxt(']')),
        ];
        const eq3Lines = [
          h('div', { class: 'sim-eq-line' },
            mVar('Y', 'eff'), mOp('='), mTxt('100'), mOp('×'),
            mVar('I', isKo ? '암종' : 'ind'), mOp('×'), mVar('C', isKo ? '접합' : 'pair'), mOp('×'), mTxt('('),
            mNum((sNow.nwSel || 0.25).toFixed(2)), mOp('×'), mVar('S', 'sel'),
            mOp('+'),
            mNum((sNow.nwPot || 0.30).toFixed(2)), mOp('×'), mVar('S', 'pot'),
            mOp('+'),
            mNum((sNow.nwDel || 0.23).toFixed(2)), mOp('×'), mVar('S', 'deliv'),
            mOp('+'),
            mNum((sNow.nwBys || 0.22).toFixed(2)), mOp('×'), mVar('S', 'bys'),
            mTxt(')')),
        ];

        const cards = isKo
          ? [
              {
                tag: '1. 치료지수 목적함수 — 초대규모 최적 설계 결정',
                sym: '최종 최적점 결정',
                lines: eq1Lines,
                desc: `아래 2번(가로축 장기 안전도 X)과 3번(세로축 항암 효능 Y) 점수를 결합해 ${totalCombTxt}개 후보 중 최적점(${plainName(spNow.best.spec.target)} + ${plainName(spNow.best.spec.payload)}, DAR ${spNow.best.spec.dar})을 결정합니다.`,
              },
              {
                tag: '2. 경로 분해 장기 안전도 — 가로축(X) 좌표 산출',
                sym: 'X축 안전도 산출',
                lines: eq2Lines,
                desc: '하단 독성 경로 슬라이더(ω_peak, α_on, β_leak, γ_agg, φ_Fc)가 전신 누출, 소수성 응집, Fc감마 흡수, 정상조직 발현 위험에 반영되어 X축 안전도 점수를 산출합니다.',
              },
              {
                tag: '3. 멀티모달 신경망 항암 효능 — 세로축(Y) 좌표 산출',
                sym: 'Y축 효능 산출',
                lines: eq3Lines,
                desc: `하단 효능 슬라이더(w_sel, w_bys)가 신경망 예측치(접합체 pIC50 = ${picTxt}, 혈장 보존율 = ${stabTxt})의 가중합을 조절해 Y축 항암 효능 점수를 산출합니다.`,
              },
            ]
          : [
              {
                tag: '1. Therapeutic Index Objective — Construct Selection',
                sym: 'Optimal Point',
                lines: eq1Lines,
                desc: `Combines X-axis organ safety (Eq. 2) and Y-axis antitumor efficacy (Eq. 3) across ${totalCombTxt} candidates to select the optimal construct (${plainName(spNow.best.spec.target)} + ${plainName(spNow.best.spec.payload)}, DAR ${spNow.best.spec.dar}).`,
              },
              {
                tag: '2. Pathway-Decomposed Organ Safety — X-Axis Coordinate',
                sym: 'X-Axis Safety',
                lines: eq2Lines,
                desc: 'Maps the toxicity pathway sliders below (ω_peak, α_on, β_leak, γ_agg, φ_Fc) onto 5-fold neural 13-organ hazard predictions to compute X_safe.',
              },
              {
                tag: '3. Multimodal Neural Antitumor Efficacy — Y-Axis Coordinate',
                sym: 'Y-Axis Efficacy',
                lines: eq3Lines,
                desc: `Applies the efficacy sliders below (w_sel, w_bys) to neural potency and delivery predictions (conjugate pIC50 = ${picTxt}, plasma retention = ${stabTxt}) to compute Y_eff.`,
              },
            ];

        cards.forEach((c) => {
          eqGrid.append(h('div', { class: 'sim-eq-card' },
            h('div', { class: 'sim-eq-card-head' },
              h('span', { class: 'sim-eq-tag', text: c.tag }),
              h('span', { class: 'sim-eq-sym', text: c.sym })),
            h('div', { class: 'sim-eq-math' }, c.lines),
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
          ko: 'Fc 엔지니어링 보호율', en: 'Fc-Engineering Protection',
          subKo: '폐포 대식세포, 간, 골수의 Fc감마 비특이 흡수 차단율', subEn: 'Attenuation of FcgammaR macrophage uptake in lung, liver, and marrow' },
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
        clearTimeout(sliderDebounceTimer);
        sliderDebounceTimer = setTimeout(async () => {
          const seq = ++evalReqSeq;
          let nextSpace = null;
          if (API.studioEvaluate) {
            try {
              const res = await API.studioEvaluate(buildEvalRequestBody());
              if (seq !== evalReqSeq || !box.isConnected) return;
              nextSpace = adaptServerSpace(res);
            } catch (e) {
              nextSpace = evaluateLocalFallbackSpace();
            }
          } else {
            nextSpace = evaluateLocalFallbackSpace();
          }
          serverSpace = nextSpace;
          if (S.studioDesignMode === 'auto' && hasPatientProfile()) {
            const b = nextSpace.best;
            S.studio.target = b.spec.target;
            S.studio.linker = b.spec.linker;
            S.studio.payload = b.spec.payload;
            S.studio.dar = b.spec.dar;
            S.studio.fcFormat = b.spec.fcFormat || (b.spec.fc ? 'igg1_lalapg' : 'igg1_wt');
            S.studio.fc = S.studio.fcFormat !== 'igg1_wt';
            save();
            renderControls();
          }
          const newSim = (S.studioDesignMode === 'auto' && hasPatientProfile()) ? nextSpace.best : (nextSpace.current || computeStudioSimulation());
          updateFormulaLines(newSim, nextSpace);
          updateOrganRowsDom(newSim);
          updateRationaleDom(newSim, nextSpace);
          if (S.studioDesignMode !== 'idle' && hasPatientProfile()) {
            simStatusEl.textContent = isKo
              ? `안전도 ${newSim.safetyScore}점 / 항암 효능 ${newSim.efficacyScore}점`
              : `Safety ${newSim.safetyScore} / Efficacy ${newSim.efficacyScore}`;
          }
          initDesignChart(cvs, newSim, nextSpace, false);
        }, 40);
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
      simWrap.append(simHead, chartWrap);
      if (deepStrip) simWrap.append(deepStrip);
      simWrap.append(explain);

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
      (tgt.tissues || []).forEach((tis) => {
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
        (f, shownTotal) => {
          simStatusEl.textContent = isDeepResult
            ? (isKo
                ? `설계 조합 ${shownTotal.toLocaleString()} / ${total.toLocaleString()}개 정밀 평가 중`
                : `Evaluating ${shownTotal.toLocaleString()} / ${total.toLocaleString()} combinations`)
            : (isKo
                ? `설계 조합 ${shownTotal.toLocaleString()} / ${total.toLocaleString()}개 계산 중`
                : `Scoring ${shownTotal.toLocaleString()} / ${total.toLocaleString()} combinations`);
          if (optBtn) optBtn.style.setProperty('--p', (f * 100).toFixed(1) + '%');
        },
        async () => {
          if (!animateScan) return;
          if (optBtn) optBtn.style.setProperty('--p', '100%');
          setTimeout(async () => {
            isOptimizing = false;
            const best = evalSpace.best;
            S.studio.target = best.spec.target;
            S.studio.linker = best.spec.linker;
            S.studio.payload = best.spec.payload;
            S.studio.dar = best.spec.dar;
            S.studio.fcFormat = best.spec.fcFormat || (best.spec.fc ? 'igg1_lalapg' : 'igg1_wt');
            S.studio.fc = S.studio.fcFormat !== 'igg1_wt';
            if (evalSpace.isServer) {
              evalSpace.current = best;
              if (evalSpace.refBest) evalSpace.refCurrent = evalSpace.refBest;
            }
            save();
            if (S.mode !== 2 || !box.isConnected) return;
            renderControls();
            renderStudioCanvas(false);
            pollGpuStatus(true);
            setTimeout(() => { if (S.mode === 2 && box.isConnected) openStudioCompareDrawer(best, evalSpace); }, 450);
          }, 500);
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

      const isServer = Boolean(evalSpace.isServer);
      const totalCombos = evalSpace.totalCombinations || (evalSpace.cands ? evalSpace.cands.length : 368640);
      const best = evalSpace.best;

      const rawCloud = isServer
        ? evalSpace.cloud
        : (evalSpace.cands || []).map((c) => ({
            safetyRaw: c.safetyRaw,
            efficacyRaw: c.efficacyRaw,
            isCompat: c.isCompat,
            isBestTarget: c.spec.target === best.spec.target,
          }));

      const minX = 0, maxX = 100, minY = 0, maxY = 100, spanX = 100, spanY = 100;

      const shuffled = rawCloud.slice().map((c, i) => ({
        c,
        sortKey: Math.sin(i * 12345.67) * 10000 - Math.floor(Math.sin(i * 12345.67) * 10000),
      })).sort((a, b) => a.sortKey - b.sortKey).map((item) => item.c);

      const startTime = performance.now();
      const duration = (animate && !still()) ? (evalSpace.mode === 'deep_research_v2' ? 2400 : 3200) : 0;
      let completed = false;

      let paretoFront = [];
      if (isServer && Array.isArray(evalSpace.paretoFront) && evalSpace.paretoFront.length) {
        paretoFront = evalSpace.paretoFront;
      } else {
        const compatCands = rawCloud.filter((c) => c.isCompat).slice().sort((a, b) => (b.safetyRaw - a.safetyRaw) || (b.efficacyRaw - a.efficacyRaw));
        let maxEffSeen = -1;
        for (const c of compatCands) {
          if (c.efficacyRaw > maxEffSeen + 0.2) {
            paretoFront.push(c);
            maxEffSeen = c.efficacyRaw;
          }
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

        const lBox = { x: tx - 4 * dpr, y: ty - 11 * dpr, w: textW + 8 * dpr, h: boxH };
        if (avoidBox) {
          const overlapsX = lBox.x < avoidBox.x + avoidBox.w + 4 * dpr && lBox.x + lBox.w + 4 * dpr > avoidBox.x;
          const overlapsY = lBox.y < avoidBox.y + avoidBox.h + 2 * dpr && lBox.y + lBox.h + 2 * dpr > avoidBox.y;
          if (overlapsX && overlapsY) {
            const downY = avoidBox.y + avoidBox.h + 14 * dpr;
            const upY = avoidBox.y - 6 * dpr;
            if (downY <= offsetY + plotH - 5 * dpr) ty = downY;
            else if (upY - 11 * dpr >= offsetY + 4 * dpr) ty = upY;
            lBox.y = ty - 11 * dpr;
          }
        }

        ctx.textAlign = 'left';
        ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
        ctx.fillRect(lBox.x, lBox.y, lBox.w, lBox.h);
        ctx.strokeStyle = 'rgba(203, 213, 225, 0.85)';
        ctx.lineWidth = 1 * dpr;
        ctx.strokeRect(lBox.x, lBox.y, lBox.w, lBox.h);
        ctx.fillStyle = color;
        ctx.fillText(text, tx, ty);
        return lBox;
      }

      function renderFrame(now) {
        if (!cvs.isConnected) return;
        const rect = cvs.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const w = Math.max(260 * dpr, Math.round((rect.width || 600) * dpr));
        const hPx = Math.max(240 * dpr, Math.round((rect.height || 380) * dpr));
        if (cvs.width !== w || cvs.height !== hPx) {
          cvs.width = w;
          cvs.height = hPx;
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
                ['rgba(100, 116, 139, 0.75)', 3, `${t('legendCand')} ${totalCombos.toLocaleString()}`],
                ['rgba(239, 68, 68, 0.6)', 3, t('legendBad')],
                ['#0D9488', 4.5, t('legendBest')],
                ['#2563EB', 4.5, t('legendCur')],
              ];
        ctx.font = `600 ${10 * dpr}px sans-serif`;
        const padL = 52 * dpr, padR = 24 * dpr, padB = 42 * dpr, padT = 44 * dpr;
        const maxPlotW = Math.max(140 * dpr, w - padL - padR);
        const maxPlotH = Math.max(140 * dpr, hPx - padT - padB);

        const plotSize = Math.max(140 * dpr, Math.min(maxPlotW, maxPlotH));
        const plotW = plotSize;
        const plotH = plotSize;
        const offsetX = padL + (maxPlotW - plotW) / 2;
        const offsetY = padT + (maxPlotH - plotH) / 2;

        const toX = (val) => offsetX + ((Math.max(minX, Math.min(maxX, val)) - minX) / spanX) * plotW;
        const toY = (val) => offsetY + (1 - (Math.max(minY, Math.min(maxY, val)) - minY) / spanY) * plotH;

        const tfrac = duration > 0 ? Math.min(1, (now - startTime) / duration) : 1;
        const f = duration > 0 ? pace(tfrac) : 1;
        const shownDots = Math.floor(shuffled.length * f);
        const shownTotal = Math.floor(totalCombos * f);
        if (animate && onProgress && !completed) onProgress(f, shownTotal);

        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(0, 0, w, hPx);

        ctx.strokeStyle = '#CBD5E1';
        ctx.lineWidth = 1 * dpr;
        ctx.strokeRect(offsetX, offsetY, plotW, plotH);

        ctx.strokeStyle = '#F1F5F9';
        ctx.lineWidth = 1 * dpr;
        ctx.font = `600 ${10 * dpr}px sans-serif`;
        ctx.fillStyle = '#64748B';

        for (let v = 0; v <= 100; v += 20) {
          const gx = toX(v);
          ctx.beginPath(); ctx.moveTo(gx, offsetY); ctx.lineTo(gx, offsetY + plotH); ctx.stroke();
          ctx.textAlign = 'center';
          ctx.fillText(String(v), gx, offsetY + plotH + 14 * dpr);

          const gy = toY(v);
          ctx.beginPath(); ctx.moveTo(offsetX, gy); ctx.lineTo(offsetX + plotW, gy); ctx.stroke();
          ctx.textAlign = 'right';
          ctx.fillText(String(v), offsetX - 7 * dpr, gy + 3 * dpr);
        }

        ctx.font = `bold ${11 * dpr}px sans-serif`;
        ctx.fillStyle = '#1E293B';
        ctx.textAlign = 'center';
        ctx.fillText(t('axisSafety'), offsetX + plotW / 2, offsetY + plotH + 31 * dpr);
        ctx.save();
        ctx.translate(offsetX - 34 * dpr, offsetY + plotH / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(t('axisEfficacy'), 0, 0);
        ctx.restore();

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
          for (let k = 0; k < shownDots; k++) {
            const c = shuffled[k];
            ctx.fillStyle = !c.isCompat
              ? 'rgba(239, 68, 68, 0.25)'
              : c.isBestTarget
                ? 'rgba(13, 148, 136, 0.55)'
                : 'rgba(100, 116, 139, 0.36)';
            ctx.beginPath();
            ctx.arc(toX(c.safetyRaw), toY(c.efficacyRaw), (c.isBestTarget && c.isCompat ? 2.7 : 2.1) * dpr, 0, Math.PI * 2);
            ctx.fill();
          }

          if ((f >= 0.97 || !animate) && paretoFront.length >= 2) {
            ctx.save();
            ctx.strokeStyle = 'rgba(13, 148, 136, 0.62)';
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
          const sameTargetCands = isServer
            ? (evalSpace.sameTargetCloud || [])
            : (evalSpace.cands || []).filter((c) => c.spec.target === currentSim.spec.target && c.isCompat);
          sameTargetCands.forEach((c) => {
            ctx.fillStyle = 'rgba(148, 163, 184, 0.35)';
            ctx.beginPath();
            ctx.arc(toX(c.safetyRaw), toY(c.efficacyRaw), 2.3 * dpr, 0, Math.PI * 2);
            ctx.fill();
          });

          const refSim = (isServer && evalSpace.refCurrent)
            ? evalSpace.refCurrent
            : computeStudioSimulation(Object.assign({ target: currentSim.spec.target }, getRefStudioForTarget(currentSim.spec.target)));
          let refBox = null;
          if (refSim) {
            const rx = toX(refSim.safetyRaw), ry = toY(refSim.efficacyRaw);
            const sxNow = toX(currentSim.safetyRaw), syNow = toY(currentSim.efficacyRaw);

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

        if (f >= 0.97 || !animate) {
          ctx.fillStyle = 'rgba(13, 148, 136, 0.22)';
          ctx.beginPath(); ctx.arc(bx, by, 10.5 * dpr, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = '#0D9488';
          ctx.strokeStyle = '#FFFFFF';
          ctx.lineWidth = 2 * dpr;
          ctx.beginPath(); ctx.arc(bx, by, 5.2 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        }

        if (!sameSpot || (f < 0.97 && animate)) {
          ctx.fillStyle = 'rgba(37, 99, 235, 0.2)';
          ctx.beginPath(); ctx.arc(sx, sy, 10 * dpr, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = '#2563EB';
          ctx.strokeStyle = '#FFFFFF';
          ctx.lineWidth = 2 * dpr;
          ctx.beginPath(); ctx.arc(sx, sy, 5 * dpr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        }

        const bestPayLbl = best.spec.customPayloadLabel || plainName(best.spec.payload);
        if (f >= 0.97 || !animate) {
          if (sameSpot) {
            const unifiedLabel = `${t('legendBest')} / ${t('legendCur')}: ${plainName(best.spec.target)} + ${bestPayLbl}, DAR ${best.spec.dar} (${best.safetyScore}, ${best.efficacyScore})`;
            drawCalloutLabel(unifiedLabel, bx, by, true, offsetX, offsetY, plotW, plotH, dpr, '#065F46', null);
          } else {
            const bestLabel = `${t('legendBest')}: ${plainName(best.spec.target)} + ${bestPayLbl}, DAR ${best.spec.dar}`;
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
    renderStudioCanvas(false);
    triggerServerEvaluate(false);
    clear(barKeys);
    return box;
  }

  // ------------------------------------------------------------------ Mode 2: Patient & Labs (Required Basic Info + Collapsible Biomarker Flowsheet)
  function buildPatientLabsMode() {
    const box = h('div', { class: 's2' });
    const wbMount = h('div');
    const content = h('div');
    box.append(wbMount, content);

    function renderWb() {
      if (wbMount.contains(document.activeElement)) return;
      clear(wbMount);
      wbMount.append(buildWorkspaceBar(() => renderActiveMode(false)));
    }
    renderWb();

    let pointerDownInFlow = false;
    let pendingRender = false;
    content.addEventListener('pointerdown', () => {
      pointerDownInFlow = true;
      const release = () => {
        pointerDownInFlow = false;
        if (pendingRender) {
          pendingRender = false;
          setTimeout(() => { if (box.isConnected) renderFlowsheet(); }, 0);
        }
      };
      window.addEventListener('pointerup', release, { once: true });
      window.addEventListener('pointercancel', release, { once: true });
    });

    function safeRenderFlowsheet() {
      if (pointerDownInFlow) {
        pendingRender = true;
        return;
      }
      renderFlowsheet();
    }

    const BASIC_KEYS = new Set([
      'age', 'sex', 'weight',
      'creatinine', 'esrd',
      'bilirubin', 'ast', 'alt',
      'platelet', 'anc', 'hb',
    ]);

    const REQ_LAB_SECTIONS = [
      {
        id: 'renal_req',
        ko: '신장 기능 선별',
        en: 'Renal Baseline',
        showDerivedCrcl: true,
        numeric: [
          { key: 'creatinine', name: 'Serum Creatinine', unit: 'mg/dL', refLow: 0.6, refHigh: 1.2, scaleMin: 0, scaleMax: 3.5 },
        ],
        discrete: [
          {
            key: 'esrd',
            name: 'Dialysis / ESRD',
            subKo: '투석 또는 말기 신부전 여부',
            subEn: 'Dialysis or end-stage renal disease status',
            options: [
              { val: '', ko: '미선택', en: 'Unset' },
              { val: 'n', ko: '아니오', en: 'No' },
              { val: 'y', ko: '예', en: 'Yes', flag: true },
            ],
          },
        ],
      },
      {
        id: 'hepatic_req',
        ko: '간 기능 선별',
        en: 'Hepatic Baseline',
        numeric: [
          { key: 'bilirubin', name: 'Total Bilirubin', unit: 'mg/dL', refLow: 0.2, refHigh: 1.2, scaleMin: 0, scaleMax: 3.0 },
          { key: 'ast', name: 'AST (Aminotransferase)', unit: 'U/L', refLow: 10, refHigh: 40, scaleMin: 0, scaleMax: 120 },
          { key: 'alt', name: 'ALT (Aminotransferase)', unit: 'U/L', refLow: 7, refHigh: 56, scaleMin: 0, scaleMax: 160 },
        ],
        discrete: [],
      },
      {
        id: 'blood_req',
        ko: '혈액 및 골수 선별',
        en: 'Hematology (CBC)',
        numeric: [
          { key: 'platelet', name: 'Platelets', unit: 'x10³/µL', refLow: 150, refHigh: 450, scaleMin: 0, scaleMax: 600 },
          { key: 'anc', name: 'ANC (Neutrophils)', unit: 'x10³/µL', refLow: 1.5, refHigh: 8.0, scaleMin: 0, scaleMax: 12.0 },
          { key: 'hb', name: 'Hemoglobin (Hb)', unit: 'g/dL', refLow: 12.0, refHigh: 17.5, scaleMin: 6.0, scaleMax: 21.0 },
        ],
        discrete: [],
      },
    ];

    const OPT_LAB_SECTIONS = [
      {
        id: 'renal_hep_opt',
        ko: '정밀 신장 지표 및 간 등급',
        en: 'Direct Clearance & Hepatic Grade',
        numeric: [
          { key: 'crcl', name: 'CLcr (Creatinine Clearance)', unit: 'mL/min', refLow: 60, refHigh: 120, scaleMin: 0, scaleMax: 150, highOk: true },
          { key: 'egfr', name: 'eGFR', unit: 'mL/min/1.73m²', refLow: 60, refHigh: 120, scaleMin: 0, scaleMax: 150, highOk: true },
        ],
        discrete: [
          {
            key: 'child_pugh',
            name: 'Child-Pugh Class',
            subKo: '간경변 또는 간기능 저하 임상 등급',
            subEn: 'Hepatic impairment clinical grade',
            options: [
              { val: '', ko: '미선택', en: 'Unset' },
              { val: 'A', ko: 'A', en: 'A' },
              { val: 'B', ko: 'B', en: 'B', flag: true },
              { val: 'C', ko: 'C', en: 'C', flag: true },
            ],
          },
        ],
      },
      {
        id: 'cardiac_meta',
        ko: '심장, 대사 및 유전형',
        en: 'Cardiac, Metabolic & Genotype',
        numeric: [
          { key: 'lvef', name: 'LVEF (Ejection Fraction)', unit: '%', refLow: 50, refHigh: 75, scaleMin: 20, scaleMax: 90, highOk: true },
          { key: 'hba1c', name: 'HbA1c', unit: '%', refLow: 4.0, refHigh: 5.6, scaleMin: 3.5, scaleMax: 11.0 },
        ],
        discrete: [
          {
            key: 'ugt1a1',
            name: 'UGT1A1*28 Homozygous',
            subKo: 'SN-38 계열(트로델비 등) 대사 유전형',
            subEn: 'Homozygous *28/*28 genotype for SN-38 metabolism',
            options: [
              { val: '', ko: '미선택', en: 'Unset' },
              { val: 'n', ko: '아니오', en: 'No' },
              { val: 'y', ko: '예', en: 'Yes', flag: true },
            ],
          },
        ],
      },
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
        if (bf.highOk) {
          if (valNum < bf.refLow * 0.5) {
            statusClass = 'alarm'; statusText = t('lowVal');
          } else if (valNum < bf.refLow) {
            statusClass = 'warn'; statusText = t('lowVal');
          } else {
            statusClass = 'normal'; statusText = t('normal');
          }
        } else if (valNum > bf.refHigh * 1.5) {
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

    function normalizeDiscreteVal(rawVal) {
      if (rawVal === true) return 'y';
      if (rawVal === false) return 'n';
      if (rawVal === undefined || rawVal === null) return '';
      return String(rawVal).trim();
    }

    function renderLabSectionCards(sections, isKo) {
      const secGrid = h('div', { class: 'lab-sections-grid' });
      sections.forEach((sec) => {
        const derivedCrcl = sec.showDerivedCrcl && S.labs && S.labs.derived && S.labs.derived.crcl != null && !String(S.raw.crcl || '').trim()
          ? S.labs.derived
          : null;
        const derivedPill = derivedCrcl
          ? h('span', {
              class: 'cg-derived-pill',
              text: isKo
                ? `산출 CLcr ${(derivedCrcl.shown && derivedCrcl.shown.crcl) || Number(derivedCrcl.crcl).toFixed(1)} mL/min`
                : `Derived CLcr ${(derivedCrcl.shown && derivedCrcl.shown.crcl) || Number(derivedCrcl.crcl).toFixed(1)} mL/min`,
            })
          : null;

        const cardEl = h('div', { class: 'lab-section-card' },
          h('div', { class: 'lab-sec-head' },
            h('h3', { class: 'lab-sec-title', text: isKo ? sec.ko : sec.en }),
            derivedPill));

        const groupEl = h('div', { class: 'lab-card-group' });

        sec.numeric.forEach((bf) => {
          const valStr = S.raw[bf.key];
          const m = computeBioRowMetrics(bf, valStr);

          const trackEl = h('div', { class: 'bio-spectrum-track' },
            h('i', {
              class: 'bio-spectrum-normal',
              style: `left:${m.normalLeft.toFixed(1)}%;width:${m.normalWidth.toFixed(1)}%`,
              title: `${t('refRange')}: ${bf.refLow} - ${bf.refHigh} ${bf.unit}`,
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
            'data-lab-key': bf.key,
            type: 'text', inputmode: 'decimal', placeholder: '—', value: valStr ?? '',
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
              renderWb();
              safeRenderFlowsheet();
            },
          });

          const labName = isKo ? (LAB_KO[bf.key] || bf.name) : bf.name;

          groupEl.append(h('div', { class: 'bio-row' },
            h('div', { class: 'bio-info' },
              h('span', { class: 'bio-name', text: labName }),
              h('span', { class: 'bio-ref', text: `${t('refRange')}: ${bf.refLow} - ${bf.refHigh} ${bf.unit}` })),
            h('div', { class: 'bio-input-wrap' }, input),
            h('div', { class: 'bio-spectrum-wrap' }, trackEl, ticksEl),
            statusBadgeEl));
        });

        sec.discrete.forEach((df) => {
          const curVal = normalizeDiscreteVal(S.raw[df.key]);
          const segGroup = h('div', { class: 'bio-seg-group', role: 'group', 'aria-label': isKo ? (LAB_KO[df.key] || df.name) : df.name });
          df.options.forEach((opt) => {
            const active = curVal.toUpperCase() === opt.val.toUpperCase();
            segGroup.append(h('button', {
              type: 'button',
              class: 'bio-seg-btn' + (active ? ' is-selected' : '') + (active && opt.flag ? ' is-flagged' : ''),
              'aria-pressed': active ? 'true' : 'false',
              text: isKo ? opt.ko : opt.en,
              onclick: async () => {
                if (opt.val === '') delete S.raw[df.key];
                else S.raw[df.key] = opt.val;
                S.presetId = null;
                if (opt.val !== '') S.studioNeedInputWarn = false;
                else if (!hasPatientProfile()) S.studioDesignMode = 'idle';
                save();
                await refreshBackendData();
                renderWb();
                renderFlowsheet();
              },
            }));
          });

          groupEl.append(h('div', { class: 'bio-discrete-row' },
            h('div', { class: 'bio-info' },
              h('span', { class: 'bio-name', text: isKo ? (LAB_KO[df.key] || df.name) : df.name }),
              h('span', { class: 'bio-ref', text: isKo ? df.subKo : df.subEn })),
            segGroup));
        });

        cardEl.append(groupEl);
        secGrid.append(cardEl);
      });
      return secGrid;
    }

    function buildRequiredLabsPanel(isKo, reqEnteredCount) {
      const isReqOpen = Boolean(S.basicLabsOpen);
      const labErrors = (S.labs && S.labs.errors) || {};
      const derivedObj = S.labs && S.labs.derived && S.labs.derived.crcl != null && !String(S.raw.crcl || '').trim() && S.labs.derived.crcl_source === 'Cockcroft-Gault'
        ? S.labs.derived
        : null;
      const basicDerivedPill = derivedObj
        ? h('span', {
            class: 'cg-derived-pill',
            text: isKo
              ? `산출 CLcr ${(derivedObj.shown && derivedObj.shown.crcl) || Number(derivedObj.crcl).toFixed(1)} mL/min`
              : `Derived CLcr ${(derivedObj.shown && derivedObj.shown.crcl) || Number(derivedObj.crcl).toFixed(1)} mL/min`,
          })
        : null;
      const reqCountBadge = reqEnteredCount > 0
        ? h('span', { class: 'flowsheet-count-badge', text: isKo ? `${reqEnteredCount}개 항목 입력됨` : `${reqEnteredCount} entered` })
        : null;

      const reqPanel = h('section', { class: 'flowsheet-collapsible panel req-flowsheet', 'aria-label': t('basicTitle') });
      const reqToggleBtn = h('button', {
        type: 'button',
        class: 'flowsheet-toggle-bar',
        'aria-expanded': isReqOpen ? 'true' : 'false',
        onclick: () => {
          S.basicLabsOpen = !S.basicLabsOpen;
          save();
          renderFlowsheet();
        },
      },
      h('div', { class: 'flowsheet-toggle-left' },
        h('div', { class: 'flowsheet-title-row' },
          h('h2', { class: 'flowsheet-title', text: t('basicTitle') }),
          h('span', { class: 'flowsheet-req-badge', text: t('basicReqTag') }),
          reqCountBadge,
          basicDerivedPill)),
      h('span', { class: 'flowsheet-toggle-action', text: isReqOpen ? t('basicCollapse') : t('basicExpand') }));

      reqPanel.append(reqToggleBtn);

      if (isReqOpen) {
        const makeBasicNumField = (key, labelTxt, unitTxt, ph) => {
          const hasErr = Boolean(labErrors[key]);
          const inp = h('input', {
            id: 'bf-' + key,
            'data-lab-key': key,
            type: 'text',
            inputmode: 'decimal',
            placeholder: ph,
            value: S.raw[key] ?? '',
            class: hasErr ? 'flagged' : '',
            title: labErrors[key] || '',
            oninput: (e) => {
              S.raw[key] = e.target.value;
              S.presetId = null;
              if (String(e.target.value).trim()) S.studioNeedInputWarn = false;
              else if (!hasPatientProfile()) S.studioDesignMode = 'idle';
              save();
            },
            onblur: async () => {
              await refreshBackendData();
              renderWb();
              safeRenderFlowsheet();
            },
          });
          return h('div', { class: 'basic-field-item' + (hasErr ? ' has-error' : '') },
            h('label', { class: 'basic-field-label', for: 'bf-' + key, text: labelTxt }),
            h('div', { class: 'basic-input-unit' },
              inp,
              h('span', { class: 'basic-unit', text: unitTxt })));
        };

        const curSex = String(S.raw.sex || '').trim().toUpperCase();
        const sexSeg = h('div', { class: 'bio-seg-group', role: 'group', 'aria-label': isKo ? '성별' : 'Sex' });
        [
          { val: 'M', ko: '남성 (M)', en: 'Male (M)' },
          { val: 'F', ko: '여성 (F)', en: 'Female (F)' },
        ].forEach((opt) => {
          const active = curSex === opt.val;
          sexSeg.append(h('button', {
            type: 'button',
            class: 'bio-seg-btn' + (active ? ' is-selected' : ''),
            'aria-pressed': active ? 'true' : 'false',
            title: active ? (isKo ? '클릭 시 선택 해제' : 'Click to clear') : '',
            text: isKo ? opt.ko : opt.en,
            onclick: async () => {
              if (active) delete S.raw.sex;
              else S.raw.sex = opt.val;
              S.presetId = null;
              if (S.raw.sex) S.studioNeedInputWarn = false;
              else if (!hasPatientProfile()) S.studioDesignMode = 'idle';
              save();
              await refreshBackendData();
              renderWb();
              renderFlowsheet();
            },
          }));
        });
        const sexField = h('div', { class: 'basic-field-item' },
          h('span', { class: 'basic-field-label', text: isKo ? '성별' : 'Sex' }),
          sexSeg);

        const reqBody = h('div', { class: 'flowsheet-body' },
          h('div', { class: 'basic-fields-grid req-basic-grid' },
            makeBasicNumField('age', isKo ? '나이' : 'Age', isKo ? '세' : 'yr', '65'),
            sexField,
            makeBasicNumField('weight', isKo ? '체중' : 'Weight', 'kg', '60')),
          renderLabSectionCards(REQ_LAB_SECTIONS, isKo));
        reqPanel.append(reqBody);
      }

      return reqPanel;
    }

    function renderFlowsheet() {
      const activeEl = document.activeElement;
      const activeKey = activeEl && content.contains(activeEl) && activeEl.dataset ? activeEl.dataset.labKey : null;
      const selStart = activeKey ? activeEl.selectionStart : null;
      const selEnd = activeKey ? activeEl.selectionEnd : null;

      clear(content);
      const isKo = S.lang === 'ko';
      const enteredKeys = Object.keys(rawValues());
      const reqEnteredCount = enteredKeys.filter((k) => BASIC_KEYS.has(k)).length;
      const optEnteredCount = enteredKeys.filter((k) => !BASIC_KEYS.has(k)).length;
      const isOpen = Boolean(S.labsOpen);

      const basicPanel = buildRequiredLabsPanel(isKo, reqEnteredCount);

      const panelWrap = h('section', { class: 'flowsheet-collapsible panel' });
      const countBadge = optEnteredCount > 0
        ? h('span', { class: 'flowsheet-count-badge', text: isKo ? `${optEnteredCount}개 항목 입력됨` : `${optEnteredCount} entered` })
        : null;

      const toggleBtn = h('button', {
        type: 'button',
        class: 'flowsheet-toggle-bar',
        'aria-expanded': isOpen ? 'true' : 'false',
        onclick: () => {
          S.labsOpen = !S.labsOpen;
          save();
          renderFlowsheet();
        },
      },
      h('div', { class: 'flowsheet-toggle-left' },
        h('div', { class: 'flowsheet-title-row' },
          h('h2', { class: 'flowsheet-title', text: t('flowTitle') }),
          h('span', { class: 'flowsheet-opt-badge', text: t('flowOptTag') }),
          countBadge),
        h('span', { class: 'flowsheet-sub', text: t('flowSub') })),
      h('span', { class: 'flowsheet-toggle-action', text: isOpen ? t('flowCollapse') : t('flowExpand') }));

      panelWrap.append(toggleBtn);

      if (isOpen) {
        const bodyEl = h('div', { class: 'flowsheet-body' }, renderLabSectionCards(OPT_LAB_SECTIONS, isKo));
        panelWrap.append(bodyEl);
      }

      content.append(basicPanel, panelWrap);

      if (activeKey) {
        const restored = content.querySelector(`input[data-lab-key="${activeKey}"]`);
        if (restored) {
          restored.focus({ preventScroll: true });
          try {
            if (selStart !== null) restored.setSelectionRange(selStart, selEnd);
          } catch (e) { /* ignore */ }
        }
      }
    }

    renderFlowsheet();
    clear(barKeys);
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
      h('ul', { class: 'dash' }, d.missing.map((m) => h('li', { text: isKo ? (MISSING_KO[m] || m) : m })))) : null;

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
      { id: 'Structure', label: t('tabStructure'), secs: [secStructure3d].filter(Boolean) },
      { id: 'Study', label: t('tabStudy'), secs: [secStudy].filter(Boolean) },
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

  function fcFormatLabel(fcFormat, fcSilenced, isKo) {
    const id = fcFormat || (fcSilenced ? 'igg1_lalapg' : 'igg1_wt');
    const item = STUDIO_FC_ITEMS.find((x) => x.id === id);
    if (item) return isKo ? item.ko : item.en;
    return fcSilenced ? (isKo ? 'Fc 침묵화 (LALA-PG)' : 'Fc-Silenced (LALA-PG)') : (isKo ? '야생형 IgG1' : 'Wild-type IgG1');
  }

  function getDeriskDefs(tgt, refBrand, isKo) {
    if (DERISK[tgt.id]) return DERISK[tgt.id];
    const topTis = (tgt.tissues && tgt.tissues[0]) || { organ: 'haematologic', tpm: 30 };
    const orgLabelKo = ORGAN_KO[topTis.organ] || topTis.organ;
    const orgLabelEn = SHORT[topTis.organ] || topTis.organ;
    return [
      {
        ko: [
          `${orgLabelKo} 표적 및 전신 독성 완화`,
          `${refBrand} 등 동일 계열 약물에서는 ${orgLabelKo} 및 조혈계 독성이 용량 제한 요인으로 작용합니다.`,
          `${plainName(tgt.id)}의 정상 조직 발현(${topTis.tpm} nTPM)과 혈중 유리 페이로드 누출, 대식세포 Fc감마 수용체 흡수가 복합적으로 작용해 조직 손상을 유발합니다.`,
        ],
        en: [
          `${orgLabelEn} & systemic toxicity mitigation`,
          `Reference regimens such as ${refBrand} are limited by ${orgLabelEn.toLowerCase()} and marrow toxicities.`,
          `Baseline ${plainName(tgt.id)} expression (${topTis.tpm} nTPM), premature plasma payload release, and macrophage FcgammaR uptake combine to injure healthy tissue.`,
        ],
        kinds: ['fc', 'linker', `pay:${topTis.organ}`, 'dar'],
      },
    ];
  }

  // one sentence per kind: tone better / same / worse than the approved drug, for the parts the user chose
  function deriskAnswer(kind, sim, refSim, isKo) {
    const L = (ko, en) => (isKo ? ko : en);
    const simFcFmt = (sim.spec && sim.spec.fcFormat) || (sim.fcSilenced ? 'igg1_lalapg' : 'igg1_wt');
    const refFcFmt = (refSim.spec && refSim.spec.fcFormat) || (refSim.fcSilenced ? 'igg1_lalapg' : 'igg1_wt');
    if (kind === 'fc') {
      if (simFcFmt === 'igg1_lalapg') return { tone: 'better', text: L('Fc 침묵화(LALA-PG)로 대식세포의 Fc감마 수용체 결합이 차단되어 비특이 흡수 경로가 억제됩니다.', 'Fc silencing (LALA-PG) blocks FcgammaR binding on macrophages, suppressing non-specific uptake.') };
      if (simFcFmt === 'igg4_s228p' || simFcFmt === 'igg2_lowfc') {
        const lbl = fcFormatLabel(simFcFmt, true, isKo);
        return refFcFmt === 'igg1_wt'
          ? { tone: 'better', text: L(`${lbl} 골격을 채택해 야생형 IgG1 대비 대식세포 비특이 흡수를 낮췄습니다.`, `${lbl} backbone lowers macrophage non-specific uptake compared with wild-type IgG1.`) }
          : { tone: 'same', text: L(`${lbl} 골격으로 기존 약물과 유사한 저효능기 특성을 유지합니다.`, `${lbl} maintains low effector uptake similar to the reference drug.`) };
      }
      return { tone: 'same', text: L('야생형 IgG1 골격이라 대식세포 비특이 흡수 경로가 기존 약물과 동일합니다.', 'Wild-type IgG1 retains the same macrophage uptake route as the reference drug.') };
    }
    if (kind === 'dar') {
      if (sim.dar < refSim.dar) return { tone: 'better', text: L(`DAR이 ${refSim.dar}에서 ${sim.dar}로 낮아 약물 부하와 응집 위험이 줄었습니다.`, `DAR is lower, ${refSim.dar} to ${sim.dar}, so drug load and clumping risk are reduced.`) };
      if (sim.dar > refSim.dar) return { tone: 'worse', text: L(`DAR이 ${refSim.dar}에서 ${sim.dar}로 높아져 약물 부하와 응집 위험이 커졌습니다.`, `DAR is higher, ${refSim.dar} to ${sim.dar}, so drug load and clumping risk are greater.`) };
      return { tone: 'same', text: L(`DAR ${sim.dar}로 기존 약물과 같아 약물 부하는 줄지 않았습니다.`, `DAR ${sim.dar} is the same as the approved drug, so drug load is not reduced.`) };
    }
    if (kind === 'linker') {
      const a = refSim.plasmaStabPct != null ? refSim.plasmaStabPct : refSim.lnk.stability;
      const b = sim.plasmaStabPct != null ? sim.plasmaStabPct : sim.lnk.stability;
      if (sim.lnk.id === refSim.lnk.id && Math.abs(b - a) <= 1) return { tone: 'same', text: L(`같은 링커라서 혈장 안정도(${b}%)가 기존 약물과 같습니다.`, `Same linker, so plasma stability (${b}%) is the same as the approved drug.`) };
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
      const pldOrgs = (sim.pld && sim.pld.organs) || {};
      const refPldOrgs = (refSim.pld && refSim.pld.organs) || {};
      const mine = (sim.organRiskMap && sim.organRiskMap[organ] != null) ? sim.organRiskMap[organ] : (pldOrgs[organ] != null ? pldOrgs[organ] : 22);
      const ref = (refSim.organRiskMap && refSim.organRiskMap[organ] != null) ? refSim.organRiskMap[organ] : (refPldOrgs[organ] != null ? refPldOrgs[organ] : 22);
      const name = organKo(organ);
      if (sim.pld.id === refSim.pld.id && Math.abs(mine - ref) <= 2) return { tone: 'same', text: L(`같은 페이로드라서 ${name}에 대한 독성도 같습니다.`, `Same payload, so its toxicity on ${name} is the same.`) };
      if (mine < ref - 4) return { tone: 'better', text: L(`${plainName(sim.pld.id)} 조합은 ${name}에 대한 신경망 독성 위험(${mine}%)이 ${plainName(refSim.pld.id)}(${ref}%)보다 낮습니다.`, `${plainName(sim.pld.id)} has lower predicted ${name} risk (${mine}%) than ${plainName(refSim.pld.id)} (${ref}%).`) };
      if (mine > ref + 4) return { tone: 'worse', text: L(`${plainName(sim.pld.id)} 조합은 ${name}에 대한 신경망 독성 위험(${mine}%)이 ${plainName(refSim.pld.id)}(${ref}%)보다 높습니다.`, `${plainName(sim.pld.id)} has higher predicted ${name} risk (${mine}%) than ${plainName(refSim.pld.id)} (${ref}%).`) };
      return { tone: 'same', text: L(`${name}에 대한 예측 독성 위험은 기존 약물과 비슷합니다.`, `Predicted toxicity risk on ${name} is similar to the approved drug.`) };
    }
    return { tone: 'same', text: '' };
  }

  function fillStudioCompareDrawer(simInput, spaceInput) {
    const sim = simInput || computeStudioSimulation();
    const isKo = S.lang === 'ko';
    const L = (ko, en) => (isKo ? ko : en);

    const tgt = sim.tgt || STUDIO_TARGETS[0];
    const lnk = sim.lnk || STUDIO_LINKERS[0];
    const pld = sim.pld || STUDIO_PAYLOADS[0];
    const dar = Number(sim.dar || (sim.spec && sim.spec.dar) || 4);
    const fcSilenced = Boolean(sim.fcSilenced !== undefined ? sim.fcSilenced : (sim.spec && sim.spec.fc));
    const fcFormat = (sim.spec && sim.spec.fcFormat) || (fcSilenced ? 'igg1_lalapg' : 'igg1_wt');
    const mineFcLabel = fcFormatLabel(fcFormat, fcSilenced, isKo);

    const refAdcId = (tgt && tgt.refAdc) || 'trastuzumab-deruxtecan';
    const refSpec = ADC_SPECS[refAdcId] || {};
    const refMech = MECH[refAdcId] || {};
    const refRow = (S.result && S.result.data && S.result.data.rows && S.result.data.rows.find((r) => r.adc === refAdcId)) || null;
    const refBrand = (refRow && refRow.brand) || refSpec.brand || refMech.brand || refAdcId;
    const refName = (refRow && refRow.name) || (refSpec.brand ? `${refSpec.brand} (${refAdcId})` : refAdcId);

    let refSim = null;
    if (spaceInput && spaceInput.refBest && spaceInput.best && spaceInput.best.spec && spaceInput.best.spec.target === tgt.id) {
      refSim = spaceInput.refBest;
    } else if (spaceInput && spaceInput.refCurrent && spaceInput.current && spaceInput.current.spec && spaceInput.current.spec.target === tgt.id) {
      refSim = spaceInput.refCurrent;
    } else {
      const fallbackRefArch = getRefStudioForTarget(tgt.id) || { linker: lnk.id, payload: pld.id, dar: 4, fc: false, fcFormat: 'igg1_wt' };
      refSim = computeStudioSimulation(Object.assign({ target: tgt.id }, fallbackRefArch), sim.organRisks ? sim.organRisks.map((r) => ({ organ: r.organ, score: 0.8 })) : null);
    }
    const refFcFmt = (refSim.spec && refSim.spec.fcFormat) || (refSim.fcSilenced ? 'igg1_lalapg' : 'igg1_wt');
    const refFcLabel = fcFormatLabel(refFcFmt, refSim.fcSilenced, isKo);

    const tgtName = plainName(tgt.id);
    const customLabel = sim.spec && sim.spec.customPayloadLabel;
    const payLabel = customLabel || plainName(pld.id);
    const designName = `${tgtName}-${payLabel}`;
    const doseTag = sim.optimalDoseMgKg ? `, ${sim.optimalDoseMgKg} mg/kg` : '';
    const designSub = `${lnk.id}, DAR ${dar}, ${mineFcLabel}${doseTag}`;

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
        h('span', { class: 'ch-sub', text: `${refSpec.linker || refSim.lnk.id}, DAR ${refSim.dar}, ${refFcLabel}` }),
        h('span', { class: 'ch-score', style: 'color:var(--dim)', text: L(`안전도 ${refSim.safetyScore}점 / 효능 ${refSim.efficacyScore}점`, `Safety ${refSim.safetyScore} / Efficacy ${refSim.efficacyScore}`) })));

    // 2. Part by part, with what it means clinically
    const burden = (sObj) => sim.organRisks.reduce((acc, r) => {
      const pldOrgs = (sObj.pld && sObj.pld.organs) || {};
      const v = (sObj.organRiskMap && sObj.organRiskMap[r.organ] != null)
        ? sObj.organRiskMap[r.organ]
        : (pldOrgs[r.organ] != null ? pldOrgs[r.organ] : 22);
      return acc + v;
    }, 0) / Math.max(1, sim.organRisks.length);
    const dSafety = sim.safetyScore - refSim.safetyScore;
    const dEff = sim.efficacyScore - refSim.efficacyScore;
    const toneOf = (d) => (d >= 3 ? 'better' : d <= -3 ? 'worse' : 'same');

    const linkerGain = deriskAnswer('linker', sim, refSim, isKo);
    const darGain = deriskAnswer('dar', sim, refSim, isKo);
    const fcGain = deriskAnswer('fc', sim, refSim, isKo);
    let payGain;
    if (!customLabel && pld.id === refSim.pld.id) payGain = { tone: 'same', text: L('같은 페이로드를 사용하므로 고유 약리 기전이 같습니다.', 'The same payload is used, so intrinsic pharmacology is the same.') };
    else {
      const a = burden(refSim);
      const b = burden(sim);
      const pct = a ? Math.round(Math.abs(1 - b / a) * 100) : 0;
      const tox = b < a - 2 ? L(`환자의 취약 장기에 대한 신경망 예측 위험이 약 ${pct}% 낮고`, `neural predicted risk on the patient's vulnerable organs is about ${pct}% lower, `)
        : b > a + 2 ? L(`환자의 취약 장기에 대한 신경망 예측 위험이 약 ${pct}% 높고`, `neural predicted risk on the patient's vulnerable organs is about ${pct}% higher, `)
          : L('환자의 취약 장기에 대한 예측 위험은 비슷하고', 'predicted risk on the patient\'s vulnerable organs is similar, ');
      const curPic = sim.pIC50Pos != null ? sim.pIC50Pos : pld.potency / 12;
      const refPic = refSim.pIC50Pos != null ? refSim.pIC50Pos : refSim.pld.potency / 12;
      const pot = curPic > refPic + 0.15 ? L(' 세포독성 효력(pIC50)은 더 높습니다.', 'and conjugate potency (pIC50) is stronger.')
        : curPic < refPic - 0.15 ? L(' 세포독성 효력(pIC50)은 더 낮습니다.', 'and conjugate potency (pIC50) is lower.') : L(' 세포독성 효력은 비슷합니다.', 'and conjugate potency is similar.');
      payGain = { tone: b < a - 2 ? 'better' : b > a + 2 ? 'worse' : 'same', text: tox + pot };
    }

    const rows = [
      [t('compTarget'), tgtName, plainName(refSim.tgt.id),
        { tone: 'same', text: L(`같은 ${tgtName} 표적이라 종양 선택도(+${tgt.selectivity.toFixed(1)} log2FC)는 같습니다. 차이는 아래 항목에서 생깁니다.`, `Same ${tgtName} target, so tumor selectivity (+${tgt.selectivity.toFixed(1)} log2FC) is the same. The differences come from the parts below.`) }],
      [t('compLinker'), `${lnk.id}, ${lnk.cleavable ? L('절단형', 'cleavable') : L('비절단형', 'non-cleavable')}`, refSpec.linker || refSim.lnk.id, linkerGain],
      [t('compPayload'), payLabel, plainName(refSim.pld.id), payGain],
      [t('compDar'), `DAR ${dar}`, `DAR ${refSim.dar}`, darGain],
      [t('compFc'), mineFcLabel, refFcLabel, fcGain],
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
    const deriskDefs = getDeriskDefs(tgt, refBrand, isKo);
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
      payload: payLabel,
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
        [L('세포독성 페이로드', 'Payload'), `${payLabel}, ${pld.cls}`],
        [L('항체 골격 / Fc', 'Antibody / Fc'), mineFcLabel],
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


  function openStudioCompareDrawer(simInput, spaceInput) {
    const sim = simInput || computeStudioSimulation();
    fillStudioCompareDrawer(sim, spaceInput);
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
    verEl.textContent = 'v' + (APP.version || '0.8.5');

    if (API.studioCatalog) {
      try {
        const cat = await API.studioCatalog();
        if (cat && Array.isArray(cat.targets) && cat.targets.length) STUDIO_TARGETS = cat.targets;
        if (cat && Array.isArray(cat.linkers) && cat.linkers.length) STUDIO_LINKERS = cat.linkers;
        if (cat && Array.isArray(cat.payloads) && cat.payloads.length) STUDIO_PAYLOADS = cat.payloads;
        if (cat && Array.isArray(cat.dars) && cat.dars.length) STUDIO_DAR_ITEMS = cat.dars;
        if (cat && Array.isArray(cat.fc_formats) && cat.fc_formats.length) {
          STUDIO_FC_ITEMS = cat.fc_formats.map((f) => ({
            id: f.id,
            ko: f.ko,
            en: f.en,
            isotype: f.isotype,
            isSilenced: Boolean(f.fc_silenced),
            fcActivity: f.fc_activity,
            adcc: f.adcc,
            popover: f.popover,
            popover_ko: f.popover_ko,
          }));
        }
      } catch (e) { /* embedded catalog already loaded */ }
    }

    restore();
    renderHeaderControls();
    renderActiveMode(false);
    await refreshBackendData();
    renderActiveMode(false);
  }

  start();
})();
