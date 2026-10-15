export function latestJob(jobs=[]){return [...jobs].filter(j=>!j.archived).sort((a,b)=>String(b.created_at||'').localeCompare(String(a.created_at||'')))[0];}

export function flowHTML(esc,task,jobs=[]){
 const job=latestJob(jobs);
 let steps=job?.steps?.length?job.steps:[
  {key:'input',label:'输入',status:'completed'},
  {key:'draft',label:'生成目标稿',status:['running','queued'].includes(task.status)?'running':'pending'},
  {key:'decision',label:'等待你的决定',status:task.status==='completed'?'current':'pending'}
 ];
 const names={theme:'主题',idea:'中文思路',chinese:'中文表达',english:'英文成品',cb:'中文 CB'};
 const creative=['post','comment'].includes(task.kind),phase=task.workflow_phase;
 const checkpoint=task.checkpoint_stage||task.target_stage,intermediate=creative&&checkpoint!=='english';
 if(creative){
  const part=key=>job?.steps?.find(s=>s.key===key)||{status:'pending'};
  const group=task.kind==='post'&&!task.post_group_id;
  const advanced=group?['final_ready','finished'].includes(phase):task.target_stage==='english';
  const finalReady=['final_ready','finished'].includes(phase),checkpointReady=['checkpoint_ready','mixed'].includes(phase);
  steps=[{key:'input',label:'输入想法与原帖',status:'completed'}];
  if(group)steps.push({key:'community',label:'确定模拟社群',...part('community')});
  if(intermediate){
   steps.push({key:'checkpoint',label:`生成${names[checkpoint]||checkpoint}`,status:advanced||checkpointReady?'completed':part('draft').status,content_zh:!advanced?part('draft').content_zh:''});
   steps.push({key:'continue',label:'节点通过 → 英文',status:advanced?'completed':checkpointReady?'current':'pending'});
  }
  steps.push({key:'fact',label:'具体信息核验',status:finalReady?'completed':advanced?part('fact').status:'pending',content_zh:advanced?part('fact').content_zh:''});
  const partial=group&&task.final_counts?.english_ready>0;
  steps.push({key:'english',label:'生成英文成品',status:finalReady?'completed':partial?'partial':advanced?part('draft').status:'pending'});
  steps.push({key:'translation',label:'对应中文回译',status:finalReady?'completed':partial?'partial':advanced?part('backtranslation').status:'pending'});
  steps.push({key:'decision',label:'英文成品最终通过',status:phase==='finished'?'completed':phase==='final_ready'?'current':'pending'});
 }
 const path=creative?`${names[task.input_stage]||'输入'}${intermediate?' → 查看'+(names[checkpoint]||checkpoint):''} → 英文成品`:`${names[task.input_stage]||'输入'} → 中文 CB`;
 const counts=task.final_counts?` · ${task.final_counts.english_ready}/${task.final_counts.total} 篇已生成英文，${task.final_counts.passed} 篇最终通过`:'';
 return `<section class="flow-panel" aria-label="本次模拟流程"><div class="flow-heading"><strong>模拟创作流程${esc(counts)}</strong><span>${esc(path)}</span></div><ol class="flow-track">${steps.map((step,i)=>`<li class="flow-step ${esc(step.status)}"><span class="flow-index">${i+1}</span><div><strong>${esc(step.label)}</strong><small>${{completed:'已完成',running:'进行中',current:'等待你的决定',partial:'部分稿件已完成',pending:'待进行'}[step.status]||'待进行'}</small>${step.content_zh?`<details><summary>查看内容</summary><p>${esc(step.content_zh)}</p></details>`:''}</div></li>`).join('')}</ol></section>`;
}

export function factHTML(esc,revision){
 const check=revision?.fact_check;
 if(!check)return '';
 const label={supported:'有公开来源',unverified:'未核实',conflicted:'来源冲突'};
 const rows=(check.claims||[]).map(item=>{const urls=(item.source_urls||[]).filter(url=>typeof url==='string'&&/^https:\/\/[a-z0-9.-]+(?:[/:?#]|$)/i.test(url));return `<li><strong>${label[item.status]||'未核实'}</strong> · ${esc(item.claim_zh)}${urls.length?` · ${urls.map((url,i)=>`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">来源 ${i+1} ↗</a>`).join(' ')}`:''}</li>`;}).join('');
 return `<div class="fact-note"><strong>具体信息核验</strong><p>${esc(check.summary_zh||'本轮未取得可核实结果。')}</p>${rows?`<ul>${rows}</ul>`:''}<small>模拟稿中的未核实说法保留在正文，核验提示不会混入复制内容。</small></div>`;
}
