'use strict';
/* Render explicit TeX from trusted question data and formula-like plain text.
   Text is escaped by the existing application renderer; no HTML injection. */
(function(){
 let scheduled=false,busy=false;
 function convert(t){
  if(/\\\(|\\\[|\\\$/.test(t))return t;
  return t.replace(/(?:Qd|Qs|CMg|IMg|CT|P|Q|M|Px|q1|q2|X)\s*(?:\([^)]{1,12}\))?\s*=\s*[0-9A-Za-z()+−×*\/².\s-]{2,75}/g,m=>{
    const v=m.trim().replace(/²/g,'^{2}').replace(/×/g,'\\times ').replace(/−/g,'-').replace(/\b(q1|q2|Qd|Qs|CMg|IMg|CT|Px)\b/g,x=>({'q1':'q_{1}','q2':'q_{2}','Qd':'Q_d','Qs':'Q_s','CMg':'CMg','IMg':'IMg','CT':'CT','Px':'P_x'}[x]));
    return '\\('+v+'\\)';
  });
 }
 function apply(){
  if(busy)return;busy=true;
  try{
   const roots=[document.querySelector('#content'),document.querySelector('#teacherContent')].filter(Boolean);
   for(const root of roots){
    const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;
    while(n=w.nextNode()){
      if(!n.parentElement||n.parentElement.closest('script,style,textarea,pre,code,input,mjx-container,[data-math-done]'))continue;
      const val=n.nodeValue;if(!val||val.length>1200)continue;
      const next=convert(val);if(next!==val){const span=document.createElement('span');span.dataset.mathDone='1';span.textContent=next;n.replaceWith(span)}
    }
   }
   if(window.MathJax?.typesetPromise)window.MathJax.typesetPromise(roots).catch(()=>{});
  }finally{busy=false}
 }
 function schedule(){if(scheduled)return;scheduled=true;setTimeout(()=>{scheduled=false;apply()},140)}
 document.addEventListener('DOMContentLoaded',()=>{schedule();new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true})});
 window.adaptaTypeset=schedule;
})();