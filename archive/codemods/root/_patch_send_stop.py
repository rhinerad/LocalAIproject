from pathlib import Path

path = Path(r"local_agent/static/index.html")
text = path.read_text(encoding="utf-8")

old_globals = """let cid=localStorage.getItem('active_chat_id')||null, busy=false, atts=[], chatTitle='Chat', activeModel='', activeRouting='', activeWorkspace='auto', modelSignature='';
let traceCard=null, traceSteps=[], traceLast='', turnHost=null, pendingToolCards=[];
let traceStarted=0, elapsedTimer=null;"""

new_globals = """let cid=localStorage.getItem('active_chat_id')||null, busy=false, atts=[], chatTitle='Chat', activeModel='', activeRouting='', activeWorkspace='auto', modelSignature='';
let traceCard=null, traceSteps=[], traceLast='', turnHost=null, pendingToolCards=[];
let traceStarted=0, elapsedTimer=null;
// streamEpoch orphans an in-flight SSE reader when Stop unlocks early so a
// hung tool/Ollama call cannot leave Send stuck on Stop forever.
let streamEpoch=0;
function setBusy(on){
  busy=!!on;
  send.textContent=busy?'Stop':'Send';
  if(busy) send.classList.add('stop'); else send.classList.remove('stop');
}"""

if old_globals not in text:
    raise SystemExit("globals block not found")
text = text.replace(old_globals, new_globals, 1)

old_stream = """async function stream(url,payload){
  busy=true; send.textContent='Stop'; send.classList.add('stop');
  const b=bubble('agent'); const body=b.querySelector('.body');
  let acc='', lastMediaHost=b;
  turnHost=b.querySelector('.activity');
  pendingToolCards=[];
  startTrace(); trace('Request received locally');

  const resp=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
                             body:JSON.stringify(payload)});
  const rd=resp.body.getReader(), dec=new TextDecoder(); let buf='';
  while(true){
    const {done,value}=await rd.read(); if(done) break;
    buf+=dec.decode(value,{stream:true});
    const parts=buf.split('\\n\\n'); buf=parts.pop();
    for(const p of parts){
      if(!p.startsWith('data: ')) continue;
      const ev=JSON.parse(p.slice(6));
      if(ev.kind==='conversation'){ const c=JSON.parse(ev.data); cid=c.id; chatTitle=c.title||'Chat';
        activeRouting=c.routing||'';
        activeModel=c.model||'';
        activeWorkspace=c.workspace||activeWorkspace||$('#workspace').value;
        if(activeRouting==='auto_farm' && !activeModel) $('#chatmodel').value='auto_farm';
        else if(activeModel) $('#chatmodel').value=activeModel;
        $('#workspace').value=activeWorkspace;
        $('#chatmodel').disabled=true; $('#workspace').disabled=true; loadChats(); }
      else if(ev.kind==='route'){ const r=JSON.parse(ev.data); refresh();
        const proposal=r.source==='proposal';
        if(!proposal) applyRouteWho(b, r);
        const shown=(String(r.backend||'').toLowerCase()==='farm'||String(r.tier||'').toLowerCase()==='farm')
          ?'FARM':String(r.tier||'').toUpperCase();
        trace(proposal
          ? ('Attempting '+shown+' — not yet observed')
          : ('Routing on '+shown+' with '+(r.model||'the selected model')));
        cardHost().appendChild(lifeNode({
          kind:'route',
          state:proposal?'announced':'result',
          source:proposal?'proposal':'observation',
          hop:r.hop, hop_index:r.hop_index,
          tier:r.tier, model:r.model, backend:r.backend, reason:r.reason,
          gpu_busy:r.gpu_busy, capability:(r.detail&&r.detail.capability),
          label:proposal?'attempting farm':(shown+' '+(r.model||''))
        })); }
      else if(ev.kind==='progress'){
        let prog={}; try{prog=JSON.parse(ev.data)}catch(e){prog={label:ev.data}}
        if(prog.label) trace(prog.label);
        const mapped=progressLifecycle(prog);
        if(mapped){ mapped.hop=prog.hop; mapped.hop_index=prog.hop_index;
          cardHost().appendChild(lifeNode(mapped)); } }
      else if(ev.kind==='token'){ trace('Writing the answer'); acc+=ev.data; body.innerHTML=render(acc); }
      else if(ev.kind==='tool'){ const t=JSON.parse(ev.data); acc=''; body.innerHTML='';
        trace('Announced local tool: '+t.tool+' (not yet observed)');
        const card=lifeNode({
          kind:'tool_call', state:'announced', source:'proposal',
          hop:t.hop, hop_index:t.hop_index,
          tool:t.tool, label:t.tool, args:redactArgs(t.args)
        });
        cardHost().appendChild(card);
        pendingToolCards.push(card);
        lastMediaHost=card; }
      else if(ev.kind==='tool_result'){
        const text=String(ev.data||'');
        const isErr=/^\\s*(ERROR:|REFUSED)/.test(text);
        trace(isErr?'Observed tool error':'Observed tool result');
        const announced=pendingToolCards.shift();
        const toolName=(announced&&announced.dataset.tool)||'tool_result';
        const result=lifeNode({
          kind:'tool_result',
          state:isErr?'error':'result',
          source:'observation',
          hop:announced&&announced.dataset.hop,
          tool:toolName,
          summary:text.replace(/\\n/g,' ').slice(0,240),
          label:toolName
        });
        cardHost().appendChild(result);
        lastMediaHost=result; }
      else if(ev.kind==='media'){ try{ mountMediaArtifact(lastMediaHost||b, JSON.parse(ev.data)); }catch(e){} }
      else if(ev.kind==='queued'){ const q=JSON.parse(ev.data);
        cardHost().appendChild(lifeNode({
          kind:'queued', state:'announced', source:'observation',
          label:q.reason||'GPU busy', job_id:q.job_id||''
        }));
        setTimeout(refreshQueue,500); }
      else if(ev.kind==='note'){
        const mapped=classifyNote(ev.data);
        cardHost().appendChild(lifeNode({
          kind:mapped.kind, state:mapped.state, source:mapped.source, label:ev.data
        }));
        if(mapped.kind==='waiting_for_permission') refresh(); }
      else if(ev.kind==='error'){
        body.innerHTML='<span class="err">'+esc(ev.data)+'</span>';
        cardHost().appendChild(lifeNode({kind:'blocked', state:'error', source:'observation', label:ev.data}));
        finishTrace(true); }
      else if(ev.kind==='done'){
        body.innerHTML=render(ev.data);
        cardHost().appendChild(lifeNode({kind:'complete', state:'result', source:'observation', label:'Turn complete'}));
        finishTrace(false); }
      log.scrollTop=log.scrollHeight;
    }
  }
  busy=false; send.textContent='Send'; send.classList.remove('stop');
  turnHost=null; pendingToolCards=[];
  finishTrace(false);
  addRegen(); input.focus(); refresh(); updateCharCount();
}"""

new_stream = """async function stream(url,payload){
  const epoch=++streamEpoch;
  setBusy(true);
  const b=bubble('agent'); const body=b.querySelector('.body');
  let acc='', lastMediaHost=b;
  turnHost=b.querySelector('.activity');
  pendingToolCards=[];
  startTrace(); trace('Request received locally');

  try{
    const resp=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
                               body:JSON.stringify(payload)});
    if(!resp.body){
      body.innerHTML='<span class="err">No response stream from the local agent.</span>';
      finishTrace(true);
      return;
    }
    const rd=resp.body.getReader(), dec=new TextDecoder(); let buf='';
    while(true){
      const {done,value}=await rd.read(); if(done) break;
      // Stop (or a newer send) orphaned this reader: keep draining so the
      // server can finish/save, but do not touch the Send/Stop button.
      const orphaned=epoch!==streamEpoch;
      buf+=dec.decode(value,{stream:true});
      const parts=buf.split('\\n\\n'); buf=parts.pop();
      for(const p of parts){
        if(orphaned) continue;
        if(!p.startsWith('data: ')) continue;
        let ev;
        try{ ev=JSON.parse(p.slice(6)); }catch(e){ continue; }
        try{
          if(ev.kind==='conversation'){ const c=JSON.parse(ev.data); cid=c.id; chatTitle=c.title||'Chat';
            activeRouting=c.routing||'';
            activeModel=c.model||'';
            activeWorkspace=c.workspace||activeWorkspace||$('#workspace').value;
            if(activeRouting==='auto_farm' && !activeModel) $('#chatmodel').value='auto_farm';
            else if(activeModel) $('#chatmodel').value=activeModel;
            $('#workspace').value=activeWorkspace;
            $('#chatmodel').disabled=true; $('#workspace').disabled=true; loadChats(); }
          else if(ev.kind==='route'){ const r=JSON.parse(ev.data); refresh();
            const proposal=r.source==='proposal';
            if(!proposal) applyRouteWho(b, r);
            const shown=(String(r.backend||'').toLowerCase()==='farm'||String(r.tier||'').toLowerCase()==='farm')
              ?'FARM':String(r.tier||'').toUpperCase();
            trace(proposal
              ? ('Attempting '+shown+' — not yet observed')
              : ('Routing on '+shown+' with '+(r.model||'the selected model')));
            cardHost().appendChild(lifeNode({
              kind:'route',
              state:proposal?'announced':'result',
              source:proposal?'proposal':'observation',
              hop:r.hop, hop_index:r.hop_index,
              tier:r.tier, model:r.model, backend:r.backend, reason:r.reason,
              gpu_busy:r.gpu_busy, capability:(r.detail&&r.detail.capability),
              label:proposal?'attempting farm':(shown+' '+(r.model||''))
            })); }
          else if(ev.kind==='progress'){
            let prog={}; try{prog=JSON.parse(ev.data)}catch(e){prog={label:ev.data}}
            if(prog.label) trace(prog.label);
            const mapped=progressLifecycle(prog);
            if(mapped){ mapped.hop=prog.hop; mapped.hop_index=prog.hop_index;
              cardHost().appendChild(lifeNode(mapped)); } }
          else if(ev.kind==='token'){ trace('Writing the answer'); acc+=ev.data; body.innerHTML=render(acc); }
          else if(ev.kind==='tool'){ const t=JSON.parse(ev.data); acc=''; body.innerHTML='';
            trace('Announced local tool: '+t.tool+' (not yet observed)');
            const card=lifeNode({
              kind:'tool_call', state:'announced', source:'proposal',
              hop:t.hop, hop_index:t.hop_index,
              tool:t.tool, label:t.tool, args:redactArgs(t.args)
            });
            cardHost().appendChild(card);
            pendingToolCards.push(card);
            lastMediaHost=card; }
          else if(ev.kind==='tool_result'){
            const text=String(ev.data||'');
            const isErr=/^\\s*(ERROR:|REFUSED)/.test(text);
            trace(isErr?'Observed tool error':'Observed tool result');
            const announced=pendingToolCards.shift();
            const toolName=(announced&&announced.dataset.tool)||'tool_result';
            const result=lifeNode({
              kind:'tool_result',
              state:isErr?'error':'result',
              source:'observation',
              hop:announced&&announced.dataset.hop,
              tool:toolName,
              summary:text.replace(/\\n/g,' ').slice(0,240),
              label:toolName
            });
            cardHost().appendChild(result);
            lastMediaHost=result; }
          else if(ev.kind==='media'){ try{ mountMediaArtifact(lastMediaHost||b, JSON.parse(ev.data)); }catch(e){} }
          else if(ev.kind==='queued'){ const q=JSON.parse(ev.data);
            cardHost().appendChild(lifeNode({
              kind:'queued', state:'announced', source:'observation',
              label:q.reason||'GPU busy', job_id:q.job_id||''
            }));
            setTimeout(refreshQueue,500); }
          else if(ev.kind==='note'){
            const mapped=classifyNote(ev.data);
            cardHost().appendChild(lifeNode({
              kind:mapped.kind, state:mapped.state, source:mapped.source, label:ev.data
            }));
            // Permission cards are not a parked SSE: the turn usually continues
            // on CPU. Still refresh the sidebar; busy clears when the stream ends
            // or the operator hits Stop (which orphans this epoch immediately).
            if(mapped.kind==='waiting_for_permission') refresh(); }
          else if(ev.kind==='error'){
            body.innerHTML='<span class="err">'+esc(ev.data)+'</span>';
            cardHost().appendChild(lifeNode({kind:'blocked', state:'error', source:'observation', label:ev.data}));
            finishTrace(true); }
          else if(ev.kind==='done'){
            body.innerHTML=render(ev.data);
            cardHost().appendChild(lifeNode({kind:'complete', state:'result', source:'observation', label:'Turn complete'}));
            finishTrace(false); }
          log.scrollTop=log.scrollHeight;
        }catch(e){ /* one bad event must not leave Stop stuck */ }
      }
    }
  }catch(e){
    if(epoch===streamEpoch){
      const msg=(e&&e.message)?e.message:String(e||'stream failed');
      body.innerHTML='<span class="err">'+esc(msg)+'</span>';
      finishTrace(true);
    }
  }finally{
    // Every terminal path restores Send when this epoch still owns the button:
    // normal done, error, empty completion, exception, client disconnect, and
    // Stop (Stop bumps streamEpoch first so an orphaned reader does not flip
    // a newer turn back to Send mid-flight).
    if(epoch===streamEpoch){
      setBusy(false);
      turnHost=null; pendingToolCards=[];
      finishTrace(false);
      addRegen(); input.focus(); refresh(); updateCharCount();
    }
  }
}"""

if old_stream not in text:
    raise SystemExit("stream() block not found")
text = text.replace(old_stream, new_stream, 1)

old_click = """send.onclick=async()=>{
  if(busy){ await fetch('/api/stop',{method:'POST',headers:{'Content-Type':'application/json'},
              body:JSON.stringify({id:cid})}); return; }
  ask(input.value);
};"""

new_click = """send.onclick=async()=>{
  if(busy){
    // Unlock Send immediately. Keep draining the orphaned SSE so the server
    // can observe /api/stop and persist _[stopped]_ without a BrokenPipe.
    streamEpoch++;
    setBusy(false);
    turnHost=null; pendingToolCards=[];
    finishTrace(true);
    try{
      await fetch('/api/stop',{method:'POST',headers:{'Content-Type':'application/json'},
                  body:JSON.stringify({id:cid})});
    }catch(e){}
    input.focus();
    return;
  }
  ask(input.value);
};"""

if old_click not in text:
    raise SystemExit("send.onclick block not found")
text = text.replace(old_click, new_click, 1)

path.write_text(text, encoding="utf-8")
print("index.html updated OK")
