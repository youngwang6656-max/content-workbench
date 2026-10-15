export function contentIcon(kind){
 const body=kind==='comment'?'<text x="16" y="20" text-anchor="middle">c</text><path d="M9 24h14M9 28h14"/>':kind==='cb'?'<rect x="3" y="3" width="26" height="26" rx="1"/><text x="16" y="24" text-anchor="middle" class="brief-letter">B</text>':'<text x="16" y="25" text-anchor="middle">A</text>';
 return `<svg class="content-type-icon" data-content-kind="${['post','comment','cb'].includes(kind)?kind:'post'}" viewBox="0 0 32 32" aria-hidden="true">${body}</svg>`;
}
