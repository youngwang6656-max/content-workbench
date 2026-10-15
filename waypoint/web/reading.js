// Reading aids never replace originals, workflow stages, or review evidence.
export function readingControl(c,host,request,options={}){
 if(!host)return;
 const button=document.createElement('button');button.type='button';button.textContent='中文译读';button.className='reading-button';
 const output=document.createElement('div');output.className='reading-result';output.hidden=true;host.append(button,output);
 if(options.copyText){
  const copy=document.createElement('button');copy.type='button';copy.textContent='复制';copy.className='reading-copy';button.after(copy);
  copy.onclick=async()=>{const text=options.copyText();try{await navigator.clipboard.writeText(text);c.toast('已复制英文成品');}catch{const modal=c.dialog('复制英文成品',`<textarea id="english-copy-fallback" readonly rows="10">${c.esc(text)}</textarea>`,async()=>{});modal.querySelector('#english-copy-fallback').select();}};
 }
 button.onclick=async()=>{
  const payload=request(),signature=JSON.stringify(payload);button.disabled=true;output.hidden=false;output.textContent='正在翻译当前内容…';
  try{const result=await c.api('/reading-translation',{method:'POST',body:payload});
   if(!host.isConnected)return;
   if(JSON.stringify(request())!==signature){output.textContent='原文已改变，本次译读已保存；请重新翻译当前内容。';return;}
   output.innerHTML=`<div class="note">对应本次原文 · 辅助理解，不改变原稿或审核状态</div><div class="draft">${c.esc(result.text)}</div>`;
  }catch(e){output.textContent=e.message;}finally{button.disabled=false;}
 };
 return {button,output};
}
export function quickReading(c){
 const selection=window.getSelection()?.toString()||'';
 const d=c.dialog('随时中文译读',`<p class="note">可先选中页面文字，也可直接粘贴。主题、思路、原帖、历史稿件和修改建议中的英文都能在这里译读。</p><textarea id="reading-input" rows="8" placeholder="粘贴需要理解的英文…">${c.esc(selection)}</textarea><div id="reading-tool"></div>`,async()=>{});
 readingControl(c,d.querySelector('#reading-tool'),()=>({project_id:c.state.project||null,text:d.querySelector('#reading-input').value}));
}
