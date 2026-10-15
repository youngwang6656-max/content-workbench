const root=document.documentElement;
let mode='system';try{mode=localStorage.getItem('waypoint_theme')||'system';}catch{}
const media=matchMedia('(prefers-color-scheme: dark)');
const labels={system:'跟随系统',light:'浅色',dark:'深色'};
function apply(){root.dataset.theme=mode==='system'?(media.matches?'dark':'light'):mode;const b=document.querySelector('#theme-toggle');if(b){b.textContent='◐ '+labels[mode];b.setAttribute('aria-label','切换外观，当前'+labels[mode]);}}
apply();media.addEventListener('change',apply);
document.addEventListener('DOMContentLoaded',()=>{apply();document.querySelector('#theme-toggle').onclick=()=>{mode={system:'light',light:'dark',dark:'system'}[mode]||'system';try{localStorage.setItem('waypoint_theme',mode);}catch{}apply();};});
