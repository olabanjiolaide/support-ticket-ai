const el = (tag,text='') => { const node=document.createElement(tag);node.textContent=text;return node; };

export function initProposals(host,getSource,onAdopt) {
  host.className='proposal-panel';
  host.dataset.state='checking';
  const eyebrow=el('p','AI NEEDS ANALYSIS');eyebrow.className='proposal-eyebrow';
  const title=el('h3','Propose needs with a local language model');
  const description=el('p','Find proposed goals, obstacles and relationships across the whole message. Review the draft before using it.');description.className='proposal-description';
  const badge=el('span','Checking model');badge.className='proposal-state';
  const status=el('p','Checking proposal configuration…');status.className='technical-note';status.setAttribute('role','status');
  const generate=el('button','Generate needs proposals');generate.className='primary-button proposal-generate';generate.type='button';generate.disabled=true;
  const refresh=el('button','Check local model');refresh.type='button';refresh.className='secondary-button proposal-check';
  const cancel=el('button','Cancel generation');cancel.type='button';cancel.className='secondary-button';cancel.hidden=true;
  const feedback=el('p');feedback.className='technical-note';feedback.setAttribute('role','status');
  const timing=el('p');timing.className='proposal-timing';timing.setAttribute('aria-hidden','true');timing.hidden=true;
  const progress=el('div');progress.className='proposal-progress';progress.hidden=true;progress.setAttribute('role','progressbar');progress.setAttribute('aria-label','Generating needs proposals');
  const spinner=el('span');spinner.className='proposal-spinner';spinner.setAttribute('aria-hidden','true');progress.append(spinner,el('span','Generating and validating · up to two local attempts'));
  const recovery=el('section');recovery.className='proposal-recovery';recovery.hidden=true;recovery.setAttribute('role','alert');
  const errorTitle=el('h4','Proposal could not be generated'), errorMessage=el('p'), nextStep=el('p');
  const retry=el('button','Retry generation');retry.type='button';retry.className='primary-button';
  const copy=el('button','Copy error details');copy.type='button';copy.className='secondary-button';
  const diagnostics=el('pre');diagnostics.className='proposal-error-details';
  recovery.append(errorTitle,errorMessage,nextStep,retry,copy,diagnostics);
  const result=el('div');result.className='proposal-result';
  const setup=el('a','Local model setup');setup.href='https://github.com/olabanjiolaide/support-ticket-ai/blob/main/docs/41-local-needs-proposals.md';setup.target='_blank';setup.rel='noopener';setup.className='text-button';
  const header=el('div');header.className='proposal-heading';header.append(eyebrow,badge);
  const actions=el('div');actions.className='proposal-actions';actions.append(generate,cancel,refresh);
  const more=el('details');more.className='proposal-setup';more.append(el('summary','Setup and local processing'),status,setup);
  host.append(header,title,description,actions,progress,timing,recovery,feedback,result,more);
  let available=false, configured=false, sequence=0, controller=null, ticker=null, model=null, lastError=null;
  function state(name,label){host.dataset.state=name;badge.textContent=label;}
  const sourceKey=()=>JSON.stringify([getSource()?.text,getSource()?.key]);
  function reset() {
    ++sequence;controller?.abort();controller=null;clearInterval(ticker);ticker=null;
    result.replaceChildren();feedback.textContent='';cancel.hidden=true;generate.disabled=!available;refresh.disabled=false;recovery.hidden=true;timing.hidden=true;progress.hidden=true;lastError=null;state(available?'ready':'unavailable',available?'Model available':'Setup required');
  }
  async function check() {
    refresh.disabled=true;
    try {
      const response=await fetch('/proposals/status',{cache:'no-store',signal:AbortSignal.timeout(5000)});
      if (!response.ok) throw new Error('unavailable');
      const data=await response.json();available=data.available===true;configured=data.configured===true;model=data.model || null;
      if(!controller && recovery.hidden)state(available?'ready':'unavailable',available?'Model available':configured?'Model unavailable':'Setup required');
      status.textContent=available ? `Local proposal model ready: ${data.model}. Generation sends this message to local Ollama at 127.0.0.1:11434.`
        : configured ? 'Local proposal model unavailable. Start Ollama and install the configured model. Manual breakdown is available.'
        : 'Optional language-model proposals are not configured. Manual breakdown is available; setup is separate from the semantic category encoder.';
    } catch { available=false;if(!controller && recovery.hidden)state('unavailable','Connection unavailable');status.textContent='Could not check the local proposal model. Manual breakdown is available.'; }
    finally {generate.disabled=!available || controller!==null;retry.disabled=!available || controller!==null;refresh.disabled=false;}
  }
  generate.addEventListener('click',async()=>{
    if (!available || controller) return;
    const source=getSource();
    if (!source?.text?.trim() || Array.from(source.text).length>2000) {feedback.textContent='Enter a message of 1–2,000 characters first.';return;}
    const token=++sequence,key=sourceKey();controller=new AbortController();const active=controller;
    generate.disabled=true;retry.disabled=true;cancel.hidden=false;refresh.disabled=true;result.replaceChildren();recovery.hidden=true;progress.hidden=false;timing.hidden=false;lastError=null;state('generating','Generating…');
    const start=Date.now();
    feedback.textContent='Generating a reviewable proposal. A validation failure may trigger one regeneration within the same time budget.';
    const tick=()=>{timing.textContent=`Elapsed: ${Math.floor((Date.now()-start)/1000)}s · model loading and validation may take time.`;};tick();ticker=setInterval(tick,1000);
    const timeout=setTimeout(()=>active.abort(),125000);
    try {
      const response=await fetch('/proposals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:source.text}),signal:active.signal});
      const data=await response.json();
      if (sequence!==token || sourceKey()!==key) return;
      if (!response.ok) {const error=new Error(typeof data.detail==='string'?data.detail:'Proposal generation failed.');error.code=data.code || `http_${response.status}`;error.validationCode=data.validation_code || null;error.attempts=data.attempts ?? null;error.promptVersion=data.prompt_version ?? null;throw error;}
      const review=data.review;
      if (data.status!=='draft' || data.requires_human_review!==true || review?.source_text!==source.text || review.schema_version!==2 || !Array.isArray(review.parts) || !Array.isArray(review.groups) || !Array.isArray(review.relations)) throw new Error('The proposal response did not match the current message.');
      const warning=el('p','Model draft — evidence checks passed, but the meaning, categories and relationships still need your review.');warning.className='technical-note';result.append(warning);
      for (const group of review.groups) {
        const card=el('article');card.className='proposal-need';card.append(el('strong',group.title),el('p',`${group.kind} · proposed category: ${group.category}`));
        for (const part of review.parts.filter(p=>p.group_id===group.id)) card.append(el('blockquote',`${part.role}: ${part.text}`));
        result.append(card);
      }
      const unassigned=review.parts.filter(p=>!p.group_id);
      if (unassigned.length) {const details=el('details');details.append(el('summary','Other source evidence'));for(const part of unassigned)details.append(el('p',`${part.role}: ${part.text}`));result.append(details);}
      for (const relation of review.relations) result.append(el('p',`Relationship hypothesis: ${relation.source} ${relation.kind} ${relation.target}. ${relation.note}`));
      if (review.clarification) result.append(el('p','Proposed clarification: '+review.clarification));
      const identity=el('details');identity.append(el('summary','Proposal identity'),el('pre',JSON.stringify({model:data.model,model_digest:data.model_digest,prompt_version:data.prompt_version,prompt_sha256:data.prompt_sha256,source_sha256:data.source_sha256},null,2)));result.append(identity);
      const adopt=el('button','Use as editable draft');adopt.type='button';adopt.className='secondary-button';
      result.append(el('p','This replaces unsaved grouping choices in this tab. It does not save, route or resolve the request.'),adopt);
      adopt.addEventListener('click',()=>{if(sequence!==token || sourceKey()!==key)return;onAdopt(structuredClone(review));});
      feedback.textContent=`Proposal ready. Inspect it before replacing your editable draft.${data.generation_attempts===2?' The first attempt failed validation; the second passed structural checks.':''}`;state('draft','Draft ready for review');
    } catch(error) {
      if(sequence===token){
        state('error','Generation failed');recovery.hidden=false;
        errorMessage.textContent=error.name==='AbortError'?'Generation stopped or timed out. The local model may still be finishing.':error.message;
        nextStep.textContent=error.code==='busy'?'Wait for the current local generation to finish, then retry.':error.code==='unavailable'?'Open Ollama, choose Check local model, then retry.':'Retry generation once, or use Break down message to review the original text manually. Copy the error details if it fails again.';
        lastError={code:error.code || (error.name==='AbortError'?'client_timeout':'invalid_response'),validation_code:error.validationCode || null,attempts:error.attempts ?? null,model,prompt_version:error.promptVersion ?? null};
        diagnostics.textContent=JSON.stringify(lastError,null,2);
        feedback.textContent='Generation failed. Your current review is unchanged.';
      }
    } finally {
      clearTimeout(timeout);
      if(sequence===token){clearInterval(ticker);ticker=null;controller=null;cancel.hidden=true;generate.disabled=!available;retry.disabled=!available;refresh.disabled=false;progress.hidden=true;timing.hidden=true;}
    }
  });
  cancel.addEventListener('click',()=>{reset();feedback.textContent='Cancelled in this tab. Your current review is unchanged. Local generation may still be finishing.';});
  retry.addEventListener('click',()=>generate.click());
  copy.addEventListener('click',async()=>{if(!lastError)return;try{await navigator.clipboard.writeText(JSON.stringify(lastError,null,2));feedback.textContent='Error details copied. Customer message and generated text are not included.';}catch{feedback.textContent='Copy was unavailable. Select the visible error details to copy them.';}});
  refresh.addEventListener('click',check);check();
  return {reset,generate:()=>{host.scrollIntoView({block:'center',behavior:'instant'});if(available){generate.focus();generate.click();}else{host.querySelector('.proposal-setup').open=true;refresh.focus();feedback.textContent='Check the local model configuration before generating a proposal.';}}};
}
