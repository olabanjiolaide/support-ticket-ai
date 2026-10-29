// Read-only operational state. Never sends or stores the customer message.
export function initDiagnostics() {
  const panel=document.getElementById('diagnostics-panel');
  const status=document.getElementById('diagnostics-status');
  const values=document.getElementById('diagnostics-values');
  const summary=document.getElementById('diagnostics-summary');
  const refresh=document.getElementById('refresh-diagnostics');
  let loading=false;
  async function load() {
    if(loading)return;
    loading=true;refresh.disabled=true;status.textContent='Checking application and model identities…';
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try {
      const response=await fetch('/diagnostics',{cache:'no-store',signal:controller.signal});
      if(!response.ok)throw new Error('unavailable');
      const data=await response.json();
      const client=document.querySelector('meta[name="workspace-build"]').content;
      const matches=client===data.frontend_build;
      values.replaceChildren();
      const entries=[['Application',data.application_version],['Page build',client],['Server frontend build',data.frontend_build],
        ...Object.entries(data.models).map(([name,model])=>[`${name} model`,model.loaded ? `Loaded · SHA256 ${model.model_sha256}` : 'Not loaded']),
        ['Local proposals',!data.proposals.configured ? 'Not configured' : data.proposals.available ? `Available · ${data.proposals.model} · SHA256 ${data.proposals.model_digest}` : 'Configured, unavailable'],
        ['Request storage',data.storage_available?'Available':'Unavailable']];
      for(const [label,value] of entries){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;values.append(dt,dd);}
      summary.textContent=`v${data.application_version} · ${matches?'page build matches':'reload needed'}`;
      status.textContent=matches?'Page and server build identities match. Every model suggestion still requires review.':'The server frontend changed after this page loaded. Reload this page before continuing.';
    } catch {status.textContent='Diagnostics could not be loaded. Check that the local server is running and retry.';}
    finally{clearTimeout(timer);loading=false;refresh.disabled=false;}
  }
  panel.addEventListener('toggle',()=>{if(panel.open)load();});
  refresh.addEventListener('click',load);
}
