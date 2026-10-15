import {readingControl} from './reading.js';

const stages=['theme','idea','chinese','english','cb'];
const uuid=()=>crypto.randomUUID();

export async function commentForm(c,existing=null,defaults={}){
 const {api,esc,state,dialog,toast}=c,pid=existing?.project_id||state.project,t=existing||defaults;
 let source=null,epoch=0,job=null,selected=new Set(),timer,saveTimer,saveChain=Promise.resolve(),batchRequest=uuid();
 const bound=!!existing?.comment_source_id;
 const d=dialog(existing?'编辑评论要求':'选择原帖，生成模拟评论',`
 <section><h3>① ${bound?'本任务固定围绕的原帖':'先确定一篇或多篇原帖'}</h3>
 <p class="note">一篇原帖对应一个独立评论任务。任务创建后不能换帖，需要换帖时新建任务。</p>
 ${bound?'':`<label>原帖来源<select id="source-mode"><option value="project">引用项目中正在进行的帖文</option><option value="text">粘贴原帖纯文字</option><option value="link">输入原帖链接</option><option value="screenshot">上传原帖截图</option><option value="search">全站搜索适合评论的帖文</option></select></label>`}
 <div id="source-input"></div><p id="source-status" class="note" role="status"></p><div id="source-results"></div>
 <div id="source-preview" hidden><h3>${bound?'固定原帖快照':'选用的原帖'}</h3><div id="source-meta"></div><textarea id="source-text" rows="7" aria-label="原帖内容"></textarea><div id="source-reading"></div></div></section>
 <section id="comment-intent" hidden><h3>② 评论意图与先查看的节点</h3>
 <label>任务名称<input name="name" value="${esc(t.name||'')}" maxlength="200" placeholder="可留空，按原帖命名"></label>
 <label>我的评论意图<textarea name="raw_input" rows="4" placeholder="回应什么、保留什么，可留空让 AI 自拟。多篇原帖分别理解，不套同一段评论。">${esc(t.raw_input||'')}</textarea></label><div id="intent-reading"></div>
 <div class="grid2"><label>输入阶段<select name="input_stage">${stages.map(k=>`<option value="${k}" ${(t.input_stage||'idea')===k?'selected':''}>${c.labels[k]}</option>`).join('')}</select></label>
 <label>先查看哪一步（终点为英文成品）<select name="target_stage">${stages.map(k=>`<option value="${k}" ${(t.target_stage||'english')===k?'selected':''}>${c.labels[k]}</option>`).join('')}</select></label></div>
 <p class="note">默认每篇生成一条 40–90 词英文评论及对应中文回译。明确的篇幅要求优先。</p></section>
 <div class="form-footer"><button class="primary" id="save-comment" disabled>${existing?'保存评论要求':'生成所选铺评'}</button></div>`,async(f,form,modal)=>{
  if(existing){
   if(!source)throw Error('请先绑定一篇原帖');
   if(bound)await api('/tasks/'+existing.id,{method:'PATCH',body:Object.fromEntries(f)});
   else await api('/comments',{method:'POST',body:{...Object.fromEntries(f),project_id:pid,task_id:existing.id,expected_epoch:existing.input_epoch,source_id:source.id,source_text:d.querySelector('#source-text').value,selection_mode:'automatic_simulation'}});
   await api('/tasks/'+existing.id+'/run',{method:'POST',body:{resume:true}});modal.close();await c.openTask(existing.id);return;
  }
  if(mode()==='search'||defaults.revision_ids){
   const ids=[...selected];if(!ids.length)throw Error('请至少勾选一篇原帖');
   await persist();
   const result=await api('/comments/batch',{method:'POST',body:{...Object.fromEntries(f),project_id:pid,request_id:batchRequest,
    ...(defaults.revision_ids?{revision_ids:ids}:{source_ids:ids})}});
   modal.close();state.project=pid;state.page='home';state.kind='comment';state.task=null;state.revision=null;
   await c.render();toast('已开启 '+result.results.length+' 个独立评论任务');return;
  }
  if(!source)throw Error('请先选择评论围绕的原帖');
  const result=await api('/comments',{method:'POST',body:{...Object.fromEntries(f),project_id:pid,source_id:source.id,source_text:d.querySelector('#source-text').value,selection_mode:'automatic_simulation'}});
  await api('/tasks/'+result.id+'/run',{method:'POST',body:{resume:true}});modal.close();await c.openTask(result.id);
 },true);
 const input=d.querySelector('#source-input'),status=d.querySelector('#source-status'),results=d.querySelector('#source-results');
 const alive=()=>d.open&&input.isConnected;
 const mode=()=>d.querySelector('#source-mode')?.value||'fixed';
 function ready(){const yes=existing?!!source:mode()==='search'||defaults.revision_ids?selected.size>0:!!source;
  d.querySelector('#comment-intent').hidden=!yes;d.querySelector('#save-comment').disabled=!yes;
  if(!existing)d.querySelector('#save-comment').textContent='生成所选铺评'+(selected.size?' · '+selected.size+' 篇':'');}
 function persist(){
  clearTimeout(saveTimer);if(!job||!input.isConnected)return saveChain;
  const id=job.id,body={batch_request_id:batchRequest,...Object.fromEntries(new FormData(d.querySelector('form')))};
  // A completed server result may not yet have reached this browser. Never
  // overwrite its default selection with the empty local running state.
  if(job.result)body.selected_source_ids=[...selected];
  saveChain=saveChain.catch(()=>{}).then(()=>api('/comment-search-jobs/'+id,{method:'PATCH',body}));return saveChain;
 }
 function saveSoon(){clearTimeout(saveTimer);saveTimer=setTimeout(()=>persist().catch(e=>{if(alive())status.textContent=e.message;}),250);}
 d.addEventListener('close',()=>{clearTimeout(timer);persist().catch(()=>{});},{once:true});
 d.querySelector('#comment-intent').addEventListener('input',()=>{batchRequest=uuid();saveSoon();});
 readingControl(c,d.querySelector('#intent-reading'),()=>({project_id:pid,text:d.querySelector('[name="raw_input"]').value}));
 function preview(m){
  source=m;d.querySelector('#source-preview').hidden=false;d.querySelector('#source-text').value=m.text;d.querySelector('#source-text').readOnly=bound||!!m.parent_revision_id;
  const href=/^https:\/\/(www\.|old\.)?reddit\.com\//.test(m.url||'')||/^https:\/\/redd\.it\//.test(m.url||'')?m.url:'';
  d.querySelector('#source-meta').innerHTML=`<strong>${esc(m.name)}</strong>${href?` <a href="${esc(href)}" target="_blank" rel="noopener">打开原帖 ↗</a>`:''}${m.source_mode==='screenshot'?`<details><summary>查看原始截图</summary><img class="source-image" src="/api/materials/${m.id}/file" alt="原帖截图"></details>`:''}<p class="note">${esc(m.note_zh||'')}${m.verification_status==='web_excerpt'?' 联网结果为原帖摘录，不代表全文。':''}</p>`;
  const host=d.querySelector('#source-reading');host.replaceChildren();readingControl(c,host,()=>({project_id:pid,text:d.querySelector('#source-text').value}));ready();
 }
 function candidates(value){
  selected=new Set(value.selected_source_ids);source=null;d.querySelector('#source-preview').hidden=true;
  if(existing&&value.result?.items?.length)selected=new Set([value.result.items[0].id]);
  results.innerHTML=(value.result?.items||[]).map((m,i)=>`<article class="panel"><div class="panel-heading"><label><input type="checkbox" data-pick-source="${esc(m.id)}" ${selected.has(m.id)?'checked':''}> ${i+1}. ${esc(m.name)}</label><span class="badge">推荐程度：${{high:'高',medium:'中',low:'低'}[m.recommendation]}</span></div>
   <p class="note">${esc(m.date_evidence||m.published_at?.slice(0,10)||'')} · ${esc(m.url)}</p>${m.date_note_zh?`<p class="note">${esc(m.date_note_zh)}</p>`:''}
   <p>适合理由：${esc(m.reason_zh)}</p><p>切入点：${esc(m.angle_zh)}</p>${m.caution_zh?`<p class="note">${esc(m.caution_zh)}</p>`:''}
   <details><summary>原帖摘录与查询依据</summary><div class="draft">${esc(m.text)}</div><pre>${esc(JSON.stringify(m.sources,null,2))}</pre><div data-result-reading="${i}"></div></details></article>`).join('');
  results.querySelectorAll('[data-pick-source]').forEach(el=>el.onchange=()=>{
   if(existing){selected.clear();source=null;results.querySelectorAll('[data-pick-source]').forEach(other=>other.checked=other===el&&el.checked);if(el.checked)preview(value.result.items.find(x=>x.id===el.dataset.pickSource));}
   el.checked?selected.add(el.dataset.pickSource):selected.delete(el.dataset.pickSource);batchRequest=uuid();ready();saveSoon();});
  results.querySelectorAll('[data-result-reading]').forEach(h=>readingControl(c,h,()=>({project_id:pid,material_id:value.result.items[Number(h.dataset.resultReading)].id})));
  if(existing&&selected.size)preview(value.result.items[0]);ready();
 }
 function showJob(value,restore=false){
  const changed=!job||job.id!==value.id||job.status!==value.status;job=value;
  status.textContent=({queued:'排队中',running:'搜索中',completed:'已完成',paused:'! 待你处理',failed:'! 待你处理',interrupted:'已中断'}[value.status]||value.status)+' · '+value.message+(value.result?.note_zh?' '+value.result.note_zh:'');
  if(restore){batchRequest=value.batch_request_id||uuid();input.querySelector('#search-goal').value=value.keywords;input.querySelector('#search-count').value=value.count;input.querySelector('#search-days').value=value.days;
   for(const key of ['name','raw_input','input_stage','target_stage'])d.querySelector('[name="'+key+'"]').value=value[key]||({'input_stage':'idea','target_stage':'english'}[key]||'');}
  const running=['queued','running'].includes(value.status);input.querySelector('#load-source').disabled=running;input.querySelector('#load-source').textContent=value.result?'重新搜索':'全站搜索并推荐';input.querySelector('#stop-search').hidden=!running;
  if(changed||restore)candidates(value);clearTimeout(timer);if(running)timer=setTimeout(poll,900);
 }
 async function poll(){if(!alive()||mode()!=='search')return;try{showJob(await api('/comment-search-jobs/'+job.id));}catch(e){if(!alive())return;status.textContent=e.message;timer=setTimeout(poll,2500);}}
 async function action(button,fn,apply){const current=++epoch;button.disabled=true;status.textContent='正在读取原帖依据…';
  try{const value=await fn();if(current===epoch&&alive())apply(value);}catch(e){if(current===epoch&&alive())status.textContent=e.message;}finally{if(button.isConnected)button.disabled=false;}}
 async function draw(){
  await persist().catch(()=>{});clearTimeout(timer);job=null;epoch++;const currentEpoch=epoch;
  source=null;selected.clear();results.replaceChildren();status.textContent='';d.querySelector('#source-preview').hidden=true;ready();const current=mode();
  if(current==='project'){
   input.innerHTML='<p class="note">正在读取本品牌帖文版本…</p>';
   const tasks=await api('/tasks?project_id='+pid),detail=await Promise.all(tasks.filter(x=>x.kind==='post'&&!x.retired&&!x.abandoned).map(x=>api('/tasks/'+x.id)));
   if(currentEpoch!==epoch||!alive())return;
   const revisions=detail.flatMap(x=>x.revisions.filter(v=>v.stage!=='backtranslation'&&!v.stale&&!v.candidate&&v.complete&&x.task.active[v.stage]===v.id).map(v=>({...v,task:x.task})));
   input.innerHTML=`<label>帖文及确切版本<select id="source-revision"><option value="">请选择当前稿件</option>${revisions.map(v=>`<option value="${v.id}">${esc(v.task.name||v.task.raw_input.slice(0,25))} · ${esc(v.task.community?.name||'')} · ${c.labels[v.stage]}</option>`).join('')}</select></label><button type="button" id="load-source">引用并预览</button>${revisions.length?'':'<p class="note">本品牌暂无可引用的有效帖文稿件。</p>'}`;
  }else if(current==='text')input.innerHTML='<label>原帖文字<textarea id="source-paste" rows="7" placeholder="粘贴标题和正文，保留原文"></textarea></label><button type="button" id="load-source">读取这篇原帖</button>';
  else if(current==='link')input.innerHTML='<label>原帖链接<input id="source-url" type="url" placeholder="https://www.reddit.com/r/.../comments/..."></label><button type="button" id="load-source">联网读取原帖</button>';
  else if(current==='screenshot')input.innerHTML='<label>原帖截图<input id="source-file" type="file" accept=".png,.jpg,.jpeg"></label><button type="button" id="load-source">读取截图中的原帖</button><p class="note">保留原始附件，仅识别可见内容。</p>';
  else input.innerHTML='<label>搜索意图或产品重点<textarea id="search-goal" rows="3" placeholder="留空则依据本品牌资料"></textarea></label><div class="grid2"><label>目标数量<select id="search-count">'+[1,2,3,4,5].map(n=>`<option ${n===3?'selected':''}>${n}</option>`).join('')+'</select></label><label>最近几天<input id="search-days" type="number" min="0" max="30" step="1" value="10"></label></div><p class="note">0 = 今天，1 = 最近 24 小时，最多 30 天。关闭窗口后后台搜索继续，再次打开恢复结果。公开检索可能有遗漏，不足数量如实说明。</p><div class="actions"><button type="button" id="load-source">全站搜索并推荐</button><button type="button" id="stop-search" hidden>停止搜索</button></div>';
  input.querySelector('#load-source').onclick=async ev=>{
   if(current==='search'){
    const button=ev.currentTarget;button.disabled=true;
    try{await persist().catch(()=>{});const value=await api('/comment-search-jobs',{method:'POST',body:{project_id:pid,keywords:input.querySelector('#search-goal').value,count:Number(input.querySelector('#search-count').value),days:Number(input.querySelector('#search-days').value),request_id:uuid()}});
     if(!alive()||mode()!=='search')return;batchRequest=uuid();showJob(value);await persist();}
    catch(e){if(alive()){status.textContent=e.message;button.disabled=false;}}return;
   }
   action(ev.currentTarget,async()=>{
    const data={project_id:pid,mode:current};
    if(current==='project')data.revision_id=input.querySelector('#source-revision').value;
    if(current==='text')data.text=input.querySelector('#source-paste').value;
    if(current==='link')data.url=input.querySelector('#source-url').value;
    if(current==='screenshot'){const file=input.querySelector('#source-file').files[0];if(!file)throw Error('请先选择截图');const fd=new FormData();fd.append('project_id',pid);fd.append('file',file);data.material_id=(await api('/materials/upload',{method:'POST',body:fd})).id;}
    return api('/comment-sources',{method:'POST',body:data});
   },value=>{preview(value);status.textContent='原帖已读取，创建后固定保留。';});
  };
  if(current==='search'){
   input.querySelector('#stop-search').onclick=async()=>{if(job){const value=await api('/comment-search-jobs/'+job.id+'/stop',{method:'POST'});if(alive()&&mode()==='search')showJob(value);}};
   input.querySelector('#load-source').disabled=true;status.textContent='正在恢复搜索记录…';
   const latest=await api('/comment-search-jobs?project_id='+pid);
   if(currentEpoch===epoch&&alive()){if(latest)showJob(latest,true);else{input.querySelector('#load-source').disabled=false;status.textContent='';}}
  }
 }
 if(bound){
  const rows=await api('/materials?project_id='+pid),found=rows.find(x=>x.id===existing.comment_source_id);if(!alive())return;if(found)preview(found);else status.textContent='固定原帖快照缺失，请检查迁移资料；不能改用其他原帖。';
 }else if(defaults.revision_ids){
  const details=await Promise.all(defaults.revision_ids.map(id=>api('/tasks/'+defaults.revision_tasks[id])));if(!alive())return;d.querySelector('#source-mode').hidden=true;selected=new Set(defaults.revision_ids);
  results.innerHTML=details.map((item,i)=>{const rev=item.revisions.find(x=>x.id===defaults.revision_ids[i]);return `<article class="panel"><label><input type="checkbox" data-own="${esc(rev.id)}" checked> ${esc(item.task.name)} · ${esc(item.task.community?.name||'')}</label><h3>${esc(rev.title)}</h3><div class="draft">${esc(rev.body)}</div></article>`;}).join('');
  results.querySelectorAll('[data-own]').forEach(el=>el.onchange=()=>{el.checked?selected.add(el.dataset.own):selected.delete(el.dataset.own);batchRequest=uuid();ready();});ready();
 }else{
  d.querySelector('#source-mode').onchange=()=>draw().catch(e=>status.textContent=e.message);d.querySelector('#source-mode').value=defaults.source_mode||'project';await draw();
 }
}

export async function commentSourcePanel(c,t,host){
 host.innerHTML='<div class="panel-heading"><h3>评论围绕的固定原帖</h3></div><div id="confirmed-source"></div>';const box=host.querySelector('#confirmed-source');
 if(!t.comment_source_id){box.innerHTML='<p class="note">旧任务尚未绑定原帖，绑定一次后固定保留。</p><button type="button">选择一篇原帖</button>';box.querySelector('button').onclick=()=>commentForm(c,t);return;}
 const rows=await c.api('/materials?project_id='+t.project_id),source=rows.find(m=>m.id===t.comment_source_id);if(!source||!host.isConnected)return;
 let url='';try{const parsed=new URL(source.url);if(['https:','http:'].includes(parsed.protocol)&&!parsed.username&&!parsed.password)url=source.url;}catch{}
 box.innerHTML=`<details><summary><span>${c.esc(source.name)}</span>${url?`<span class="source-link-actions"><a href="${c.esc(url)}" target="_blank" rel="noopener noreferrer" title="打开原帖">${c.esc(url)}</a><button type="button" class="quiet" data-copy-source-link aria-label="复制原帖链接">复制链接</button></span>`:''}</summary><div class="draft">${c.esc(source.text)}</div><div id="confirmed-source-reading"></div></details><button type="button" class="quiet" data-new-source-comment>围绕其他原帖新建任务</button>`;
 box.querySelector('[data-new-source-comment]').onclick=()=>commentForm(c);
 const copy=box.querySelector('[data-copy-source-link]');if(copy)copy.onclick=async event=>{
  event.preventDefault();event.stopPropagation();
  try{await navigator.clipboard.writeText(url);c.toast('原帖链接已复制');}
  catch{const modal=c.dialog('复制原帖链接',`<input id="source-link-copy" readonly value="${c.esc(url)}" aria-label="原帖链接">`,async()=>{});modal.querySelector('#source-link-copy').select();}
 };
 if(t.parent_revision_id){
  const tasks=await c.api('/tasks?project_id='+t.project_id);
  for(const parent of tasks.filter(x=>x.kind==='post')){const detail=await c.api('/tasks/'+parent.id);if(!detail.revisions.some(x=>x.id===t.parent_revision_id))continue;
   const revision=parent.active.english;if(revision&&revision!==t.parent_revision_id&&host.isConnected){const button=document.createElement('button');button.type='button';button.textContent='围绕新版本新建任务';button.onclick=()=>quickComment(c,revision,t.project_id,button);box.append(button);}break;}
 }
 readingControl(c,box.querySelector('#confirmed-source-reading'),()=>({project_id:t.project_id,material_id:source.id}));
}

export async function quickComment(c,revisionId,projectId,button){
 const label=button.textContent;button.disabled=true;button.textContent='正在创建铺评…';
 try{const result=await c.api('/revisions/'+revisionId+'/quick-comment',{method:'POST',body:{project_id:projectId}});
  c.state.kind='comment';c.toast(result.created?'正在生成英文铺评与中文回译':'已打开这篇帖文的铺评任务');await c.openTask(result.id);
 }catch(error){button.disabled=false;button.textContent=label;c.toast(error.message);}
}
