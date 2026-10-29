import { initProposals } from './proposal-view.js';
import { describeResult } from './result-view.js';

const roles = [['unconfirmed','Not reviewed'],['request','Current request'],['obstacle','Current obstacle'],['context','Background / context'],
  ['unclear','Unclear — ask customer'],['conditional','Conditional request'],['alternative','Alternative request'],
  ['negated','Not requested'],['resolved','Already resolved']];
const categories = ['ACCOUNT','CANCEL','CONTACT','DELIVERY','FEEDBACK','INVOICE','ORDER','PAYMENT','REFUND','SHIPPING','SUBSCRIPTION'];
function el(tag, text = '', className = '') {
  const node = document.createElement(tag); node.textContent = text;
  if (className) node.className = className;
  return node;
}
function select(label, values) {
  const wrapper = el('label', label), control = el('select');
  for (const [value, text] of values) control.add(new Option(text, value));
  wrapper.append(control); return [wrapper, control];
}
async function post(path, body, signal) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body), signal});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the message and retry.');
  return data;
}

// Fresh previews and fragment predictions are never persisted implicitly.
export function initBreakdown(host, getSource, stageNote = null, persistence = null) {
  const heading = el('h2', 'Understand the individual needs');
  heading.tabIndex = -1;
  const intro = el('p', 'Human-assisted preview · group related fragments under one customer goal, attach background, and review one category for each need.', 'section-description');
  const caution = el('p', 'Read the complete message when grouping fragments. Manual fragments are text boundaries; optional language-model proposals are unverified interpretations. You make the final decision.', 'technical-note');
  const proposalHost = el('section');
  const build = el('button', 'Break down message', 'secondary-button'); build.type = 'button';
  const feedback = el('p', '', 'technical-note'); feedback.setAttribute('role','status');
  const compact = el('p', 'No customer needs grouped yet.', 'need-summary'); compact.setAttribute('role','status');
  const reviewProgress=el('div','','review-progress');reviewProgress.hidden=true;reviewProgress.setAttribute('role','progressbar');reviewProgress.setAttribute('aria-label','Fragment review progress');reviewProgress.setAttribute('aria-valuemin','0');
  const progressFill=el('span');reviewProgress.append(progressFill);
  const nextReview=el('div','','next-review-action');nextReview.hidden=true;
  const nextText=el('p'), nextButton=el('button','Review next fragment','secondary-button');nextButton.type='button';nextReview.append(nextText,nextButton);
  const groupPanel = el('div', '', 'customer-needs');
  const addGroup = el('button', '+ Add customer need', 'secondary-button'); addGroup.type = 'button'; addGroup.hidden = true;
  const details = el('details', '', 'breakdown-details'); details.open = true; details.hidden = true;
  details.append(el('summary', 'Review fragments and assign them to needs'));
  const filters=el('div','','evidence-filters');filters.setAttribute('aria-label','Filter evidence by need');
  const emptyFilter=el('p','No fragments assigned to this need yet. Choose All fragments to assign evidence.','technical-note');emptyFilter.hidden=true;
  const results = el('div', '', 'breakdown-parts'); details.append(filters,emptyFilter,results);
  const footer = el('div'); footer.hidden = true;
  const questionLabel = el('label', 'Clarification question / coordination note');
  const question = el('textarea'); question.rows = 2; question.maxLength = 600;
  question.placeholder = 'Ask for the specific missing detail, or explain how the requests depend on one another.'; questionLabel.append(question);
  footer.append(questionLabel, el('p', 'Categories describe routing only. Offers, eligibility, account facts and approved actions require separate evidence. SUBSCRIPTION means newsletter preferences; actual order cancellation is ORDER.', 'technical-note'));
  const transfer = el('button', 'Add reviewed breakdown to note draft', 'secondary-button'); transfer.type = 'button';
  if (stageNote) footer.append(transfer, el('p','This fills the review note. Use Add note to save it explicitly. It creates no tasks and confirms no overall category.','technical-note'));
  const confirmation = el('label','I reviewed the proposed evidence, roles, categories and relationships against the complete message.');
  const confirmed = el('input'); confirmed.type='checkbox'; confirmation.prepend(confirmed); confirmation.className='proposal-confirmation'; confirmation.hidden=true; footer.append(confirmation);
  const relationPanel = el('div'); relationPanel.className='need-relations';
  const saveGroups = el('button', 'Save grouped review', 'primary-button'); saveGroups.type = 'button';
  if (persistence) footer.append(saveGroups, el('p', 'Explicitly saves your roles, need groups, categories and clarification. It does not confirm the overall category, change status or create tasks. Reviewer label above is required.', 'technical-note'));
  host.replaceChildren(heading, intro, caution, proposalHost, build, feedback, compact, reviewProgress, nextReview, groupPanel, relationPanel, addGroup, details, footer);
  let generation = 0, currentKey = null, records = [], preview = null;
  let groups = [], relations = [], modelDraft = false, selectedNeed = null;
  const proposalsUI = initProposals(proposalHost, getSource, document => restore(document, true));
  const controllers = new Set();
  const sourceKey = (source) => JSON.stringify([source?.key, source?.text, source?.mode]);
  const makeController = () => { const controller = new AbortController(); controllers.add(controller); return controller; };
  function reset() {
    proposalsUI.reset();
    ++generation; for (const controller of controllers) controller.abort(); controllers.clear();
    currentKey = null; preview = null; records = []; groups = []; relations = []; selectedNeed=null; reviewProgress.hidden=true; nextReview.hidden=true; filters.replaceChildren(); emptyFilter.hidden=true; modelDraft=false; confirmation.hidden=true; confirmed.checked=false; relationPanel.replaceChildren(); results.replaceChildren(); groupPanel.replaceChildren(); addGroup.hidden = true; details.open = true; details.hidden = true; compact.textContent = 'No customer needs grouped yet.'; footer.hidden = true; question.value = '';
    build.disabled = false; build.textContent = 'Break down message'; feedback.textContent = '';
    host.removeAttribute('aria-busy');
  }
  function valid(token, key) { return token === generation && key === sourceKey(getSource()); }
  function filterEvidence(id) {
    selectedNeed = id;
    for(const record of records) record.card.hidden = Boolean(id && record.group.value !== id);
    for(const group of groups) group.card.classList.toggle('selected-need',group.id===id);
    filters.querySelectorAll('button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.need === (id || 'all'))));
    emptyFilter.hidden = !id || records.some(record=>record.group.value===id);
  }
  function updateReviewNavigation() {
    const done=records.filter(record=>record.role.value!=='unconfirmed').length;
    reviewProgress.hidden=!records.length;nextReview.hidden=!records.length;
    reviewProgress.setAttribute('aria-valuemax',String(records.length));reviewProgress.setAttribute('aria-valuenow',String(done));progressFill.style.width=`${records.length ? done/records.length*100 : 0}%`;
    const unreviewed=records.find(record=>record.role.value==='unconfirmed');
    const unassigned=records.find(record=>['request','obstacle','unclear','conditional','alternative'].includes(record.role.value) && !record.group.value);
    const pendingNeed=groups.find(group=>!group.title.value.trim() || !group.category.value);
    const needsQuestion=!question.value.trim() && (relations.length || records.some(record=>['unclear','conditional','alternative'].includes(record.role.value)) || groups.some(group=>group.category.value==='UNCLEAR' || group.kind.value==='unclear'));
    nextText.textContent=unreviewed ? `Next: decide what fragment ${records.indexOf(unreviewed)+1} means. ${records.length-done} left to review.`
      : unassigned ? 'Next: attach each current or unresolved request to a customer need.'
      : pendingNeed ? 'Next: give each customer need a title and category.'
      : needsQuestion ? 'Next: add a clarification question or explain the relationship.'
      : modelDraft && !confirmed.checked ? 'Next: confirm that you reviewed the model interpretations against the original message.'
      : 'All fragment interpretations selected. Review the grouped needs before saving.';
    nextButton.textContent=unreviewed?'Review next fragment':unassigned && !groups.length?'Create first need':unassigned?'Assign a need':pendingNeed?'Finish need details':needsQuestion?'Add clarification':modelDraft && !confirmed.checked?'Review model draft':'View need summary';
    nextButton.onclick=()=>{
      filterEvidence(null);details.open=true;
      if(!unreviewed && unassigned && !groups.length){const group=addNeed();group?.title.focus();return;}
      const record=unreviewed || unassigned;
      if(record){const target=unreviewed?record.role:record.group;target.focus({preventScroll:true});record.card.scrollIntoView({block:'center',behavior:'instant'});}
      else if(pendingNeed){const target=!pendingNeed.title.value.trim()?pendingNeed.title:pendingNeed.category;target.focus();}
      else if(needsQuestion){question.focus();}
      else if(modelDraft && !confirmed.checked){confirmed.focus();}
      else{compact.tabIndex=-1;compact.focus({preventScroll:true});compact.scrollIntoView({block:'center',behavior:'instant'});}
    };
    filters.replaceChildren();
    for(const [id,label] of [[null,'All fragments'],...groups.map(group=>[group.id,group.title.value.trim() || group.id])]){
      const button=el('button',label,'evidence-filter');button.type='button';button.dataset.need=id || 'all';button.title=label;
      button.addEventListener('click',()=>filterEvidence(id));filters.append(button);
    }
    if(selectedNeed && !groups.some(group=>group.id===selectedNeed))selectedNeed=null;
    filterEvidence(selectedNeed);
  }
  function syncGroups(invalidate = true) {
    for (const record of records) {
      for(const radio of record.shortcuts)radio.checked=radio.value===record.role.value;
      record.badge.textContent=roles.find(([value])=>value===record.role.value)?.[1] || 'Not reviewed';
      record.badge.dataset.role=record.role.value;
      const previous = record.group.value;
      record.group.replaceChildren(new Option('Not assigned to a need', ''));
      for (const group of groups) record.group.add(new Option(group.title.value.trim() || group.id, group.id));
      record.group.value = groups.some(g => g.id === previous) ? previous : '';
      record.category.disabled = record.role.value !== 'request' || Boolean(record.group.value);
      if (record.group.value) record.category.value = '';
      record.categoryLabel.hidden = record.role.value !== 'request' || Boolean(record.group.value);
      record.assess.hidden = Boolean(record.group.value);
      record.prediction.hidden = Boolean(record.group.value);
      record.ownership.hidden = !record.group.value;
      const selected = groups.find(g => g.id === record.group.value);
      if (selected) record.ownership.textContent = record.role.value === 'context'
        ? 'Background supporting this need; not classified as a separate request.'
        : `Uses the need category above: ${selected.category.value || 'not classified yet'}.`;
    }
    for (const group of groups) {
      const members = records.filter(r => r.group.value === group.id);
      const requestCount = members.filter(r => r.role.value === 'request').length;
      const obstacleCount = members.filter(r => r.role.value === 'obstacle').length;
      const background = members.filter(r => r.role.value === 'context').length;
      group.members.textContent = `${requestCount} current request fragment(s)${obstacleCount ? ` · ${obstacleCount} obstacle fragment(s)` : ''} · ${background} background fragment(s) · ${members.length} total assigned`;
      if (invalidate) { ++group.call; group.pending = false; group.result.textContent = 'Optional suggestion uses the selected original evidence. Your category remains your choice.'; }
      group.assess.disabled = group.pending || !(requestCount + obstacleCount) || members.some(r => !['request','obstacle','context'].includes(r.role.value));
    }
    compact.textContent = `${groups.length} customer need(s) drafted by you · ${records.filter(r => r.role.value === 'context').length} background fragment(s) · ${records.filter(r => r.role.value !== 'unconfirmed').length}/${records.length} fragments reviewed`;
    addGroup.disabled = groups.length >= 12;
    updateReviewNavigation();
  }
  function addNeed(saved = null) {
    if (groups.length >= 12) return;
    const id = saved?.id || Array.from({length:12}, (_,index) => `need-${index+1}`).find(id => !groups.some(group => group.id === id));
    const card = el('article', '', 'customer-need'); card.dataset.needId = id;
    const titleLabel = el('label', 'Customer need / goal'), title = el('input');
    title.type = 'text'; title.maxLength = 160; title.placeholder = 'Describe one current customer goal'; title.value = saved?.title || ''; titleLabel.append(title);
    const [categoryLabel, category] = select('Your category for this need', [['','Choose a category'],...categories.map(c => [c,c]),['OUTSIDE_SCOPE','Outside current categories'],['UNCLEAR','Unclear']]);
    category.value = saved?.category || '';
    const [kindLabel, kind] = select('Need type', [['goal','Goal'],['obstacle','Obstacle'],['unclear','Unclear']]);
    kind.value = saved?.kind || 'goal';
    const members = el('p', '', 'technical-note');
    const assess = el('button', 'Suggest category using need evidence', 'secondary-button'); assess.type = 'button';
    const result = el('p', '', 'technical-note'); result.setAttribute('role','status');
    const remove = el('button', 'Remove need', 'text-button'); remove.type = 'button';
    const groupHeading = el('h3', saved?.title || `Your need ${id.slice(5)}`);
    const group = {id, title, kind, category, card, members, assess, result, call:0, pending:false}; groups.push(group);
    const inspect=el('button','Inspect assigned evidence','text-button');inspect.type='button';inspect.addEventListener('click',()=>{details.open=true;filterEvidence(id);details.scrollIntoView({block:'start',behavior:'instant'});});
    card.append(groupHeading, titleLabel, kindLabel, categoryLabel, members, assess, result, inspect, remove);
    groupPanel.append(card);
    title.addEventListener('input', () => { groupHeading.textContent = title.value.trim() || `Your need ${id.slice(5)}`; syncGroups(false); });
    category.addEventListener('change', () => syncGroups(false));
    kind.addEventListener('change', () => syncGroups(false));
    remove.addEventListener('click', () => { ++group.call; groups = groups.filter(g => g !== group); relations = relations.filter(r => r.source !== group.id && r.target !== group.id); card.remove(); renderRelations(); syncGroups(); });
    assess.addEventListener('click', async () => {
      if (assess.disabled) return;
      const source = getSource(), token = generation, key = sourceKey(source), attempt = ++group.call;
      const evidence = records.filter(r => r.group.value === id).map(r => r.part.text).join('\n');
      group.pending = true; assess.disabled = true; result.textContent = 'Assessing the selected need evidence…';
      const controller = makeController(), timer = setTimeout(() => controller.abort(),15000);
      try {
        const data = await post('/predict', {text:evidence,mode:source.mode,check_multiple_requests:false},controller.signal);
        if (!valid(token,key) || attempt !== group.call || !groups.includes(group)) return;
        result.textContent = `${describeResult(data).title} · ${data.model_name}. Grouped-evidence hypothesis, not a context-trained extractor. It may miss references or relationships. Your category remains your choice.`;
      } catch (error) {
        if (valid(token,key) && attempt === group.call) result.textContent = error.name === 'AbortError' ? 'Timed out. Retry or classify manually.' : `${error.message} You can classify manually.`;
      } finally {
        clearTimeout(timer); controllers.delete(controller);
        if (valid(token,key) && attempt === group.call) { group.pending = false; syncGroups(false); }
      }
    });
    syncGroups(); return group;
  }
  question.addEventListener('input',updateReviewNavigation);
  confirmed.addEventListener('change',updateReviewNavigation);
  addGroup.addEventListener('click', () => { const group = addNeed(); if (group) group.title.focus(); });
  function renderRelations() {
    relationPanel.replaceChildren();
    for (const relation of relations) {
      const card=el('article','','need-relation');
      card.append(el('strong',`Review hypothesis: ${relation.source} → ${relation.target}`));
      const [kindLabel,kind]=select('Relationship type',[['may_block','May block'],['depends_on','Depends on'],['alternative_to','Alternative to']]);kind.value=relation.kind;
      kind.addEventListener('change',()=>{relation.kind=kind.value;});
      const label=el('label','Relationship note'), note=el('textarea');note.rows=2;note.maxLength=300;note.value=relation.note;label.append(note);
      note.addEventListener('input',()=>{relation.note=note.value;});
      const evidence=el('details');evidence.append(el('summary','Supporting original evidence'));
      for(const id of relation.evidence_parts){const part=records.find(r=>r.part.id===id);if(part)evidence.append(el('blockquote',`${id}: ${part.part.text}`));}
      const remove=el('button','Remove relationship','text-button');remove.type='button';remove.addEventListener('click',()=>{relations=relations.filter(r=>r!==relation);renderRelations();});
      card.append(kindLabel,label,evidence,remove);relationPanel.append(card);
    }
  }
  function reviewedDocument() {
    if (!preview || currentKey !== sourceKey(getSource())) throw new Error('Generate a fresh preview for this message first.');
    if (modelDraft && !confirmed.checked) throw new Error('Confirm that you reviewed the model draft before saving or staging it.');
    if (records.some(r => r.role.value === 'unconfirmed')) throw new Error('Review the interpretation of every fragment first.');
    if (records.some(r => ['request','obstacle','unclear','conditional','alternative'].includes(r.role.value) && !r.group.value)) throw new Error('Assign each current or unresolved request to a customer need.');
    for (const group of groups) {
      if (!group.title.value.trim() || !group.category.value) throw new Error('Give each need a title and human category (or choose Outside current categories / Unclear).');
      if (!records.some(r => r.group.value === group.id && ['request','obstacle','unclear','conditional','alternative'].includes(r.role.value))) throw new Error('Background alone is not a current need. Assign a current or unresolved request, or remove the empty need.');
    }
    if ((records.some(r => ['unclear','conditional','alternative'].includes(r.role.value)) || groups.some(g => g.category.value === 'UNCLEAR' || g.kind.value === 'unclear') || relations.length) && !question.value.trim()) throw new Error('Add a clarification question or relationship note for unresolved requests.');
    return {schema_version:2, source_text:preview.source_text,
      parts:records.map(r => ({id:r.part.id,start:r.part.start,end:r.part.end,text:r.part.text,role:r.role.value,group_id:r.group.value || null,category:r.category.value || null})),
      groups:groups.map(g => ({id:g.id,title:g.title.value.trim(),category:g.category.value,kind:g.kind.value})), relations:structuredClone(relations), clarification:question.value.trim()};
  }
  saveGroups.addEventListener('click', async () => {
    let document;
    try { document = reviewedDocument(); } catch (error) { feedback.textContent = error.message; return; }
    const token = generation;
    const controls = [...host.querySelectorAll('button,input,select,textarea')].map(node => [node,node.disabled]);
    controls.forEach(([node]) => { node.disabled = true; });
    feedback.textContent = 'Saving grouped review…';
    try {
      await persistence.save(document);
      if (token === generation) feedback.textContent = 'Grouped review saved locally. Handling status and overall category are unchanged.';
    } catch (error) { if (token === generation) feedback.textContent = error.message; }
    finally { if (token === generation) controls.forEach(([node,disabled]) => { node.disabled = disabled; }); }
  });
  function drawPart(part, index, token, key, mode) {
    const card = el('article', '', 'breakdown-part');
    const badge=el('span','Not reviewed','role-badge');
    const cardHeader=el('div','','fragment-heading');cardHeader.append(el('h3',`Fragment ${index+1}`),badge);
    card.append(cardHeader, el('blockquote', part.text, 'saved-message'),
      el('p', `Original characters ${part.start}–${part.end} · boundaries need review`, 'technical-note'));
    if (part.coordination_cue) card.append(el('p', 'Possible condition or alternative. Confirm the relationship against the complete message.', 'technical-note'));
    const [roleLabel, role] = select('Your interpretation', roles);
    const quick=el('fieldset','','role-shortcuts');quick.append(el('legend',`Quick interpretation for fragment ${index+1}`,'sr-only'));
    const shortcuts=[], radioName=`role-${crypto.randomUUID()}`;
    for(const [value,label] of [['request','Request'],['context','Context'],['unclear','Unclear']]){
      const wrapper=el('label','','role-shortcut'), radio=el('input');radio.type='radio';radio.name=radioName;radio.value=value;
      wrapper.append(radio,el('span',label));quick.append(wrapper);shortcuts.push(radio);
      radio.addEventListener('change',()=>{if(radio.checked){role.value=value;role.dispatchEvent(new Event('change'));}});
    }
    card.append(quick);
    const [groupLabel, group] = select('Attach to customer need', [['','Not assigned to a need']]);
    const [categoryLabel, category] = select('Your category for this fragment', [['','Not classified'],...categories.map(c => [c,c]),['OUTSIDE_SCOPE','Outside current categories'],['UNCLEAR','Unclear']]);
    category.disabled = true;
    const controls = el('div', '', 'breakdown-controls'); controls.append(roleLabel, groupLabel, categoryLabel); card.append(controls);
    const assess = el('button', 'Suggest category for this request', 'secondary-button'); assess.type = 'button'; assess.disabled = true;
    const prediction = el('p', 'Confirm that this fragment is a current request before asking a model to classify it.', 'technical-note'); prediction.setAttribute('role','status');
    const ownership = el('p', '', 'technical-note'); ownership.hidden = true; controls.append(ownership);
    const record = {part, card, badge, shortcuts, role, group, category, categoryLabel, ownership, assess, prediction, result:null}; records.push(record);
    group.addEventListener('change', () => syncGroups());
    let assessing = false, call = 0;
    role.addEventListener('change', () => {
      ++call; record.result = null; category.value = ''; category.disabled = role.value !== 'request';
      assess.disabled = role.value !== 'request'; assessing = false;
      prediction.textContent = role.value === 'request' ? 'Choose a category yourself or request a separate model suggestion. The full message may change its meaning.'
        : 'No category suggestion for background, unresolved relationships, unclear or excluded requests.';
      syncGroups();
    });
    assess.addEventListener('click', async () => {
      if (assessing || role.value !== 'request') return;
      const attempt = ++call; assessing = true; assess.disabled = true; prediction.textContent = 'Assessing this fragment…';
      const controller = makeController(), timer = setTimeout(() => controller.abort(),15000);
      try {
        const data = await post('/predict',{text:part.text, mode, check_multiple_requests:false},controller.signal);
        if (!valid(token,key) || call !== attempt) return;
        record.result = data;
        prediction.textContent = `${describeResult(data).title} · ${data.model_name}. Fragment-only hypothesis; review with the complete message. Your category remains your choice.`;
      } catch (error) {
        if (valid(token,key) && call === attempt) prediction.textContent = error.name === 'AbortError' ? 'Timed out. Retry or classify manually.' : `${error.message} You can classify manually.`;
      } finally {
        clearTimeout(timer); controllers.delete(controller);
        if (valid(token,key) && call === attempt) { assessing = false; assess.disabled = role.value !== 'request'; }
      }
    });
    card.append(assess,prediction); return card;
  }
  build.addEventListener('click', async () => {
    reset(); const source = getSource(), token = generation, key = sourceKey(source);
    if (!source?.text?.trim() || Array.from(source.text).length > 2000) { feedback.textContent = 'Enter a message of 1–2,000 characters first.'; return; }
    currentKey = key; build.disabled = true; host.setAttribute('aria-busy','true'); feedback.textContent = 'Preparing text fragments…';
    const controller = makeController(), timer = setTimeout(() => controller.abort(),15000);
    try {
      const data = await post('/breakdown',{text:source.text},controller.signal);
      if (!valid(token,key)) return;
      preview = data;
      results.replaceChildren(...data.parts.map((part,index) => drawPart(part,index,token,key,source.mode)));
      footer.hidden = false; addGroup.hidden = false; details.hidden = false; syncGroups();
      feedback.textContent = `${data.parts.length} text fragment(s), not a verified count of needs. All interpretations start unconfirmed.${data.grouped_remainder ? ' The last fragment groups the remaining text; inspect it for additional needs.' : ''}`;
    } catch (error) { if (valid(token,key)) feedback.textContent = error.name === 'AbortError' ? 'Timed out. Retry the preview.' : error.message; }
    finally {
      clearTimeout(timer); controllers.delete(controller);
      if (token === generation) { build.disabled = false; host.removeAttribute('aria-busy'); }
    }
  });
  transfer.addEventListener('click', () => {
    if (!preview || currentKey !== sourceKey(getSource())) { reset(); return; }
    if (groups.length) { try { reviewedDocument(); } catch (error) { feedback.textContent = error.message; return; } }
    if (records.some(r => r.role.value === 'unconfirmed')) { feedback.textContent = 'Review the interpretation of every fragment first.'; return; }
    if (records.some(r => r.role.value === 'request' && !r.group.value && !r.category.value)) { feedback.textContent = 'Choose a human category, Outside current categories or Unclear for each current request.'; return; }
    if (records.some(r => ['unclear','conditional','alternative'].includes(r.role.value) || r.category.value === 'UNCLEAR') && !question.value.trim()) {
      feedback.textContent = 'Add a clarification question or explain the relationship before staging this note.'; question.focus(); return;
    }
    const lines = ['Human-assisted breakdown v1. Evidence ranges use original Unicode character offsets.'];
    for (const r of records) {
      const p = r.result;
      lines.push(`[${r.part.start}:${r.part.end}] Human: ${r.role.value}${r.category.value ? ' / '+r.category.value : ''}.${p ? ` Model hypothesis (${p.model_mode}): ${p.suggested_category ?? 'withheld'}; sha256=${p.model_sha256}.` : ''}`);
    }
    for (const g of groups) lines.push(`Human need ${g.id}: ${g.title.value.trim() || 'Untitled'} / ${g.category.value || 'Unclassified'}; evidence fragments: ${records.filter(r => r.group.value === g.id).map(r => r.part.id).join(', ')}.`);
    for (const relation of relations) lines.push(`Relationship hypothesis: ${relation.source} ${relation.kind} ${relation.target}; evidence: ${relation.evidence_parts.join(', ')}; ${relation.note}`);
    if (question.value.trim()) lines.push('Clarification / coordination: '+question.value.trim());
    const error = stageNote(lines.join('\n'));
    feedback.textContent = error || 'Added to the note draft. Review it and use Add note to save; status and overall category are unchanged.';
  });
  function open() {
    // Reopening the same preview must preserve the reviewer's unsaved choices.
    if (currentKey !== sourceKey(getSource()) || (!preview && !build.disabled)) build.click();
    heading.focus({preventScroll:true});
    host.scrollIntoView({block:'start', behavior:'instant'});
  }
  function restore(document, fromProposal = false) {
    reset(); if (!document) return;
    const source = getSource(); if (document.source_text !== source?.text) return;
    currentKey = sourceKey(source); preview = {source_text:document.source_text,parts:document.parts};
    results.replaceChildren(...document.parts.map((part,index) => drawPart(part,index,generation,currentKey,source.mode)));
    for (const saved of document.groups) addNeed(saved);
    for (const record of records) {
      const saved = document.parts.find(p => p.id === record.part.id);
      record.role.value = saved.role; record.role.dispatchEvent(new Event('change'));
      record.group.value = saved.group_id || ''; record.category.value = saved.category || '';
    }
    relations = structuredClone(document.relations || []); renderRelations();
    modelDraft = fromProposal; confirmation.hidden = !fromProposal; confirmed.checked = false;
    question.value = document.clarification; footer.hidden = false; addGroup.hidden = false; details.hidden = false; details.open = false; syncGroups();
    details.open = fromProposal;
    feedback.textContent = fromProposal ? 'Model proposals loaded as an unsaved draft. Review and confirm them before saving.' : 'Loaded the last saved human review. Model hypotheses are not restored as human decisions.';
  }
  return {reset, open, restore};
}
