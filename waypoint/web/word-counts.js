export function countWords(text){return (String(text||'').match(/https?:\/\/[^\s]+|[A-Za-z0-9]+(?:[.,][0-9]+)*(?:[’'-][A-Za-z0-9]+)*/g)||[]).length;}
export function wordCountHTML(title,body){
 const a=countWords(title),b=countWords(body);
 return `<span class="word-count" title="本机统计，不调用模型。英文词、数字、URL各计一个；缩写和带连字符名称计一个；中文不计入。">正文 ${b} 词${title?` · 标题 ${a} 词 · 合计 ${a+b} 词`:''}</span>`;
}
