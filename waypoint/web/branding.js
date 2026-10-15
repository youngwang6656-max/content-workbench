const fallback='/static/workbench-mark.svg';
export async function refreshBranding(c){
 c.state.branding=await c.api('/branding');applyBranding(c.state.branding);
}
export function applyBranding(config){
 const url=config?.logo_url||fallback;
 document.querySelectorAll('[data-workbench-logo]').forEach(image=>{image.src=url;image.onerror=()=>{image.onerror=null;image.src=fallback;};});
 document.querySelector('.brand')?.classList.toggle('has-custom-logo',!!config?.custom_logo);
 const icon=document.querySelector('link[rel="icon"]');if(icon){icon.href=url;icon.type=config?.custom_logo?'image/png':'image/svg+xml';}
}
export function brandingHTML(c){return `<div class="panel" id="branding-settings"><div class="panel-heading"><h2>工作台标识</h2><span class="badge">本机管理员</span></div><div class="branding-setting-row"><img data-workbench-logo class="branding-preview" src="${c.esc(c.state.branding?.logo_url||fallback)}" alt="当前工作台标识"><div><p class="muted">上传自己的图片，显示在侧栏顶部和登录页。</p><p class="note">PNG、JPEG、WebP，最多 5 MB；保留图片原色与透明背景。</p><button type="button" id="edit-branding">${c.state.branding?.custom_logo?'更换标识':'上传标识'}</button></div></div></div>`;}
export function bindBranding(c){const b=c.main.querySelector('#edit-branding');if(b)b.onclick=()=>openBranding(c);}
export function openBranding(c){
 if(c.state.auth?.enabled&&!c.state.auth.user)return;
 const d=c.dialog('自定义工作台标识',`<p class="muted">此标识只保存在当前安装，原有工作台不受影响。</p><div class="branding-dialog-preview"><img data-workbench-logo src="${c.esc(c.state.branding?.logo_url||fallback)}" alt="当前工作台标识"></div><label for="branding-file">选择图片</label><input id="branding-file" name="file" type="file" accept="image/png,image/jpeg,image/webp" required><p class="note">静态 PNG、JPEG 或 WebP，最多 5 MB。图片自动等比缩小，不改色，不裁掉内容。</p><div class="form-footer">${c.state.branding?.custom_logo?'<button type="button" id="remove-branding" class="quiet">移除自定义标识</button>':'<span></span>'}<button class="primary">保存图片</button></div>`,async(form,el,dialog)=>{
  const file=form.get('file');if(!file?.size)throw Error('请选择图片');if(file.size>5000000)throw Error('标识图片上限为 5 MB');
  c.state.branding=await c.api('/branding/logo',{method:'POST',body:form});applyBranding(c.state.branding);dialog.close();updatePanel(c);c.toast('工作台标识已保存');
 });
 const remove=d.querySelector('#remove-branding');if(remove)remove.onclick=async()=>{remove.disabled=true;try{c.state.branding=await c.api('/branding/logo',{method:'DELETE'});applyBranding(c.state.branding);d.close();updatePanel(c);c.toast('已恢复默认标识');}catch(e){c.toast(e.message,true);}finally{remove.disabled=false;}};
}
function updatePanel(c){const panel=c.main.querySelector('#branding-settings');if(panel){panel.outerHTML=brandingHTML(c);bindBranding(c);}}
