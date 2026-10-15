import {uploadMaterials,bindMaterialDrop} from './material_upload.js';
import {batchReadMaterials,batchArchiveMaterials} from './material_batch.js';
import {materialReading,supplementMaterial} from './material_reading.js';
import {commentForm} from './comments.js';
import {readingControl} from './reading.js';
export async function renderMaterials(c,globalScope=false){const {state,main,api,esc,dialog,toast}=c;const projectId=globalScope?null:state.project;const scopeTitle=globalScope?'全局规则与资料':(state.projects.find(p=>p.id===projectId)?.name||'当前品牌')+' · 品牌资料';if(!globalScope&&!projectId){main.innerHTML='<h1>品牌资料</h1><p>请先选择品牌；通用内容可直接进入侧栏“全局规则与资料”。</p>';return;}const materials=await api('/materials'+(globalScope?'':'?project_id='+projectId));const rules=await api('/rules'+(globalScope?'':'?project_id='+projectId));main.innerHTML=`<div class="eyebrow">让每次创作都有依据</div><div class="topbar"><div><h1>${esc(scopeTitle)}</h1><p class="muted">${globalScope?'适用于所有品牌。通用事实和策略自动作为创作依据；附件、样例可在具体任务中选择。':'当前品牌的事实、策略、附件与规则单独归纳；同时沿用全局规则和通用资料。'}</p></div><div class="actions"><button id="find-posts" ${globalScope?'hidden':''}>寻找原帖</button><button id="upload">导入文件</button><button class="primary" id="add-material">＋ 添加资料</button></div></div><div id="material-drop" class="material-drop" role="button" tabindex="0" aria-label="拖拽上传资料">拖拽文件到此处上传 · 支持多文件 · 保存至 ${esc(scopeTitle)}</div><div class="grid2"><div class="panel"><div class="panel-heading"><h2>${globalScope?'全局资料':'本品牌资料'}</h2><span class="badge">${materials.filter(x=>!x.archived).length} 份</span></div><div class="material-batch-tools"><label><input type="checkbox" id="material-select-all"> 全选</label><span id="material-selection-count" class="note">已选 0 份</span><details><summary>人工重读（可选）</summary><button id="batch-read-materials">读取所选资料</button></details><button id="batch-archive-materials" disabled>归档所选资料</button></div>${materials.filter(x=>!x.archived).map(m=>`<article class="material" data-material="${m.id}"><div class="row"><label class="material-select"><input type="checkbox" data-select-material="${m.id}" aria-label="选择资料：${esc(m.name)}"><h3>${esc(m.name)}</h3></label><span class="badge">${{fact:'产品事实',strategy:'项目策略',sample:'认可样例',thread:'原帖',attachment:'附件'}[m.kind]}</span></div><small>${m.trust==='user_confirmed'?'用户确认':'待核实'} · ${m.extraction==='needs_image'?'需要图片识别':m.extraction==='needs_text'?(m.units?.some(u=>u.text?.trim())?'已收录部分文字':'需要文字或图片识别'):m.extraction==='needs_link'?'需要读取链接':'已保留文字'}</small>${localStatus(m)}<details><summary>查看原文与来源</summary><p>${esc(m.text||'尚无提取文字，请在任务中关联截图或补充原文。')}</p>${m.url?`<p>来源：${esc(m.url)}</p>`:''}${m.path?`<a href="/api/materials/${m.id}/file">下载原始文件</a>`:''}</details>${m.missing_attachment?`<div class="hint needs-attention"><strong class="attention-label">! 待你处理</strong> 原附件缺失：${esc(m.original_filename||m.name)}<div><button data-complete-material="${m.id}">补传原文件</button></div></div>`:''}<details><summary>处理详情与人工修正</summary><div class="actions"><button data-read-material="${m.id}">重新逐页读取</button><button data-review-material="${m.id}">按范围查看 / 分析历史${m.analysis_history?.length?' · '+m.analysis_history.length:''}</button><button data-supplement="${m.id}">补充文字</button></div></details>${(m.supplements||[]).length?`<details><summary>补充记录（${m.supplements.length}）</summary>${m.supplements.map(x=>`<p class="reading-text">${esc(x.text)}</p>`).join('')}</details>`:''}<button class="quiet" data-archive="${m.id}">归档此资料</button></article>`).join('')||'<div class="empty"><p>先添加此范围的资料。<br>不会假定已读取你的历史对话。</p></div>'}<details><summary>归档材料（${materials.filter(x=>x.archived).length}）</summary>${materials.filter(x=>x.archived).map(x=>`<p>${esc(x.name)}</p>`).join('')}</details></div><div><div class="panel"><div class="panel-heading"><h2>生效规则</h2><button id="add-rule">更新规则</button></div>${rules.map(r=>`<div class="material"><small>${r.id==='builtin-v1'?'内置基础规则':r.project_id?'本品牌规则':'全局规则'}</small><p>${esc(r.text)}</p></div>`).join('')}</div><div class="hint">新资料与旧版本分别保留。一次客户要求不会自动变成长期偏好，你可以在意见记录中明确采纳。</div></div></div>`;
main.querySelectorAll('[data-material]').forEach(card=>{const host=document.createElement('div');card.querySelector('details').append(host);readingControl(c,host,()=>({project_id:projectId,material_id:card.dataset.material}));});
startAutoPolling(c,projectId,globalScope,materials);
main.querySelectorAll('[data-complete-material]').forEach(b=>b.onclick=()=>dialog('补传原文件',`<p class="note">补传到此资料，保留迁入摘录和旧分析。</p><label>选择对应原文件<input type="file" name="file" required accept=".txt,.md,.pdf,.docx,.pptx,.xlsx,.csv,.tsv,.png,.jpg,.jpeg,.webp"></label><div class="form-footer"><button class="primary">补传并保留原稿</button></div>`,async(f,form,d)=>{await api('/materials/'+b.dataset.completeMaterial+'/complete-file',{method:'POST',body:f});d.close();await c.render();}));
main.querySelectorAll('[data-read-material]').forEach(b=>b.onclick=()=>batchReadMaterials(c,[materials.find(m=>m.id===b.dataset.readMaterial)],projectId,scopeTitle));
main.querySelectorAll('[data-review-material]').forEach(b=>b.onclick=()=>materialReading(c,b.dataset.reviewMaterial));
main.querySelectorAll('[data-supplement]').forEach(b=>b.onclick=()=>supplementMaterial(c,materials.find(m=>m.id===b.dataset.supplement)));
if(state.materialFocus){const card=[...main.querySelectorAll('[data-material]')].find(x=>x.dataset.material===state.materialFocus);if(card){card.classList.add('material-focused');card.tabIndex=-1;card.scrollIntoView({block:'center'});card.focus({preventScroll:true});}else toast('此资料已归档或不在当前范围，请检查归档记录');state.materialFocus='';}
main.querySelector('#find-posts').onclick=()=>commentForm(c,null,{source_mode:'search'});
main.querySelector('#add-material').onclick=()=>dialog(globalScope?'添加全局资料':'添加品牌资料',`<p class="note">保存范围：${esc(scopeTitle)}</p><label>资料名称<input name="name" required></label><label>资料类型<select name="kind"><option value="fact">产品事实</option><option value="strategy">策略目标与人群</option><option value="sample">认可样例</option><option value="thread">需要评论的原帖</option></select></label><label>原文<textarea name="text" rows="7" placeholder="粘贴原文，或在下方填写公开 HTTPS 链接"></textarea></label><label>来源链接<input name="url" type="url"></label><label>发布日期<input name="published_at" type="date"></label><label>事实状态<select name="trust"><option value="unverified">待核实</option><option value="user_confirmed">已由我核实</option></select></label><div class="form-footer"><button class="primary">保存资料</button></div>`,async(f,form,d)=>{if(!String(f.get('text')||'').trim()&&!f.get('url'))throw Error('请提供原文或链接');await api('/materials',{method:'POST',body:{project_id:projectId,...Object.fromEntries(f)}});d.close();await c.render();});
main.querySelector('#upload').onclick=()=>uploadMaterials(c,projectId,scopeTitle);
bindMaterialDrop(main.querySelector('#material-drop'),files=>uploadMaterials(c,projectId,scopeTitle,files),()=>uploadMaterials(c,projectId,scopeTitle));
const activeMaterials=materials.filter(m=>!m.archived),selected=new Set();
const selectedMaterials=()=>activeMaterials.filter(m=>selected.has(m.id));
const updateSelection=()=>{const count=selected.size,all=main.querySelector('#material-select-all');all.checked=count>0&&count===activeMaterials.length;all.indeterminate=count>0&&count<activeMaterials.length;all.disabled=!activeMaterials.length;main.querySelector('#material-selection-count').textContent='已选 '+count+' 份';main.querySelector('#batch-read-materials').textContent=count?'AI 精读所选资料':'批量 AI 精读（可选）';main.querySelector('#batch-read-materials').disabled=!activeMaterials.length;main.querySelector('#batch-archive-materials').disabled=!count;};
main.querySelectorAll('[data-select-material]').forEach(box=>box.onchange=()=>{if(box.checked)selected.add(box.dataset.selectMaterial);else selected.delete(box.dataset.selectMaterial);updateSelection();});
main.querySelector('#material-select-all').onchange=ev=>{selected.clear();main.querySelectorAll('[data-select-material]').forEach(box=>{box.checked=ev.target.checked;if(box.checked)selected.add(box.dataset.selectMaterial);});updateSelection();};
main.querySelector('#batch-read-materials').onclick=()=>batchReadMaterials(c,selected.size?selectedMaterials():activeMaterials,projectId,scopeTitle);
main.querySelector('#batch-archive-materials').onclick=()=>batchArchiveMaterials(c,selectedMaterials(),projectId,scopeTitle);updateSelection();
main.querySelectorAll('[data-archive]').forEach(b=>b.onclick=()=>dialog('归档资料',`<p>旧稿依据仍会保留，当前任务会提示重新核对。</p><div class="form-footer"><button class="primary">归档</button></div>`,async(f,form,d)=>{await api('/materials/'+b.dataset.archive+'/archive',{method:'POST'});d.close();await c.render();}));
main.querySelector('#add-rule').onclick=()=>dialog(globalScope?'更新全局规则':'更新品牌规则',`<p class="muted">保存范围：${esc(scopeTitle)}。新版本会替换此范围的自定义规则，历史版本及内置规则保留。</p><label>完整规则<textarea name="text" rows="8" required>${esc(rules.findLast(r=>r.id!=='builtin-v1'&&r.project_id===projectId)?.text||'')}</textarea></label><div class="form-footer"><button class="primary">保存规则版本</button></div>`,async(f,form,d)=>{await api('/rules',{method:'POST',body:{project_id:projectId,text:f.get('text')}});d.close();await c.render();toast('规则已更新');});}
let materialStatusTimer;
function autoStatus(m){
 const state=m.auto_processing;
 if(!state)return '原件和本地页索引已保存；此旧资料未自动启动模型重读。';
 const progress=state.total_units?` ${state.covered||0} / ${state.total_units} 页/段`:'';
 if(state.status==='complete')return `模型已逐页分析并采纳${progress}；品牌说法仍保留为待核实来源。${m.web_verification?.status==='sources_found'?'已找到公开网页摘录，可在处理详情查看。':m.web_verification?.status==='no_evidence'?'公开搜索未找到可用证据。':''}`;
 if(state.status==='needs_attention')return `! 待你处理：模型已分析${progress}，部分页面未通过读取核对。${state.message||''}`;
 if(state.status==='paused')return `! 模型读取暂停：${state.message||'连接或额度不可用'}。原件和本地文字仍保留。`;
 if(state.status==='queued')return '原件已保存，模型分析正在排队。';
 return `模型正在逐页读取${progress}；可离开本页继续使用工作台。`;
}
function startAutoPolling(c,projectId,globalScope,materials){
 clearInterval(materialStatusTimer);
 if(!materials.some(m=>['queued','running','working'].includes(m.auto_processing?.status)))return;
 materialStatusTimer=setInterval(async()=>{
   if(c.state.page!==(globalScope?'global-materials':'materials')||(!globalScope&&c.state.project!==projectId)){
     clearInterval(materialStatusTimer);return;
   }
   try{
     const current=await c.api('/materials'+(globalScope?'':'?project_id='+projectId));
     for(const m of current){const label=c.main.querySelector(`[data-auto-material="${m.id}"]`);if(label){label.textContent=autoStatus(m);if(m.web_verification?.status==='sources_found'&&!label.parentElement.querySelector('[data-web-evidence]'))label.insertAdjacentHTML('afterend',webEvidence(m));}}
     if(!current.some(m=>['queued','running','working'].includes(m.auto_processing?.status)))clearInterval(materialStatusTimer);
   }catch{clearInterval(materialStatusTimer);}
 },3000);
}
function webEvidence(m){
 const check=m.web_verification;
 if(check?.status!=='sources_found'||!check.sources?.length)return '';
 const safe=value=>String(value||'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
 return `<details data-web-evidence><summary>公开来源摘录（并非事实认证）</summary><p>${safe(check.summary_zh)}</p>${check.sources.map(source=>`<p><a href="${safe(source.url)}" target="_blank" rel="noopener noreferrer">${safe(source.title||source.url)}</a> · ${safe(source.snippet)}</p>`).join('')}</details>`;
}
function localStatus(m){
 const units=m.units||[];if(!units.length)return `<p class="note" data-auto-material="${m.id}">${autoStatus(m).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}</p>${webEvidence(m)}`;
 const text=units.filter(u=>u.text?.trim()).length;
 const pictures=units.filter(u=>u.visual).length;
 const incomplete=(m.extraction_warnings||[]).some(w=>w.startsWith('未读取：'));
 return `<p class="note">本机已收录 ${text} / ${units.length} 页/段文字${pictures?' · '+pictures+' 页/段含视觉内容':''}。${text?(m.project_id===null?'在任务中选择此全局附件后使用相关页。':'本品牌写作可自动检索相关页。'):''}${incomplete||text<units.length?'部分视觉或空白内容需进一步核对。':''}</p><p class="note" data-auto-material="${m.id}">${autoStatus(m).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}</p>${webEvidence(m)}`;
}
