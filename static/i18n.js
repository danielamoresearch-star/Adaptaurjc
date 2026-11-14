'use strict';
/* UI localization. Spanish is canonical; the English dictionary covers authored UI.
   Parametric exercises are translated with deterministic patterns in the question view.
   Unmatched academic text stays in Spanish rather than being mistranslated. */
(function(){
 const pairs=[
 ['Campus de aprendizaje adaptativo','Adaptive learning campus'],
 ['Aprende a tu ritmo.','Learn at your own pace.'],
 ['Tu espacio personal de Microeconomía I. Cada ejercicio te ayuda a comprender mejor, no solo a memorizar.','Your personal Microeconomics I learning space. Every exercise helps you understand, not just memorize.'],
 ['Soy estudiante','I am a student'],['Soy docente','I am a teacher'],['Código de estudiante','Student code'],
 ['Contraseña personal','Personal password'],['Contraseña docente','Teacher password'],
 ['Invitación (solo al activar tu cuenta)','Invitation (first account activation only)'],
 ['Acceder a ADAPTA','Sign in to ADAPTA'],
 ['Prototipo de investigación independiente. No es una aplicación oficial de la URJC.','Independent research prototype. Not an official URJC application.'],
 ['MI ESPACIO','MY SPACE'],['Mi progreso','My progress'],['Diagnóstico','Diagnostic'],
 ['Practicar','Practice'],['Tutor personal','Personal tutor'],['Investigación','Research'],
 ['Cerrar sesión','Sign out'],['Inicio','Home'],['Evaluar','Assess'],['Datos','Data'],
 ['Conectado','Connected'],['Sin conexión','Offline'],
 ['Tu aprendizaje importa','Your learning matters'],['Avanza con constancia, sin prisas.','Make steady progress at your own pace.'],
 ['Microeconomía I','Microeconomics I'],['DOCENCIA','TEACHING'],
 ['Exámenes','Exams'],['Configurar exámenes','Configure exams'],['Exámenes inteligentes','Intelligent exams'],
 ['Crear examen docente','Create teacher exam'],['Crear autoevaluación','Create self-assessment'],
 ['Selecciona los temas','Select topics'],['Modalidades','Question types'],['Preguntas','Questions'],
 ['Duración (minutos)','Duration (minutes)'],['Teoría y test','Theory and multiple choice'],
 ['Interpretación gráfica','Graph interpretation'],['Problemas numéricos','Numerical problems'],
 ['Noticias económicas documentadas','Documented economic news'],
 ['Ajustar la dificultad al dominio previo del estudiante','Adapt difficulty to the student’s prior mastery'],
 ['Publicar para los estudiantes','Publish for students'],['Guardar examen','Save exam'],
 ['Exámenes disponibles','Available exams'],['Aún no hay exámenes creados.','No exams created yet.'],
 ['Comenzar o continuar','Start or continue'],['Publicado','Published'],['Privado','Private'],
 ['Dificultad adaptativa','Adaptive difficulty'],['Dificultad común','Common difficulty'],
 ['Entregar examen','Submit exam'],['Anterior','Previous'],['Siguiente','Next'],
 ['Respuesta guardada','Answer saved'],['Las respuestas se guardan en el servidor.','Answers are saved on the server.'],
 ['Volver a exámenes','Back to exams'],['Examen ya entregado','Exam already submitted'],
 ['Calificación','Grade'],['Correcta','Correct'],['Incorrecta','Incorrect'],
 ['Evaluación inicial','Initial assessment'],['APRENDIZAJE ADAPTATIVO','ADAPTIVE LEARNING'],
 ['Descubramos qué sabes.','Let’s find out what you know.'],
 ['Practica con sentido.','Practice with purpose.'],['Comenzar diagnóstico','Start diagnostic'],
 ['Comenzar práctica','Start practice'],['Preparar siguiente ejercicio','Prepare next exercise'],
 ['Filtrar ejercicios','Filter exercises'],['Competencia','Topic'],['Tipo de ejercicio','Question type'],
 ['Restablecer','Reset'],['Todas (recomendado)','All (recommended)'],
 ['Todos (recomendado)','All (recommended)'],['Cálculo numérico','Numerical calculation'],
 ['Problema de desarrollo','Open-ended problem'],['Conceptos y casos (test)','Concepts and cases (multiple choice)'],
 ['Oferta y demanda','Supply and demand'],['Elasticidad','Elasticity'],
 ['Teoría del consumidor','Consumer theory'],['Producción y costes','Production and costs'],
 ['Competencia perfecta','Perfect competition'],['Monopolio','Monopoly'],
 ['Oligopolios','Oligopoly'],['Competencia monopolística','Monopolistic competition'],
 ['Teoría de juegos','Game theory'],['Estudiante','Student'],['Grupo','Group'],
 ['Profesor','Teacher'],['Titulación','Degree'],['Respuestas','Answers'],
 ['Tiempo','Time'],['Aprendizaje','Learning'],['Incorporar noticia económica','Add economic news'],
 ['Registrar noticia revisada','Register reviewed news'],
 ['¡Hola! Estoy aquí para ayudarte a entender cada concepto.','Hello! I am here to help you understand every concept.'],
 ['Saltar al contenido principal','Skip to main content'],
 ['Sin conexión. Conserva tus respuestas: el envío requiere conexión al servidor.','Offline. Keep your answers: submitting requires a server connection.']
 ];
 const exact=new Map(pairs),reverse=new Map(pairs.map(([a,b])=>[b,a]));
 const patterns=[
 [/^En el mercado Qd=(.+) Calcula el precio de equilibrio\.$/,m=>'In the market Qd='+m[1]+' Calculate the equilibrium price.'],
 [/^Si el precio cae un (.+) calcula el valor absoluto de la elasticidad arco aproximada \(cociente de variaciones porcentuales\)\.$/,m=>'If price falls by '+m[1]+' calculate the absolute approximate price elasticity (ratio of percentage changes).'],
 [/^Un consumidor tiene renta (.+) Si solo compra X, ¿cuántas unidades adquiere\?$/,m=>'A consumer has income '+m[1]+' If they buy only X, how many units do they purchase?'],
 [/^Una empresa tiene CT\(Q\)=(.+) Calcula el coste marginal cuando Q=(.+)\.$/,m=>'A firm has TC(Q)='+m[1]+' Calculate marginal cost when Q='+m[2]+'.'],
 [/^En competencia perfecta (.+) Calcula Q óptima interior\.$/,m=>'Under perfect competition '+m[1]+' Calculate the interior optimal output Q.'],
 [/^Un monopolista enfrenta (.+) Calcula Q óptima interior\.$/,m=>'A monopolist faces '+m[1]+' Calculate the interior optimal output Q.'],
 [/^Duopolio Cournot: (.+) Calcula la producción de cada empresa en equilibrio simétrico\.$/,m=>'Cournot duopoly: '+m[1]+' Calculate each firm’s output in symmetric equilibrium.'],
 [/^Una empresa diferenciada tiene (.+) Calcula la producción que maximiza beneficio a corto plazo\.$/,m=>'A differentiated firm has '+m[1]+' Calculate the short-run profit-maximizing output.'],
 [/^Juego simultáneo de dos empresas\. (.+) Si B coopera, ¿cuál es el beneficio de A al cooperar\?$/,m=>'Simultaneous game between two firms. '+m[1]+' If B cooperates, what is A’s payoff from cooperating?']
 ];
 const fragments=[
 ['Calcula el precio de equilibrio','Calculate the equilibrium price'],
 ['Calcula el coste marginal','Calculate marginal cost'],
 ['Calcula Q óptima interior','Calculate the interior optimal Q'],
 ['Calcula la producción','Calculate the output'],
 ['costes marginales iguales a','marginal costs equal to'],
 ['coste marginal constante','constant marginal cost'],
 ['y precio','and price'],['y el precio cubre','and the price covers'],
 ['tiene demanda','has demand'],['tiene renta','has income'],
 ['precio Px','price Px'],['beneficio de cooperar','payoff from cooperating'],
 ['beneficio de competir','payoff from competing'],
 ['si B coopera','if B cooperates'],['si B compite','if B competes'],
 ['si B coopera y','if B cooperates and'],['si B compite;','if B competes;'],
 ['El equilibrio','Equilibrium'],['Igualando','Equating'],['implica','implies'],
 ['en valor absoluto','in absolute value'],['sustituye','substitute'],
 ['Identifica la función relevante, sustituye los datos y verifica el resultado.','Identify the relevant function, substitute the data, and verify your result.']
 ];
 let lang=localStorage.getItem('adapta_lang')==='en'?'en':'es',busy=false;
 function translate(raw){
   if(exact.has(raw))return exact.get(raw);
   let t=raw;
   for(const [re,fn] of patterns){const m=t.match(re);if(m)return fn(m)}
   for(const [a,b] of fragments)t=t.split(a).join(b);
   return t;
 }
 function apply(root=document){
   if(busy)return;busy=true;
   try{
    document.documentElement.lang=lang;
    document.querySelectorAll('[data-lang]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.lang===lang));b.classList.toggle('selected',b.dataset.lang===lang)});
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    let n;while(n=walker.nextNode()){
      if(!n.parentElement||n.parentElement.closest('script,style,textarea,code,pre'))continue;
      const t=n.nodeValue,trim=t.trim();if(!trim)continue;
      if(lang==='en'){const next=translate(trim);if(next!==trim)n.nodeValue=t.replace(trim,next)}
      else if(reverse.has(trim))n.nodeValue=t.replace(trim,reverse.get(trim));
    }
    root.querySelectorAll?.('input[placeholder],textarea[placeholder]').forEach(el=>{let v=el.getAttribute('placeholder');if(lang==='en'&&exact.has(v))el.placeholder=exact.get(v);else if(lang==='es'&&reverse.has(v))el.placeholder=reverse.get(v)});
   }finally{busy=false}
 }
 function setLang(next){if(next!=='es'&&next!=='en')return;lang=next;localStorage.setItem('adapta_lang',lang);document.documentElement.lang=lang;
   // Restore Spanish source by re-rendering active page; avoid modifying answers or restarting timers.
   window.location.reload();
 }
 document.addEventListener('click',e=>{const b=e.target.closest('[data-lang]');if(b){e.preventDefault();setLang(b.dataset.lang)}});
 const observer=new MutationObserver(()=>{if(!busy)apply(document)});
 document.addEventListener('DOMContentLoaded',()=>{apply(document);observer.observe(document.body,{subtree:true,childList:true,characterData:true})});
 window.adaptaLanguage={get:()=>lang,set:setLang,apply:()=>apply(document),translate};
})();
