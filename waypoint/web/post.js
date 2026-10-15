import {renderStatus,progressLabel} from './status.js';
import {readingControl} from './reading.js';
import {flowHTML,factHTML} from './flow.js';
import {quickComment,commentForm} from './comments.js';
import {wordCountHTML} from './word-counts.js';

function communityLink(name){return /^\/?r\/[A-Za-z0-9_]{1,30}$/.test(name)?'https://www.reddit.com/'+name.replace(/^\//,'')+'/about/rules':'https://www.reddit.com/';}
let refreshTimer;

export async function renderPost(c,id){
 clearTimeout(refreshTimer);
 const {api,esc,main,state,toast,dialog,labels}=c;
 const [{variants},groupDetail]=await Promise.all([api('/tasks/'+id+'/communities'),api('/tasks/'+id)]);
 const t=groupDetail.task;
 const active=variants.filter(x=>!x.retired&&!x.abandoned);
 const details=await Promise.all(active.map(x=>api('/tasks/'+x.id)));
 const live=[groupDetail,...details].some(d=>d.jobs?.some(j=>['queued','running'].includes(j.status)));
 let rows=(t.community_plan||[]).map(x=>({...x,selected:true})),dirty=false,epoch=t.input_epoch,selectionPending=!!t.community_selection_pending;
 const multi=active.length>1;
 main.innerHTML=`<button id="post-back" class="quiet">← 返回品牌项目</button>
  <div class="eyebrow">${esc(state.projects.find(x=>x.id===t.project_id)?.name)} / 帖文 <span class="simulation-label">· 仅供模拟分析</span></div>
  <div class="topbar"><div><h1>${esc(t.name||'新的帖文')}</h1><p class="muted" id="live-state">${esc(labels[t.status])} · ${esc(t.message)}</p></div>
   <div class="actions"><button id="post-input">编辑输入</button><button id="post-stop" ${!live?'disabled':''}>停止</button><button class="primary" id="run-post" ${live?'disabled':''}>${active.length?'继续生成':'生成模拟稿'}</button></div></div>
  ${flowHTML(esc,t,groupDetail.jobs)}
  <div class="panel"><strong>本次输入</strong><div class="draft brief-input">${esc(t.raw_input||'尚未填写想法')}</div></div>
  <details class="panel" id="community-settings" ${selectionPending?'open':''}><summary>社群选择与帖文数量${selectionPending?' · 等待你的确认':''}</summary>
   <p class="note">AI 推荐后，请勾选要保留的社群，为每个社群设置 1–3 篇帖文，确认后开始生成。禁止推广的规则不阻断模拟创作；推荐不代表真实发帖许可。</p>
   <div class="research-tools"><label>推荐数量<select id="recommend-count"><option value="0">由 AI 决定</option>${[1,2,3,4,5].map(n=>`<option value="${n}">${n} 个社群</option>`).join('')}</select></label><button id="recommend">重新推荐</button><button id="add-community">＋ 手动添加社群</button></div>
   <p id="research-status" class="note"></p><div id="community-cards"></div>
   <div class="form-footer"><span class="note" id="plan-total"></span><button class="primary" id="save-plan" ${live?'disabled':''}>确认社群并生成稿件</button></div>
  </details>
  <section class="panel"><div class="panel-heading"><div><h2>模拟稿件</h2><p class="muted">每篇候选独立推进到英文成品。中途节点通过后继续创作，英文成品通过后完成；多稿时可移除一篇。</p></div><span class="badge">${active.length} 篇当前候选</span></div><div id="variant-groups"></div></section>
  <details class="panel abandoned-list"><summary>原稿、历史方案与已移除稿件</summary><button id="original-post">查看原主帖稿件与意见</button>
   ${(t.community_plan_history||[]).length?`<details><summary>历史社群方案</summary><pre>${esc(JSON.stringify(t.community_plan_history,null,2))}</pre></details>`:''}
   ${variants.filter(x=>x.retired||x.abandoned).map(x=>`<div class="row opinion-item"><span>${esc(x.name)} · ${x.abandoned?'已移除':'旧方案'}</span><div class="actions"><button data-open="${x.id}">查看历史</button>${x.abandoned?`<button data-restore="${x.id}">恢复</button>`:''}</div></div>`).join('')}
  </details>`;
 renderStatus(c,t,main.querySelector('#live-state'));
 const inputReading=document.createElement('div');main.querySelector('.brief-input').after(inputReading);
 readingControl(c,inputReading,()=>({project_id:t.project_id,text:t.raw_input}));
 const status=main.querySelector('#research-status');
 const evidenceByName=new Map((t.community_evidence||[]).map(x=>[x.name.toLowerCase(),x]));
 const researching=new Set();
 function evidenceHTML(name){
  const evidence=evidenceByName.get(name.toLowerCase());if(!evidence)return '';
  const sources=[...(evidence.sources||[]),...(evidence.direct_sources||[])];
  const unique=[...new Map(sources.map(x=>[x.url,x])).values()];
  const safe=url=>{try{const u=new URL(url);return u.protocol==='https:'&&['reddit.com','www.reddit.com','old.reddit.com'].includes(u.hostname)&&!u.username&&!u.password;}catch{return false;}};
  return `<div class="community-evidence"><p class="note">${evidence.cache_hit?'复用近期记录':'本次读取'} · ${esc(evidence.checked_at?new Date(evidence.checked_at).toLocaleString():'读取时间未知')} · ${Number(evidence.sample_count)||0} 个帖子样本${evidence.status==='partial'?' · 证据不完整':''}</p><p class="note">${esc(evidence.message||'读取记录已保存')}</p>${!evidence.rules_zh?'<p class="note">规则摘要尚未取得。</p>':''}${(Number(evidence.sample_count)||0)<3?'<p class="note">样本不足三个，无法据此概括整个社群。</p>':''}<details><summary>查看来源与原始证据（${unique.length}）</summary>${unique.map(x=>`<div class="evidence-source">${safe(x.url)?`<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.url)}</a>`:esc(x.url)}<pre>${esc(JSON.stringify(x.content??{},null,2))}</pre></div>`).join('')}</details></div>`;
 }
 function total(){const selected=rows.filter(x=>x.selected&&x.name);main.querySelector('#plan-total').textContent=`已选 ${selected.length} 个社群 · ${selected.reduce((n,x)=>n+Number(x.variants||1),0)} 篇帖文`;main.querySelector('#save-plan').disabled=live||!selected.length;const run=main.querySelector('#run-post');run.textContent=!rows.length?'AI 推荐社群':dirty||selectionPending?'查看并确认社群':'继续生成';if(dirty||selectionPending)run.hidden=false;}
 function draw(){
  main.querySelector('#community-cards').innerHTML=rows.map((x,i)=>`<article class="community-card" data-index="${i}"><label class="community-selection"><input type="checkbox" data-select-community="${i}" ${x.selected?'checked':''} ${live?'disabled':''}>选用此社群</label><div class="community-heading"><label>模拟社群<input data-field="name" placeholder="r/社群名" value="${esc(x.name)}" ${live?'disabled':''}></label><label>帖文数量<select data-field="variants" ${live?'disabled':''}>${[1,2,3].map(n=>`<option value="${n}" ${Number(x.variants)===n?'selected':''}>${n} 篇</option>`).join('')}</select></label><button data-remove="${i}" class="quiet" ${live?'disabled':''}>移除社群</button></div>
   ${x.reason_zh?`<p class="note">推荐理由：${esc(x.reason_zh)}</p>`:''}
   <div class="actions"><button data-research="${i}" ${researching.has(x.name.toLowerCase())?'disabled':''}>查询规则与讨论风格</button><button data-refresh-research="${i}" class="quiet" ${researching.has(x.name.toLowerCase())?'disabled':''}>刷新</button><a href="${communityLink(x.name)}" target="_blank" rel="noopener">打开社群 ↗</a></div>
   ${evidenceHTML(x.name)}
   <div class="grid2"><label>已知规则或限制<textarea data-field="rules_zh" placeholder="可留空；未核实会显示为待核对">${esc(x.rules_zh)}</textarea></label><label>风格与生态<textarea data-field="culture_zh" placeholder="可留空；模型会按已知内容模拟">${esc(x.culture_zh)}</textarea></label></div></article>`).join('');
  main.querySelectorAll('[data-index]').forEach(card=>{const i=Number(card.dataset.index);card.querySelectorAll('[data-field]').forEach(input=>input.oninput=()=>{const key=input.dataset.field;rows[i][key]=key==='variants'?Number(input.value):input.value;rows[i].confirmed=false;dirty=true;total();});});
  main.querySelectorAll('[data-select-community]').forEach(input=>input.onchange=()=>{rows[Number(input.dataset.selectCommunity)].selected=input.checked;dirty=true;total();});
  main.querySelectorAll('[data-remove]').forEach(button=>button.onclick=()=>{rows.splice(Number(button.dataset.remove),1);dirty=true;draw();});
  main.querySelectorAll('[data-research],[data-refresh-research]').forEach(button=>button.onclick=async()=>{
   const refresh=button.dataset.refreshResearch!==undefined,row=rows[Number(refresh?button.dataset.refreshResearch:button.dataset.research)],name=row.name,key=name.toLowerCase();
   if(researching.has(key))return;researching.add(key);draw();status.textContent='正在读取公开规则和帖子样本…';
   try{const evidence=await api(`/tasks/${id}/communities/research`,{method:'POST',body:{name,refresh}});evidenceByName.set(key,evidence);
    if(row.name.toLowerCase()===key&&rows.includes(row)){if(evidence.rules_zh)row.rules_zh=evidence.rules_zh;if(evidence.culture_zh)row.culture_zh=evidence.culture_zh;row.confirmed=false;dirty=true;}
    status.textContent=evidence.message||'查询记录已保存。';
   }catch(error){status.textContent=error.message;}finally{researching.delete(key);draw();}
  });
  total();
 }
 draw();
 if(!selectionPending&&!dirty&&!live&&active.length&&details.every(d=>['checkpoint_ready','final_ready','finished'].includes(d.task.workflow_phase)))main.querySelector('#run-post').hidden=true;
 async function save(confirm=false){const items=rows.filter(x=>x.selected&&x.name?.trim()).map(({selected,...x})=>({...x,confirmed:confirm}));if(confirm&&!items.length)throw Error('请至少勾选一个社群');const saved=await api(`/tasks/${id}/communities`,{method:'PUT',body:{items,expected_epoch:epoch}});epoch=saved.input_epoch;selectionPending=!!saved.community_selection_pending;dirty=false;return saved;}
 main.querySelector('#add-community').disabled=live;main.querySelector('#recommend').disabled=live;
 main.querySelector('#add-community').onclick=()=>{if(rows.length>=5)return toast('最多选择 5 个社群');rows.push({name:'',variants:1,rules_zh:'',culture_zh:'',confirmed:false,selected:true});dirty=true;draw();};
 main.querySelector('#recommend').onclick=async event=>{event.target.disabled=true;status.textContent='正在推荐模拟社群…';try{const answer=await api(`/tasks/${id}/communities/recommend`,{method:'POST',body:{count:Number(main.querySelector('#recommend-count').value)}});rows=answer.items.map(x=>({...x,selected:true}));dirty=true;await save(false);draw();status.textContent='推荐已保存，请勾选社群和帖文数量，再确认生成。';}catch(error){status.textContent=error.message;}finally{event.target.disabled=false;}};
 main.querySelector('#save-plan').onclick=async event=>{event.target.disabled=true;try{await save(true);await api(`/tasks/${id}/run`,{method:'POST',body:{resume:true}});toast('社群与数量已确认，正在生成稿件');await c.render();}catch(error){toast(error.message);event.target.disabled=false;}};
 main.querySelector('#run-post').onclick=async()=>{if(rows.length&&(dirty||selectionPending)){const panel=main.querySelector('#community-settings');panel.open=true;panel.scrollIntoView({behavior:'smooth'});return;}await api(`/tasks/${id}/run`,{method:'POST',body:{resume:true}});toast(rows.length?'模拟稿正在生成':'正在推荐社群，完成后请确认');await c.render();};
 main.querySelector('#post-back').onclick=()=>{state.page='home';c.render();};
 main.querySelector('#post-input').onclick=async()=>{if(dirty&&rows.length)await save();c.taskForm((await api('/tasks/'+id)).task);};
 main.querySelector('#post-stop').onclick=async()=>{if(t.job_id)await api('/jobs/'+t.job_id+'/stop',{method:'POST'});await c.render();};
 main.querySelector('#original-post').onclick=()=>{state.originalPost=id;c.render();};

 const names=[...new Set(active.map(x=>x.community.name))];
 main.querySelector('#variant-groups').innerHTML=names.map(name=>`<div class="variant-group"><h3>${esc(name)}</h3><div class="variant-grid">${details.filter(d=>d.task.community.name===name).map(d=>{
  const x=d.task,en=d.revisions.find(r=>r.id===x.active[x.target_stage]);
  const tr=d.revisions.find(r=>r.id===x.active.backtranslation);
  const intermediate=x.target_stage!=='english';
  const passed=!intermediate&&en&&d.approvals.some(a=>a.revision_id===en.id&&a.simulation_pass);
  const translating=x.target_stage==='english'&&(!tr||tr.stale||tr.source_revision_id!==en?.id);
  return `<article class="variant-card" data-variant-task="${x.id}"><div class="panel-heading"><strong>候选 ${x.variant_number} · ${esc(labels[x.target_stage])}${intermediate?'查看节点':''}</strong><span class="badge">${passed?'已通过 · ':''}${esc(progressLabel(x,labels))}</span></div>
   <p class="muted">${esc(x.message)}</p><h3>${esc(en?.title)}</h3><div class="variant-preview">${esc(en?.body||'等待生成')}</div>
   ${factHTML(esc,en)}
   ${(en?.questions||[]).map(q=>`<p class="note">待核实：${esc(q)}</p>`).join('')}
   ${(en?.issues||[]).map(issue=>`<p class="note">${esc(issue.message_zh)}</p>`).join('')}
   ${tr&&tr.source_revision_id===en?.id&&!tr.stale?`<details><summary>对应中文回译</summary><p class="draft">${esc(tr.title)}\n${esc(tr.body)}</p></details>`:''}
   <div class="actions decision-actions">${en&&!en.stale&&!en.candidate?`${intermediate?`<button class="primary" data-continue="${x.id}" data-revision="${en.id}" ${live?'disabled':''}>通过并直达英文成品</button>`:`<button data-pass="${x.id}" data-revision="${en.id}" ${passed||translating?'disabled':''}>${passed?'已通过':'通过'}</button>`}<button data-opinion="${x.id}" data-revision="${en.id}">添加意见</button>${multi&&!['queued','running'].includes(x.status)?`<button data-abandon="${x.id}" class="quiet">移除</button>`:''}`:''}</div>
   <button class="quiet" data-open="${x.id}">查看稿件与历史</button>${en?.stale?'<p class="note">依据有变化，旧稿保留，需重新核对。</p>':''}</article>`;
 }).join('')}</div></div>`).join('')||'<p class="empty">填写输入后点击“生成模拟稿”；社群可由模型选择。</p>';
 main.querySelectorAll('[data-variant-task]').forEach(card=>{const item=details.find(x=>x.task.id===card.dataset.variantTask),rev=item?.revisions.find(x=>x.id===item.task.active[item.task.target_stage]);if(rev){const host=document.createElement('div');card.querySelector('.variant-preview').after(host);readingControl(c,host,()=>({project_id:t.project_id,revision_id:rev.id}),rev.stage==='english'?{copyText:()=>[rev.title,rev.body].filter(Boolean).join('\n\n')}:{});}});
 main.querySelectorAll('[data-open]').forEach(button=>button.onclick=()=>c.openTask(button.dataset.open));
 main.querySelectorAll('[data-variant-task]').forEach(card=>{const d=details.find(x=>x.task.id===card.dataset.variantTask),rev=d?.revisions.find(x=>x.id===d.task.active.english);
  if(rev&&d.task.target_stage==='english')card.querySelector('.variant-preview').insertAdjacentHTML('beforebegin',wordCountHTML(rev.title,rev.body));
  if(d?.task.target_stage!=='english'||!rev?.complete||rev.stale||rev.candidate||d.task.abandoned||d.task.retired)return;
  const button=document.createElement('button');button.dataset.quickComment=rev.id;button.textContent='生成铺评';button.disabled=live;
  button.onclick=()=>quickComment(c,rev.id,d.task.project_id,button);const actions=card.querySelector('.decision-actions');actions.insertBefore(button,actions.querySelector('[data-abandon]'));
  const choice=document.createElement('label');choice.className='note';choice.innerHTML=`<input type="checkbox" data-comment-revision="${rev.id}"> 批量铺评`;
  card.querySelector('.panel-heading').after(choice);
 });
 const choices=[...main.querySelectorAll('[data-comment-revision]')];
 if(choices.length>1){const tools=document.createElement('div');tools.className='actions';tools.innerHTML='<button type="button" id="select-comment-posts">全选原帖</button><button type="button" id="batch-own-comments" disabled>生成所选铺评</button>';
  main.querySelector('#variant-groups').before(tools);const generate=tools.querySelector('#batch-own-comments');
  function selectedChanged(){const count=choices.filter(x=>x.checked).length;generate.disabled=!count||live;generate.textContent='生成所选铺评'+(count?' · '+count+' 篇':'');}
  choices.forEach(x=>x.onchange=selectedChanged);tools.querySelector('#select-comment-posts').onclick=()=>{const all=choices.every(x=>x.checked);choices.forEach(x=>x.checked=!all);selectedChanged();};
  generate.onclick=()=>{const ids=choices.filter(x=>x.checked).map(x=>x.dataset.commentRevision);const owners=Object.fromEntries(details.flatMap(d=>d.revisions.map(r=>[r.id,d.task.id])));commentForm(c,null,{revision_ids:ids,revision_tasks:owners});};
 }
 main.querySelectorAll('[data-pass]').forEach(button=>button.onclick=async()=>{await api(`/revisions/${button.dataset.revision}/pass`,{method:'POST'});toast('这篇模拟稿已通过');await c.render();});
 main.querySelectorAll('[data-continue]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await api(`/tasks/${button.dataset.continue}/to-english`,{method:'POST',body:{revision_id:button.dataset.revision}});toast('查看节点已通过，正在生成英文与回译');await c.render();}catch(error){button.disabled=false;toast(error.message);}});
 main.querySelectorAll('[data-opinion]').forEach(button=>button.onclick=()=>{const detail=details.find(x=>x.task.id===button.dataset.opinion),rev=detail.revisions.find(x=>x.id===button.dataset.revision);const selected=window.getSelection()?.toString()||'',scope=selected&&rev.body.includes(selected)?selected:'';dialog('添加修改意见',`<p class="note">意见会针对这篇稿件生成新版本，原稿保留。</p>${scope?`<p class="note">只改所选片段：${esc(scope)}</p>`:''}<textarea name="raw_text" rows="5" required placeholder="说出要保留或修改的内容"></textarea><div class="form-footer"><button class="primary">添加意见并重写</button></div>`,async(f,form,d)=>{await api(`/tasks/${detail.task.id}/opinions`,{method:'POST',body:{stage:rev.stage,base_revision_id:rev.id,source:'user',raw_text:f.get('raw_text'),scope:scope?'selection':'task',selection:scope,field:'body'}});await api(`/tasks/${detail.task.id}/run`,{method:'POST',body:{resume:true}});d.close();toast('已保存意见并开始返修');await c.render();});});
 main.querySelectorAll('[data-abandon]').forEach(button=>button.onclick=async()=>{await api(`/tasks/${button.dataset.abandon}/abandon`,{method:'POST'});toast('候选稿已移至历史');await c.render();});
 main.querySelectorAll('[data-restore]').forEach(button=>button.onclick=async()=>{await api(`/tasks/${button.dataset.restore}/restore`,{method:'POST'});toast('候选稿已恢复');await c.render();});
 if(live)refreshTimer=setTimeout(async()=>{if(state.task===id&&state.page==='task')await c.render();},900);
}
