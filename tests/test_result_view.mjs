import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source = await readFile(new URL('../support_ticket_ai/web/result-view.js', import.meta.url));
const {describeResult, technicalFacts} = await import(`data:text/javascript;base64,${source.toString('base64')}`);
const suggested = {decision:'suggestion', suggested_category:'REFUND', uncalibrated_probability:.822, abstention_threshold:.5, requires_human_review:true, review_reason:'Recorded note'};
const withheld = {...suggested, decision:'abstain', suggested_category:null, uncalibrated_probability:.557, abstention_threshold:.7};

test('a suggestion is a review task, never a claimed explanation of category choice', () => {
 const r=describeResult(suggested);
 assert.equal(r.title,'Refund'); assert.equal(r.status,'Category suggested');
 assert.deepEqual(r.reasons,[]); assert.match(r.nextDescription,/can still be wrong/);
 assert.equal(r.recordedNote,'Recorded note');
});
test('word withholding is derived from its actual cutoff, not a generic semantic warning', () => {
 const r=describeResult(withheld);
 assert.equal(r.status,'Needs manual classification'); assert.equal(r.title,'Category withheld');
 assert.deepEqual(r.reasons.map(r=>r.code),['category']);
});
test('all simultaneously returned withholding conditions are visible', () => {
 const r=describeResult({...withheld,input_truncated:true,scope_score:.1,scope_threshold:.5,multiple_requests_detected:true});
 assert.deepEqual(r.reasons.map(r=>r.code),['truncated','scope','category','multiple']);
 assert.match(r.nextDescription,/each requested outcome/);
 assert.match(r.reasons[1].description,/does not prove/);
});
test('equal cutoff passes; no false reason at the boundary', () => {
 const r=describeResult({...withheld,uncalibrated_probability:.7,scope_score:.5,scope_threshold:.5});
 assert.deepEqual(r.reasons.map(r=>r.code),['policy']);
});
test('absent, string, nonfinite and out-of-range fields cannot manufacture a reason', () => {
 for(const score of [null,undefined,'0.1',NaN,Infinity,-.1,1.1]){
  const r=describeResult({...withheld,uncalibrated_probability:score,scope_score:score,scope_threshold:.5});
  assert.deepEqual(r.reasons.map(r=>r.code),['policy']);
 }
});
test('unknown withholding stays explicit; never infer reasons by parsing free text', () => {
 const r=describeResult({...withheld,abstention_threshold:null,review_reason:'scope truncated separate requests'});
 assert.deepEqual(r.reasons.map(r=>r.code),['policy']);
 assert.equal(r.recordedNote,'scope truncated separate requests');
});
test('a returned suggestion is not relabelled or withheld by the presentation layer', () => {
 const r=describeResult({...suggested,input_truncated:true,scope_score:.1,scope_threshold:.5});
 assert.equal(r.withheld,false); assert.equal(r.title,'Refund'); assert.deepEqual(r.reasons,[]);
});
test('missing technical values are not converted to zeros or implied passing checks', () => {
 const facts=Object.fromEntries(technicalFacts({uncalibrated_probability:.557}));
 assert.equal(facts['Category score · uncalibrated'],'0.557');
 assert.equal(facts['Scope score · uncalibrated'],'Not provided');
 assert.equal(facts['Encoder truncation reported'],'Not provided');
 assert.equal(facts['Separate-request check'],'Off / not reported');
});
test('an enabled guard with no flag is not proof of a single intent', () => {
 const facts=Object.fromEntries(technicalFacts({...suggested,multiple_request_check_enabled:true,multiple_requests_detected:false}));
 assert.equal(facts['Separate-request check'],'Enabled · no flag reported');
});
test('describing a result leaves the recorded decision and scores intact', () => {
 const original=structuredClone(withheld); describeResult(withheld);technicalFacts(withheld);
 assert.deepEqual(withheld,original);
});
