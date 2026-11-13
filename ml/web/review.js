/* Shared, side-effect-free summary formatter for ADCToX screen export. */
(function (root) {
  'use strict';

  function labState(value, error, flagged, checked, isReference) {
    if (value === undefined || value === null || String(value).trim() === '') {
      return isReference ? 'Default reference' : 'Not entered';
    }
    if (error) return 'Check input';
    if (flagged) return 'Review needed';
    return checked ? 'No flag triggered' : 'Entered';
  }

  function indicationText(indicated, hasCancer, ko) {
    if (!hasCancer) return ko ? '암종 미입력' : 'Cancer not entered';
    if (indicated === true) return ko ? '적응증 일치' : 'Cancer match';
    if (indicated === false) return ko ? '적응증 외 암종' : 'No cancer match';
    return ko ? '미평가' : 'Not assessed';
  }

  function formatConstructLine(label, item) {
    if (!item) return [];
    const lines = [
      `${label}: ${item.arch || '-'}`,
      `  Model Safety Score: ${item.safetyScore !== undefined ? item.safetyScore : '-'}/100 | Model Efficacy Score: ${item.efficacyScore !== undefined ? item.efficacyScore : '-'}/100${item.utility !== undefined ? ' | Utility U_TI: ' + item.utility : ''}`,
    ];
    if (item.optimalDose) lines.push(`  Modeled Optimal Dose: ${item.optimalDose}`);
    if (item.uncertainty) lines.push(`  5-Fold Ensemble Uncertainty: ${item.uncertainty}`);
    if (item.organRisks && item.organRisks.length) {
      lines.push(`  Modeled Organ Risks (ADCSurrogateNet v2): ${item.organRisks.join(', ')}`);
    }
    return lines;
  }

  function reviewText(app, conditions, raw, fields, result, ctx) {
    const ko = !!(ctx && ctx.lang === 'ko');
    const res = result || {};
    const patient = res.patient || {};
    const hasCancer = !!(patient.cancers || []).length;
    const lines = [
      ko ? 'ADCToX 분석 요약 보고서' : 'ADCToX Evidence & Design Summary',
      `App ${app && app.version ? app.version : 'unknown'} | Models ${app && app.models ? app.models : '5-fold ADCSurrogateNet v2'}`,
      `${ko ? '생성 시각' : 'Created'}: ${new Date().toISOString()}`,
    ];

    if (ctx) {
      const caseType = ctx.sampleCase
        ? (ko ? `가상 샘플 사례 (${ctx.sampleCase})` : `Virtual sample case (${ctx.sampleCase})`)
        : (ko ? '직접 입력 사례' : 'User-entered profile');
      lines.push(`${ko ? '사례 구분' : 'Case type'}: ${caseType}`);
      lines.push(`${ko ? '우선 보호 장기' : 'Priority organ'}: ${ctx.prioOrgan || (ko ? '자동 (없음)' : 'Automatic (none)')}`);
      lines.push(`${ko ? '비교 필터' : 'Comparison filter'}: ${ctx.matrixFilter === 'relevant' ? (ko ? '적응증 일치만 보기' : 'Cancer match only') : (ko ? '전체 15개 승인 ADC' : 'All 15 approved ADCs')}`);
    }

    lines.push('', ko ? '입력 질환 및 상태 (INPUTS)' : 'INPUTS');
    if (conditions && conditions.length) {
      for (const c of conditions) lines.push(`- ${c}`);
    } else {
      lines.push(ko ? '- 입력된 질환 없음' : '- None entered');
    }

    lines.push('', ko ? '검사 수치 (LAB VALUES)' : 'LAB VALUES');
    for (const field of fields || []) {
      const value = raw ? raw[field.key] : undefined;
      const entered = value !== undefined && value !== null && String(value).trim() !== '';
      const fallback = field.key.startsWith('uln_')
        ? (ko ? '기본 기준치 (Default reference)' : 'Default reference')
        : (ko ? '미입력 (Not entered)' : 'Not entered');
      lines.push(`${field.label}: ${entered ? value : fallback}${entered && field.unit ? ' ' + field.unit : ''}`);
    }
    if (ctx && Array.isArray(ctx.derivedNotes) && ctx.derivedNotes.length) {
      lines.push('', ko ? '자동 계산 지표 (DERIVED METRICS)' : 'DERIVED METRICS');
      for (const note of ctx.derivedNotes) lines.push(`- ${note}`);
    }

    lines.push('', ko ? '승인 ADC 비교 (ADC REVIEW - Source: FDA Label & ClinicalTrials.gov)' : 'ADC REVIEW');
    const rows = (ctx && Array.isArray(ctx.rows)) ? ctx.rows : (res.rows || []);
    for (const row of rows) {
      const detail = row.detail || {};
      const rankPrefix = (ctx && ctx.hasProfile === false)
        ? '[Catalog] '
        : (row.rank ? `#${row.rank} ` : '');
      lines.push(
        '',
        `${rankPrefix}${row.name}`,
        indicationText(row.indicated, hasCancer, ko),
        `Label status: ${row.status}${row.sure ? '' : ' (may depend on missing values)'} [Source: FDA DailyMed SPL]`
      );
      for (const reason of detail.reasons || []) {
        lines.push(`- ${reason.organ}: ${reason.status}; patient: ${reason.patient || 'Not entered'}; label condition: ${reason.basis}`);
      }
      for (const warning of detail.warnings || []) {
        lines.push(`- Patient organ: ${warning.organ} ${warning.mark} ${warning.text}`);
      }
      for (const warning of detail.other_warnings || []) {
        lines.push(`- Other organ: ${warning.organ} ${warning.mark} ${warning.text}`);
      }
      for (const missing of detail.missing || []) {
        lines.push(`- Missing: ${missing}`);
      }
      if (detail.indication) lines.push(`Approved uses: ${detail.indication}`);
      const trial = detail.trial;
      if (trial && trial.no_results) {
        lines.push(`No results in bundled trial snapshot: ${trial.trial}`);
      } else if (trial && trial.trial) {
        lines.push(
          `Study: ${trial.trial} (${trial.nct}) [Observed clinical cohort]`,
          `Population: ${trial.population || 'Not specified'}`,
          `Treatment: ${trial.regimen} (n=${trial.n})`
        );
        if (trial.comparator) lines.push(`Comparator: ${trial.comparator.regimen} (n=${trial.comparator.n})`);
        if (Array.isArray(trial.organs)) {
          for (const org of trial.organs.slice(0, 4)) {
            if (org && Array.isArray(org.events) && org.events.length) {
              lines.push(`  Trial AE (${org.organ}): ${org.events.map(e => e.text).join('; ')}`);
            }
          }
        }
        if (/^NCT\d{8}$/.test(trial.nct || '')) lines.push('https://clinicaltrials.gov/study/' + trial.nct);
      }
    }

    if (ctx && ctx.studio) {
      const st = ctx.studio;
      lines.push(
        '',
        ko ? '신규 ADC 설계 요약 (모델 추정)' : 'ADC DESIGN (Model estimates)',
        `${ko ? '실행 방식' : 'Execution mode'}: ${st.modeLabel || st.mode || 'Manual'}`,
        st.searchExecuted
          ? `${ko ? '탐색 조합 수' : 'Search space'}: ${st.totalCombinations} (${ko ? '호환 가능' : 'viable'}: ${st.compatibleCombinations || '-'})`
          : (ko ? '자동 탐색: 실행 전' : 'Auto search: not run'),
        `${ko ? '가중치 설정' : 'Scoring weights'}: ${st.presetLabel || 'Balanced'} (w_safe=${st.wSafe}, w_eff=${st.wEff}, gamma=${st.gamma}, beta=${st.beta})`
      );
      if (st.customSmiles) lines.push(`Custom Payload SMILES: ${st.customSmiles}`);
      lines.push(...formatConstructLine(ko ? '현재 선택/편집 설계 (Current Design)' : 'Current Edited Design', st.current));
      if (st.searchExecuted && st.optimal) {
        lines.push(...formatConstructLine(ko ? '탐색 선정 최적 설계 (Search Optimal Design)' : 'Search Optimal Design', st.optimal));
      }
      if (st.reference) {
        lines.push(...formatConstructLine(ko ? `승인 기준 약물 (${st.reference.name})` : `Approved Reference ADC (${st.reference.name})`, st.reference));
      }
    }

    return lines.join('\n');
  }

  const api = { labState, indicationText, reviewText };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ADCTOX_REVIEW = api;
})(typeof window === 'undefined' ? this : window);
