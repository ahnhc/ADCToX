const assert = require('node:assert/strict');
const { labState, indicationText, reviewText } = require('../../ml/web/review.js');

assert.equal(labState('', null, false, false, false), 'Not entered');
assert.equal(labState('', null, false, false, true), 'Default reference');
assert.equal(indicationText(null, false, true), '진단 미입력');

const current = { arch: 'HER2 / GGFG / DXd / DAR 4', safetyScore: 80, efficacyScore: 70 };
const optimal = { arch: 'TROP2 / GGFG / DXd / DAR 6', safetyScore: 85, efficacyScore: 75 };
const studio = { current, optimal, totalCombinations: '368,640', compatibleCombinations: '20,000' };
const render = (lang, searchExecuted) => reviewText(
  { version: 'test', models: 'test' }, [], {}, [{ key: 'creatinine', label: 'Creatinine', unit: 'mg/dL' }],
  { rows: [{ name: 'Reference', detail: { reasons: [{ organ: 'renal', status: 'Monitor', basis: 'CrCl < 30' }] } }] },
  { lang, studio: { ...studio, searchExecuted } }
);

for (const lang of ['ko', 'en']) {
  const manual = render(lang, false);
  assert(manual.includes(current.arch));
  assert(!manual.includes(optimal.arch));
  assert(!manual.includes('368,640'));
  assert(!manual.includes('실행 방식'));
  assert(!manual.includes('실행 전'));
  assert(manual.includes(lang === 'ko' ? '신규 설계' : 'New Design'));
  assert(manual.includes('Not entered'));
  assert(manual.includes('CrCl < 30'));
  const auto = render(lang, true);
  assert(auto.includes(optimal.arch));
  assert(auto.includes('368,640'));
}

console.log('PASS review preserves unknown inputs and separates manual evaluation from auto search');
