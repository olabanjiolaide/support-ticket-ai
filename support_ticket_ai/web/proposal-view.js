const el = (tag,text='') => { const node=document.createElement(tag);node.textContent=text;return node; };

export function initProposals(host,getSource,onAdopt) {
  host.className='proposal-panel';
  const title=el('h3','Propose needs with a local language model');
  const status=el('p','Checking proposal configuration…');status.className='technical-note';status.setAttribute('role','status');
  const generate=el('button','Generate needs proposals');generate.className='secondary-button';generate.type='button';generate.disabled=true;
  const refresh=el('button','Check local model');refresh.type='button';refresh.className='text-button';
  const cancel=el('button','Cancel generation');cancel.type='button';cancel.className='text-button';cancel.hidden=true;
  const feedback=el('p');feedback.className='technical-note';feedback.setAttribute('role','status');
  const result=el('div');
  const setup=el('a','Local model setup');setup.href='https://github.com/olabanjiolaide/support-ticket-ai/blob/main/docs/41-local-needs-proposals.md';setup.target='_blank';setup.rel='noopener';setup.className='text-button';
  host.append(title,status,generate,cancel,refresh,setup,feedback,result);
  let available=false, configured=false, sequence=0, controller=null, ticker=null;
  const sourceKey=()=>JSON.stringify([getSource()?.text,getSource()?.key]);
  function reset() {
    ++sequence;controller?.abort();controller=null;clearInterval(ticker);ticker=null;
    result.replaceChildren();feedback.textContent='';cancel.hidden=true;generate.disabled=!available;refresh.disabled=false;
  }
  async function check() {
    refresh.disabled=true;
    try {
      const response=await fetch('/proposals/status',{cache:'no-store',signal:AbortSignal.timeout(5000)});
      if (!response.ok) throw new Error('unavailable');
      const data=await response.json();available=data.available===true;configured=data.configured===true;
      status.textContent=available ? `Local proposal model ready: ${data.model}. Generation sends this message to local Ollama at 127.0.0.1:11434.`
        : configured ? 'Local proposal model unavailable. Start Ollama and install the configured model. Manual breakdown is available.'
        : 'Optional language-model proposals are not configured. Manual breakdown is available; setup is separate from the semantic category encoder.';
    } catch { available=false;status.textContent='Could not check the local proposal model. Manual breakdown is available.'; }
    finally {generate.disabled=!available || controller!==null;refresh.disabled=false;}
  }
  generate.addEventListener('click',async()=>{
    if (!available || controller) return;
    const source=getSource();
    if (!source?.text?.trim() || Array.from(source.text).length>2000) {feedback.textContent='Enter a message of 1–2,000 characters first.';return;}
    const token=++sequence,key=sourceKey();controller=new AbortController();const active=controller;
    generate.disabled=true;cancel.hidden=false;refresh.disabled=true;result.replaceChildren();
    const start=Date.now();
    const progress=()=>{feedback.textContent=`Generating a reviewable proposal… ${Math.floor((Date.now()-start)/1000)}s. Your existing review stays unchanged.`;};progress();ticker=setInterval(progress,1000);
    const timeout=setTimeout(()=>active.abort(),125000);
    try {
      const response=await fetch('/proposals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:source.text}),signal:active.signal});
      const data=await response.json();
      if (sequence!==token || sourceKey()!==key) return;
      if (!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'Proposal generation failed.');
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
      feedback.textContent='Proposal ready. Inspect it before replacing your editable draft.';
    } catch(error) {
      if(sequence===token)feedback.textContent=error.name==='AbortError'?'Generation stopped or timed out. Your current review is unchanged. The local model may still be finishing.':`${error.message} Your current review is unchanged.`;
    } finally {
      clearTimeout(timeout);
      if(sequence===token){clearInterval(ticker);ticker=null;controller=null;cancel.hidden=true;generate.disabled=!available;refresh.disabled=false;}
    }
  });
  cancel.addEventListener('click',()=>{reset();feedback.textContent='Cancelled in this tab. Your current review is unchanged. Local generation may still be finishing.';});
  refresh.addEventListener('click',check);check();
  return {reset};
}
