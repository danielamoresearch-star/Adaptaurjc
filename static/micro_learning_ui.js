'use strict';
/* MICRO ADAPTA-ITS 2026-27: topic selection, mandatory diagnostic, notes & grounded NOVA. */
(()=>{
 const $=id=>document.getElementById(id);
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','"':'&#39;'}[c]));
 const NAMES={micro1:'Microeconomía I',micro2:'Microeconomía II'};
 const TYPES={teorica:'Teoría',rapida:'Cálculo rápido',grafica:'Análisis gráfico',noticia:'Noticia económica',caso:'Caso práctico'};
 let state={course:'micro1',unit:1,selected:new Set([1]),tab:'practice',kind:'',progress:null,catalog:null,lang:'es',question:null,t0:0,interval:null,noteId:null,noteSince:0,noteTimer:null,chat:[]};
 const api=async(url,opt={})=>{
  const headers={Authorization:'Bearer '+token,...(opt.headers||{})};
  let r=await fetch(url,{...opt,headers});
  let d=await r.json().catch(()=>({detail:'Respuesta del servidor no interpretable'}));
  if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'Error HTTP '+r.status);
  return d
 };
 function topics(){return state.catalog?.curriculum?.[state.course]?.[state.lang]||[]}
 function progressFor(unit){return state.progress?.units?.[String(unit)]||{}}
 function selectedString(){return [...state.selected].sort((a,b)=>a-b).join(',')}
 function updateMath(){window.adaptaTypeset?.()}
 function message(text,isError=false){const e=$('mlNotice');if(e){e.textContent=text;e.classList.toggle('error-text',isError)}}
 function badges(){
  const p=state.progress;if(!p)return '';
  return '<div class="ml-summary" aria-label="Indicadores de aprendizaje">'+
   '<div><small>Diagnóstico</small><b>'+p.diagnostic_count+'/'+p.diagnostic_total+'</b><div class="ml-track"><i style="width:'+(100*p.diagnostic_count/p.diagnostic_total)+'%"></i></div></div>'+
   '<div><small>Actividad de estudio</small><b>'+p.participation_pct+' %</b><div class="ml-track"><i style="width:'+p.participation_pct+'%"></i></div></div>'+
   '<div><small>Dominio estimado · BKT</small><b>'+p.estimated_mastery_pct+' %</b><div class="ml-track mastery"><i style="width:'+p.estimated_mastery_pct+'%"></i></div></div>'+
   '</div><p class="ml-disclaimer">El dominio es una estimación probabilística no calibrada, distinta de la nota. El índice de actividad incluye ejercicios y consulta de apuntes.</p>';
 }
 function cards(){
  return '<div class="ml-topics">'+topics().map((name,i)=>{
   const u=i+1,p=progressFor(u),done=p.diagnostic_complete;
   return '<label class="ml-topic '+(state.selected.has(u)?'selected':'')+'">'+
    '<input type="checkbox" data-mltopic="'+u+'" '+(state.selected.has(u)?'checked':'')+' '+(!state.progress?.diagnostic_complete?'disabled':'')+'>'+
    '<span><small>Tema '+u+(done?' · diagnosticado':' · pendiente de diagnóstico')+'</small><b>'+esc(name)+'</b>'+
    '<span class="ml-topic-stats">'+(p.attempts||0)+' ejercicios · '+(p.notes_views||0)+' lecturas · '+Math.round(100*(p.mastery??.24))+' % dominio estimado</span>'+
    '<span class="ml-track"><i style="width:'+(p.participation_pct||0)+'%"></i></span></span></label>'
  }).join('')+'</div>';
 }
 function header(){
  return '<div class="eyebrow">MICRO ADAPTA-ITS · 2026–2027</div>'+
   '<div class="between ml-head"><div><h1>'+esc(NAMES[state.course])+'</h1><p class="muted">Aprende con evidencias, paso a paso. Elige qué conceptos deseas practicar.</p></div>'+
   '<button class="btn btn-outline" id="mlAllCourses">Cambiar asignatura</button></div>'+badges()+
   '<div class="ml-tabs" role="tablist" aria-label="Herramientas del curso">'+
   [['practice','Practicar'],['notes','Apuntes'],['tutor','Tutor NOVA'],['progress','Mi progreso']].map(([k,t])=>
    '<button type="button" data-mltab="'+k+'" role="tab" aria-selected="'+(state.tab===k)+'" class="'+(state.tab===k?'active':'')+'">'+t+'</button>').join('')+
   '</div><div id="mlNotice" role="status" aria-live="polite"></div><div id="mlBody"></div>'+
   '<nav class="ml-bottom" aria-label="Accesos rápidos del curso"><button data-mltab="practice">Practicar</button><button data-mltab="notes">Apuntes</button><button data-mltab="tutor">NOVA</button><button data-mltab="progress">Progreso</button></nav>';
 }
 function attachShell(){
  $('mlAllCourses').onclick=()=>navigate('courses');
  document.querySelectorAll('[data-mltab]').forEach(b=>b.onclick=()=>showTab(b.dataset.mltab));
 }
 function showTab(tab){
  stopNotes();
  clearInterval(state.interval);state.tab=tab;state.question=null;
  document.querySelectorAll('[data-mltab]').forEach(b=>{
   const yes=b.dataset.mltab===tab;
   b.classList.toggle('active',yes);
   if(b.getAttribute('role')==='tab')b.setAttribute('aria-selected',String(yes));
  });
  if(tab==='practice')showPractice();
  if(tab==='notes')showNotes();
  if(tab==='tutor')showTutor();
  if(tab==='progress')showProgress();
 }
 function showPractice(){
  const body=$('mlBody');if(!body)return;
  if(!state.progress?.diagnostic_complete){
   const n=state.progress?.diagnostic_count||0,all=state.progress?.diagnostic_total||topics().length;
   body.innerHTML='<section class="card ml-diagnostic"><span class="pill">Paso 1 · Evaluación inicial</span>'+
    '<h2>Diagnóstico por competencias</h2><p>Antes de iniciar la práctica, responde <b>una pregunta por cada tema</b>. Se actualizará el conocimiento estimado tras cada respuesta.</p>'+
    '<p class="ml-step">Pregunta '+Math.min(n+1,all)+' de '+all+'</p>'+
    '<button class="btn btn-primary" id="mlStartDiagnostic">'+(n?'Continuar diagnóstico':'Comenzar diagnóstico')+'</button>'+
    '</section><section class="card"><h3>Qué ocurre después</h3><p>Podrás seleccionar uno, varios o todos los temas, consultar sus apuntes y practicar cuestiones de las modalidades disponibles.</p></section>'+
    '<div id="mlQuestion"></div>';
   $('mlStartDiagnostic').onclick=()=>nextQuestion('diagnostic');
   return;
  }
  body.innerHTML='<section class="card"><h2>Selecciona los temas de estudio</h2><p class="muted">Marca uno o varios temas. En los grupos con aprendizaje adaptativo, se reforzarán los contenidos con mayores dificultades observadas.</p>'+
   '<div class="ml-selection"><button type="button" class="btn btn-soft" id="mlSelectAll">Todos los temas</button><button type="button" class="btn btn-outline" id="mlClearSelected">Limpiar selección</button></div>'+
   cards()+'<div class="ml-settings"><label for="mlKind">Tipo de ejercicio</label><select id="mlKind"><option value="">Todas las modalidades</option>'+
   Object.entries(TYPES).map(([k,v])=>'<option value="'+k+'">'+esc(v)+'</option>').join('')+
   '</select><button id="mlBeginPractice" class="btn btn-primary">Practicar temas seleccionados</button></div>'+
   '<p class="muted-note">Las preguntas siguientes se adaptan a tu historial solo si perteneces a un grupo de tratamiento. Las preguntas y respuestas quedan registradas para su análisis docente.</p></section><div id="mlQuestion"></div>';
  $('mlKind').value=state.kind;
  $('mlKind').onchange=e=>state.kind=e.target.value;
  body.querySelectorAll('[data-mltopic]').forEach(input=>input.onchange=()=>{
   const k=Number(input.dataset.mltopic);if(input.checked)state.selected.add(k);else state.selected.delete(k);
   input.closest('.ml-topic')?.classList.toggle('selected',input.checked)
  });
  $('mlSelectAll').onclick=()=>{state.selected=new Set(topics().map((_,i)=>i+1));showPractice()};
  $('mlClearSelected').onclick=()=>{state.selected=new Set();showPractice()};
  $('mlBeginPractice').onclick=()=>{if(!state.selected.size){message('Selecciona al menos un tema.',true);return}nextQuestion('practice')};
 }
 async function nextQuestion(phase='practice'){
  clearInterval(state.interval);
  const box=$('mlQuestion');if(!box)return;
  box.innerHTML='<p class="muted">Preparando una pregunta…</p>';
  try{
   const par=new URLSearchParams({course:state.course,units:selectedString()||'1',unit:'1',phase,modality:phase==='practice'?state.kind:'',lang:state.lang});
   const q=await api('/api/micro/next?'+par);
   if(q.complete){
    state.progress=await api('/api/micro/progress?course='+state.course);
    redraw();showPractice();message('Evaluación diagnóstica completada. Ya puedes seleccionar tus temas.');return;
   }
   if(!q.available){box.innerHTML='<p class="muted">'+esc(q.message)+'</p>';return}
   state.question=q;state.t0=performance.now();
   const options=q.options.map((opt,i)=>'<label class="ml-option"><input type="radio" name="mlAnswer" value="'+i+'" required><span class="ml-option-key">'+String.fromCharCode(65+i)+'</span><span>'+esc(opt)+'</span></label>').join('');
   box.innerHTML='<article class="card ml-question"><div class="between"><span class="pill">'+esc(q.id)+'</span>'+
    '<span class="pill neutral">'+(phase==='diagnostic'?'Diagnóstico':esc(TYPES[q.modality]||q.modality))+' · Tema '+q.unit+'</span></div>'+
    '<h2>'+esc(q.prompt)+'</h2>'+(q.figure_id?'<figure class="micro-figure"><img loading="lazy" alt="Gráfico del ejercicio '+esc(q.id)+'" src="/api/micro/figure/'+encodeURIComponent(q.figure_id)+'"></figure>':'')+
    '<form id="mlAnswerForm"><fieldset><legend>Elige tu respuesta</legend>'+options+'</fieldset>'+
    '<div class="ml-question-actions"><span id="mlElapsed">00:00</span><button class="btn btn-primary" type="submit">Comprobar respuesta</button></div></form>'+
    '<div id="mlFeedback"></div></article>';
   $('mlAnswerForm').onsubmit=submit;
   const stamp=()=>{const node=$('mlElapsed');if(node){const sec=Math.floor((performance.now()-state.t0)/1000);node.textContent=String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0')}};
   state.interval=setInterval(stamp,1000);
   box.scrollIntoView({behavior:'smooth',block:'start'});
   updateMath();
  }catch(e){box.innerHTML='<div class="error-text">'+esc(e.message)+'</div>'}
 }
 async function submit(e){
  e.preventDefault();const q=state.question,form=$('mlAnswerForm');
  if(!q||!form)return;
  const chosen=form.querySelector('input[name=mlAnswer]:checked');if(!chosen)return;
  form.querySelectorAll('input,button').forEach(e=>e.disabled=true);clearInterval(state.interval);
  const elapsed=Number(((performance.now()-state.t0)/1000).toFixed(1));
  try{
   const a=await api('/api/micro/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:q.token,answer:Number(chosen.value),elapsed_sec:elapsed})});
   state.progress=await api('/api/micro/progress?course='+state.course);
   const p=state.progress;
   const summary=document.querySelector('.ml-summary');if(summary){const frag=document.createElement('div');frag.innerHTML=badges();summary.replaceWith(frag.firstElementChild)}
   const msg=a.correct?'Respuesta correcta. Vas consolidando este concepto.':'Este intento señala qué conviene repasar. Puedes mejorar con una explicación y otro ejercicio.';
   const panel=$('mlFeedback');
   panel.innerHTML='<div class="ml-feedback '+(a.correct?'good':'review')+'" role="status">'+
    '<h3>'+esc(msg)+'</h3><p><b>Opción correcta:</b> '+String.fromCharCode(65+a.answer)+'. '+esc(a.answer_text)+'</p>'+
    '<div class="ml-explanation">'+esc(a.explanation)+'</div>'+
    '<div class="ml-confidence"><small>Probabilidad posterior estimada para este tema</small>'+
    '<b>'+Math.round(100*a.posterior_before)+' % → '+Math.round(100*a.posterior_after)+' %</b>'+
    '<span class="ml-track mastery"><i style="width:'+Math.round(100*a.posterior_after)+'%"></i></span></div>'+
    '<p class="muted-note">'+esc(a.model_version)+' · La estimación no equivale a una calificación.</p>'+
    '<div class="ml-actions"><button class="btn btn-soft" id="mlReviewNotes">Ver apuntes relacionados</button>'+
    '<button class="btn btn-outline" id="mlAskTutor">Pedir ayuda a NOVA</button>'+
    '<button class="btn btn-primary" id="mlNextQuestion">'+(q.phase==='diagnostic'?'Continuar diagnóstico':'Otra pregunta')+'</button></div></div>';
   $('mlReviewNotes').onclick=()=>{state.unit=q.unit;showTab('notes')};
   $('mlAskTutor').onclick=()=>{state.unit=q.unit;showTab('tutor');const input=$('mlTutorText');if(input){input.value=state.lang==='en'?'Explain the concept of question '+q.id:'Explícame el concepto que evalúa la pregunta '+q.id;input.focus()}};
   $('mlNextQuestion').onclick=async()=>{
    if(q.phase==='diagnostic'&&!p.diagnostic_complete)await nextQuestion('diagnostic');
    else if(q.phase==='diagnostic'){redraw();showPractice();message('Diagnóstico completado: puedes elegir tus temas.')}
    else await nextQuestion('practice')
   };
   if(window.say)window.say(a.correct?'Buen trabajo. Seguimos avanzando.':'Repasa la explicación de los apuntes y vuelve a intentarlo.');
   updateMath();
  }catch(err){const panel=$('mlFeedback');if(panel)panel.textContent=err.message;form.querySelectorAll('input,button').forEach(x=>x.disabled=false)}
 }
 function redraw(){
  const h=$('content');if(!h)return;h.innerHTML=header();attachShell()
 }
 async function showProgress(){
  const node=$('mlBody');if(!node)return;
  try{state.progress=await api('/api/micro/progress?course='+state.course)}catch(e){message(e.message,true);return}
  const p=state.progress;
  node.innerHTML='<section class="card"><h2>Seguimiento por área temática</h2><p>Se muestran por separado la participación académica y la probabilidad estimada de dominio.</p>'+
   '<div class="ml-progress-list">'+topics().map((name,i)=>{
    const u=i+1,x=progressFor(u),acc=x.accuracy===null?'Sin respuestas':x.accuracy+' %';
    return '<div class="ml-progress-item"><div class="between"><b>Tema '+u+'. '+esc(name)+'</b><span>'+Math.round(100*(x.mastery??.24))+' % · BKT</span></div>'+
    '<div class="ml-track mastery"><i style="width:'+Math.round(100*(x.mastery??.24))+'%"></i></div>'+
    '<small>Aciertos: '+acc+' · Respuestas: '+(x.attempts||0)+' · Visitas a apuntes: '+(x.notes_views||0)+' · Tiempo medio por ejercicio: '+(x.avg_seconds||0)+' s · Actividad: '+(x.participation_pct||0)+' %</small></div>'
   }).join('')+'</div><p class="ml-disclaimer">Una mayor duración no implica necesariamente mayor aprendizaje. Los tiempos se muestran como indicadores descriptivos y están limitados para evitar inflar las barras.</p></section>';
 }
 async function showNotes(){
  const node=$('mlBody');if(!node)return;
  const menu='<div class="ml-lesson-selector"><label for="mlNoteUnit">Apuntes del tema</label><select id="mlNoteUnit">'+topics().map((topic,i)=>'<option value="'+(i+1)+'">'+(i+1)+'. '+esc(topic)+'</option>').join('')+'</select></div>';
  node.innerHTML='<section class="card"><h2>Apuntes de '+esc(NAMES[state.course])+'</h2><p>Estos recursos se vinculan con la corrección de cada ejercicio y las respuestas de NOVA.</p>'+menu+'<div id="mlNotesContent"></div></section>';
  $('mlNoteUnit').value=state.unit;
  $('mlNoteUnit').onchange=e=>{stopNotes();state.unit=Number(e.target.value);loadNotes()};
  await loadNotes();
 }
 async function loadNotes(){
  const box=$('mlNotesContent');if(!box)return;
  box.innerHTML='<p class="muted">Consultando apuntes…</p>';
  try{
   const d=await api('/api/micro/lesson?'+new URLSearchParams({course:state.course,unit:String(state.unit),lang:state.lang}));
   box.innerHTML='<h3>'+esc(d.title)+'</h3>'+d.sections.map((section,i)=>
    '<details class="ml-note-section" '+(i===0?'open':'')+'><summary>'+esc(section.heading)+'</summary>'+
    (section.parts||[]).map(part=>'<div class="ml-note-part '+esc(part.type)+'">'+esc(part.text)+
    (part.figure_id?'<figure class="micro-figure"><img loading="lazy" src="/api/micro/figure/'+encodeURIComponent(part.figure_id)+'" alt="Figura de los apuntes"></figure>':'')+'</div>').join('')+'</details>').join('');
   const visit=await api('/api/micro/notes/view',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({course:state.course,unit:state.unit,kind:'lesson',seconds:0})});
   if(visit.view_id){state.noteId=visit.view_id;state.noteSince=performance.now();state.noteTimer=setInterval(syncNotes,12500)}
   refreshMeters();
   updateMath();
  }catch(e){box.innerHTML='<p class="error-text">'+esc(e.message)+'</p>'}
 }
 async function syncNotes(){
  if(!state.noteId)return;
  const seconds=Math.max(0,(performance.now()-state.noteSince)/1000);
  const id=state.noteId;
  try{await api('/api/micro/notes/duration/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({seconds})})}catch(e){}
 }
 function stopNotes(){
  if(state.noteId)syncNotes();
  clearInterval(state.noteTimer);state.noteTimer=null;state.noteId=null;
 }
 function showTutor(){
  const node=$('mlBody');if(!node)return;
  node.innerHTML='<section class="card ml-tutor"><div class="between"><div><h2>NOVA · Tutor vinculado a tus apuntes</h2><p class="muted">Formula preguntas sobre el contenido del tema. Las explicaciones se recuperan de los materiales que ha cargado el docente.</p></div><span class="ml-nova-face" aria-hidden="true">N</span></div>'+
   '<label for="mlTutorUnit">Tema</label><select id="mlTutorUnit">'+topics().map((topic,i)=>'<option value="'+(i+1)+'">'+(i+1)+'. '+esc(topic)+'</option>').join('')+'</select>'+
   '<div id="mlChatLog" class="ml-chat-log" aria-live="polite"></div>'+
   '<form id="mlTutorForm"><label for="mlTutorText">¿Qué te gustaría comprender mejor?</label><textarea id="mlTutorText" maxlength="500" rows="3" placeholder="Ej.: ¿Por qué cambia la elasticidad cuando sube el precio?"></textarea>'+
   '<div class="ml-actions"><button class="btn btn-primary" type="submit">Preguntar a NOVA</button>'+
   '<label class="ml-voice"><input type="checkbox" id="mlVoiceOpt"> Leer respuesta en voz alta</label></div></form>'+
   '<p class="ml-disclaimer">NOVA usa recuperación local de pasajes de los apuntes; no aprende de forma autónoma ni sustituye la supervisión docente. La voz neuronal requiere configurar un proveedor externo.</p></section>';
  $('mlTutorUnit').value=state.unit;
  $('mlTutorUnit').onchange=e=>state.unit=Number(e.target.value);
  const choice=$('mlVoiceOpt');
  choice.checked=localStorage.getItem('mlVoiceOpt')==='yes';
  choice.onchange=()=>localStorage.setItem('mlVoiceOpt',choice.checked?'yes':'no');
  $('mlTutorForm').onsubmit=askTutor;
  renderChat()
 }
 function renderChat(){
  const box=$('mlChatLog');if(!box)return;
  box.innerHTML=state.chat.length?state.chat.slice(-16).map(m=>
   '<div class="ml-message '+(m.user?'student':'nova')+'"><strong>'+(m.user?'Tú':'NOVA')+'</strong><p>'+esc(m.text)+'</p>'+
   (m.source?'<small>Fuente: '+esc(m.source)+(m.section?' · '+esc(m.section):'')+'</small>':'')+'</div>').join(''):
   '<div class="ml-message nova"><strong>NOVA</strong><p>Cuando necesites ayuda, podré localizar una explicación del tema en tus apuntes y sugerirte qué repasar.</p></div>';
  box.scrollTop=box.scrollHeight;
  updateMath();
 }
 async function askTutor(e){
  e.preventDefault();const input=$('mlTutorText'),btn=$('mlTutorForm')?.querySelector('button[type=submit]');
  const msg=input.value.trim();if(msg.length<3)return;
  state.chat.push({user:true,text:msg});input.value='';renderChat();btn.disabled=true;
  try{
   const out=await api('/api/micro/tutor',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({course:state.course,unit:state.unit,text:msg,lang:state.lang})});
   const answer=out.answer+(out.suggestion?'\n\n'+out.suggestion:'');
   state.chat.push({user:false,text:answer,source:out.source,section:out.section});
   renderChat();
   if($('mlVoiceOpt')?.checked && typeof speak==='function')speak(answer.replace(/\\[a-z]+/g,' ').slice(0,1000));
   const n=$('mentorSpeech');if(n)n.textContent=answer.slice(0,140);
   const figure=out.figure_id;const log=$('mlChatLog');
   if(figure&&log){const p=document.createElement('p');p.className='micro-figure';const img=document.createElement('img');img.alt='Gráfico de los apuntes';img.src='/api/micro/figure/'+encodeURIComponent(figure);p.appendChild(img);log.appendChild(p)}
   refreshMeters();
  }catch(err){state.chat.push({user:false,text:'No he podido consultar los apuntes: '+err.message});renderChat()}
  finally{btn.disabled=false}
 }
 async function refreshMeters(){
  try{state.progress=await api('/api/micro/progress?course='+state.course);
   const old=document.querySelector('.ml-summary');if(old){
    const temp=document.createElement('div');temp.innerHTML=badges();
    const nodes=temp.querySelector('.ml-summary');if(nodes)old.replaceWith(nodes);
   }}catch(e){}
 }
 function mentorClick(e){
  if(!['micro1','micro2'].includes(typeof page==='string'?page:''))return;
  e.stopImmediatePropagation();e.preventDefault();showTab('tutor');
 }
 document.addEventListener('DOMContentLoaded',()=>{
  $('mentorToggle')?.addEventListener('click',mentorClick,true);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)syncNotes()});
  window.addEventListener('pagehide',()=>syncNotes());
 });
 async function drawCourse(c){
  stopNotes();clearInterval(state.interval);
  state.course=c;state.lang=document.documentElement.lang==='en'?'en':'es';
  state.unit=1;state.kind='';state.tab='practice';state.question=null;state.selected=new Set([1]);state.chat=[];
  const root=$('content');if(!root)return;
  root.innerHTML='<section class="card"><p>Cargando el curso…</p></section>';
  try{
   [state.catalog,state.progress]=await Promise.all([api('/api/micro/catalog'),api('/api/micro/progress?course='+c)]);
   redraw();showTab('practice');
  }catch(e){root.innerHTML='<section class="card"><h2>'+esc(NAMES[c])+'</h2><p class="error-text">'+esc(e.message)+'</p><button class="btn" id="mlGoBack">Volver</button></section>';if($('mlGoBack'))$('mlGoBack').onclick=()=>navigate('courses')}
 }
 window.drawMicroCourse=drawCourse;
})();