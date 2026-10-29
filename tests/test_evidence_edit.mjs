import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../support_ticket_ai/web/evidence-edit.js',import.meta.url));
const {editEvidence}=await import(`data:text/javascript;base64,${source.toString('base64')}`);
function plan(){return {schema_version:2,source_text:'😀 Find order. Cannot log in.',
 parts:[{id:'part-1',start:0,end:13,text:'😀 Find order.',role:'request',group_id:'need-1',category:null},
 {id:'part-2',start:14,end:28,text:'Cannot log in.',role:'obstacle',group_id:'need-2',category:null}],
 groups:[{id:'need-1',title:'Order',category:'ORDER',kind:'goal'},{id:'need-2',title:'Login',category:'ACCOUNT',kind:'obstacle'}],
 relations:[{source:'need-2',target:'need-1',kind:'may_block',evidence_parts:['part-1','part-2'],note:'Check dependency'}],clarification:'What happens?'};}
test('Unicode split preserves exact text and clears only changed interpretation',()=>{
 const original=plan(), edited=editEvidence(original,'split',0,2);
 assert.equal(edited.parts[0].text,'😀 ');assert.equal(edited.parts[1].text,'Find order.');
 assert.equal(edited.parts[2].text,'Cannot log in.');assert.equal(edited.parts[2].role,'obstacle');
 assert.equal(edited.parts[2].id,'part-3');assert.equal(edited.parts[0].role,'unconfirmed');
 assert.equal(edited.parts[0].group_id,null);assert.equal(edited.relations.length,0);
 assert.equal(original.parts.length,2);assert.equal(original.relations.length,1);
 for(const part of edited.parts)assert.equal(Array.from(original.source_text).slice(part.start,part.end).join(''),part.text);
});
test('merge retains intervening original whitespace and requires re-review',()=>{
 const edited=editEvidence(plan(),'merge',0);
 assert.equal(edited.parts.length,1);assert.equal(edited.parts[0].text,edited.source_text);
 assert.equal(edited.parts[0].role,'unconfirmed');assert.equal(edited.parts[0].group_id,null);
});
test('empty, outside, terminal and fractional edits rejected',()=>{
 for(const offset of [0,13,14,2.5])assert.throws(()=>editEvidence(plan(),'split',0,offset));
 assert.throws(()=>editEvidence(plan(),'merge',1));
});
