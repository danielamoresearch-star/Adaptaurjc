'use strict';
/* MICRO ADAPTA-ITS curricular interface. Full content is teacher-sourced. */
(function(){
 const COURSE_LABELS={micro1:'Microeconomía I',micro2:'Microeconomía II'};
 const COURSE_DESC={micro1:'Decisiones de consumo, precios y mercados',micro2:'Producción, costes y decisiones de la empresa'};
 const MODE_LABELS={teorica:'Teoría',rapida:'Cálculo rápido',grafica:'Interpretación gráfica',noticia:'Noticia económica',caso:'Caso de estudio'};
 let course='micro1',unit=1,modality='',current=null,started=0,language='es',catalog=null;
 const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
 const lessonPart=p=>'<div class="micro-lesson-part '+esc(p.type)+'">'+esc(p.text)+(p.figure_id?'<figure class="micro-figure"><img loading="lazy" src="/api/micro/figure/'+encodeURIComponent(p.figure_id)+'" alt="'+esc(p.text)+'"></figure>':'')+'</div>';
 const el=id=>document.getElementById(id);
 const parseJSON=async r=>{let d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:('Error HTTP '+r.status));return d};
 async function call(url,options={}){return parseJSON(await fetch(url,{...options,headers:{...options.headers,Authorization:'Bearer '+token}}))}
 const getLang=()=>document.documentElement.lang==='en'?'en':'es';
 const theme=c=>COURSE_LABELS[c]||'Microeconomía';
 function status(msg){const n=el('microStatus');if(n)n.textContent=msg}
 function host(){return el('content')}
 function navButtons(){
  const side=document.querySelector('.side-nav');
  if(side&&!side.querySelector('[data-page="courses"]')){
   const a=document.createElement('button');a.dataset.page='courses';a.innerHTML='<span aria-hidden="true">▦</span> Mis asignaturas';
   side.prepend(a);
   const b=document.createElement('button');b.dataset.page='micro1';b.innerHTML='<span aria-hidden="true">I</span> Microeconomía I';
   const c=document.createElement('button');c.dataset.page='micro2';c.innerHTML='<span aria-hidden="true">II</span> Microeconomía II';
   a.after(b,c);
   for(const n of [a,b,c])n.onclick=()=>navigate(n.dataset.page);
  }
  const dock=document.querySelector('.mobile-dock');
  if(dock&&!dock.querySelector('[data-page="courses"]')){
   const b=document.createElement('button');b.dataset.page='courses';
   b.innerHTML='<span aria-hidden="true">▦</span><small>Asignaturas</small>';
   dock.prepend(b);b.onclick=()=>navigate('courses');
  }
 }
 function courseTiles(){return '<div class="micro-tiles">'+['micro1','micro2'].map(c=>
  '<button class="micro-course-card '+c+'" data-course="'+c+'"><span class="micro-icon">'+(c==='micro1'?'I':'II')+'</span><span><b>'+esc(theme(c))+'</b><small>'+esc(COURSE_DESC[c])+'</small></span><span aria-hidden="true">→</span></button>').join('')+'</div>'}
 async function drawCourses(){
  const root=host();if(!root)return;
  root.innerHTML='<div class="eyebrow">MICRO ADAPTA-ITS</div><h1>Selecciona tu asignatura</h1><p class="muted">Microeconomía I y II tienen temarios, material de estudio y seguimiento diferenciados.</p>'+courseTiles()+'<div id="microStatus" class="muted-note">Cargando disponibilidad de materiales…</div><div class="card"><h2>Materiales y evaluación</h2><p>Los apuntes se organizan por temas y las soluciones completas se muestran después de responder. Los identificadores originales se conservan para facilitar la revisión.</p></div>';
  root.querySelectorAll('[data-course]').forEach(x=>x.onclick=()=>navigate(x.dataset.course));
  try{catalog=await call('/api/micro/catalog');status('Microeconomía I: '+(catalog.question_counts.micro1||0)+' preguntas publicadas; Microeconomía II: '+(catalog.question_counts.micro2||0)+' preguntas publicadas.')}catch(e){status(e.message)}
 }
 async function drawCourse(c){
  course=c;language=getLang();unit=1;modality='';current=null;
  const root=host();if(!root)return;
  root.innerHTML='<div class="eyebrow">MICRO ADAPTA-ITS · 2026–27</div><div class="between"><div><h1>'+esc(theme(course))+'</h1><p class="muted">'+esc(COURSE_DESC[course])+'</p></div><button class="btn btn-outline" id="microBack">Todas las asignaturas</button></div><div id="microStatus" class="muted-note">Cargando contenido…</div><div id="microUnits"></div><div id="microPanel" class="micro-panel card"></div>';
  el('microBack').onclick=()=>navigate('courses');
  try{
   catalog=await call('/api/micro/catalog');
   const topics=catalog.curriculum[course][language]||catalog.curriculum[course].es;
   const progress=await call('/api/micro/progress?course='+course);
   const box=el('microUnits');
   if(!box)return;
   box.innerHTML='<div class="micro-unit-grid">'+topics.map((t,i)=>{const p=progress.units[String(i+1)]||{attempts:0,correct:0};return '<button class="micro-unit" data-unit="'+(i+1)+'"><small>Tema '+(i+1)+'</small><b>'+esc(t)+'</b><span>'+p.attempts+' respuestas · '+(p.attempts?Math.round(100*p.correct/p.attempts):0)+' % aciertos</span></button>'}).join('')+'</div>';
   box.querySelectorAll('[data-unit]').forEach(x=>x.onclick=()=>{unit=Number(x.dataset.unit);openUnit()});
   status('Banco: '+(catalog.question_counts[course]||0)+' preguntas · Materiales: '+(catalog.lesson_counts[course]?.[language]||0)+' temas');
   openUnit();
  }catch(e){status(e.message)}
 }
 function openUnit(){
  const panel=el('microPanel');if(!panel)return;
  el('microUnits')?.querySelectorAll('[data-unit]').forEach(x=>x.classList.toggle('selected',Number(x.dataset.unit)===unit));
  const title=catalog?.curriculum?.[course]?.[language]?.[unit-1]||('Tema '+unit);
  panel.innerHTML='<h2>'+esc(title)+'</h2><p class="muted">Selecciona una actividad. La práctica mantiene el registro de intentos independiente por asignatura.</p><div class="micro-actions"><button class="btn btn-primary" id="microPractice">Practicar preguntas</button><button class="btn btn-soft" id="microRead">Consultar apuntes</button><button class="btn btn-outline" id="microExtra">Recursos y prácticas complementarias</button></div><div id="microSlot"></div>';
  el('microPractice').onclick=()=>practiceSettings();
  el('microRead').onclick=()=>loadLesson();el('microExtra').onclick=loadSupplementary;
 }
 function practiceSettings(){
  current=null;const slot=el('microSlot');if(!slot)return;
  slot.innerHTML='<div class="micro-settings"><label for="microMode">Modalidad de pregunta</label><select id="microMode"><option value="">Todas (aleatorias)</option>'+
  Object.entries(MODE_LABELS).map(([k,v])=>'<option value="'+k+'">'+esc(v)+'</option>').join('')+'</select><button class="btn btn-primary" id="microNext">Nueva pregunta aleatoria</button></div><div id="microQuestion"></div>';
  el('microMode').value=modality;el('microMode').onchange=e=>{modality=e.target.value};
  el('microNext').onclick=loadQuestion;
 }
 async function loadQuestion(){
  const box=el('microQuestion');if(!box)return;
  box.innerHTML='<p class="muted">Preparando ejercicio…</p>';
  try{
   const params=new URLSearchParams({course,unit:String(unit),modality,lang:language});
   const data=await call('/api/micro/next?'+params);
   if(!data.available){box.innerHTML='<div class="guide"><p>'+esc(data.message)+'</p></div>';return}
   current=data;started=performance.now();
   box.innerHTML='<article class="micro-question"><div class="between"><span class="pill">'+esc(data.id)+'</span><span class="pill neutral">'+esc(MODE_LABELS[data.modality]||data.modality)+'</span></div><h3>'+esc(data.prompt)+'</h3>'+
    (data.figure_id?'<figure class="micro-figure"><img src="/api/micro/figure/'+encodeURIComponent(data.figure_id)+'" alt="Figura económica correspondiente al ejercicio"></figure>':'')+
    '<form id="microAnswerForm">'+data.options.map((opt,i)=>'<label class="micro-answer"><input type="radio" name="microAnswer" value="'+i+'" required><span>'+String.fromCharCode(65+i)+'. '+esc(opt)+'</span></label>').join('')+'<button class="btn btn-primary" type="submit">Comprobar respuesta</button></form><div id="microFeedback"></div></article>';
   el('microAnswerForm').onsubmit=submit;
   window.adaptaTypeset?.();
  }catch(e){box.innerHTML='<p class="error-text">'+esc(e.message)+'</p>'}
 }
 async function submit(e){
  e.preventDefault();if(!current)return;
  const form=el('microAnswerForm');const chosen=form?.querySelector('input[name="microAnswer"]:checked');
  if(!chosen)return;
  form.querySelectorAll('input,button').forEach(n=>n.disabled=true);
  const elapsed=Math.round((performance.now()-started)/1000);
  try{
   const result=await call('/api/micro/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:current.token,answer:Number(chosen.value),elapsed_sec:elapsed})});
   const fb=el('microFeedback');
   if(fb){fb.innerHTML='<div class="micro-feedback '+(result.correct?'ok':'retry')+'"><h3>'+(result.correct?'Respuesta correcta':'Revisa tu razonamiento')+'</h3><p><b>Opción correcta:</b> '+esc(String.fromCharCode(65+result.answer))+'. '+esc(result.answer_text)+'</p><div class="micro-explanation">'+esc(result.explanation).replace(/\n/g,'\n')+'</div><button class="btn btn-soft" id="microContinue">Siguiente pregunta</button></div>';
    el('microContinue').onclick=loadQuestion;
    window.adaptaTypeset?.();}
  }catch(err){const fb=el('microFeedback');if(fb)fb.textContent=err.message}
 }
 async function loadLesson(){
  const slot=el('microSlot');if(!slot)return;
  slot.innerHTML='<div class="muted-note">Cargando apuntes…</div>';
  try{
   const d=await call('/api/micro/lesson?'+new URLSearchParams({course,unit:String(unit),lang:language}));
   const htmlParts=d.sections.map((s,i)=>'<details class="micro-lesson-section" '+(i===0?'open':'')+'><summary>'+esc(s.heading)+'</summary>'+s.parts.map(p=>lessonPart(p)).join('')+'</details>').join('');
   slot.innerHTML='<div class="micro-lesson"><h3>'+esc(d.title)+'</h3><p class="muted-note">Apuntes de referencia del curso. Las ecuaciones están expresadas en LaTeX.</p>'+htmlParts+'</div>';window.adaptaTypeset?.();
  }catch(err){slot.innerHTML='<p class="muted-note">'+esc(err.message)+'</p>'}
 }
 async function loadSupplementary(){
  const slot=el('microSlot');if(!slot)return;
  slot.innerHTML='<div class="muted-note">Cargando recursos complementarios…</div>';
  try{
   const data=await call('/api/micro/supplementary?'+new URLSearchParams({course,lang:language}));
   const resources=data.resources||[];
   slot.innerHTML='<div class="micro-lesson"><label for="microExtraSelect"><b>Selecciona un recurso de estudio</b></label><select id="microExtraSelect">'+resources.map((r,i)=>'<option value="'+i+'">'+esc(r.title)+'</option>').join('')+'</select><div id="microExtraText"></div></div>';
   const draw=()=>{
    const r=resources[Number(el('microExtraSelect').value)],box=el('microExtraText');if(!r||!box)return;
    box.innerHTML='<h3>'+esc(r.title)+'</h3>'+r.sections.map((section,i)=>'<details class="micro-lesson-section" '+(i===0?'open':'')+'><summary>'+esc(section.heading)+'</summary>'+section.parts.map(part=>lessonPart(part)).join('')+'</details>').join('');
    window.adaptaTypeset?.();
   };
   el('microExtraSelect').onchange=draw;draw();
  }catch(e){slot.innerHTML='<p class="muted-note">'+esc(e.message)+'</p>'}
 }
 async function teacherPanel(){
  const root=el('teacherContent');if(!root||root.querySelector('#microTeacherPackage'))return;
  const sec=document.createElement('section');sec.className='card elevate';sec.id='microTeacherPackage';
  sec.innerHTML='<h2>MICRO ADAPTA-ITS · Materiales de Microeconomía I y II</h2><p>Importa el paquete curricular: 5.000 preguntas originales de Microeconomía I con solucionarios y figuras, 5.000 variantes paramétricas de Microeconomía II (requieren revisión docente), y apuntes bilingües de ambas asignaturas.</p><p class="muted-note">El archivo ZIP se carga únicamente desde la cuenta docente. Es posible volver a importarlo para actualizar contenidos; antes de sustituir material de una investigación en curso, conserva una copia de seguridad.</p><input id="microPackageInput" type="file" accept=".zip"><button id="microPackageUpload" class="btn btn-primary" type="button">Importar paquete curricular</button><button id="microCourseCsv" class="btn btn-outline" type="button">Exportar resultados Micro I/II (CSV)</button><button id="microBackupDb" class="btn btn-outline" type="button">Descargar copia de seguridad</button><button id="microValidateModels" class="btn btn-soft" type="button">Auditar modelo bayesiano y neuronal</button><div id="microValidationStatus" class="muted-note" role="status"></div><div id="microStorageStatus" class="muted-note" role="status">Verificando la persistencia de los datos…</div><div id="microPackageStatus" role="status"></div>';
  root.appendChild(sec);
  try{
   const data=await call('/api/micro/teacher/storage');
   const message=data.persistent_disk_verified?'Disco persistente detectado. Tamaño de la base de datos: '+data.database_size_mb+' MB.':
    'AVISO: almacenamiento persistente no verificado. Descarga copias de seguridad y configura un disco persistente en Render antes de recopilar datos reales.';
   const status=el('microStorageStatus');if(status){status.textContent=message;status.classList.toggle('error-text',!data.persistent_disk_verified)}
  }catch(err){const status=el('microStorageStatus');if(status)status.textContent='No se ha podido comprobar el almacenamiento: '+err.message}
  el('microValidateModels').onclick=async()=>{
   const box=el('microValidationStatus');box.textContent='Contrastando predicción BKT y MLP en estudiantes reservados para validación…';
   try{
    const data=await call('/api/micro/teacher/model-validation');
    box.textContent=data.reports.map(r=>{
     const course=r.course==='micro1'?'Micro I':'Micro II';
     if(!r.models)return course+': '+r.observations+' respuestas de '+r.students+' estudiantes; muestra insuficiente para validar la red.';
     return course+': '+r.recommended_model+'; Brier BKT '+r.models.BKT.brier+', Brier MLP '+r.models.MLP_16_8.brier+'; n de validación '+r.held_out_observations+'.';
    }).join(' | ')+' Las métricas predictivas no demuestran una mejora causal del rendimiento.';
   }catch(e){box.textContent='No se ha podido validar: '+e.message}
  };
  el('microBackupDb').onclick=async()=>{
   try{
    const r=await fetch('/api/micro/teacher/backup.sqlite3',{headers:{Authorization:'Bearer '+token},cache:'no-store'});
    if(!r.ok)throw Error('No se pudo realizar el respaldo.');
    const blob=await r.blob();const u=URL.createObjectURL(blob);const a=document.createElement('a');
    a.href=u;a.download='MICRO_ADAPTA_ITS_respaldo.sqlite3';document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(u),2000);
   }catch(err){const x=el('microStorageStatus');if(x)x.textContent=err.message}
  };
  el('microCourseCsv').onclick=async()=>{
   try{
    const r=await fetch('/api/micro/teacher/export',{headers:{Authorization:'Bearer '+token}});
    if(!r.ok)throw Error('Error de exportación');
    const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=url;a.download='MICRO_ADAPTA_ITS_datos_asignaturas.csv';document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1500);
   }catch(err){el('microPackageStatus').textContent=err.message}
  };
  el('microPackageUpload').onclick=async()=>{
   const f=el('microPackageInput').files[0],b=el('microPackageUpload'),dest=el('microPackageStatus');
   if(!f)return dest.textContent='Selecciona el archivo ZIP de contenidos.';
   if(f.size>12*1024*1024)return dest.textContent='El archivo supera los 12 MB.';
   b.disabled=true;dest.textContent='Validando corpus, claves y documentos…';
   try{
    const form=new FormData();form.append('file',f);
    const data=await call('/api/micro/import',{method:'POST',body:form});
    dest.textContent='Importados '+data.imported_questions+' ejercicios ('+JSON.stringify(data.imported_by_course||{})+'), '+data.figures+' figuras y '+data.lesson_units+' unidades bilingües y '+(data.supplementary_languages||0)+' colecciones complementarias. Los ejercicios paramétricos de Micro II requieren revisión docente.';
   }catch(e){dest.textContent=e.message}finally{b.disabled=false}
  };
 }
 function watchTeacher(){
  const target=el('teacherContent');if(!target)return;
  new MutationObserver(()=>{if(!el('teacher')?.hidden&&!el('microTeacherPackage'))teacherPanel()}).observe(target,{childList:true});
 }
 window.drawMicroCourses=drawCourses;
 window.drawMicroCourse=drawCourse;
 document.addEventListener('DOMContentLoaded',()=>{navButtons();watchTeacher()});
})();