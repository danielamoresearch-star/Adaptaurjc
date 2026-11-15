'use strict';
/**
 * Student idle-session controller.
 * Only trusted pointer, keyboard, wheel, and touch interactions renew the lease.
 * Passive fetches, background timers, speech, and notes pings do not renew it.
 * Server enforces the same 900-second idle boundary.
 */
(()=>{
 const IDLE=900000,WARNING=60000,RENEW_EVERY=25000,KEY='adapta_v6_last_interaction';
 let lastInput=0,lastRenewed=0,timer=null,pending=false,warning=null,installed=false;
 const session=()=>window.adaptaSessionInfo?.()||{};
 const student=()=>session().role==='student'&&!!session().token;
 const now=()=>Date.now();
 function hideWarning(){if(warning){warning.hidden=true;warning.textContent=''}}
 function makeWarning(){
  warning=document.getElementById('adaptaIdleWarning');
  if(!warning){warning=document.createElement('div');warning.id='adaptaIdleWarning';warning.setAttribute('role','status');warning.setAttribute('aria-live','polite');warning.hidden=true;document.body.appendChild(warning)}
 }
 function stop(){
  if(timer){clearInterval(timer);timer=null}
  pending=false;lastRenewed=0;hideWarning();sessionStorage.removeItem(KEY)
 }
 function expire(){
  stop();
  window.adaptaExpireIdleSession?.('Tu sesión ha finalizado porque han pasado 15 minutos sin actividad. Accede de nuevo para continuar donde lo dejaste.');
 }
 async function renew(){
  if(pending||!student())return;
  pending=true;const credentials=session();
  try{
   const res=await fetch('/api/session/activity',{method:'POST',headers:{Authorization:'Bearer '+credentials.token},cache:'no-store'});
   if(res.status===401){if(session().token===credentials.token)expire();return}
   if(res.ok){lastRenewed=now()}
  }catch(e){/* A transient network loss must not be interpreted as an idle timeout. */}
  finally{pending=false}
 }
 function check(){
  if(!student()){hideWarning();return}
  let left=IDLE-(now()-lastInput);
  if(left<=0){expire();return}
  if(left<=WARNING){
   if(!warning)makeWarning();
   warning.hidden=false;
   warning.textContent='La sesión se cerrará por inactividad en '+Math.ceil(left/1000)+' s. Interactúa con la aplicación para continuar.';
  }else hideWarning()
 }
 function interaction(event){
  if(!event.isTrusted||!student()||document.hidden||document.querySelector('#app')?.hidden)return;
  // A synthetic event or a background script cannot extend the student session.
  const moment=now();
  if(moment-lastInput>=IDLE){expire();return}
  lastInput=moment;sessionStorage.setItem(KEY,String(moment));hideWarning();
  if(moment-lastRenewed>=RENEW_EVERY)renew()
 }
 function start(freshLogin=false){
  if(!student())return;
  makeWarning();
  const saved=Number(sessionStorage.getItem(KEY));
  const time=now();
  if(!freshLogin&&saved&&time-saved>=IDLE){expire();return}
  lastInput=freshLogin||!saved?time:Math.min(time,saved);
  lastRenewed=lastInput;
  sessionStorage.setItem(KEY,String(lastInput));
  if(timer)clearInterval(timer);
  timer=setInterval(check,2000);check();
  if(!installed){
   installed=true;
   ['pointerdown','keydown','wheel','touchstart'].forEach(type=>
     document.addEventListener(type,interaction,{capture:true,passive:true}));
   document.addEventListener('visibilitychange',()=>{if(!document.hidden)check()});
   window.addEventListener('focus',check);
   window.addEventListener('pageshow',check);
  }
 }
 window.adaptaIdleStart=start;
 window.adaptaIdleStop=stop;
 window.adaptaSecondsSinceInteraction=()=>student()?Math.max(0,(now()-lastInput)/1000):Infinity;
 window.addEventListener('DOMContentLoaded',()=>{if(student())start(false)});
})();
