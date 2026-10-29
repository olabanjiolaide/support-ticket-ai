// Human-authored proposed steps and exact target references; never executes actions.
export function createNeedContract(saved,source,onChange){
  const node=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
  const host=node('details');host.className='need-contract';host.append(node('summary','Proposed actions, targets and unknowns'));
  host.append(node('p','Describe steps to review, not approved operations. Target quotes identify wording in this message; they do not verify an order or authorize a change.'));
  const unknownLabel=node('label','Unknowns to clarify — one per line'),unknowns=node('textarea');unknowns.rows=2;unknowns.maxLength=1607;unknowns.value=(saved?.unknowns || []).join('\n');unknownLabel.append(unknowns);
  unknowns.addEventListener('input',onChange);
  const list=node('div');list.className='need-action-list';
  const add=node('button','Add proposed action');add.type='button';add.className='secondary-button';
  const records=[];
  function addAction(initial={}){
    if(records.length>=8)return;
    const card=node('div');card.className='need-action';
    const descriptionLabel=node('label','Proposed action'),description=node('input');description.type='text';description.maxLength=200;description.value=initial.description || '';descriptionLabel.append(description);
    const targetNote=node('p');targetNote.className='technical-note';targetNote.setAttribute('role','status');
    const selection=node('details');selection.append(node('summary','Choose target wording from original message'));
    const originalLabel=node('label','Original message — select action target'),original=node('textarea');original.readOnly=true;original.rows=3;original.value=source;originalLabel.append(original);
    const bind=node('button','Use selected target'),clear=node('button','Clear target reference'),remove=node('button','Remove proposed action');
    for(const button of [bind,clear,remove]){button.type='button';button.className='text-button';}
    let target=initial.target?structuredClone(initial.target):null;
    function render(){targetNote.textContent=target?`Target [${target.start}:${target.end}]: ${target.text}`:'No target selected. Leave unset if the message does not identify one.';}
    bind.addEventListener('click',()=>{
      const start=Array.from(source.slice(0,original.selectionStart)).length,end=Array.from(source.slice(0,original.selectionEnd)).length;
      const text=Array.from(source).slice(start,end).join('');
      if(!text.trim() || Array.from(text).length>300){targetNote.textContent='Select 1–300 characters identifying the target in the original message.';return;}
      target={start,end,text};render();onChange();
    });
    clear.addEventListener('click',()=>{target=null;render();onChange();});
    const record={description,read:()=>({description:description.value.trim(),target:target?structuredClone(target):null})};records.push(record);
    description.addEventListener('input',onChange);
    remove.addEventListener('click',()=>{records.splice(records.indexOf(record),1);card.remove();add.disabled=false;onChange();});
    selection.append(originalLabel,bind);card.append(descriptionLabel,targetNote,selection,clear,remove);list.append(card);render();add.disabled=records.length>=8;
  }
  add.addEventListener('click',()=>{addAction();records.at(-1)?.description.focus();onChange();});
  for(const action of saved?.actions || [])addAction(action);
  host.append(unknownLabel,list,add);
  function read(){return {actions:records.map(r=>r.read()),unknowns:unknowns.value.split('\n').map(s=>s.trim()).filter(Boolean)};}
  function validate(){const value=read();if(value.actions.some(a=>!a.description))throw new Error('Describe or remove each proposed action before saving.');if(value.unknowns.length>8 || value.unknowns.some(s=>Array.from(s).length>200))throw new Error('Use at most eight unknowns, each up to 200 characters.');}
  return {host,read,validate};
}
