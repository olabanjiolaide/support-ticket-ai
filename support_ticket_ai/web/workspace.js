import { initBreakdown } from './breakdown.js';
import { describeResult } from './result-view.js';

const byId = (id) => document.getElementById(id);
const element = (tag, text = '', className = '') => {
  const node = document.createElement(tag); node.textContent = text;
  if (className) node.className = className;
  return node;
};
const shortId = (id) => `REQ-${id.slice(0, 8).toUpperCase()}`;
const date = (value) => new Date(value).toLocaleString();
const statusLabel = (r) => r.status === 'resolved' ? 'Resolved' : r.status === 'in_progress' ? 'In progress'
  : r.status === 'needs_clarification' ? 'Needs clarification' : r.review_state === 'reviewed' ? 'Ready to handle' : 'Awaiting review';
const titles = {new: 'New request', requests: 'All requests', review: 'Review queue', 'in-progress': 'In progress', resolved: 'Resolved requests', overview: 'Overview'};
const actionLabels = {created: 'Request saved', review: 'Category reviewed', clarify: 'Clarification needed', start: 'Handling started', resolve: 'Request resolved', reopen: 'Reopened for review', note: 'Note added', needs_review: 'Customer needs reviewed'};

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(path, {...options, signal: controller.signal, cache: 'no-store',
      headers: options.body ? {'Content-Type': 'application/json'} : {}});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the fields and try again.');
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The operation timed out. Retry to check the saved result.');
    if (error instanceof TypeError) throw new Error('Cannot connect to local request storage. Keep the server running and retry.');
    throw error;
  } finally { clearTimeout(timeout); }
}

export function initWorkspace({getDraft, setSaving, onSaved}) {
  let config = null, route = 'new', detailId = null, current = null;
  let offset = 0, total = 0, listSequence = 0, detailSequence = 0, overviewSequence = 0;
  let saving = false, actionPending = false, saveMessage = '', saveKey = null, reviewer = '';
  const savedBreakdown = initBreakdown(byId('saved-breakdown'),
    () => current ? {text:current.message, mode:current.prediction?.model_mode || 'word', key:current.id} : null,
    (text) => {
      const field = byId('review-note');
      if (field.disabled) return 'Wait for the current operation to complete.';
      const combined = [field.value.trim(), text].filter(Boolean).join('\n\n');
      if (Array.from(combined).length > 2000) return 'The combined note exceeds 2,000 characters. Save your existing note separately or shorten the clarification.';
      field.value = combined; field.focus(); return null;
    }, {save: async (review) => {
      if (!current || actionPending) throw new Error('Wait for the current operation to complete.');
      const actor = byId('reviewer-name').value.trim();
      if (!actor) { byId('reviewer-name').focus(); throw new Error('Enter a reviewer label above before saving.'); }
      const id = current.id, version = current.version;
      ++detailSequence; actionPending = true; updateActions();
      try {
        const record = await api(`/requests/${id}/needs-review`, {method:'POST',body:JSON.stringify({version,actor,review})});
        if (detailId === id) { renderDetail(record, true); showError('detail-feedback', 'Grouped needs review saved locally. Handling status and overall category are unchanged.'); }
      } finally { actionPending = false; updateActions(); }
    }});
  const saveButton = byId('save-request');
  const savePrediction = byId('save-with-prediction');

  function updateSave() {
    const draft = getDraft();
    const valid = Boolean(draft.text.trim()) && Array.from(draft.text).length <= 2000;
    saveButton.disabled = !config?.storage_available || saving || draft.blocked || !valid || (savePrediction.checked && !draft.ready);
    savePrediction.disabled = saving || draft.blocked;
    saveButton.textContent = saving ? 'Saving request…' : 'Save to review queue';
    byId('save-feedback').textContent = saveMessage || (valid && savePrediction.checked && !draft.ready
      ? 'The selected model is unavailable. Uncheck the prediction option to save for manual review.' : '');
  }

  async function configure() {
    const note = byId('storage-notice');
    try {
      config = await api('/workspace/config');
      note.textContent = config.storage_available
        ? 'Local workspace · requests are stored only when you choose Save to review queue.'
        : 'Request storage is unavailable. Check the server database configuration. Predictions can still be used without saving.';
      for (const id of ['category-filter', 'review-category']) {
        const select = byId(id);
        while (select.options.length > 1) select.remove(1);
        for (const category of config.categories) select.add(new Option(category, category));
      }
      byId('category-contract').textContent = config.category_notes;
    } catch {
      config = null;
      note.replaceChildren(element('span', 'Cannot check local request storage. '));
      const retry = element('button', 'Check storage', 'text-button');
      retry.type = 'button'; retry.addEventListener('click', configure); note.append(retry);
    }
    updateSave();
  }

  document.addEventListener('draft-controls-changed', updateSave);
  document.addEventListener('ticket-edited', () => { saveMessage = ''; updateSave(); });
  savePrediction.addEventListener('change', () => { saveMessage = ''; updateSave(); });
  saveButton.addEventListener('click', async () => {
    if (saveButton.disabled) return;
    const draft = getDraft();
    const payload = {text: draft.text, mode: draft.mode, check_multiple_requests: draft.check_multiple_requests,
      include_prediction: savePrediction.checked};
    const signature = JSON.stringify(payload);
    if (!saveKey || saveKey.signature !== signature) saveKey = {signature, id: crypto.randomUUID()};
    saving = true; saveMessage = 'Saving locally…'; setSaving(true); updateSave();
    try {
      const result = await api('/requests', {method: 'POST', body: JSON.stringify({...payload, client_request_id: saveKey.id})});
      saveKey = null; saveMessage = ''; onSaved();
      location.hash = `request/${result.id}`;
    } catch (error) { saveMessage = error.message; }
    finally { saving = false; setSaving(false); updateSave(); }
  });

  function showError(id, message = '') {
    byId(id).textContent = message; byId(id).hidden = !message;
  }
  function focusTitle(id) {
    byId(id).focus({preventScroll: true});
    window.scrollTo({top: 0, behavior: 'instant'});
  }
  function requestRow(item) {
    const link = element('a', '', 'request-row'); link.href = `#request/${item.id}`;
    const message = element('div', '', 'request-row-message');
    message.append(element('strong', shortId(item.id)), element('p', Array.from(item.message).slice(0, 140).join('')));
    const review = element('div', '', 'request-row-review');
    review.append(element('span', 'Human category', 'row-label'), element('strong', item.confirmed_category || 'Not reviewed'));
    const status = element('span', statusLabel(item), 'status-pill'); status.dataset.status = item.status;
    const updated = element('span', date(item.updated_at), 'row-updated');
    link.append(message, review, status, updated); return link;
  }
  async function loadList() {
    const sequence = ++listSequence;
    byId('request-list').setAttribute('aria-busy', 'true'); showError('records-error');
    const params = new URLSearchParams({q: byId('request-search').value, limit: '20', offset: String(offset)});
    const category = byId('category-filter').value;
    if (category) params.set('category', category);
    if (route === 'review') params.set('queue', 'review');
    const status = route === 'in-progress' ? 'in_progress' : route === 'resolved' ? 'resolved' : byId('status-filter').value;
    if (status) params.set('status', status);
    byId('previous-page').disabled = true; byId('next-page').disabled = true;
    try {
      const data = await api(`/requests?${params}`);
      if (sequence !== listSequence || !['requests','review','in-progress','resolved'].includes(route)) return;
      total = data.total;
      if (offset >= total && offset > 0) { offset = Math.max(0, Math.floor((total - 1) / 20) * 20); return loadList(); }
      byId('request-list').replaceChildren(...data.items.map(requestRow));
      if (!data.items.length) {
        const empty = element('div', '', 'empty-list'); empty.append(element('h2', 'No requests here yet.'), element('p', 'Save a new request or adjust the filters. Suggestions alone are not saved.'));
        byId('request-list').append(empty);
      }
      byId('page-summary').textContent = total ? `${offset + 1}–${Math.min(offset + 20, total)} of ${total}` : '0 saved requests';
      byId('previous-page').disabled = offset === 0;
      byId('next-page').disabled = offset + 20 >= total;
    } catch (error) {
      if (sequence === listSequence) { showError('records-error', error.message); byId('request-list').replaceChildren(); byId('page-summary').textContent = ''; }
    } finally { if (sequence === listSequence) byId('request-list').setAttribute('aria-busy', 'false'); }
  }
  byId('request-filters').addEventListener('submit', (event) => { event.preventDefault(); offset = 0; loadList(); });
  for (const id of ['status-filter', 'category-filter']) byId(id).addEventListener('change', () => { offset = 0; loadList(); });
  byId('previous-page').addEventListener('click', () => { offset = Math.max(0, offset - 20); loadList(); });
  byId('next-page').addEventListener('click', () => { if (offset + 20 < total) { offset += 20; loadList(); } });

  function updateActions() {
    const disabled = actionPending || !current;
    for (const id of ['reviewer-name','review-category','review-note','add-review-note','reload-request']) byId(id).disabled = disabled;
    const resolved = current?.status === 'resolved';
    byId('review-category').disabled = disabled || resolved;
    byId('confirm-review').disabled = disabled || resolved;
    byId('needs-clarification').disabled = disabled || resolved;
    byId('start-handling').disabled = disabled || current.status !== 'open' || current.review_state !== 'reviewed';
    byId('resolve-request').disabled = disabled || current.status !== 'in_progress' || current.review_state !== 'reviewed';
    byId('reopen-request').disabled = disabled || !resolved;
  }
  function renderDetail(record, preserveDraft = false) {
    savedBreakdown.reset();
    current = record;
    savedBreakdown.restore(record.need_review?.review);
    byId('request-detail-content').hidden = false;
    byId('request-detail-title').textContent = shortId(record.id);
    byId('breadcrumb-current').textContent = `Requests / ${shortId(record.id)}`;
    byId('detail-metadata').textContent = `Created ${date(record.created_at)} · Updated ${date(record.updated_at)} · Version ${record.version}`;
    byId('detail-status').textContent = statusLabel(record); byId('detail-status').dataset.status = record.status;
    byId('detail-review-state').textContent = record.review_state === 'reviewed' ? 'Human category reviewed' : 'Human review pending';
    byId('saved-message').textContent = record.message;
    byId('saved-prediction-summary').textContent = record.prediction
      ? `${describeResult(record.prediction).title} · ${record.prediction.model_name} · Original snapshot, not the human decision.` : 'No model prediction was requested. Manual classification is available.';
    byId('saved-prediction-json').textContent = record.prediction ? JSON.stringify(record.prediction, null, 2) : 'No prediction snapshot.';
    byId('confirmed-category').textContent = record.confirmed_category || 'Not reviewed';
    byId('resolution-note').textContent = record.resolution_note || 'No current resolution note.';
    byId('review-category').value = record.confirmed_category || '';
    if (!preserveDraft) byId('reviewer-name').value = reviewer;
    if (!preserveDraft) byId('review-note').value = '';
    byId('request-history').replaceChildren(...record.history.map((event) => {
      const item = element('li');
      item.append(element('strong', actionLabels[event.action] || event.action), element('p', `${date(event.happened_at)} · ${event.actor} · Version ${event.after.version}`, 'history-meta'));
      if (event.note) item.append(element('p', event.note, 'saved-message'));
      if (event.action === 'needs_review') {
        const details = element('details', '', 'response-details');
        details.append(element('summary','Grouped review before / after'), element('pre',JSON.stringify({before:event.before?.need_review,after:event.after?.need_review},null,2)));
        item.append(element('p',`${event.after.need_review.groups.length} human-authored need(s) recorded. Handling status was not changed.`,'technical-note'),details);
      }
      const changes = [];
      for (const key of ['status','review_state','confirmed_category']) {
        const previous = event.before?.[key] ?? '—', next = event.after[key] ?? '—';
        if (previous !== next) {
          const label = {status:'Handling status',review_state:'Review',confirmed_category:'Human category'}[key];
          const human = (value) => ({open:'Open',needs_clarification:'Needs clarification',in_progress:'In progress',resolved:'Resolved',pending:'Pending',reviewed:'Confirmed'}[value] || value);
          changes.push(`${label}: ${human(previous)} → ${human(next)}`);
        }
      }
      if (changes.length) item.append(element('p', changes.join(' · '), 'technical-note'));
      return item;
    }));
    updateActions();
  }
  async function loadDetail(id, preserveDraft = false) {
    const sequence = ++detailSequence; showError('detail-error');
    if (!preserveDraft) { current = null; byId('request-detail-content').hidden = true; }
    byId('request-detail-title').textContent = 'Loading request…';
    try {
      const record = await api(`/requests/${encodeURIComponent(id)}`);
      if (detailId !== id || sequence !== detailSequence) return;
      renderDetail(record, preserveDraft); focusTitle('request-detail-title');
    } catch (error) { if (sequence === detailSequence) { showError('detail-error', error.message); byId('request-detail-title').textContent = 'Request unavailable'; } }
  }
  async function action(name) {
    if (!current || actionPending) return;
    showError('detail-error'); showError('detail-feedback');
    const actor = byId('reviewer-name').value.trim(), note = byId('review-note').value.trim(), category = byId('review-category').value;
    if (!byId('request-review-form').reportValidity()) return;
    if (!actor) { showError('detail-error', 'Enter a reviewer label.'); byId('reviewer-name').focus(); return; }
    if (Array.from(note).length > 2000) { showError('detail-error', 'Use a note of at most 2,000 characters.'); byId('review-note').focus(); return; }
    if (name === 'review' && !category) { showError('detail-error', 'Choose the human category before confirming.'); byId('review-category').focus(); return; }
    if (['clarify','resolve','reopen','note'].includes(name) && !note) { showError('detail-error', 'Add a note explaining this action.'); byId('review-note').focus(); return; }
    reviewer = actor;
    const id = current.id, version = current.version;
    ++detailSequence;
    actionPending = true; updateActions();
    try {
      const record = await api(`/requests/${id}/actions`, {method: 'POST', body: JSON.stringify({version, action: name, actor, note, ...(name === 'review' ? {category} : {})})});
      if (detailId === id) { renderDetail(record); showError('detail-feedback', `${actionLabels[name]}. Saved locally.`); }
    } catch (error) { if (detailId === id) showError('detail-error', error.message); }
    finally { actionPending = false; updateActions(); }
  }
  byId('request-review-form').addEventListener('submit', (event) => { event.preventDefault(); action('review'); });
  for (const button of document.querySelectorAll('[data-action]')) button.addEventListener('click', () => action(button.dataset.action));
  byId('reload-request').addEventListener('click', () => { if (detailId) loadDetail(detailId, true); });

  async function loadOverview() {
    const sequence = ++overviewSequence;
    byId('overview-content').setAttribute('aria-busy', 'true'); showError('overview-error');
    byId('refresh-overview').disabled = true;
    try {
      const data = await api('/requests/overview');
      if (sequence !== overviewSequence || route !== 'overview') return;
      const metrics = [['Saved requests',data.total,'requests'],['Pending review',data.pending_review,'review'],['Ready to handle',data.ready_to_handle,'requests'],['In progress',data.by_status.in_progress,'in-progress'],['Resolved',data.by_status.resolved,'resolved'],['Needs clarification',data.by_status.needs_clarification,'review']];
      byId('overview-metrics').replaceChildren(...metrics.map(([label,count,target]) => {
        const card = element('a', '', 'card metric-card'); card.href = `#${target}`;
        card.append(element('span', label), element('strong', String(count))); return card;
      }));
      const categories = Object.entries(data.confirmed_categories).sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0]));
      byId('overview-categories').replaceChildren(...(categories.length ? categories.map(([label,count]) => {
        const row = element('p', '', 'category-total'); row.append(element('span',label),element('strong',String(count))); return row;
      }) : [element('p','No human-confirmed categories yet.','technical-note')]));
      byId('overview-activity').replaceChildren(...(data.recent_activity.length ? data.recent_activity.map((event) => {
        const link = element('a', '', 'activity-row'); link.href = `#request/${event.request_id}`;
        link.append(element('strong', `${shortId(event.request_id)} · ${actionLabels[event.action] || event.action}`), element('span',`${date(event.happened_at)} · ${event.actor}`)); return link;
      }) : [element('p','Activity appears after you save a request.','technical-note')]));
    } catch (error) { if (sequence === overviewSequence) showError('overview-error', error.message); }
    finally { if (sequence === overviewSequence) { byId('overview-content').setAttribute('aria-busy','false'); byId('refresh-overview').disabled = false; } }
  }
  byId('refresh-overview').addEventListener('click', loadOverview);
  byId('workspace-view').addEventListener('change', () => { location.hash = byId('workspace-view').value; });

  function navigate(initial = false) {
    const hash = location.hash.slice(1) || 'new';
    const isDetail = hash.startsWith('request/');
    route = isDetail ? 'detail' : Object.hasOwn(titles, hash) ? hash : 'new';
    detailId = isDetail ? hash.slice(8) : null;
    savedBreakdown.reset();
    ++listSequence; ++detailSequence; ++overviewSequence;
    for (const [id, name] of [['classification-view','new'],['records-view','list'],['request-detail-view','detail'],['overview-view','overview']])
      byId(id).hidden = name === 'list' ? !['requests','review','in-progress','resolved'].includes(route) : route !== name;
    document.querySelectorAll('[data-view]').forEach((link) => {
      const active = link.dataset.view === (isDetail ? 'requests' : route);
      link.classList.toggle('active',active);
      if (active) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current');
    });
    byId('workspace-view').value = isDetail ? 'requests' : route;
    byId('breadcrumb-current').textContent = isDetail ? 'Requests / Details' : route === 'new' ? 'New request' : `Requests / ${titles[route]}`;
    document.title = `${titles[route] || 'Request details'} · Support Ticket AI`;
    if (isDetail) { showError('detail-feedback'); loadDetail(detailId); }
    else if (route === 'overview') { loadOverview(); if (!initial) focusTitle('overview-title'); }
    else if (route !== 'new') {
      offset = 0; byId('request-search').value = ''; byId('category-filter').value = ''; byId('status-filter').value = '';
      byId('records-title').textContent = titles[route];
      byId('records-description').textContent = route === 'review' ? 'Pending reviews and requests that need clarification. Confirming a category does not resolve a request.'
        : route === 'resolved' ? 'Completed requests with resolution notes and their original prediction history.' : route === 'in-progress' ? 'Reviewed requests someone has started handling.' : 'Saved messages, original predictions and human decisions.';
      byId('status-filter-control').hidden = ['in-progress','resolved'].includes(route);
      loadList(); if (!initial) focusTitle('records-title');
    } else if (!initial) {
      if (hash === 'how-it-works') byId('how-it-works').scrollIntoView();
      else { byId('workspace').focus({preventScroll:true}); window.scrollTo({top:0,behavior:'instant'}); }
    }
  }
  window.addEventListener('hashchange', () => navigate());
  configure().finally(() => navigate(true));
}
