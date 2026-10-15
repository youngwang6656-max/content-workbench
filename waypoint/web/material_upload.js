// Each file uses the existing bounded upload endpoint; failures are independent.
export function uploadMaterials(c,projectId,scopeTitle,initialFiles=[]){
 const {api,esc,dialog,toast}=c;let entries=[],running=false;
 const d=dialog(projectId===null?'导入全局文件':'导入品牌文件',`<p class="note">保存范围：${esc(scopeTitle)}</p><p class="muted">把文件放进来即可。工作台保存原件，并用当前已授权的模型配置在后台逐页读取、分析和整理依据；连接失败会暂停，已上传内容保留。若当前配置是已启用的 API，处理会遵守现有价格与预算设置并可能产生费用。单个文件上限二十 MB。</p><div id="upload-drop" class="material-drop" role="button" tabindex="0" aria-label="拖拽文件到此处或点击选择">拖拽文件到此处，或点击选择（支持多文件）</div><label>选择文件（可多选）<input type="file" name="file" multiple required accept=".txt,.md,.pdf,.docx,.pptx,.xlsx,.csv,.tsv,.png,.jpg,.jpeg,.webp,.doc,.ppt,.xls"></label><p id="upload-summary" role="status" aria-live="polite"></p><div id="upload-results"></div><div class="form-footer"><button class="primary" id="upload-submit">放入工作台</button><button type="button" id="upload-done" hidden>查看已导入资料</button></div>`,async(f,form,modal)=>{
   if(running)return;
   if(!entries.length)entries=f.getAll('file').filter(x=>x instanceof File&&x.name).map(file=>({file,status:'pending',message:''}));
   if(!entries.length)throw Error('请选择文件');
   const input=form.elements.file,submit=form.querySelector('#upload-submit'),done=form.querySelector('#upload-done');
   running=true;input.disabled=true;done.disabled=true;
   try{
     for(const entry of entries){
       if(entry.status==='success')continue;
       entry.status='uploading';entry.message='';paint(form);
       try{
         if(entry.file.size>20_000_000)throw Error('单个文件上限为二十 MB，请拆分后导入');
         const body=new FormData();body.append('file',entry.file);if(projectId!==null)body.append('project_id',projectId);
         await api('/materials/upload',{method:'POST',body});entry.status='success';
       }catch(e){entry.status='failed';entry.message=e.message||'导入未完成，请核对资料列表后重试';}
       paint(form);
     }
     const success=entries.filter(x=>x.status==='success').length,failed=entries.length-success;
     submit.hidden=!failed;submit.textContent='重试未成功的文件';done.hidden=false;
     if(!failed&&modal.open){modal.close();await c.render();toast(`${success} 份资料已保存，后台将自动读取分析`);return;}
     if(!modal.open||!modal.contains(form))toast(`资料导入完成：${success} 个成功，${failed} 个未导入`,failed>0);
   }finally{running=false;input.disabled=false;done.disabled=false;}
 },true);
 const form=d.querySelector('form');
 function paint(host){
   const success=entries.filter(x=>x.status==='success').length,failed=entries.filter(x=>x.status==='failed').length,working=entries.find(x=>x.status==='uploading');
   host.querySelector('#upload-summary').textContent=working?`正在导入 ${entries.indexOf(working)+1} / ${entries.length}：${working.file.name}`:`${success} 个成功，${failed} 个未导入${entries.some(x=>x.status==='pending')?' · 等待开始':''}`;
   host.querySelector('#upload-results').innerHTML=entries.map(x=>`<div class="upload-result"><span>${esc(x.file.name)}</span><strong class="${x.status==='failed'?'attention-label':''}">${{pending:'待导入',uploading:'导入中',success:'已导入',failed:'未导入'}[x.status]}</strong>${x.message?`<p>${esc(x.message)}</p>`:''}</div>`).join('');
 }
 function setFiles(files,append=false){
   if(running){toast('正在上传，请完成后再添加文件');return;}
   const added=[...files].filter(file=>file instanceof File&&file.name).map(file=>({file,status:'pending',message:''}));
   if(!added.length){toast('请拖入文件；文件夹请先打开后选择其中的文件',true);return;}
   entries=append?[...entries,...added]:added;form.elements.file.required=false;paint(form);const submit=form.querySelector('#upload-submit');submit.hidden=false;submit.textContent='放入工作台';form.querySelector('#upload-done').hidden=true;
 }
 form.elements.file.onchange=()=>setFiles(form.elements.file.files);
 bindMaterialDrop(form.querySelector('#upload-drop'),files=>setFiles(files,true),()=>form.elements.file.click());
 form.querySelector('#upload-done').onclick=async()=>{d.close();await c.render();};
 if(initialFiles.length)setFiles(initialFiles);
 return d;
}

export function bindMaterialDrop(zone,onFiles,onPick){
 let depth=0;
 zone.onclick=onPick;zone.onkeydown=ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();onPick();}};
 zone.ondragenter=ev=>{if(![...ev.dataTransfer.types].includes('Files'))return;ev.preventDefault();depth++;zone.classList.add('drag-over');};
 zone.ondragover=ev=>{if(![...ev.dataTransfer.types].includes('Files'))return;ev.preventDefault();ev.dataTransfer.dropEffect='copy';};
 zone.ondragleave=ev=>{ev.preventDefault();if(--depth<=0){depth=0;zone.classList.remove('drag-over');}};
 zone.ondrop=ev=>{ev.preventDefault();depth=0;zone.classList.remove('drag-over');onFiles([...ev.dataTransfer.files]);};
}
