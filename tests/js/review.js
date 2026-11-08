const assert = require('node:assert/strict');
const { labState, indicationText, reviewText } = require('../../ml/web/review.js');
assert.equal(labState('', false, false, false, false), 'Not entered');
assert.equal(labState('', false, false, false, true), 'Default reference');
assert.equal(labState(0, false, false, true), 'No flag triggered');
assert.equal(labState('0,8', true, false, false), 'Check input');
assert.equal(labState(45, false, true, false), 'Review needed');
assert.equal(indicationText(true, false), 'Cancer not entered');
assert.equal(indicationText(false, true), 'No cancer match');
assert.equal(indicationText(undefined, true), 'Not assessed');
const text = reviewText({version:'test',models:'0.8'}, ['Heart failure'], {lvef:0},
  [{key:'lvef',label:'LVEF',unit:'%'},{key:'creatinine',label:'Creatinine'}],
  {patient:{cancers:[]},rows:[{name:'Example',status:'Not studied',sure:false,
    detail:{missing:['Bilirubin'],reasons:[{organ:'Cardio',status:'Not studied',patient:'Heart failure',basis:'LVEF < 50%'}]}}]});
assert.match(text,/LVEF: 0 %/);
assert.match(text,/Creatinine: Not entered/);
assert.match(text,/Cancer not entered/);
assert.match(text,/may depend on missing values/);
assert.match(text,/Missing: Bilirubin/);
assert.match(text,/label condition: LVEF < 50%/);
console.log('Review state and export checks passed');
