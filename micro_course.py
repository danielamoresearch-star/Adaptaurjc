"""MICRO ADAPTA-ITS: separate curricular courses with auditable teacher-imported content.
The supplied course archive is imported only by an authenticated teacher. A missing
archive is reported as missing content rather than silently replaced by synthetic items.
"""
import io,json,csv,random,secrets,zipfile,re,math
from datetime import datetime
from collections import Counter
from xml.etree import ElementTree
from fastapi import File,UploadFile,Header,HTTPException,Query
from fastapi.responses import Response,StreamingResponse
from pydantic import BaseModel,Field
from micro_intelligence import PRIOR, bayesian_update, model_features, posterior_update, grounded_tutor

CURRICULUM={
 'micro1':{
  'es':['Elementos básicos de la oferta y la demanda','La conducta de los consumidores','La demanda del consumidor y del mercado'],
  'en':['The Basics of Supply and Demand','Consumer Behaviour','Consumer and Market Demand']},
 'micro2':{
  'es':['La función de producción','Los costes de la empresa','Los mercados competitivos','La competencia imperfecta'],
  'en':['The Production Function','Firm Costs','Competitive Markets','Imperfect Competition']}
}
MODALITIES=['teorica','rapida','grafica','noticia','caso']
MAX_UPLOAD=12*1024*1024
MAX_UNCOMPRESSED=60*1024*1024

def register(app,db,auth,iso,utc):
 with db() as c:
  c.executescript("""
  CREATE TABLE IF NOT EXISTS micro_bank(
   id TEXT PRIMARY KEY,course TEXT NOT NULL,unit INTEGER NOT NULL,
   modality TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
  CREATE INDEX IF NOT EXISTS idx_micro_course_unit ON micro_bank(course,unit);
  CREATE TABLE IF NOT EXISTS micro_figures(
   id TEXT PRIMARY KEY,svg TEXT NOT NULL,caption TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS micro_supplementary(
   course TEXT NOT NULL,lang TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(course,lang));
  CREATE TABLE IF NOT EXISTS micro_lessons(
   course TEXT NOT NULL,lang TEXT NOT NULL,unit INTEGER NOT NULL,payload TEXT NOT NULL,
   PRIMARY KEY(course,lang,unit));
  CREATE TABLE IF NOT EXISTS micro_activities(
   token TEXT PRIMARY KEY,student_id INTEGER NOT NULL,course TEXT NOT NULL,
   question_id TEXT NOT NULL,started_at TEXT NOT NULL,answer INTEGER,
   finished_at TEXT,correct INTEGER,elapsed_sec REAL,lang TEXT NOT NULL);
  CREATE INDEX IF NOT EXISTS idx_micro_student_course ON micro_activities(student_id,course);
  """)
  cols={r['name'] for r in c.execute('PRAGMA table_info(micro_activities)')}
  for column,sqltype in (
   ('selection_policy',"TEXT NOT NULL DEFAULT 'random-v1'"),
   ('phase',"TEXT NOT NULL DEFAULT 'practice'"),
   ('p_before','REAL'),('p_after','REAL'),('model_version','TEXT'),('features_json','TEXT')):
   if column not in cols:c.execute("ALTER TABLE micro_activities ADD COLUMN "+column+" "+sqltype)
  c.executescript("""
   CREATE TABLE IF NOT EXISTS micro_mastery(
    student_id INTEGER NOT NULL,course TEXT NOT NULL,unit INTEGER NOT NULL,
    posterior REAL NOT NULL,updated_at TEXT NOT NULL,
    PRIMARY KEY(student_id,course,unit));
   CREATE TABLE IF NOT EXISTS micro_notes_views(
    id INTEGER PRIMARY KEY AUTOINCREMENT,student_id INTEGER NOT NULL,
    course TEXT NOT NULL,unit INTEGER NOT NULL,kind TEXT NOT NULL,
    seconds REAL NOT NULL,viewed_at TEXT NOT NULL);
   CREATE INDEX IF NOT EXISTS idx_micro_views ON micro_notes_views(student_id,course,unit);
   CREATE TABLE IF NOT EXISTS micro_tutor_log(
    id INTEGER PRIMARY KEY AUTOINCREMENT,student_id INTEGER NOT NULL,course TEXT NOT NULL,
    unit INTEGER NOT NULL,asked_at TEXT NOT NULL,question TEXT NOT NULL,
    source_heading TEXT,matched INTEGER NOT NULL);
  """)
 class NotesEvent(BaseModel):
  course:str
  unit:int=Field(ge=1,le=4)
  seconds:float=Field(ge=0,le=3600)
  kind:str='lesson'
 class TutorPrompt(BaseModel):
  course:str
  unit:int=Field(ge=1,le=4)
  text:str=Field(min_length=3,max_length=500)
  lang:str='es'
 class Answer(BaseModel):
  token:str=Field(min_length=20,max_length=70)
  answer:int=Field(ge=0,le=5)
  elapsed_sec:float=Field(ge=0,le=86400)
 def must_course(c):
  if c not in CURRICULUM:raise HTTPException(400,'Asignatura desconocida')
  return c
 def must_lang(lang):
  return 'en' if lang=='en' else 'es'
 def student(header):
  s=auth(header)
  if s['role']!='student':raise HTTPException(403,'Acceso exclusivo al alumnado')
  return s['student_id']
 def read_archive(raw):
  try:z=zipfile.ZipFile(io.BytesIO(raw))
  except (ValueError,zipfile.BadZipFile):raise HTTPException(422,'ZIP no válido')
  names=z.namelist()
  if len(names)>50 or sum(i.file_size for i in z.infolist())>MAX_UNCOMPRESSED:
   raise HTTPException(413,'El paquete supera los límites de seguridad')
  if any('..' in i.filename.split('/') or i.filename.startswith('/') or i.flag_bits&1 for i in z.infolist()):
   raise HTTPException(400,'Rutas no válidas o ZIP cifrado')
  if 'manifest.json' not in names:raise HTTPException(422,'Falta manifest.json')
  def jd(p):
   return json.loads(z.read(p).decode('utf8'))
  manifest=jd('manifest.json')
  if not isinstance(manifest.get('courses'),dict):raise HTTPException(422,'Manifiesto incompleto')
  questions=[]
  for name in sorted(names):
   if re.fullmatch(r'micro[12]/questions_\d\d\.json',name):
    questions+=jd(name)
  counts=Counter(q.get('course') for q in questions)
  if counts.get('micro1')!=5000 or counts.get('micro2') not in (0,5000):raise HTTPException(422,'Número incorrecto de preguntas por asignatura')
  qids=set()
  for q in questions:
   qid=q.get('external_id','')
   if not re.fullmatch(r'I-\d{4}' if q.get('course')=='micro1' else r'II-\d{4}',qid) or qid in qids:raise HTTPException(422,'Identificador duplicado/inválido')
   qids.add(qid)
   if q.get('course') not in CURRICULUM or q.get('unit') not in range(1,len(CURRICULUM[q['course']]['es'])+1) or q.get('modality') not in MODALITIES:
    raise HTTPException(422,'Asignación curricular incorrecta')
   if q.get('answer') not in (0,1,2,3):raise HTTPException(422,'Clave incorrecta')
   for lang in ('es','en'):
    if len(q.get('options_'+lang,[]))!=4 or len(set(q['options_'+lang]))!=4 or not q.get('prompt_'+lang) or not q.get('explanation_'+lang):
     raise HTTPException(422,'Pregunta incompleta: '+qid)
  figures=jd('micro1/figures.json')
  if 'lessons/figures.json' in names:figures.update(jd('lessons/figures.json'))
  if len(figures)>400:raise HTTPException(413,'Demasiadas figuras')
  for ident,obj in figures.items():
   if not re.fullmatch(r'fig_[a-f0-9]{14}',ident):raise HTTPException(422,'Código de figura incorrecto')
   svg=obj['svg']
   if len(svg)>300000:raise HTTPException(413,'Figura demasiado grande')
   try:root=ElementTree.fromstring(svg)
   except ElementTree.ParseError:raise HTTPException(422,'SVG mal formado')
   for elem in root.iter():
    tag=elem.tag.rsplit('}',1)[-1].lower()
    if tag in ('script','foreignobject','image','iframe','animate','set'):
     raise HTTPException(422,'Contenido activo no autorizado en SVG')
    for att,value in elem.attrib.items():
     if att.lower().startswith('on') or 'javascript:' in str(value).lower() or 'http://' in str(value).lower() or 'https://' in str(value).lower():
      raise HTTPException(422,'Atributo SVG no autorizado')
  lessons=[]
  for course in CURRICULUM:
   for lang in ('es','en'):
    path=f'lessons/{course}_{lang}.json'
    if path not in names:raise HTTPException(422,'Faltan apuntes: '+path)
    entries=jd(path)
    if len(entries)!=len(CURRICULUM[course][lang]):raise HTTPException(422,'Índice de temas incorrecto')
    for entry in entries:
     unit=entry.get('unit')
     if unit not in range(1,len(entries)+1):raise HTTPException(422,'Unidad no válida')
     lessons.append((course,lang,unit,json.dumps(entry,ensure_ascii=False)))
  supplements=[]
  for course in CURRICULUM:
   for lang in ('es','en'):
    path=f'lessons/supplementary_{course}_{lang}.json'
    if path in names:
     sections=jd(path)
     if not isinstance(sections,list) or len(sections)>30:raise HTTPException(422,'Recursos complementarios no válidos')
     supplements.append((course,lang,json.dumps(sections,ensure_ascii=False)))
  return questions,figures,lessons,supplements
 @app.post('/api/micro/import')
 async def import_package(file:UploadFile=File(...),authorization:str|None=Header(default=None)):
  auth(authorization,True)
  if not file.filename or not file.filename.lower().endswith('.zip'):
   raise HTTPException(400,'Se requiere el paquete ZIP de MICRO ADAPTA-ITS')
  raw=await file.read(MAX_UPLOAD+1)
  if len(raw)>MAX_UPLOAD:raise HTTPException(413,'Paquete superior a 12 MB')
  try:questions,figures,lessons,supplements=read_archive(raw)
  except HTTPException:raise
  except Exception:raise HTTPException(422,'No se pudo validar la estructura del paquete')
  with db() as c:
   c.execute("DELETE FROM micro_bank WHERE course IN ('micro1','micro2')")
   c.executemany('INSERT INTO micro_bank VALUES(?,?,?,?,?,?)',[(q['external_id'],q['course'],q['unit'],q['modality'],json.dumps(q,ensure_ascii=False),iso()) for q in questions])
   c.executemany('INSERT OR REPLACE INTO micro_figures VALUES(?,?,?)',[(k,v['svg'],v['caption']) for k,v in figures.items()])
   c.executemany('INSERT OR REPLACE INTO micro_lessons VALUES(?,?,?,?)',lessons)
   c.executemany('INSERT OR REPLACE INTO micro_supplementary VALUES(?,?,?)',supplements)
  return {'imported_questions':len(questions),'imported_by_course':dict(Counter(q['course'] for q in questions)),'figures':len(figures),'lesson_units':len(lessons),'supplementary_languages':len(supplements),'courses':['micro1','micro2'],
   'notice':'Microeconomía I utiliza preguntas originales. Microeconomía II utiliza variantes paramétricas, sujetas a validación docente.'}
 @app.get('/api/micro/catalog')
 def catalog(authorization:str|None=Header(default=None)):
  auth(authorization)
  with db() as c:
   counts={r['course']:r['n'] for r in c.execute('SELECT course,COUNT(*) n FROM micro_bank GROUP BY course')}
   lessons={(r['course'],r['lang']):r['n'] for r in c.execute('SELECT course,lang,COUNT(*) n FROM micro_lessons GROUP BY course,lang')}
  return {'curriculum':CURRICULUM,'question_counts':counts,
    'lesson_counts':{course:{lang:lessons.get((course,lang),0) for lang in ('es','en')} for course in CURRICULUM}}
 @app.get('/api/micro/lesson')
 def lesson(course:str,unit:int=Query(ge=1,le=4),lang:str='es',authorization:str|None=Header(default=None)):
  auth(authorization);must_course(course);lang=must_lang(lang)
  with db() as c:r=c.execute('SELECT payload FROM micro_lessons WHERE course=? AND lang=? AND unit=?',(course,lang,unit)).fetchone()
  if not r:raise HTTPException(404,'Apuntes pendientes de carga docente')
  return json.loads(r['payload'])
 @app.get('/api/micro/supplementary')
 def supplementary(course:str='micro1',lang:str='es',authorization:str|None=Header(default=None)):
  auth(authorization);must_course(course);lang=must_lang(lang)
  with db() as c:r=c.execute('SELECT payload FROM micro_supplementary WHERE course=? AND lang=?',(course,lang)).fetchone()
  if not r:raise HTTPException(404,'Material complementario pendiente de carga')
  return {'resources':json.loads(r['payload'])}
 @app.get('/api/micro/figure/{fid}')
 def figure(fid:str):
  if not re.fullmatch(r'fig_[a-f0-9]{14}',fid):raise HTTPException(404)
  with db() as c:r=c.execute('SELECT svg FROM micro_figures WHERE id=?',(fid,)).fetchone()
  if not r:raise HTTPException(404)
  return Response(r['svg'],media_type='image/svg+xml',headers={'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; sandbox",'X-Content-Type-Options':'nosniff'})
 @app.get('/api/micro/next')
 def next_question(course:str='micro1',unit:int=Query(default=1,ge=1,le=4),
                   units:str='',modality:str='',lang:str='es',phase:str='practice',
                   authorization:str|None=Header(default=None)):
  sid=student(authorization);must_course(course);lang=must_lang(lang)
  if phase not in ('diagnostic','practice'):raise HTTPException(400,'Fase no reconocida')
  if modality and modality not in MODALITIES:raise HTTPException(400,'Modalidad desconocida')
  maximum=len(CURRICULUM[course]['es'])
  if units and not re.fullmatch(r'[1-4](,[1-4])*',units):raise HTTPException(400,'Temas inválidos')
  selected=sorted({int(v) for v in units.split(',')}) if units else [unit]
  if any(v<1 or v>maximum for v in selected):raise HTTPException(400,'Tema fuera del temario')
  with db() as c:
   diag=c.execute("""SELECT b.unit,COUNT(*) n FROM micro_activities a
                     JOIN micro_bank b ON a.question_id=b.id
                     WHERE a.student_id=? AND a.course=? AND a.phase='diagnostic'
                       AND a.finished_at IS NOT NULL GROUP BY b.unit""",(sid,course)).fetchall()
   diag_done={r['unit'] for r in diag}
   if phase=='practice' and len(diag_done)<maximum:
    raise HTTPException(409,'Completa primero el diagnóstico inicial: una pregunta por cada tema.')
   if phase=='diagnostic':
    missing=[u for u in range(1,maximum+1) if u not in diag_done]
    if not missing:return {'complete':True,'diagnostic_complete':True}
    selected=[missing[0]]
    modality=''
   outstanding=c.execute("""SELECT a.*,b.unit,b.payload FROM micro_activities a
                            JOIN micro_bank b ON a.question_id=b.id
                            WHERE a.student_id=? AND a.course=? AND a.phase=?
                             AND a.finished_at IS NULL ORDER BY a.started_at DESC LIMIT 1""",(sid,course,phase)).fetchone()
   if outstanding and outstanding['unit'] in selected:
    q=json.loads(outstanding['payload'])
    return {'available':True,'token':outstanding['token'],'id':q['external_id'],
     'course':course,'unit':outstanding['unit'],'modality':q['modality'],
     'level':q['level'],'prompt':q['prompt_'+lang],
     'options':q['options_'+lang],'figure_id':q.get('figure_id'),
     'source':q.get('source',''),'phase':phase,'resumed':True}
   placeholders=','.join('?' for _ in selected)
   query="SELECT id,unit,modality,payload FROM micro_bank WHERE course=? AND unit IN ("+placeholders+")"
   args=[course]+selected
   if modality and phase=='practice':
    query+=' AND modality=?';args.append(modality)
   if phase=='diagnostic':query+=" AND modality='teorica'"
   rows=c.execute(query,args).fetchall()
   if phase=='diagnostic':
    low_level=[r for r in rows if json.loads(r['payload']).get('level',1)==1]
    if low_level:rows=low_level
   if not rows:return {'available':False,'message':'No hay preguntas de esta modalidad cargadas para el tema.'}
   recent={r['question_id'] for r in c.execute("""SELECT question_id FROM micro_activities
               WHERE student_id=? AND course=? ORDER BY started_at DESC LIMIT 150""",(sid,course))}
   candidates=[r for r in rows if r['id'] not in recent] or rows
   group=c.execute('SELECT group_name FROM students WHERE id=?',(sid,)).fetchone()
   treatment=bool(group and group['group_name'] in ('B','D'))
   policy='diagnostic-random-v1' if phase=='diagnostic' else ('adaptive-bkt-weakness-v2' if treatment else 'control-random-v2')
   if treatment and phase=='practice':
    mastery={r['unit']:r['posterior'] for r in c.execute("""SELECT unit,posterior FROM micro_mastery WHERE
                                student_id=? AND course=?""",(sid,course))}
    recent_errors=c.execute("""SELECT b.unit,b.modality,COUNT(*) total,
                                 SUM(CASE WHEN a.correct=0 THEN 1 ELSE 0 END) errors
                           FROM micro_activities a JOIN micro_bank b ON a.question_id=b.id
                           WHERE a.student_id=? AND a.course=? AND a.finished_at IS NOT NULL
                           GROUP BY b.unit,b.modality""",(sid,course)).fetchall()
    errors={(r['unit'],r['modality']):(r['errors'],r['total']) for r in recent_errors}
    # Exploit observed topic weaknesses in 65% of treatment selections.
    if secrets.randbelow(100)<65:
     weights={u:(0.28+1.8*(1-mastery.get(u,PRIOR))) for u in selected}
     for (topic,_),v in errors.items():
      if topic in weights:weights[topic]+=0.55*v[0]/max(1,v[1])
     topic=random.SystemRandom().choices(selected,weights=[weights[u] for u in selected])[0]
     candidates=[r for r in candidates if r['unit']==topic] or candidates
     if not modality and secrets.randbelow(100)<70:
      modes=sorted({r['modality'] for r in candidates})
      weakness=[(1+2*(errors.get((topic,k),(0,0))[0]/max(1,errors.get((topic,k),(0,0))[1])),k) for k in modes]
      focus=random.SystemRandom().choices([x[1] for x in weakness],weights=[x[0] for x in weakness])[0]
      candidates=[r for r in candidates if r['modality']==focus] or candidates
    # Bayesian posterior sets an instructional tier; it is not an exam score.
    topic=candidates[0]['unit'] if len({r['unit'] for r in candidates})==1 else random.SystemRandom().choice(candidates)['unit']
    p=mastery.get(topic,PRIOR)
    desired=1 if p<.45 else 2 if p<.80 else 3
    ranked=[(r,abs(int(json.loads(r['payload']).get('level',2))-desired)) for r in candidates]
    least=min(score for _,score in ranked)
    candidates=[r for r,score in ranked if score==least]
   chosen=secrets.choice(candidates)
   q=json.loads(chosen['payload'])
   access=secrets.token_urlsafe(26)
   c.execute("""INSERT INTO micro_activities
      (token,student_id,course,question_id,started_at,lang,selection_policy,phase)
      VALUES(?,?,?,?,?,?,?,?)""",(access,sid,course,q['external_id'],iso(),lang,policy,phase))
  return {'available':True,'token':access,'id':q['external_id'],'course':course,'unit':q['unit'],
   'modality':q['modality'],'level':q['level'],'prompt':q['prompt_'+lang],
   'options':q['options_'+lang],'figure_id':q.get('figure_id'),
   'source':q.get('source',''),'phase':phase,'selection_policy':policy}
 @app.post('/api/micro/answer')
 def answer(data:Answer,authorization:str|None=Header(default=None)):
  sid=student(authorization)
  with db() as c:
   a=c.execute('SELECT * FROM micro_activities WHERE token=? AND student_id=?',(data.token,sid)).fetchone()
   if not a:raise HTTPException(404,'Actividad no encontrada')
   if a['finished_at']:raise HTTPException(409,'Esta pregunta ya fue respondida')
   row=c.execute('SELECT payload FROM micro_bank WHERE id=?',(a['question_id'],)).fetchone()
   if not row:raise HTTPException(409,'Contenido actualizado por el docente')
   q=json.loads(row['payload'])
   if data.answer>=len(q['options_'+a['lang']]):raise HTTPException(400,'Opción inválida')
   correct=int(data.answer==q['answer'])
   unit=q['unit'];course=a['course']
   mr=c.execute('SELECT posterior FROM micro_mastery WHERE student_id=? AND course=? AND unit=?',(sid,course,unit)).fetchone()
   prior=float(mr['posterior']) if mr else PRIOR
   history=c.execute("""SELECT COUNT(*) n,SUM(correct) hits FROM micro_activities a
         JOIN micro_bank b ON a.question_id=b.id WHERE a.student_id=? AND a.course=?
         AND b.unit=? AND a.finished_at IS NOT NULL""",(sid,course,unit)).fetchone()
   n=history['n'];recent_accuracy=(history['hits']/n) if n else .5
   reads=c.execute('SELECT count(*) n FROM micro_notes_views WHERE student_id=? AND course=? AND unit=?',(sid,course,unit)).fetchone()['n']
   start=datetime.fromisoformat(a['started_at'])
   elapsed=max(0.,min(86400.,(utc()-start).total_seconds()))
   features=model_features(prior,int(q.get('level',2)),elapsed,recent_accuracy,n,reads)
   group=c.execute('SELECT group_name FROM students WHERE id=?',(sid,)).fetchone()['group_name']
   if group in ('B','D'):
    after,version=posterior_update(c,course,prior,bool(correct),features,a['phase']=='diagnostic')
   else:
    after=bayesian_update(prior,bool(correct),learn=(a['phase']!='diagnostic'))
    version='BKT-v2 control (tracking only)'
   c.execute("""UPDATE micro_activities SET answer=?,finished_at=?,correct=?,
       elapsed_sec=?,p_before=?,p_after=?,model_version=?,features_json=? WHERE token=?""",
       (data.answer,iso(),correct,round(elapsed,2),prior,after,version,json.dumps(features),a['token']))
   c.execute("""INSERT INTO micro_mastery(student_id,course,unit,posterior,updated_at)
       VALUES(?,?,?,?,?) ON CONFLICT(student_id,course,unit) DO UPDATE
       SET posterior=excluded.posterior,updated_at=excluded.updated_at""",(sid,course,unit,after,iso()))
   lang=a['lang']
   return {'correct':bool(correct),'answer':q['answer'],
       'answer_text':q['options_'+lang][q['answer']],
       'explanation':q['explanation_'+lang],
       'id':q['external_id'],'course':course,'unit':unit,'phase':a['phase'],
       'posterior_before':round(prior,4),'posterior_after':round(after,4),
       'model_version':version,
       'lesson_reference':{'course':course,'unit':unit},
       'encouragement':('Buen trabajo. Comprueba la explicación y consolida el concepto.' if correct else
                         'El error sirve para localizar el concepto que conviene repasar. Consulta los apuntes y vuelve a intentarlo.'
                        ) if lang=='es' else
                       ('Good work. Check the explanation to consolidate your learning.' if correct else
                        'This result identifies a concept worth reviewing. Read the notes and try again.')}
 @app.get('/api/micro/teacher/export')
 def teacher_export(authorization:str|None=Header(default=None)):
  auth(authorization,True)
  output=io.StringIO()
  writer=csv.writer(output)
  writer.writerow(['student_code','research_group','degree','course','unit','question_id','modality','source','started_at','finished_at','elapsed_seconds','chosen_index','correct','reviewed_source','selection_policy'])
  with db() as c:
   rows=c.execute("""SELECT s.code,s.group_name,s.degree,a.course,b.unit,a.question_id,b.modality,b.payload,a.started_at,a.finished_at,a.elapsed_sec,a.answer,a.correct,a.selection_policy
                     FROM micro_activities a
                     JOIN students s ON a.student_id=s.id
                     LEFT JOIN micro_bank b ON b.id=a.question_id
                     ORDER BY a.started_at""").fetchall()
   for r in rows:
    d=dict(r)
    q=json.loads(d.pop('payload') or '{}')
    vals=[d['code'],d['group_name'],d['degree'],d['course'],d['unit'],d['question_id'],
          d['modality'],q.get('source',''),d['started_at'],d['finished_at'],d['elapsed_sec'],d['answer'],d['correct'],
          q.get('reviewed',False),d['selection_policy']]
    writer.writerow(["'"+str(v) if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in vals])
  data=output.getvalue().encode('utf-8-sig')
  return StreamingResponse(io.BytesIO(data),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="micro_adapta_course_research.csv"','Cache-Control':'no-store'})
 @app.post('/api/micro/notes/view')
 def notes_view(data:NotesEvent,authorization:str|None=Header(default=None)):
  sid=student(authorization);must_course(data.course)
  if data.unit>len(CURRICULUM[data.course]['es']):raise HTTPException(400,'Tema desconocido')
  if data.kind not in ('lesson','supplementary','tutor'):raise HTTPException(400,'Material desconocido')
  with db() as c:
   recent=c.execute("""SELECT viewed_at FROM micro_notes_views
       WHERE student_id=? AND course=? AND unit=? AND kind=?
       ORDER BY id DESC LIMIT 1""",(sid,data.course,data.unit,data.kind)).fetchone()
   if recent and (utc()-datetime.fromisoformat(recent['viewed_at'])).total_seconds()<12:
    return {'logged':False,'notice':'La lectura reciente ya se registró.'}
   c.execute("""INSERT INTO micro_notes_views(student_id,course,unit,kind,seconds,viewed_at)
      VALUES(?,?,?,?,?,?)""",(sid,data.course,data.unit,data.kind,round(min(900,data.seconds),1),iso()))
  return {'logged':True}
 @app.post('/api/micro/tutor')
 def tutor_reply(data:TutorPrompt,authorization:str|None=Header(default=None)):
  sid=student(authorization);must_course(data.course)
  if data.unit>len(CURRICULUM[data.course]['es']):raise HTTPException(400,'Tema inválido')
  lang=must_lang(data.lang)
  with db() as c:
   r=c.execute('SELECT payload FROM micro_lessons WHERE course=? AND lang=? AND unit=?',
       (data.course,lang,data.unit)).fetchone()
   if not r:raise HTTPException(404,'El docente todavía no ha cargado los apuntes de este tema')
   lesson=json.loads(r['payload'])
   answer=grounded_tutor(lesson,data.text,lang)
   last=c.execute("""SELECT b.payload FROM micro_activities a JOIN micro_bank b ON a.question_id=b.id
           WHERE a.student_id=? AND a.course=? AND b.unit=? AND a.correct=0
           ORDER BY a.finished_at DESC LIMIT 1""",(sid,data.course,data.unit)).fetchone()
   mastery=c.execute('SELECT posterior FROM micro_mastery WHERE student_id=? AND course=? AND unit=?',
                    (sid,data.course,data.unit)).fetchone()
   prob=round(mastery['posterior'],4) if mastery else PRIOR
   if last:
    q=json.loads(last['payload'])
    answer['recent_error_reference']=q.get('external_id','')
    if lang=='es':answer['suggestion']='Repasa esta sección y practica después un ejercicio similar para consolidar lo aprendido.'
    else:answer['suggestion']='Review this section and then try a similar exercise to consolidate the concept.'
   else:
    answer['suggestion']=('Puedes poner a prueba esta explicación con una nueva pregunta del tema.'
      if lang=='es' else 'Try a new question from this topic to check your understanding.')
   clean=re.sub(r'[\w.+-]+@[\w.-]+','[email]',data.text)[:500]
   c.execute("""INSERT INTO micro_tutor_log(student_id,course,unit,asked_at,question,source_heading,matched)
          VALUES(?,?,?,?,?,?,?)""",(sid,data.course,data.unit,iso(),clean,answer.get('section'),int(answer['matched'])))
  answer['estimated_mastery']=prob
  answer['course']=data.course;answer['unit']=data.unit
  answer['note']='Respuesta recuperada de los apuntes originales; no se ha generado una conclusión económica nueva.'
  return answer
 @app.get('/api/micro/progress')
 def progress(course:str='micro1',authorization:str|None=Header(default=None)):
  sid=student(authorization);must_course(course)
  maximum=len(CURRICULUM[course]['es'])
  with db() as c:
   results=c.execute("""SELECT b.unit,COUNT(*) attempts,SUM(a.correct) correct,
          AVG(a.elapsed_sec) avg_seconds,SUM(a.elapsed_sec) total_seconds
          FROM micro_activities a JOIN micro_bank b ON b.id=a.question_id
          WHERE a.student_id=? AND a.course=? AND a.finished_at IS NOT NULL
          GROUP BY b.unit""",(sid,course)).fetchall()
   mastery={r['unit']:round(r['posterior'],4) for r in c.execute(
      'SELECT unit,posterior FROM micro_mastery WHERE student_id=? AND course=?',(sid,course))}
   views=c.execute("""SELECT unit,COUNT(*) notes_views,SUM(seconds) study_seconds
           FROM micro_notes_views WHERE student_id=? AND course=? GROUP BY unit""",(sid,course)).fetchall()
   reads={r['unit']:{'notes_views':r['notes_views'],'study_seconds':round(r['study_seconds'] or 0,1)} for r in views}
   diag=c.execute("""SELECT b.unit FROM micro_activities a JOIN micro_bank b ON a.question_id=b.id
            WHERE a.student_id=? AND a.course=? AND a.phase='diagnostic'
            AND a.finished_at IS NOT NULL GROUP BY b.unit""",(sid,course)).fetchall()
   passed={r['unit'] for r in diag}
   mode=c.execute('SELECT group_name FROM students WHERE id=?',(sid,)).fetchone()
   last=c.execute("""SELECT a.question_id,a.correct,b.unit,a.p_before,a.p_after,a.elapsed_sec
        FROM micro_activities a JOIN micro_bank b ON a.question_id=b.id
        WHERE a.student_id=? AND a.course=? AND a.finished_at IS NOT NULL
        ORDER BY a.finished_at DESC LIMIT 8""",(sid,course)).fetchall()
  rmap={r['unit']:dict(r) for r in results}
  units={}
  for u in range(1,maximum+1):
   r=rmap.get(u,{})
   n=r.get('attempts',0) or 0;correct=r.get('correct',0) or 0
   read=reads.get(u,{'notes_views':0,'study_seconds':0})
   mean=r.get('avg_seconds',0) or 0
   participation=round(100*(.58*min(1,n/14)+.27*min(1,read['notes_views']/3)+.15*min(1,(mean*n+read['study_seconds'])/600)))
   units[str(u)]={'attempts':n,'correct':correct,'accuracy':round(100*correct/n,1) if n else None,
     'avg_seconds':round(mean,2),'mastery':mastery.get(u,PRIOR),
     'notes_views':read['notes_views'],'study_seconds':read['study_seconds'],
     'participation_pct':min(100,participation),
     'diagnostic_complete':u in passed}
  total_attempts=sum(v['attempts'] for v in units.values())
  total_reads=sum(v['notes_views'] for v in units.values())
  return {'course':course,'diagnostic_count':len(passed),'diagnostic_total':maximum,
    'diagnostic_complete':len(passed)==maximum,'units':units,
    'total_attempts':total_attempts,'total_notes_views':total_reads,
    'participation_pct':round(sum(v['participation_pct'] for v in units.values())/maximum),
    'estimated_mastery_pct':round(100*sum(v['mastery'] for v in units.values())/maximum),
    'recent':[dict(x) for x in last],
    'selection_policy':'adaptive' if mode and mode['group_name'] in ('B','D') else 'control'}
