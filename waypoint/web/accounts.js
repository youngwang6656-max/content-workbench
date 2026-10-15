function remember(name){try{localStorage.setItem('content_workbench_name',name);}catch{}}
function remembered(){try{return localStorage.getItem('content_workbench_name')||'';}catch{return '';}}
export function renderLogin(ctx){
 const {state,main,esc,api,toast,boot}=ctx;document.body.classList.add('account-locked');
 main.innerHTML=`<div class="account-welcome"><div class="account-logo"><img data-workbench-logo src="${esc(state.branding?.logo_url||'/static/workbench-mark.svg')}" alt="工作台标识"></div><div class="panel account-card"><div class="eyebrow">本机工作空间 · ${esc(state.version)}</div><h1>怎么称呼你？</h1><p class="muted">输入名称，即可开始使用。</p><form id="account-login"><label for="account-name">名称</label><input id="account-name" name="name" autocomplete="nickname" required maxlength="80" value="${esc(remembered())}" placeholder="你的名字或昵称"><p class="form-error" id="account-error" role="alert"></p><button class="primary full">进入工作台</button></form><p class="note">无需注册或密码。名称仅用于显示，这台电脑使用同一套资料；模型连接仍由你在设置中配置。</p></div></div>`;
 const form=main.querySelector('#account-login');form.onsubmit=async e=>{e.preventDefault();const button=form.querySelector('button'),error=main.querySelector('#account-error');error.textContent='';button.disabled=true;
  try{const name=form.elements.name.value.trim();await api('/auth/name',{method:'POST',body:{name}});remember(name);await boot();toast('欢迎，'+name);}catch(e){error.textContent=e.message;}finally{button.disabled=false;}
 };
}
export async function renderAccount(ctx){
 const {state,main,esc,api,toast,boot}=ctx,user=state.auth.user;
 main.innerHTML=`<div class="eyebrow">本机工作空间</div><h1>使用名称</h1><p class="muted">名称用于显示，不区分账号和资料。</p><div class="setting-section"><div class="panel"><div class="panel-heading"><h2>${esc(user.display_name)}</h2><span class="badge">本机管理员</span></div><form id="profile-form"><label for="profile-name">名称</label><input id="profile-name" name="display_name" maxlength="80" required value="${esc(user.display_name)}"><div class="form-footer"><button>保存名称</button></div></form></div><div class="panel"><p class="muted">当前无需密码。切换名称不会删除或另建工作资料，官方模型登录与本机名称分别管理。</p><button id="logout">重新输入名称</button></div></div>`;
 main.querySelector('#profile-form').onsubmit=async e=>{e.preventDefault();const user=await api('/auth/profile',{method:'PATCH',body:Object.fromEntries(new FormData(e.target))});state.auth.user=user;remember(user.display_name);await renderAccount(ctx);toast('名称已保存');};
 main.querySelector('#logout').onclick=async()=>{await api('/auth/logout',{method:'POST',body:{}});await boot();};
}
