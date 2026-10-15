export function usageSidebar(c,status){
 const el=document.querySelector('#usage-status');if(!el)return;
 const active=status.active_call;
 const provider=active?.provider||status.effective_provider;
 const configName=active?.config_name||status.config_name||(provider==='api'?'API 配置':'Plus 订阅');
 const connection=provider==='codex'?(status.subscription_auth_state==='chatgpt'?'已登录':status.subscription_auth_state==='unverified'?'待验证':'未登录'):status.ready?'已配置':'待处理';
 el.innerHTML=`<span class="usage-config-name">${c.esc(configName)}</span><span class="usage-note">${status.switch_policy==='auto'?'自动':'手动'} · ${connection}</span>`;
 el.title=[active?'本次正在生成':'',active?.provider_name||status.provider_name,active?.model||status.model_name,status.message,status.notice,status.checked_at?'订阅检查时间：'+new Date(status.checked_at).toLocaleString():''].filter(Boolean).join('\n');
 el.dataset.ready=String(status.ready);el.hidden=false;
 const signature=`${status.switch_policy}:${status.config_id}:${status.switched}`;
 if(c.state.usageSignature!==signature&&status.switched)c.toast(status.message);
 c.state.usageSignature=signature;
}

const roles=[['write','写作与返修'],['translate','中文回译'],['read','资料读取与分析'],['extract','社群证据归纳'],['complex','CB 与社群推荐']];
const roleDefaults={write:'high',translate:'low',read:'high',extract:'medium',complex:'high'};
const effortLabels={none:'关闭推理',minimal:'最低',low:'低',medium:'中',high:'高',xhigh:'更高'};
function initialConfigs(s,profiles){
 if(s.usage_configs?.length)return structuredClone(s.usage_configs);
 const configs=[{id:'subscription-initial',name:'配置 1 · Plus 订阅',provider:'codex',model_roles:{...s.model_roles},role_efforts:{...s.role_efforts}}];
 for(const p of profiles)configs.push({id:'api-'+p.id,name:`配置 ${configs.length+1} · ${p.name}`,provider:'api',profile_id:p.id,model:p.id===s.api_default_profile_id?(s.api_default_model||p.default_model):p.default_model,api_role_models:{}});
 return configs;
}
export function usageHTML(c,s,profiles,status){
 const {esc}=c,configs=initialConfigs(s,profiles),mode=s.usage_mode||s.provider;
 const selected=s.active_usage_config_id||configs.find(x=>x.provider===mode&&(mode!=='api'||x.profile_id===s.api_default_profile_id))?.id||configs[0].id;
 const defaults=s.auto_default_config_id||configs.find(x=>x.provider==='codex')?.id||'',fallback=s.fallback_usage_config_id||configs.find(x=>x.provider==='api')?.id||'';
 const opts=(items,id)=>items.map(x=>`<option value="${esc(x.id)}" ${id===x.id?'selected':''}>${esc(x.name)}</option>`).join('');
 return `<div class="panel" id="usage-settings"><div class="panel-heading"><h2>模型配置与切换</h2><button id="add-usage-config">＋ 新建模型配置</button></div>
 <p class="muted">每份配置保存接入及各环节模型，命名后直接切换。Plus / ChatGPT 订阅使用官方登录和订阅额度；OpenAI、DeepSeek 等 API 使用独立密钥并按量计费，两者额度分开。</p>
 <div class="hint" id="usage-preview">${esc(status.config_name||'当前接入')} · ${esc(status.provider_name||'待确认')} · ${esc(status.model_name||'模型待选择')}<br>${esc(status.message)}</div>
 <div class="usage-config-list">${configs.map(x=>`<div class="usage-config-row"><div><strong>${esc(x.name)}</strong><p class="note">${x.provider==='codex'?'ChatGPT 订阅':`API · ${esc(profiles.find(p=>p.id===x.profile_id)?.name||'服务商待确认')}`} · ${esc(x.provider==='codex'?x.model_roles?.write||'写作模型待选':x.model||'默认模型待选')}${x.provider==='codex'?' · 写作'+effortLabels[x.role_efforts?.write||'high']:''}</p></div><div class="actions"><button data-edit-usage="${esc(x.id)}">编辑</button><button data-copy-usage="${esc(x.id)}">复制</button><button data-remove-usage="${esc(x.id)}">删除</button></div></div>`).join('')}</div>
 <form id="usage-form"><div class="grid2"><label>切换设置<select name="switch_policy"><option value="manual" ${s.switch_policy!=='auto'?'selected':''}>手动切换</option><option value="auto" ${s.switch_policy==='auto'?'selected':''}>自动切换（读取订阅额度）</option></select></label><label>手动当前配置<select name="active_usage_config_id">${opts(configs,selected)}</select></label></div>
 <div id="automatic-usage"><div class="grid2"><label>自动模式默认配置<select name="auto_default_config_id">${opts(configs.filter(x=>x.provider==='codex'),defaults)}</select></label><label>达到阈值后切换到<select name="fallback_usage_config_id"><option value="">请选择 API 备用配置</option>${opts(configs.filter(x=>x.provider==='api'),fallback)}</select></label></div>
 <label>5 小时额度剩余 ≤ 此百分比时提醒并切换<input name="remaining_threshold" type="number" min="0" max="99" step="1" value="${100-(s.auto_used_threshold??100)}" required></label><p class="note">例如填写 10：剩余降至 10% 时选择备用；0 表示用尽才切换。额度恢复到阈值以上后回到默认配置。其他额度窗口若用尽，同样选择备用。</p></div>
 <p class="note">API 当前${s.api_enabled?'已启用':'未启用，须在下方明确授权'}。自动切换只在额度已核实且 API 授权、价格和预算均有效时执行。未知额度、登录失效或费用未知会暂停；已发出的请求不自动重试。</p><p class="note">API 文本不代表截图识别或联网搜索可用；这些能力当前仍需订阅。每次生成前重新读取额度，侧栏显示配置与模型；不使用 credits。</p>
 <div class="form-footer"><button class="primary">保存切换设置</button><button type="button" id="refresh-usage">刷新使用状态</button></div></form></div>`;
}
export function bindUsage(c,s,profiles,connection){
 const {api,esc,dialog,toast}=c,form=c.main.querySelector('#usage-form'),configs=initialConfigs(s,profiles);
 const sync=()=>{const auto=form.elements.switch_policy.value==='auto';form.elements.active_usage_config_id.disabled=auto;c.main.querySelector('#automatic-usage').hidden=!auto;};form.elements.switch_policy.onchange=sync;sync();
 const patch=()=>({usage_configs:configs,switch_policy:form.elements.switch_policy.value,active_usage_config_id:form.elements.active_usage_config_id.value,auto_default_config_id:form.elements.auto_default_config_id.value,fallback_usage_config_id:form.elements.fallback_usage_config_id.value,auto_used_threshold:100-Number(form.elements.remaining_threshold.value)});
 async function save(data){await api('/settings',{method:'POST',body:data});await c.refreshUsage();await c.render();}
 form.onsubmit=async ev=>{ev.preventDefault();const b=ev.submitter;b.disabled=true;try{await save(patch());toast('切换设置已保存，API 授权未改变');}finally{b.disabled=false;}};
 c.main.querySelector('#refresh-usage').onclick=async ev=>{ev.target.disabled=true;try{await api('/usage-status/check',{method:'POST'});await c.refreshUsage();await c.render();}finally{ev.target.disabled=false;}};
 function edit(config=null,copy=false){
  const x=structuredClone(config||{id:crypto.randomUUID(),name:`配置 ${configs.length+1}`,provider:'codex',model_roles:{...s.model_roles},role_efforts:{...s.role_efforts}});if(copy){x.id=crypto.randomUUID();x.name+=' 副本';}const fresh=!config||copy;
  let catalog=connection;
  const plusOpts=(selected)=>'<option value="">请选择 / 沿用写作模型</option>'+(!catalog.models?.some(m=>(m.model||m.id)===selected)&&selected?`<option selected disabled value="${esc(selected)}">${esc(selected)}（当前目录不可用，请改选）</option>`:'')+(catalog.models||[]).filter(m=>!m.hidden).map(m=>{const id=m.model||m.id;return `<option value="${esc(id)}" ${selected===id?'selected':''}>${esc(m.displayName||id)}</option>`;}).join('');
  const d=dialog(fresh?'新建模型配置':'编辑模型配置',`<p class="note">Plus 订阅模型从本机官方登录的实时目录同步；默认写作、资料分析与 CB 为高，中文回译为低、社群归纳为中。各环节可覆盖强度；不支持明确选择时会提示。统计、排序与手册不调用模型，同文译文和近期社群证据可复用。第三方 API 沿用各服务商自身设置。保存配置不会调用模型或启用 API。资料读取未单独选择时沿用写作模型；付费 API 图片仍暂停。</p><label>配置名称<input name="name" maxlength="80" required value="${esc(x.name)}"></label><label>使用模式<select name="provider"><option value="codex" ${x.provider==='codex'?'selected':''}>Plus / ChatGPT 订阅额度</option><option value="api" ${x.provider==='api'?'selected':''}>API · OpenAI / 第三方</option></select></label><div id="config-subscription"><div class="actions"><button type="button" id="refresh-plus-models">同步 Plus 模型</button><span class="note" id="plus-model-status" role="status">上次目录：${esc(connection.checked_at?new Date(connection.checked_at).toLocaleString():'尚未验证')} · 正在同步</span></div>${roles.map(([role,label])=>`<div class="grid2"><label>${label}<select name="plus_${role}">${plusOpts(x.model_roles?.[role]||'')}</select></label><label>${label}强度<select name="effort_${role}"><option value="">自动 · 默认${effortLabels[roleDefaults[role]]}</option>${Object.entries(effortLabels).map(([key,value])=>`<option value="${key}" ${x.role_efforts?.[role]===key?'selected':''}>${value}</option>`).join('')}</select></label></div>`).join('')}</div>
  <div id="config-api"><label>API 服务商<select name="profile_id"><option value="">请选择服务商</option>${profiles.map(p=>`<option value="${esc(p.id)}" ${x.profile_id===p.id?'selected':''}>${esc(p.name)}</option>`).join('')}</select></label><label>默认 API 模型<select name="model"></select></label><details><summary>各环节 API 模型（可沿用默认）</summary>${roles.map(([role,label])=>`<label>${label}<select name="api_${role}"></select></label>`).join('')}</details><p class="note">价格请在对应服务商的“模型与价格”核对。保存配置不会启用 API 或生成内容。</p></div><div class="form-footer"><button class="primary">保存模型配置</button></div>`,async(f,modal,d)=>{
   const provider=f.get('provider'),model_roles={},api_role_models={},role_efforts={};if(provider==='codex'&&!synced)throw Error('请先同步当前账户模型，再保存订阅配置');for(const [role] of roles){const selected=modal.elements['plus_'+role].value;if(provider==='codex'&&selected&&!catalog.models?.some(m=>(m.model||m.id)===selected&&!m.hidden))throw Error('已选订阅模型不在当前目录，请改选或重新同步');if(selected)model_roles[role]=selected;const effort=f.get('effort_'+role);if(effort)role_efforts[role]=effort;const model=f.get('api_'+role);if(model)api_role_models[role]={provider:'api',profile_id:f.get('profile_id'),model};}
   if(provider==='codex'&&!model_roles.write)throw Error('请从当前账户目录选择写作模型');
   if(provider==='codex')for(const [role,effort] of Object.entries(role_efforts)){
    const model=catalog.models.find(m=>(m.model||m.id)===(model_roles[role]||model_roles.write));
    const supported=(model?.supportedReasoningEfforts||[]).map(x=>typeof x==='string'?x:x.reasoningEffort);
    if(supported.length&&!supported.includes(effort))throw Error(`${roles.find(x=>x[0]===role)[1]}所选模型不支持“${effortLabels[effort]}”强度，请调整后保存`);
   }
   const updated={id:x.id,name:f.get('name').trim(),provider,model_roles,role_efforts,...(provider==='api'?{profile_id:f.get('profile_id'),model:f.get('model'),api_role_models}:{})};const data=patch();data.usage_configs=fresh?[...configs,updated]:configs.map(v=>v.id===x.id?updated:v);
   await api('/settings',{method:'POST',body:data});d.close();toast('模型配置已保存，API 授权未改变');await c.refreshUsage();await c.render();
  });
  const f=d.querySelector('form');let syncing=false,synced=false;
  const syncPlus=async()=>{if(syncing)return;syncing=true;const button=d.querySelector('#refresh-plus-models'),status=d.querySelector('#plus-model-status');button.disabled=true;status.textContent='正在读取官方账户模型…';
   try{const report=await api('/connection/check',{method:'POST'});if(!d.open||!d.contains(f))return;if(report.auth_state!=='chatgpt'||!report.models?.length)throw Error(report.message||'官方订阅未返回可用模型');catalog=report;synced=true;
    for(const [role] of roles){const select=f.elements['plus_'+role],selected=select.value;select.innerHTML=plusOpts(selected);}
    status.textContent=`已同步 ${report.models.length} 个账户模型 · 按环节使用高/中/低强度`;
   }catch(e){synced=false;if(d.open&&d.contains(f))status.textContent='同步未完成：'+e.message+'。当前选项为上次缓存，请检查官方连接。';}
   finally{syncing=false;if(d.open&&d.contains(f))button.disabled=false;}};
  const syncProvider=()=>{d.querySelector('#config-api').hidden=f.elements.provider.value!=='api';d.querySelector('#config-subscription').hidden=f.elements.provider.value!=='codex';if(f.elements.provider.value==='codex')syncPlus();};
  const syncModels=()=>{const p=profiles.find(p=>p.id===f.elements.profile_id.value),same=p?.id===x.profile_id;
   f.elements.model.innerHTML='<option value="">请选择账户模型</option>'+(p?.models||[]).map(m=>`<option value="${esc(m.id)}" ${(same?x.model:p?.default_model)===m.id?'selected':''}>${esc(m.name||m.id)}</option>`).join('');
   for(const [role] of roles)f.elements['api_'+role].innerHTML='<option value="">沿用本配置默认模型</option>'+(p?.models||[]).map(m=>`<option value="${esc(m.id)}" ${same&&x.api_role_models?.[role]?.model===m.id?'selected':''}>${esc(m.name||m.id)}</option>`).join('');};
  f.elements.provider.onchange=syncProvider;f.elements.profile_id.onchange=syncModels;d.querySelector('#refresh-plus-models').onclick=syncPlus;syncProvider();syncModels();
 }
 c.main.querySelector('#add-usage-config').onclick=()=>edit();
 c.main.querySelectorAll('[data-edit-usage]').forEach(el=>el.onclick=()=>edit(configs.find(x=>x.id===el.dataset.editUsage)));
 c.main.querySelectorAll('[data-copy-usage]').forEach(el=>el.onclick=()=>edit(configs.find(x=>x.id===el.dataset.copyUsage),true));
 c.main.querySelectorAll('[data-remove-usage]').forEach(el=>el.onclick=async()=>{const id=el.dataset.removeUsage,data=patch();if([data.active_usage_config_id,data.auto_default_config_id,data.fallback_usage_config_id].includes(id))return toast('请先将当前、默认和备用选择改为其他配置并保存，再删除');data.usage_configs=configs.filter(x=>x.id!==id);await save(data);toast('模型配置已删除，项目与稿件保留');});
}
