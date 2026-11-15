'use strict';
/* Inline original vector icons (Lucide-style paths), zero third-party font/CDN. */
(()=>{
 const paths={
  courses:'<path d="m3 10 9-7 9 7-9 7-9-7Z"/><path d="M6 12v5c4 3 8 3 12 0v-5"/><path d="M21 11v6"/>',
  micro1:'<path d="M12 7v14"/><path d="m3 18 9 3 9-3V4l-9 3-9-3z"/><path d="M3 4v14"/>',
  micro2:'<path d="M9 3h6"/><path d="M10 3v6l-6 10a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3L14 9V3"/><path d="M7 16h10"/>',
  dashboard:'<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="5" rx="1"/><rect x="13" y="10" width="8" height="11" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/>',
  diagnostic:'<rect x="5" y="4" width="14" height="18" rx="2"/><path d="M9 2h6v4H9z"/><path d="m9 15 2 2 4-4"/>',
  practice:'<path d="M9 2v4M15 2v4M3 10h18"/><rect x="3" y="5" width="18" height="17" rx="2"/><path d="m8 16 3 3 5-6"/>',
  mentor:'<path d="M12 3a7 7 0 0 1 7 7 7 7 0 0 1-4 6v5l-3-2-3 2v-5a7 7 0 0 1-4-6 7 7 0 0 1 7-7Z"/><path d="M9 10h.01M15 10h.01"/><path d="M9 13q3 3 6 0"/>',
  research:'<path d="M3 3v18h18"/><path d="m7 16 4-5 3 2 5-7"/>',
  exams:'<path d="M7 3h10l4 4v14H3V3Z"/><path d="M17 3v5h4M7 12h10M7 16h7"/>'
 };
 function svg(name){
  return '<svg class="adapta-nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+paths[name]+'</svg>';
 }
 function apply(){
  document.querySelectorAll('.side-nav button[data-page],.mobile-dock button[data-page]').forEach(button=>{
   const name=button.dataset.page;
   if(!paths[name])return;
   let target=button.querySelector(':scope > span');
   if(!target)return;
   if(!target.querySelector('svg.adapta-nav-icon'))target.innerHTML=svg(name);
   target.setAttribute('aria-hidden','true');
  });
  const menu=document.getElementById('mobileMenu');
  if(menu&&!menu.querySelector('svg'))menu.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>';
 }
 document.addEventListener('DOMContentLoaded',()=>{
  apply();
  const menu=document.getElementById('sidebar');
  if(menu)new MutationObserver(apply).observe(menu,{childList:true,subtree:false});
 });
})();
