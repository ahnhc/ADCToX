/* Shared, side-effect-free presentation rules for the review screen and download. */
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
  function indicationText(indicated, hasCancer) {
    if (!hasCancer) return 'Cancer not entered';
    return indicated === true ? 'Cancer match' : indicated === false ? 'No cancer match' : 'Not assessed';
  }
  function reviewText(app, conditions, raw, fields, result) {
    const patient = result.patient || {};
    const lines = [
      'ADCToX evidence review', `App ${app.version || 'unknown'} | Models ${app.models || 'unknown'}`,
      `Created: ${new Date().toISOString()}`, '',
      'Review order is not a prediction of toxicity or treatment benefit.',
      'Cancer matches require confirmation of the full approved indication.',
      '', 'INPUTS', ...conditions.map(c => `- ${c}`), '', 'LAB VALUES',
    ];
    for (const field of fields) {
      const value = raw[field.key];
      const entered = value !== undefined && value !== null && String(value).trim() !== '';
      lines.push(`${field.label}: ${entered ? value : field.key.startsWith('uln_') ? 'Default reference' : 'Not entered'}${entered && field.unit ? ' ' + field.unit : ''}`);
    }
    lines.push('', 'ADC REVIEW');
    for (const row of result.rows || []) {
      const detail = row.detail || {};
      lines.push('', row.name, indicationText(row.indicated, !!(patient.cancers || []).length),
        `Label status: ${row.status}${row.sure ? '' : ' (may depend on missing values)'}`);
      for (const reason of detail.reasons || []) lines.push(`- ${reason.organ}: ${reason.status}; patient: ${reason.patient || 'Not entered'}; label condition: ${reason.basis}`);
      for (const warning of detail.warnings || []) lines.push(`- Patient organ: ${warning.organ} ${warning.mark} ${warning.text}`);
      for (const warning of detail.other_warnings || []) lines.push(`- Other organ: ${warning.organ} ${warning.mark} ${warning.text}`);
      for (const missing of detail.missing || []) lines.push(`- Missing: ${missing}`);
      if (detail.indication) lines.push(`Approved uses: ${detail.indication}`);
    }
    lines.push('', 'Trial percentages, when shown in the app, describe study groups, not this patient.');
    return lines.join('\n');
  }
  const api = { labState, indicationText, reviewText };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ADCTOX_REVIEW = api;
})(typeof window === 'undefined' ? this : window);
