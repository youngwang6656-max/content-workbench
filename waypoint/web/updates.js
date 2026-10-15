export function updatesHTML(c,u){
 const {esc}=c,d=u.local_changes;
 const message=d.state==='clean'?'当前程序与发布文件基线一致。':d.state==='modified'?`检测到 ${d.count} 个本地源码差异。更新包会另存，旧代码保留供你合并。`:'当前目录没有有效文件基线，请保留旧目录和自己修改的代码。';
 return `<section class="panel" id="update-panel"><div class="panel-heading"><h2>程序更新与本地修改</h2><span class="badge">当前 ${esc(u.current_version)}</span></div><p class="muted">每人独立安装、自己保存数据和修改源码。开发者发布新版后，可以在这里检查并下载。更新包解压到新文件夹；旧目录保留，资料沿用原位置。</p><p class="note">${message}</p>${d.count?`<details><summary>查看本地修改文件</summary><ul>${[['changed','已修改'],['added','本地新增'],['deleted','已删除']].flatMap(([key,label])=>d[key].map(name=>`<li>${label} · ${esc(name)}</li>`)).join('')}</ul></details>`:''}<form id="update-source-form"><label>开发者提供的更新清单地址<input name="url" type="url" maxlength="2500" value="${esc(u.manifest_url)}" placeholder="https://你的发布网站/update-manifest.json"></label><p class="note">暂未发布到外网时留空。仅保存地址，不自动检查；检查和下载不上传项目、账号或密钥，也不启用 API。</p><div class="actions"><button>保存更新源</button><button type="button" id="check-update" ${u.manifest_url?'':'disabled'}>检查新版</button></div></form><div id="update-result" aria-live="polite"></div><p class="note">源码可以自行修改。下载前自动备份业务资料，不替换账号或密钥，不自动安装或覆盖自己的代码。</p></section>`;
}

export function bindUpdates(c){
 const {main,api,esc,toast}=c;const result=main.querySelector('#update-result');
 main.querySelector('#update-source-form').onsubmit=async e=>{e.preventDefault();await api('/updates/source',{method:'POST',body:{url:new FormData(e.target).get('url').trim()}});toast('更新源已保存，未发起联网检查');await c.render();};
 main.querySelector('#check-update').onclick=async e=>{
  const button=e.currentTarget;button.disabled=true;result.textContent='正在读取更新清单…';
  try{const candidate=await api('/updates/check',{method:'POST',body:{}});
   if(!candidate.available){result.innerHTML=`<p class="note">当前没有更高版本。更新源版本：${esc(candidate.version)}。</p>`;return;}
   result.innerHTML=`<div class="hint"><strong>发现新版 ${esc(candidate.version)}</strong><p class="update-notes">${esc(candidate.notes_zh||'开发者未填写更新说明。')}</p><p>${(candidate.size/1e6).toFixed(2)} MB · 下载后请解压到新文件夹，合并自己的修改。</p><button id="download-update">备份资料并下载新版</button></div>`;
   main.querySelector('#download-update').onclick=async event=>{const download=event.currentTarget;download.disabled=true;download.textContent='正在校验下载和备份…';try{const data=await api('/updates/download',{method:'POST',body:{candidate_id:candidate.candidate_id}});const response=await fetch('/api/updates/packages/'+data.package_id);if(!response.ok)throw Error('下载文件失败，请重新检查更新');const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download=data.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);result.innerHTML=`<div class="hint"><p>${esc(data.message)}</p><p class="note">业务备份：${esc(data.backup)}</p></div>`;toast('新版已下载，当前程序仍保留');}finally{download.disabled=false;download.textContent='备份资料并下载新版';}};
  }catch(error){result.textContent=error.message;throw error;}finally{button.disabled=false;}
 };
}
