import { describeResult } from './result-view.js';

const roles = [['unconfirmed','Not reviewed'],['request','Current request'],['context','Background / context'],
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
export function initBreakdown(host, getSource, stageNote = null) {
  const heading = el('h2', 'Understand the individual needs');
  const intro = el('p', 'Human-assisted preview · inspect fragments, distinguish requests from background, and assess each confirmed request separately.', 'section-description');
  const caution = el('p', 'This preview uses text boundaries, not a trained intent extractor. Read the complete message: a fragment may contain several needs or depend on another fragment. Nothing here changes the overall prediction or handling status.', 'technical-note');
  const build = el('button', 'Break down message', 'secondary-button'); build.type = 'button';
  const feedback = el('p', '', 'technical-note'); feedback.setAttribute('role','status');
  const results = el('div', '', 'breakdown-parts');
  const footer = el('div'); footer.hidden = true;
  const questionLabel = el('label', 'Clarification question / coordination note');
  const question = el('textarea'); question.rows = 2; question.maxLength = 600;
  question.placeholder = 'For example: Do you mean your order history has disappeared?'; questionLabel.append(question);
  footer.append(questionLabel, el('p', 'Categories describe routing only. Offers, eligibility, account facts and approved actions require separate evidence. SUBSCRIPTION means newsletter preferences; actual order cancellation is ORDER.', 'technical-note'));
  const transfer = el('button', 'Add reviewed breakdown to note draft', 'secondary-button'); transfer.type = 'button';
  if (stageNote) footer.append(transfer, el('p','This fills the review note. Use Add note to save it explicitly. It creates no tasks and confirms no overall category.','technical-note'));
  host.replaceChildren(heading, intro, caution, build, feedback, results, footer);
  let generation = 0, currentKey = null, records = [], preview = null;
  const controllers = new Set();
  const sourceKey = (source) => JSON.stringify([source?.key, source?.text, source?.mode]);
  const makeController = () => { const controller = new AbortController(); controllers.add(controller); return controller; };
  function reset() {
    ++generation; for (const controller of controllers) controller.abort(); controllers.clear();
    currentKey = null; preview = null; records = []; results.replaceChildren(); footer.hidden = true; question.value = '';
    build.disabled = false; build.textContent = 'Break down message'; feedback.textContent = '';
    host.removeAttribute('aria-busy');
  }
  function valid(token, key) { return token === generation && key === sourceKey(getSource()); }
  function drawPart(part, index, token, key, mode) {
    const card = el('article', '', 'breakdown-part');
    card.append(el('h3', `Fragment ${index + 1}`), el('blockquote', part.text, 'saved-message'),
      el('p', `Original characters ${part.start}–${part.end} · boundaries need review`, 'technical-note'));
    if (part.coordination_cue) card.append(el('p', 'Possible condition or alternative. Confirm the relationship against the complete message.', 'technical-note'));
    const [roleLabel, role] = select('Your interpretation', roles);
    const [categoryLabel, category] = select('Your category for this fragment', [['','Not classified'],...categories.map(c => [c,c]),['OUTSIDE_SCOPE','Outside current categories'],['UNCLEAR','Unclear']]);
    category.disabled = true;
    const controls = el('div', '', 'breakdown-controls'); controls.append(roleLabel, categoryLabel); card.append(controls);
    const assess = el('button', 'Suggest category for this request', 'secondary-button'); assess.type = 'button'; assess.disabled = true;
    const prediction = el('p', 'Confirm that this fragment is a current request before asking a model to classify it.', 'technical-note'); prediction.setAttribute('role','status');
    const record = {part, role, category, result:null}; records.push(record);
    let assessing = false, call = 0;
    role.addEventListener('change', () => {
      ++call; record.result = null; category.value = ''; category.disabled = role.value !== 'request';
      assess.disabled = role.value !== 'request'; assessing = false;
      prediction.textContent = role.value === 'request' ? 'Choose a category yourself or request a separate model suggestion. The full message may change its meaning.'
        : 'No category suggestion for background, unresolved relationships, unclear or excluded requests.';
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
      footer.hidden = false;
      feedback.textContent = `${data.parts.length} text fragment(s), not a verified count of needs. All interpretations start unconfirmed.${data.grouped_remainder ? ' The last fragment groups the remaining text; inspect it for additional needs.' : ''}`;
    } catch (error) { if (valid(token,key)) feedback.textContent = error.name === 'AbortError' ? 'Timed out. Retry the preview.' : error.message; }
    finally {
      clearTimeout(timer); controllers.delete(controller);
      if (token === generation) { build.disabled = false; host.removeAttribute('aria-busy'); }
    }
  });
  transfer.addEventListener('click', () => {
    if (!preview || currentKey !== sourceKey(getSource())) { reset(); return; }
    if (records.some(r => r.role.value === 'unconfirmed')) { feedback.textContent = 'Review the interpretation of every fragment first.'; return; }
    if (records.some(r => r.role.value === 'request' && !r.category.value)) { feedback.textContent = 'Choose a human category, Outside current categories or Unclear for each current request.'; return; }
    if (records.some(r => ['unclear','conditional','alternative'].includes(r.role.value) || r.category.value === 'UNCLEAR') && !question.value.trim()) {
      feedback.textContent = 'Add a clarification question or explain the relationship before staging this note.'; question.focus(); return;
    }
    const lines = ['Human-assisted breakdown v1. Evidence ranges use original Unicode character offsets.'];
    for (const r of records) {
      const p = r.result;
      lines.push(`[${r.part.start}:${r.part.end}] Human: ${r.role.value}${r.category.value ? ' / '+r.category.value : ''}.${p ? ` Model hypothesis (${p.model_mode}): ${p.suggested_category ?? 'withheld'}; sha256=${p.model_sha256}.` : ''}`);
    }
    if (question.value.trim()) lines.push('Clarification / coordination: '+question.value.trim());
    const error = stageNote(lines.join('\n'));
    feedback.textContent = error || 'Added to the note draft. Review it and use Add note to save; status and overall category are unchanged.';
  });
  return {reset};
}
