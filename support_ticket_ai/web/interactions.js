// View preferences and interaction feedback only; never persists customer content.
export function initInteractions() {
  const byId=(id)=>document.getElementById(id);
  const reduced=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const sidebar=byId('workspace-sidebar'), toggle=byId('nav-toggle'), close=byId('nav-close'), scrim=byId('nav-scrim');
  const mobile=window.matchMedia('(max-width: 980px)');
  const openNavigation=(open,restoreFocus=true)=>{
    if(open && !mobile.matches)return;
    document.body.classList.toggle('navigation-open',open);toggle.setAttribute('aria-expanded',String(open));
    scrim.hidden=!open;close.hidden=!open;document.querySelector('.page').inert=open;
    if(open){sidebar.setAttribute('role','dialog');sidebar.setAttribute('aria-modal','true');close.focus();}
    else{sidebar.removeAttribute('role');sidebar.removeAttribute('aria-modal');if(restoreFocus && mobile.matches)toggle.focus();}
  };
  toggle.addEventListener('click',()=>openNavigation(toggle.getAttribute('aria-expanded')!=='true'));
  close.addEventListener('click',()=>openNavigation(false));scrim.addEventListener('click',()=>openNavigation(false));
  sidebar.addEventListener('click',event=>{if(event.target.closest('a') && document.body.classList.contains('navigation-open'))openNavigation(false,false);});
  document.addEventListener('focusin',event=>{if(document.body.classList.contains('navigation-open') && !sidebar.contains(event.target))close.focus();});
  document.addEventListener('keydown',event=>{
    if(!document.body.classList.contains('navigation-open'))return;
    if(event.key==='Escape'){event.preventDefault();openNavigation(false);return;}
    if(event.key==='Tab'){
      const focusable=[...sidebar.querySelectorAll('a,button')].filter(node=>!node.hidden && node.getClientRects().length);
      const first=focusable[0],last=focusable.at(-1);
      if(event.shiftKey && document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first.focus();}
    }
  });
  mobile.addEventListener('change',()=>openNavigation(false,false));
  const density=byId('density-toggle');
  function setDensity(compact){document.body.dataset.density=compact?'compact':'comfortable';density.setAttribute('aria-pressed',String(compact));density.textContent=compact?'Comfortable view':'Compact view';}
  try{setDensity(localStorage.getItem('support-ticket-density')==='compact');}catch{setDensity(false);}
  density.addEventListener('click',()=>{const compact=density.getAttribute('aria-pressed')!=='true';setDensity(compact);try{localStorage.setItem('support-ticket-density',compact?'compact':'comfortable');}catch{}});
  const sections={compose:()=>byId('ticket'),result:()=>[...byId('result-panel').querySelectorAll('h2,h3')].find(node=>node.getClientRects().length) || byId('result-panel'),needs:()=>byId('draft-breakdown').querySelector('h2')};
  const markSection=(name)=>document.querySelectorAll('[data-section]').forEach(button=>{if(button.dataset.section===name)button.setAttribute('aria-current','location');else button.removeAttribute('aria-current');});
  document.querySelectorAll('[data-section]').forEach(button=>button.addEventListener('click',()=>{
    const target=sections[button.dataset.section]();if(!target)return;
    if(!target.matches('input,textarea,select,button,a[href]'))target.tabIndex=-1;
    markSection(button.dataset.section);target.focus({preventScroll:true});target.scrollIntoView({block:'center',behavior:reduced()?'instant':'smooth'});
    target.closest('.card')?.classList.add('section-highlight');setTimeout(()=>target.closest('.card')?.classList.remove('section-highlight'),800);
  }));
  const state=byId('workbench-state'), result=byId('result-panel');
  const updateState=()=>{
    const value=result.dataset.state;
    state.textContent=value==='loading'?'Reading the message…':value==='success'?'Suggestion ready · review before handling':value==='error'?'Prediction needs attention':value==='cancelled'?'Prediction cancelled':'Start with a customer message';
    state.dataset.state=value;
  };
  new MutationObserver(updateState).observe(result,{attributes:true,attributeFilter:['data-state']});updateState();
  document.addEventListener('ticket-edited',()=>markSection('compose'));
  const clearPrint=()=>{document.querySelectorAll('.print-value').forEach(node=>node.remove());document.querySelectorAll('[data-print-mirror]').forEach(node=>delete node.dataset.printMirror);};
  window.addEventListener('beforeprint',()=>{clearPrint();for(const input of document.querySelectorAll('textarea')){
    if(!input.getClientRects().length)continue;
    const mirror=document.createElement('div');mirror.className='print-value';mirror.textContent=input.value || 'No text entered.';input.dataset.printMirror='true';input.after(mirror);
  }});
  window.addEventListener('afterprint',()=>{clearPrint();document.querySelectorAll('[data-print-mirror]').forEach(node=>delete node.dataset.printMirror);});
  const toast=byId('visual-toast');let toastTimer=null,last='';
  const notify=(message)=>{if(!message||message===last)return;last=message;toast.textContent=message;toast.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{toast.hidden=true;last='';},4000);};
  for(const id of ['detail-feedback','copy-feedback']){
    const node=byId(id);new MutationObserver(()=>{if(!node.hidden && node.textContent.trim())notify(node.textContent.trim());}).observe(node,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['hidden']});
  }
}
