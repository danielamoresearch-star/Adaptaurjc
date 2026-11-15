"""MICRO ADAPTA-ITS: separate curricular courses with auditable teacher-imported content.
The supplied course archive is imported only by an authenticated teacher. A missing
archive is reported as missing content rather than silently replaced by synthetic items.
"""
import io,json,random,secrets,zipfile,re,math
from collections import Counter
from xml.etree import ElementTree
from fastapi import File,UploadFile,Header,HTTPException,Query
from fastapi.responses import Response
from pydantic import BaseModel,Field

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
  if len(figures)>250:raise HTTPException(413,'Demasiadas figuras')
  for ident,obj in figures.items():
   if not re.fullmatch(r'fig_[a-f0-9]{14}',ident):raise HTTPException(422,'Código de figura incorrecto')
   svg=obj['svg']
   if len(svg)>150000:raise HTTPException(413,'Figura demasiado grande')
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
 def next_question(course:str='micro1',unit:int=Query(ge=1,le=4),modality:str='',lang:str='es',authorization:str|None=Header(default=None)):
  sid=student(authorization);must_course(course);lang=must_lang(lang)
  if unit>len(CURRICULUM[course]['es']):raise HTTPException(400,'Tema inexistente')
  if modality and modality not in MODALITIES:raise HTTPException(400,'Modalidad desconocida')
  with db() as c:
   rows=c.execute('SELECT id,payload FROM micro_bank WHERE course=? AND unit=?'+(' AND modality=?' if modality else ''),
       (course,unit,modality) if modality else (course,unit)).fetchall()
   if not rows:return {'available':False,'message':'Este banco no está cargado; solicita al docente que importe el corpus.'}
   recent={r['question_id'] for r in c.execute('SELECT question_id FROM micro_activities WHERE student_id=? AND course=? ORDER BY started_at DESC LIMIT 150',(sid,course))}
   fresh=[r for r in rows if r['id'] not in recent]
   chosen=secrets.choice(fresh or rows)
   q=json.loads(chosen['payload'])
   token=secrets.token_urlsafe(26)
   c.execute('INSERT INTO micro_activities(token,student_id,course,question_id,started_at,lang) VALUES(?,?,?,?,?,?)',(token,sid,course,q['external_id'],iso(),lang))
  return {'available':True,'token':token,'id':q['external_id'],'course':course,'unit':unit,
   'modality':q['modality'],'level':q['level'],'prompt':q['prompt_'+lang],'options':q['options_'+lang],
   'figure_id':q.get('figure_id'),'source':q.get('source','')}
 @app.post('/api/micro/answer')
 def answer(data:Answer,authorization:str|None=Header(default=None)):
  sid=student(authorization)
  with db() as c:
   a=c.execute('SELECT * FROM micro_activities WHERE token=? AND student_id=?',(data.token,sid)).fetchone()
   if not a:raise HTTPException(404,'Actividad no encontrada')
   if a['finished_at']:raise HTTPException(409,'Pregunta ya respondida')
   row=c.execute('SELECT payload FROM micro_bank WHERE id=?',(a['question_id'],)).fetchone()
   if not row:raise HTTPException(409,'Contenido actualizado por el docente')
   q=json.loads(row['payload'])
   correct=int(data.answer==q['answer'])
   c.execute('UPDATE micro_activities SET answer=?,finished_at=?,correct=?,elapsed_sec=? WHERE token=?',
     (data.answer,iso(),correct,data.elapsed_sec,data.token))
   lang=a['lang']
   return {'correct':bool(correct),'answer':q['answer'],'answer_text':q['options_'+lang][q['answer']],
     'explanation':q['explanation_'+lang],'id':q['external_id']}
 @app.get('/api/micro/progress')
 def progress(course:str='micro1',authorization:str|None=Header(default=None)):
  sid=student(authorization);must_course(course)
  with db() as c:
   rows=c.execute("""SELECT b.unit,COUNT(*) attempts,SUM(a.correct) correct,AVG(a.elapsed_sec) avg_seconds
                     FROM micro_activities a JOIN micro_bank b ON b.id=a.question_id
                     WHERE a.student_id=? AND a.course=? AND a.finished_at IS NOT NULL GROUP BY b.unit""",(sid,course)).fetchall()
  return {'course':course,'units':{str(r['unit']):{'attempts':r['attempts'],'correct':r['correct'],'avg_seconds':round(r['avg_seconds'] or 0,2)} for r in rows}}
