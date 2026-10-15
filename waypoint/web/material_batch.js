// Optional AI close reading. Local extracted text is already available after upload.
export async function batchReadMaterials(c,materials,projectId,scopeTitle){
 const {api,esc,dialog,toast}=c;
 const [settings,status]=await Promise.all([api('/settings'),api('/usage-status')]);
 const config=(settings.usage_configs||[]).find(x=>x.id===status.config_id)||settings;
 const model=status.effective_provider==='api'?(config.api_role_models?.read?.model||config.model||settings.api_default_model||status.model):(config.model_roles?.read||config.model_roles?.write||'尚未选择');
 const entries=materials.map(m=>({id:m.id,name:m.name,status:'pending',covered:0,total:0,message:''}));let running=false,stopped=false;
 const d=dialog(entries.length===1?'AI 全文精读':'批量 AI 精读',`<p>${esc(scopeTitle)} · ${entries.length} 份资料</p><p><strong>资料模型：${esc(model)}</strong> · ${esc(status.config_name||'当前配置')}</p><p class="note">上传时已在本机收录可提取的全文，写作可直接引用相关页；这里是可选的逐页 AI 精读。原文件与分析历史保留，精读结果需核对事实。</p><p class="note">本操作使用当前模型授权，可能消耗额度或产生已启用 API 的费用；不会自动启用或切换到付费 API。连接或额度失败时只暂停 AI，已收录文字仍可用于写作。</p><p id="batch-reading-summary" role="status" aria-live="polite"></p><div id="batch-reading-results"></div><div class="form-footer"><button id="batch-reading-start" class="primary">${entries.length===1?'开始 AI 精读':'开始本批 AI 精读'}</button><button type="button" id="batch-reading-pause" disabled>暂停</button><button type="button" id="batch-reading-done">返回资料页</button></div>`,async(f,form,modal)=>{
   if(running)return;running=true;stopped=false;form.querySelector('#batch-reading-pause').disabled=false;form.querySelector('#batch-reading-done').disabled=true;
   try{
     for(const entry of entries){
       if(stopped||!modal.open||!modal.contains(form))break;
       if(entry.status==='complete')continue;
       entry.status='working';entry.message='';paint(form);
       try{
         // Server chooses a bounded next range, or adopts an existing complete result without generation.
         while(!stopped&&modal.open&&modal.contains(form)){
           const result=await api('/materials/'+entry.id+'/batch-read',{method:'POST',body:{project_id:projectId}});
           entry.covered=result.covered;entry.total=result.total_units;entry.message=result.message;entry.status=result.status;paint(form);
           if(result.status!=='working')break;
         }
         if(entry.status==='working')entry.status='pending';
       }catch(e){
         const connectionIssue=/额度|连接|登录|API|预算|价格|模型.*不可用/.test(e.message||'');
         entry.status=connectionIssue?'ai_paused':'needs_attention';
         entry.message=e.message||'AI 精读未完成，请核对分析历史后继续';
         if(connectionIssue)stopped=true;
       }
       paint(form);
     }
   }finally{
     running=false;
     if(modal.open&&modal.contains(form)){
       form.querySelector('#batch-reading-pause').disabled=true;form.querySelector('#batch-reading-done').disabled=false;
       const start=form.querySelector('#batch-reading-start');start.hidden=entries.every(x=>x.status==='complete');start.textContent='继续 AI 精读';paint(form);
     }else toast('本批已停止，已完成的分析与采纳保留；可在资料页继续');
   }
 },true);
 const form=d.querySelector('form');
 function paint(host){
   if(!d.open||!d.contains(host))return;
   const done=entries.filter(x=>x.status==='complete').length,attention=entries.filter(x=>x.status==='needs_attention').length,paused=entries.filter(x=>x.status==='ai_paused').length;
   host.querySelector('#batch-reading-summary').textContent=`AI 精读 ${done} / ${entries.length} 份完成 · ${attention} 份资料待核对 · ${paused} 份 AI 暂停${running?(stopped?' · 当前段完成后暂停':' · 处理中'):' · '+(stopped?'已暂停':'可开始或继续')}`;
   host.querySelector('#batch-reading-results').innerHTML=entries.map(x=>`<div class="upload-result"><span>${esc(x.name)}</span><strong class="${x.status==='needs_attention'?'attention-label':''}">${{pending:'尚未 AI 精读',working:'AI 精读中',complete:'AI 精读已采纳',needs_attention:'! 资料待核对',ai_paused:'AI 连接待恢复'}[x.status]}</strong>${x.total?`<p class="note">AI 已采纳 ${x.covered} / ${x.total} 页/段</p>`:''}${x.status==='ai_paused'?'<p class="note">本地已提取的文字仍可用于写作。</p>':''}${x.message?`<p>${esc(x.message)}</p><button type="button" class="status-link" data-batch-material="${x.id}">前往资料处理</button>`:''}</div>`).join('');
   host.querySelectorAll('[data-batch-material]').forEach(b=>{b.disabled=running;b.onclick=async()=>{d.close();c.state.page=projectId===null?'global-materials':'materials';if(projectId!==null)c.state.project=projectId;c.state.materialFocus=b.dataset.batchMaterial;await c.render();};});
 }
 d.addEventListener('close',()=>{stopped=true;},{once:true});
 form.querySelector('#batch-reading-pause').onclick=()=>{stopped=true;form.querySelector('#batch-reading-pause').disabled=true;paint(form);};
 form.querySelector('#batch-reading-done').onclick=async()=>{d.close();await c.render();};paint(form);return d;
}

export function batchArchiveMaterials(c,materials,projectId,scopeTitle){
 const {api,esc,dialog}=c;
 return dialog('批量归档资料',`<p>保存范围：${esc(scopeTitle)} · ${materials.length} 份资料</p><p class="note">归档后不再作为新创作依据；原文件、原文和分析历史保留，关联稿件会提示重新核对。</p><ul>${materials.map(m=>'<li>'+esc(m.name)+'</li>').join('')}</ul><div class="form-footer"><button class="primary">归档所选资料</button></div>`,async(f,form,d)=>{await api('/materials/archive-batch',{method:'POST',body:{ids:materials.map(m=>m.id),project_id:projectId}});d.close();await c.render();c.toast('已归档 '+materials.length+' 份资料');});
}
