"""Research-grade MICRO ADAPTA-ITS course analytics and XLSX export.
All metrics are computed from persisted activity; never fabricate exam marks,
student session times, or causal learning gains. Restricted to teacher accounts.
"""
import io,json,math,collections,os,tempfile,sqlite3
from datetime import datetime
from fastapi import Header,HTTPException
from fastapi.responses import StreamingResponse,FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel,Field
from excel_export import create_workbook
from micro_course import CURRICULUM
from micro_kpis import build_kpi_sheets

def average(values):
 xs=[float(v) for v in values if v is not None]
 return round(sum(xs)/len(xs),2) if xs else None
def rounded(x,d=2):
 return round(float(x),d) if x is not None else None
def pct(top,bottom):
 return round(100*top/bottom,2) if bottom else None
def flag_value(r):
 return 1 if r['correct']==1 else 0 if r['correct']==0 else None
def nice(s):
 return 'Microeconomía I' if s=='micro1' else 'Microeconomía II' if s=='micro2' else str(s)
def title(unit,course):
 try:return CURRICULUM[course]['es'][int(unit)-1]
 except (IndexError,KeyError,ValueError,TypeError):return 'Sin clasificar'
def iso_seconds(first,second):
 if not first or not second:return None
 try:return max(0,(datetime.fromisoformat(second)-datetime.fromisoformat(first)).total_seconds())
 except (ValueError,TypeError):return None

def register(app,db,auth,iso,utc):
 with db() as c:
  c.execute("""CREATE TABLE IF NOT EXISTS micro_app_sessions(
   student_id INTEGER NOT NULL,course TEXT NOT NULL,session_id TEXT NOT NULL,
   opened_at TEXT NOT NULL,last_ping TEXT NOT NULL,active_seconds REAL NOT NULL DEFAULT 0,
   PRIMARY KEY(student_id,course,session_id))""")
 class Pulse(BaseModel):
  course:str
  session_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{16,64}$')
  visible:bool=True
 @app.post('/api/micro/usage/pulse')
 def usage_pulse(data:Pulse,authorization:str|None=Header(default=None)):
  user=auth(authorization)
  if user['role']!='student':raise HTTPException(403)
  if data.course not in CURRICULUM:raise HTTPException(400,'Asignatura incorrecta')
  sid=user['student_id'];now=utc()
  with db() as c:
   row=c.execute("""SELECT last_ping,active_seconds FROM micro_app_sessions
       WHERE student_id=? AND course=? AND session_id=?""",(sid,data.course,data.session_id)).fetchone()
   if row is None:
    c.execute('INSERT INTO micro_app_sessions VALUES(?,?,?,?,?,?)',
      (sid,data.course,data.session_id,iso(now),iso(now),0))
    return {'ok':True,'active_seconds':0}
   gap=(now-datetime.fromisoformat(row['last_ping'])).total_seconds()
   addition=min(max(gap,0),45) if data.visible and gap<=90 else 0
   c.execute("""UPDATE micro_app_sessions
      SET last_ping=?,active_seconds=active_seconds+?
      WHERE student_id=? AND course=? AND session_id=?""",
      (iso(now),addition,sid,data.course,data.session_id))
   return {'ok':True,'active_seconds':round(row['active_seconds']+addition,1)}

 @app.get('/api/micro/teacher/storage')
 def storage_status(authorization:str|None=Header(default=None)):
  auth(authorization,True)
  location=os.path.abspath(os.environ.get('ADAPTA_DB','adapta_v6.sqlite3'))
  directory=os.path.dirname(location)
  return {'database_size_mb':round(os.path.getsize(location)/1048576,2) if os.path.isfile(location) else 0,
   'persistent_disk_verified':os.path.ismount(directory),
   'warning':None if os.path.ismount(directory) else 'No se ha verificado un disco persistente para SQLite. Realiza copias y configura un almacenamiento persistente antes del uso en investigación.'}
 @app.get('/api/micro/teacher/backup.sqlite3')
 def teacher_db_backup(authorization:str|None=Header(default=None)):
  auth(authorization,True)
  file=tempfile.NamedTemporaryFile(delete=False,suffix='.sqlite3')
  filename=file.name;file.close()
  try:
   with db() as source,sqlite3.connect(filename) as destination:
    source.backup(destination)
   return FileResponse(filename,media_type='application/vnd.sqlite3',
    filename='MICRO_ADAPTA_ITS_respaldo.sqlite3',
    headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'},
    background=BackgroundTask(lambda:os.unlink(filename)))
  except Exception:
   if os.path.isfile(filename):os.unlink(filename)
   raise
 @app.get('/api/micro/teacher/export.xlsx')
 def export_research_excel(authorization:str|None=Header(default=None)):
  auth(authorization,True)
  with db() as c:
   students=[dict(x) for x in c.execute(
     'SELECT id,code,group_name,degree,professor FROM students ORDER BY code').fetchall()]
   attempts=[dict(x) for x in c.execute("""
      SELECT a.student_id,a.course,a.question_id,a.started_at,a.finished_at,
       a.elapsed_sec,a.phase,a.answer,a.correct,a.p_before,a.p_after,a.model_version,
       a.selection_policy,a.lang,b.unit,b.modality,b.payload
      FROM micro_activities a LEFT JOIN micro_bank b ON a.question_id=b.id
      ORDER BY a.student_id,a.course,a.started_at""").fetchall()]
   studies=[dict(x) for x in c.execute("""
      SELECT student_id,course,unit,kind,seconds,viewed_at
      FROM micro_notes_views ORDER BY student_id,course,viewed_at""").fetchall()]
   sessions=[dict(x) for x in c.execute("""
      SELECT student_id,course,session_id,opened_at,last_ping,active_seconds
      FROM micro_app_sessions ORDER BY student_id,course,opened_at""").fetchall()]
   mastery=[dict(x) for x in c.execute("""
      SELECT student_id,course,unit,posterior,updated_at FROM micro_mastery
      ORDER BY student_id,course,unit""").fetchall()]
   tutor=[dict(x) for x in c.execute("""
      SELECT student_id,course,unit,asked_at,source_heading,matched
      FROM micro_tutor_log ORDER BY student_id,course,asked_at""").fetchall()]
   exam_runs=[dict(x) for x in c.execute("""
      SELECT r.student_id,r.id run_id,r.spec_id,r.started_at,r.deadline_at,
       r.submitted_at,r.score,r.correct_count,r.graded_count,
       s.title,s.topics_json,s.kinds_json,s.duration_minutes
      FROM exam_runs r JOIN exam_specs s ON r.spec_id=s.id
      ORDER BY r.student_id,r.started_at""").fetchall()]
  index={s['id']:s for s in students}
  # Pre-compute grouped metrics, retaining unmatched historical data separately.
  per_course=collections.defaultdict(list)
  per_unit=collections.defaultdict(list)
  by_study=collections.defaultdict(list)
  by_session=collections.defaultdict(list)
  by_tutor=collections.defaultdict(list)
  by_mastery={}
  for r in attempts:
   if r['course'] in CURRICULUM:
    per_course[(r['student_id'],r['course'])].append(r)
    if r['unit'] is not None:per_unit[(r['student_id'],r['course'],r['unit'])].append(r)
  for r in studies:
   by_study[(r['student_id'],r['course'],r['unit'])].append(r)
  for r in sessions:by_session[(r['student_id'],r['course'])].append(r)
  for r in tutor:by_tutor[(r['student_id'],r['course'],r['unit'])].append(r)
  for r in mastery:by_mastery[(r['student_id'],r['course'],r['unit'])]=r

  def base(student,course,unit=None):
   return [student['code'],student['group_name'],student['professor'],
           student['degree'],nice(course),unit,title(unit,course) if unit else 'TODAS LAS UNIDADES']
  def metrics(rows,sid,course,unit=None):
   finished=[r for r in rows if r['finished_at'] is not None]
   graded=[r for r in finished if r['correct'] is not None]
   correct=sum(x['correct']==1 for x in graded);errors=sum(x['correct']==0 for x in graded)
   tests=len(finished)
   if unit is None:notes=[e for (s,c,u),rs in by_study.items() if s==sid and c==course for e in rs]
   else:notes=by_study[(sid,course,unit)]
   app=by_session[(sid,course)]
   pvalues=[r for r in finished if r['p_after'] is not None]
   p0=pvalues[0]['p_before'] if pvalues else None
   p1=pvalues[-1]['p_after'] if pvalues else None
   if unit is not None:
    m=by_mastery.get((sid,course,unit))
    if m is not None:p1=m['posterior']
   if unit is None:
    mvalues=[v['posterior'] for (s,c,u),v in by_mastery.items() if s==sid and c==course]
    p1=sum(mvalues)/len(mvalues) if mvalues else p1
   active=sum(x['active_seconds'] or 0 for x in app)
   # An item attempt is one finished response, even when the same question is repeated.
   unique_questions=len({r['question_id'] for r in finished})
   retry_count=max(0,tests-unique_questions)
   possible_grade=round(10*correct/len(graded),2) if graded else None
   return {
    'app_time_total_min':round(active/60,2) if app else None,
    'app_time_avg_session_min':round(active/60/len(app),2) if app else None,
    'app_sessions':len(app),
    'avg_question_sec':average([r['elapsed_sec'] for r in finished]),
    'question_sec_total':round(sum((r['elapsed_sec'] or 0) for r in finished),1),
    'attempts':tests,'questions_unique':unique_questions,'repetitions':retry_count,
    'correct':correct,'wrong':errors,'accuracy':pct(correct,len(graded)),
    'error_rate':pct(errors,len(graded)),
    'note_views':len(notes),
    'note_time_min':round(sum((n['seconds'] or 0) for n in notes)/60,2),
    'p0_pct':pct(p0,1) if p0 is not None else None,
    'p1_pct':pct(p1,1) if p1 is not None else None,
    'gain_points':round(100*(p1-p0),2) if p1 is not None and p0 is not None else None,
    'grade':possible_grade
   }
  summary_cols=['Usuario','Grupo','Docente','Grado','Asignatura','Unidad','Nombre de unidad',
    'Sesiones activas','Tiempo total aplicación (min)','Tiempo medio aplicación / sesión (min)',
    'Tiempo medio pregunta (seg)','Tiempo total preguntas (seg)',
    'Nº de intentos','Preguntas diferentes','Repeticiones','Aciertos','Fallos',
    'Tasa de acierto (%)','Tasa de fallo (%)',
    'Posterior inicial (%)','Posterior final (%)','Progreso estimado (puntos porcentuales)',
    'Consultas de apuntes','Tiempo de apuntes (min)',
    'Nota media ejercicios (0-10)','Exámenes realizados','Nota media exámenes (0-10)']
  summary=[];units=[]
  for student in students:
   sid=student['id']
   for course in CURRICULUM:
    rr=per_course[(sid,course)]
    stats=metrics(rr,sid,course)
    exams=[] # Exams from the older module have no course metadata: never attach to a course.
    summary.append(base(student,course)+[
      stats['app_sessions'],stats['app_time_total_min'],stats['app_time_avg_session_min'],
      stats['avg_question_sec'],stats['question_sec_total'],stats['attempts'],
      stats['questions_unique'],stats['repetitions'],stats['correct'],stats['wrong'],
      stats['accuracy'],stats['error_rate'],stats['p0_pct'],stats['p1_pct'],
      stats['gain_points'],stats['note_views'],stats['note_time_min'],stats['grade'],
      None,None])
    for unit in range(1,len(CURRICULUM[course]['es'])+1):
     rr=per_unit[(sid,course,unit)]
     s=metrics(rr,sid,course,unit)
     # Average app session time is course-wide; the unit level has only exercise / notes time.
     units.append(base(student,course,unit)+[
       s['app_sessions'],None,None,s['avg_question_sec'],
       s['question_sec_total'],s['attempts'],s['questions_unique'],s['repetitions'],
       s['correct'],s['wrong'],s['accuracy'],s['error_rate'],
       s['p0_pct'],s['p1_pct'],s['gain_points'],s['note_views'],
       s['note_time_min'],s['grade'],None,None])

  attempts_header=['Usuario','Grupo','Docente','Grado','Asignatura','Unidad',
    'Nombre unidad','ID pregunta','Intento de la pregunta (n)','Fase',
    'Modalidad','Fecha inicio','Fecha fin','Tiempo pregunta (seg)',
    'Respuesta opción','Correcta (1/0)','Tasa acumulada acierto (%)',
    'Posterior previo (%)','Posterior posterior (%)','Cambio posterior (pp)',
    'Modelo aplicado','Política de selección','Fuente del contenido','Revisión docente','Nota pregunta (0-10)']
  raw=[];numbered=collections.Counter();counters=collections.defaultdict(lambda:[0,0])
  for r in attempts:
   user=index.get(r['student_id'])
   if not user or r['course'] not in CURRICULUM:continue
   unit=r['unit'];key=(r['student_id'],r['course'],r['question_id'])
   numbered[key]+=1
   examkey=(r['student_id'],r['course'],unit)
   if r['finished_at'] is not None and r['correct'] is not None:
    counters[examkey][0]+=int(r['correct']);counters[examkey][1]+=1
   score=(pct(*counters[examkey]) if counters[examkey][1] else None)
   try:q=json.loads(r['payload'] or '{}')
   except (json.JSONDecodeError,TypeError):q={}
   raw.append([user['code'],user['group_name'],user['professor'],user['degree'],
     nice(r['course']),unit,title(unit,r['course']) if unit else None,
     r['question_id'],numbered[key],r['phase'],r['modality'],r['started_at'],
     r['finished_at'],rounded(r['elapsed_sec']),r['answer'],r['correct'],
     score,pct(r['p_before'],1) if r['p_before'] is not None else None,
     pct(r['p_after'],1) if r['p_after'] is not None else None,
     round(100*(r['p_after']-r['p_before']),2) if r['p_after'] is not None and r['p_before'] is not None else None,
     r['model_version'],r['selection_policy'],q.get('source',''),
     q.get('reviewed',False),10*r['correct'] if r['correct'] is not None else None])

  sessions_header=['Usuario','Grupo','Docente','Grado','Asignatura','ID sesión',
    'Inicio','Última actividad','Tiempo activo sesión (seg)','Tiempo activo sesión (min)']
  sessrows=[]
  for r in sessions:
   st=index.get(r['student_id'])
   if st: sessrows.append([st['code'],st['group_name'],st['professor'],st['degree'],
      nice(r['course']),r['session_id'],r['opened_at'],r['last_ping'],
      rounded(r['active_seconds']),rounded((r['active_seconds'] or 0)/60)])
  views_header=['Usuario','Grupo','Docente','Grado','Asignatura','Unidad','Nombre unidad',
   'Tipo de consulta','Tiempo lectura activo (seg)','Fecha']
  viewrows=[]
  for r in studies:
   st=index.get(r['student_id'])
   if st:viewrows.append(base(st,r['course'],r['unit'])+
      [r['kind'],rounded(r['seconds']),r['viewed_at']])
  tutor_header=['Usuario','Grupo','Docente','Grado','Asignatura','Unidad',
      'Fecha consulta','Apartado apuntes consultado','Pasaje encontrado (1/0)']
  tutorrows=[]
  for r in tutor:
   st=index.get(r['student_id'])
   if st:tutorrows.append([st['code'],st['group_name'],st['professor'],
    st['degree'],nice(r['course']),r['unit'],r['asked_at'],r['source_heading'],r['matched']])

  # Older exam module does not persist course classification nor per-question response times.
  exams_header=['Usuario','Grupo','Docente','Grado','Asignatura',
    'Examen ID','Examen nombre','Temas (registro histórico)','Modalidades',
    'Fecha inicio','Fecha fin','Tiempo de realización (seg)',
    'Tiempo de realización (min)','Preguntas evaluadas','Preguntas correctas',
    'Tasa de acierto (%)','Tasa de fallo (%)','Nota examen (0-10)','Estado']
  examrows=[]
  for r in exam_runs:
   st=index.get(r['student_id'])
   if not st:continue
   n=r['graded_count'] or 0;hits=r['correct_count'] or 0
   duration=iso_seconds(r['started_at'],r['submitted_at'])
   examrows.append([st['code'],st['group_name'],st['professor'],st['degree'],
    'Histórico ADAPTA sin asignatura confirmada',
    r['run_id'],r['title'],r['topics_json'],r['kinds_json'],r['started_at'],
    r['submitted_at'],rounded(duration),rounded(duration/60) if duration is not None else None,
    n,hits,pct(hits,n),pct(n-hits,n),r['score'],
    'Entregado' if r['submitted_at'] else 'No finalizado'])
  glossary=[
    ['Campo','Cálculo/definición','Observación metodológica'],
    ['Usuario','Código institucional seudonimizado del estudiante','No exporta contraseña, invitación ni nombre real'],
    ['Grupo','A/C control; B/D tratamiento adaptativo','Asignación de grupo es dato observado, no implica aleatorización acreditada'],
    ['Asignatura','Microeconomía I o Microeconomía II','No fusionar contenidos ni puntuaciones entre asignaturas'],
    ['Unidad','Unidad ordinal de la guía docente','Micro I: 3 unidades; Micro II: 4 unidades'],
    ['Tiempo medio aplicación / sesión','Suma tiempo activo / número de sesiones detectadas','Tiempo en primer pulso no contado; pestaña oculta no computa'],
    ['Tiempo pregunta','Segundos entre entrega y apertura registrados por servidor','No equivale al tiempo de atención efectiva'],
    ['Tiempo realización examen','Fecha entrega - fecha comienzo','Solo exámenes históricos formalmente registrados'],
    ['Número de intentos','Número de respuestas finalizadas por alumno-curso-unidad','Incluye repeticiones de preguntas'],
    ['Tasa acierto (%)','100 * aciertos / intentos evaluables','No incluye intentos sin respuesta final'],
    ['Tasa fallo (%)','100 * errores / intentos evaluables','Complementaria a tasa de acierto entre observaciones calificables'],
    ['Nota media ejercicios (0-10)','10 * aciertos / ejercicios evaluables','Indicador orientativo, no calificación académica oficial'],
    ['Nota media exámenes (0-10)','Media de resultados de exámenes con asignatura verificada','No imputada cuando la asignatura del examen histórico no está definida'],
    ['Posterior inicial/final','Probabilidad BKT / BKT + red neuronal validada','El posterior no es nota ni evidencia causal'],
    ['Progreso estimado (pp)','100 * (posterior final - posterior inicial)','Variación modelizada, no aumento observado de nota'],
    ['Consulta apuntes','Número de visitas registradas al material de la unidad','No demuestra comprensión'],
    ['Tiempo lectura','Tiempo entre apertura y actualizaciones activas, con límite','Estimación que debe usarse con cautela'],
    ['Sin datos','Celda vacía si no existen observaciones','No se imputa cero a ausencias'],
    ['Exámenes históricos','Proceden de ADAPTA anterior y no tienen curso confirmado','Se muestran por separado y no se atribuyen a Micro I/II']]
  sheets=[
   ('Resumen alumnos',summary_cols,summary),
   ('Por unidad',summary_cols,units),
   ('Preguntas',attempts_header,raw),
   ('Examenes',exams_header,examrows),
   ('Sesiones',sessions_header,sessrows),
   ('Lecturas',views_header,viewrows),
   ('Tutor',tutor_header,tutorrows),
   ('Diccionario',glossary[0],glossary[1:])]
  sheets.extend(build_kpi_sheets(students,attempts,sessions,studies,tutor,mastery,utc()))
  workbook=create_workbook(sheets)
  return StreamingResponse(io.BytesIO(workbook),
   media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
   headers={'Content-Disposition':'attachment; filename="MICRO_ADAPTA_ITS_Investigacion_Completa.xlsx"','Cache-Control':'no-store'})
