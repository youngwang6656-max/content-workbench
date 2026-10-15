function inline(esc,text){return esc(text).replace(/`([^`]+)`/g,'<code>$1</code>');}
function blocks(esc,text){
 let result='',list=false,code=false,buffer=[];
 for(const line of text.split('\n')){
  if(line.startsWith('```')){if(code){result+='<pre>'+esc(buffer.join('\n'))+'</pre>';buffer=[];}code=!code;continue;}
  if(code){buffer.push(line);continue;}
  if(/^[-*] /.test(line)||/^\d+\. /.test(line)){if(!list){result+='<ul>';list=true;}result+='<li>'+inline(esc,line.replace(/^([-*]|\d+\.) /,''))+'</li>';continue;}
  if(list){result+='</ul>';list=false;}
  if(/^### /.test(line))result+='<h3>'+inline(esc,line.slice(4))+'</h3>';
  else if(line.trim())result+='<p>'+inline(esc,line)+'</p>';
 }
 if(list)result+='</ul>';return result;
}
export async function renderManual(c){
 const {esc,main}=c,value=await c.api('/manual'),parts=value.markdown.split(/^## /m),intro=parts.shift(),sections=parts.map((raw,i)=>{
  const [title,...body]=raw.split('\n');return {title,body:body.join('\n'),raw,id:'manual-section-'+i};});
 main.innerHTML=`<div class="eyebrow">本机手册 · ${esc(value.version)}</div><div class="topbar"><div><h1>使用手册</h1><p class="muted">查看手册不消耗模型额度。可下载给用户或任意智能体阅读。</p></div><div class="actions"><a class="button-link" href="/api/manual/download" download>下载用户手册</a><a class="button-link" href="/api/manual/agent" download>下载智能体手册</a></div></div><label>搜索手册<input id="manual-search" type="search" placeholder="例如：资料、铺评、额度、启动"></label><div class="manual-layout"><nav class="panel manual-toc" aria-label="手册目录">${sections.map(x=>`<a href="#${x.id}">${esc(x.title)}</a>`).join('')}</nav><div class="manual-content"><div class="panel">${blocks(esc,intro.replace(/^# .*\n/,''))}</div>${sections.map(x=>`<section class="panel manual-section" id="${x.id}"><h2>${esc(x.title)}</h2>${blocks(esc,x.body)}</section>`).join('')}<p id="manual-empty" class="note" hidden>没有找到相关章节，请换个关键词。</p></div></div>`;
 main.querySelector('#manual-search').oninput=ev=>{const query=ev.target.value.trim().toLowerCase();let count=0;
  for(const x of sections){const match=!query||x.raw.toLowerCase().includes(query);main.querySelector('#'+x.id).hidden=!match;main.querySelector(`a[href="#${x.id}"]`).hidden=!match;if(match)count++;}
  main.querySelector('#manual-empty').hidden=!!count;
 };
}
