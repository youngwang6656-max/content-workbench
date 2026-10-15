export const rawTransferPanel=`<form id="raw-transfer-form" class="panel"><div class="panel-heading"><h2>从原始对话迁入</h2><span class="badge">本机读取 · 无需模型</span></div><p class="muted">完整度优先：使用 ChatGPT 原始数据导出，选择同一品牌的对话。各个分支和长消息均保留，不经过交接摘要。</p><label for="raw-transfer-file">原始 ZIP 或对话 JSON（可多选分卷，合计最多 100 MB）</label><input id="raw-transfer-file" type="file" accept=".zip,.json" multiple required><p class="note">若 ZIP 超过限制，可解压后选择 conversations.json 或全部编号 JSON 分卷。不会自动读取云端对话或下载附件。</p><div class="actions"><button class="primary" id="inspect-raw">读取对话清单</button></div><p class="form-error" id="raw-transfer-error" role="alert"></p></form><section id="raw-conversation-selection" class="panel" hidden></section>`;

export function installRawTransfer(c,showPreview){
 const {main,api,esc}=c,panel=main.querySelector('#raw-conversation-selection');
 main.querySelector('#raw-transfer-file').onchange=()=>{panel.hidden=true;panel.innerHTML='';};
 main.querySelector('#raw-transfer-form').onsubmit=async ev=>{
  ev.preventDefault();const btn=main.querySelector('#inspect-raw'),error=main.querySelector('#raw-transfer-error');error.textContent='';btn.disabled=true;btn.textContent='正在读取…';panel.hidden=true;panel.innerHTML='';
  try{
   const files=[...main.querySelector('#raw-transfer-file').files];if(!files.length)throw Error('请选择原始导出文件');if(files.length>100||files.reduce((sum,f)=>sum+f.size,0)>100000000)throw Error('合计最多一百 MB、一百个文件，请分批提供 JSON');
   const form=new FormData();files.forEach(file=>form.append('file',file));const info=await api('/transfer/raw/inspect',{method:'POST',body:form}),selected=new Set();
   panel.hidden=false;panel.innerHTML=`<h2>选择同一品牌的对话</h2><p class="note">${esc(info.notice)} 共读取 ${info.conversations.length} 个对话。检查结果保留 30 分钟，切换页面后可重新读取。</p><label for="raw-conversation-filter">按标题查找</label><input id="raw-conversation-filter" placeholder="例如 topdon、70mai"><div class="actions"><button type="button" id="raw-select-visible">勾选当前列表</button><button type="button" id="raw-clear">清空选择</button></div><div id="raw-conversation-rows" class="raw-conversation-rows"></div><p id="raw-selection-count" class="note"></p><label for="raw-project-name">新品牌项目名称</label><input id="raw-project-name" maxlength="200" placeholder="所选对话所属品牌"><div class="actions"><button type="button" class="primary" id="preview-raw" disabled>预览所选原文</button></div><p class="form-error" id="raw-selection-error" role="alert"></p>`;
   let visible=info.conversations;
   function updateCount(){panel.querySelector('#raw-selection-count').textContent=`已选择 ${selected.size} / ${info.conversations.length} 个对话`;panel.querySelector('#preview-raw').disabled=!selected.size;}
   function renderRows(){
    const q=panel.querySelector('#raw-conversation-filter').value.trim().toLocaleLowerCase();visible=info.conversations.filter(row=>row.title.toLocaleLowerCase().includes(q));
    panel.querySelector('#raw-conversation-rows').innerHTML=visible.map(row=>`<label class="raw-conversation-row"><input type="checkbox" data-conversation-key="${esc(row.key)}" ${selected.has(row.key)?'checked':''}><span><strong>${esc(row.title)}</strong><small>${row.message_count} 条消息 · ${row.branch_count} 个分支 · ${row.nontext_count} 条含非文字${row.updated_at?' · '+esc(new Date(row.updated_at).toLocaleDateString()):''}</small></span></label>`).join('')||'<p class="muted">没有匹配的对话。</p>';
    panel.querySelectorAll('[data-conversation-key]').forEach(input=>input.onchange=()=>{input.checked?selected.add(input.dataset.conversationKey):selected.delete(input.dataset.conversationKey);updateCount();});updateCount();
   }
   panel.querySelector('#raw-conversation-filter').oninput=renderRows;
   panel.querySelector('#raw-select-visible').onclick=()=>{visible.forEach(row=>selected.add(row.key));renderRows();};
   panel.querySelector('#raw-clear').onclick=()=>{selected.clear();renderRows();};
   panel.querySelector('#preview-raw').onclick=async()=>{const button=panel.querySelector('#preview-raw'),err=panel.querySelector('#raw-selection-error');err.textContent='';button.disabled=true;try{showPreview(await api('/transfer/raw/preview',{method:'POST',body:{token:info.token,conversation_ids:[...selected],name:panel.querySelector('#raw-project-name').value}}));}catch(e){err.textContent=e.message;}finally{updateCount();}};
   renderRows();
  }catch(e){error.textContent=e.message;}finally{btn.disabled=false;btn.textContent='读取对话清单';}
 };
}
