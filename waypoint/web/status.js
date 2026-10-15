export function progressLabel(task,labels){
 const phases={checkpoint_ready:'查看节点待确认',final_ready:'英文成品待通过',finished:'已完成',mixed:'部分稿件待推进',standalone_ready:'CB 待检查',abandoned:'已移除'};
 return phases[task.workflow_phase]||labels[task.status]||task.status;
}
export function renderStatus(c,t,host){
 if(!host)return;
 const {esc,labels}=c;const attention=['paused','failed'].includes(t.status);
 host.className='task-status'+(attention?' needs-attention':'');host.setAttribute('role','status');host.setAttribute('aria-live','polite');
 let message=esc(t.message||'');const target=t.attention;const canJump=attention&&(target||message.includes('资料'));
 if(canJump){const link='<a href="#materials" class="status-link" data-material-jump>资料</a>';message=message.includes('资料')?message.replace('资料',link):message+' · '+link;}
 host.innerHTML=`<strong class="status-label ${attention?'attention-label':''}">${attention?'! ':''}${esc(progressLabel(t,labels))}</strong>${message?' · <span>'+message+'</span>':''}`;
 host.querySelector('[data-material-jump]')?.addEventListener('click',async ev=>{ev.preventDefault();c.state.page=target?.page||'materials';c.state.project=target?.project_id??t.project_id;c.state.materialFocus=target?.material_id||'';await c.refreshProjects();await c.render();});
}
