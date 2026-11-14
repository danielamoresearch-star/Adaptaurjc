"""ADAPTA-ITS v8 research prototype. No external LLM, no automatic institutional integration."""
import os,json,sqlite3,hashlib,hmac,secrets,math,random,re,io,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from contextlib import contextmanager
from collections import Counter
from fastapi import FastAPI,HTTPException,Header,Body,Query,Request
from fastapi.responses import FileResponse,StreamingResponse
from pydantic import BaseModel,Field
from excel_export import create_workbook
ROOT=Path(__file__).resolve().parent
DB=Path(os.getenv('ADAPTA_DB',str(ROOT/'adapta_v6.sqlite3')))
TEACHER_PASSWORD=os.environ.get('ADAPTA_TEACHER_PASSWORD','')
if len(TEACHER_PASSWORD)<14:raise RuntimeError('Define ADAPTA_TEACHER_PASSWORD con al menos 14 caracteres.')
from question_generator import generate_bank
BANK={int(q['id']):q for q in generate_bank(json.loads((ROOT/'questions.json').read_text('utf-8')),10000)}
TOPICS=list(dict.fromkeys(q['topic'] for q in BANK.values()))
GROUPS=['A','B','C','D']
MODEL={'prior':.24,'learn':.09,'slip':.12,'guess':.25,'guess_with_hint':.40,'version':'BKT-1.0-uncalibrated'}
app=FastAPI(title='ADAPTA-ITS 8.0',docs_url=None,redoc_url=None)

def utc():return datetime.now(timezone.utc)
def iso(dt=None):return (dt or utc()).isoformat(timespec='milliseconds')
def hashpwd(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),250_000).hex()
def sha(value):return hashlib.sha256(value.encode()).hexdigest()
@contextmanager
def database():
    c=sqlite3.connect(DB,timeout=20)
    c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=20000')
    try:yield c;c.commit()
    except: c.rollback();raise
    finally:c.close()

def initialize():
    DB.parent.mkdir(parents=True,exist_ok=True)
    with database() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY,code TEXT NOT NULL UNIQUE,group_name TEXT NOT NULL,degree TEXT NOT NULL,professor TEXT NOT NULL,invite_hash TEXT,invite_used INTEGER NOT NULL DEFAULT 0,salt TEXT,passhash TEXT,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,student_id INTEGER,role TEXT NOT NULL,expires_at TEXT NOT NULL,FOREIGN KEY(student_id) REFERENCES students(id));
        CREATE TABLE IF NOT EXISTS knowledge(student_id INTEGER NOT NULL,topic TEXT NOT NULL,p REAL NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(student_id,topic),FOREIGN KEY(student_id) REFERENCES students(id));
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,student_id INTEGER NOT NULL,question_id INTEGER NOT NULL,phase TEXT NOT NULL,started_at TEXT NOT NULL,deadline_at TEXT NOT NULL,time_limit INTEGER NOT NULL,hints INTEGER NOT NULL DEFAULT 0,finished INTEGER NOT NULL DEFAULT 0,FOREIGN KEY(student_id) REFERENCES students(id));
        CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL UNIQUE,student_id INTEGER NOT NULL,question_id INTEGER NOT NULL,phase TEXT NOT NULL,ts_start TEXT NOT NULL,ts_end TEXT NOT NULL,elapsed_server REAL NOT NULL,elapsed_client REAL,hints INTEGER NOT NULL,answer TEXT,correct INTEGER,timed_out INTEGER NOT NULL,p_before REAL,p_after REAL,model_version TEXT,FOREIGN KEY(task_id) REFERENCES tasks(id),FOREIGN KEY(student_id) REFERENCES students(id));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,student_id INTEGER,task_id TEXT,ts TEXT NOT NULL,event_type TEXT NOT NULL,details TEXT,FOREIGN KEY(student_id) REFERENCES students(id));
        CREATE INDEX IF NOT EXISTS idx_attempts_student ON attempts(student_id);
        CREATE INDEX IF NOT EXISTS idx_events_student ON events(student_id);
        ''')
initialize()

def event(c,student_id,event_type,task=None,details=None):
    c.execute('INSERT INTO events(student_id,task_id,ts,event_type,details) VALUES(?,?,?,?,?)',(student_id,task,iso(),event_type,json.dumps(details or {},ensure_ascii=False)[:3000]))

def auth(header,teacher=False):
    if not header or not header.startswith('Bearer '):raise HTTPException(401,'Es necesario iniciar sesión.')
    with database() as c:
        r=c.execute('SELECT * FROM sessions WHERE token_hash=?',(sha(header[7:]),)).fetchone()
    if r is None or r['expires_at']<iso():raise HTTPException(401,'Sesión caducada. Vuelve a acceder.')
    if teacher and r['role']!='teacher':raise HTTPException(403,'Acceso exclusivo para el profesorado.')
    return r

def new_session(sid,role):
    token=secrets.token_urlsafe(42)
    expires=iso(utc()+timedelta(hours=10))
    with database() as c:c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(sha(token),sid,role,expires))
    return {'token':token,'role':role,'expires':expires}

class TeacherLogin(BaseModel):password:str
@app.post('/api/teacher/login')
def teacher_login(data:TeacherLogin):
    if not hmac.compare_digest(data.password,TEACHER_PASSWORD):
        time.sleep(.2);raise HTTPException(401,'Credenciales incorrectas')
    return new_session(None,'teacher')

class Enrollment(BaseModel):
    quantity:int=Field(ge=1,le=120)
    degree:str=Field(min_length=2,max_length=90)
    professor:str=Field(min_length=2,max_length=90)
    assignment:str='balanced'
    fixed_group:str|None=None
@app.post('/api/teacher/enroll')
def enroll(data:Enrollment,authorization:str|None=Header(default=None)):
    auth(authorization,True)
    if data.assignment not in ('balanced','fixed') or (data.assignment=='fixed' and data.fixed_group not in GROUPS):raise HTTPException(400,'Asignación incorrecta')
    out=[]
    with database() as c:
        counts=Counter({g:c.execute('SELECT COUNT(*) n FROM students WHERE group_name=?',(g,)).fetchone()['n'] for g in GROUPS})
        for _ in range(data.quantity):
            grp=data.fixed_group if data.assignment=='fixed' else secrets.choice([g for g in GROUPS if counts[g]==min(counts.values())])
            counts[grp]+=1
            code='U'+secrets.token_hex(5).upper();invite=secrets.token_urlsafe(15)
            c.execute('INSERT INTO students(code,group_name,degree,professor,invite_hash,created_at) VALUES(?,?,?,?,?,?)',(code,grp,data.degree.strip(),data.professor.strip(),sha(invite),iso()))
            out.append({'code':code,'group':grp,'invite':invite,'degree':data.degree.strip(),'professor':data.professor.strip()})
    return {'enrollments':out,'notice':'Los códigos de invitación se muestran una sola vez. Descárgalos y distribúyelos de forma privada.'}

class StudentLogin(BaseModel):
    code:str=Field(min_length=3,max_length=30)
    password:str=Field(min_length=10,max_length=128)
    invitation:str=''
@app.post('/api/student/login')
def student_login(data:StudentLogin):
    with database() as c:
        row=c.execute('SELECT * FROM students WHERE code=?',(data.code.strip().upper(),)).fetchone()
        if not row:raise HTTPException(401,'Código no registrado. Pide una invitación a tu profesor.')
        if row['passhash'] is None:
            if not data.invitation or not hmac.compare_digest(sha(data.invitation),row['invite_hash'] or ''):
                raise HTTPException(401,'Necesitas tu invitación personal para activar la cuenta.')
            salt=secrets.token_hex(16)
            c.execute('UPDATE students SET salt=?,passhash=?,invite_used=1,invite_hash=NULL WHERE id=?',(salt,hashpwd(data.password,salt),row['id']))
            event(c,row['id'],'account_activated')
        else:
            if not hmac.compare_digest(hashpwd(data.password,row['salt']),row['passhash']):
                time.sleep(.2);raise HTTPException(401,'Credenciales incorrectas.')
            event(c,row['id'],'login')
    return new_session(row['id'],'student')

@app.post('/api/logout')
def logout(authorization:str|None=Header(default=None)):
    auth(authorization)
    with database() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(sha(authorization[7:]),))
    return {'ok':True}

@app.get('/api/me')
def me(authorization:str|None=Header(default=None)):
    s=auth(authorization)
    if s['role']=='teacher':return {'role':'teacher'}
    with database() as c:r=c.execute('SELECT code,group_name,degree,professor FROM students WHERE id=?',(s['student_id'],)).fetchone()
    return {'role':'student',**dict(r)}

# BKT parameters are design assumptions and not empirically calibrated.
def bkt(prior,correct,with_hint,diagnostic=False):
    slip=MODEL['slip'];guess=MODEL['guess_with_hint'] if with_hint else MODEL['guess']
    prior=max(.001,min(.999,prior))
    likelihood=(prior*(1-slip)+(1-prior)*guess) if correct else (prior*slip+(1-prior)*(1-guess))
    posterior=(prior*(1-slip)/likelihood) if correct else (prior*slip/likelihood)
    learn=0 if diagnostic else MODEL['learn']
    return max(.001,min(.999,posterior+(1-posterior)*learn))

def p_topic(c,sid,topic):
    r=c.execute('SELECT p FROM knowledge WHERE student_id=? AND topic=?',(sid,topic)).fetchone()
    return r['p'] if r else MODEL['prior']

def choose_question(c,sid,phase,topic,kind):
    past=c.execute('''SELECT question_id,COUNT(*) n,MAX(ts_end) last FROM attempts WHERE student_id=? GROUP BY question_id''',(sid,)).fetchall()
    pastmap={r['question_id']:(r['n'],r['last']) for r in past}
    diag_done=set(q['topic'] for a in c.execute("SELECT question_id FROM attempts WHERE student_id=? AND phase='diagnostico'",(sid,)).fetchall() if (q:=BANK.get(a['question_id'])))
    if phase=='diagnostico':
        if len(diag_done)>=len(TOPICS):return None
        available=[q for q in BANK.values() if q['topic'] not in diag_done and q['kind']=='mcq' and q['level']==1]
        # Fixed topic order for baseline coverage.
        available.sort(key=lambda q:(TOPICS.index(q['topic']),q['id']))
        return available[0]
    candidates=[q for q in BANK.values() if (not topic or q['topic']==topic) and (not kind or q['kind']==kind)]
    if not candidates:return None
    latest=c.execute('SELECT question_id FROM attempts WHERE student_id=? ORDER BY id DESC LIMIT 1',(sid,)).fetchone()
    lastid=latest['question_id'] if latest else -1
    counts=Counter()
    for qid,(num,_) in pastmap.items():counts[BANK[qid]['topic']]+=num
    def score(q):
        p=p_topic(c,sid,q['topic']);desired=1 if p<.46 else (2 if p<.78 else 3)
        n,last=pastmap.get(q['id'],(0,None))
        age_days=999 if not last else (utc()-datetime.fromisoformat(last)).total_seconds()/86400
        return (abs(q['level']-desired)*3.2 + n*1.8 + counts[q['topic']]*.065 + (5 if q['id']==lastid else 0) + (1-p)*-.9 - min(age_days,14)*.005 + (1 if q['kind']=='development' else 0))
    candidates.sort(key=lambda q:(score(q),q['id']))
    return candidates[0]

def publicq(q):return {k:q[k] for k in ('id','topic','level','kind','prompt','options','unit','origin','reference','graph','graph_alt','graph_caption') if k in q}

def timelimit(q):return 420 if q['kind']=='development' else (220 if q['kind']=='numeric' else (180 if q['kind']=='graph' else 75+q['level']*30))
class TaskRequest(BaseModel):
    phase:str='practica'
    topic:str|None=None
    kind:str|None=None
@app.post('/api/task')
def new_task(data:TaskRequest,authorization:str|None=Header(default=None)):
    s=auth(authorization)
    if s['role']!='student':raise HTTPException(403)
    if data.phase not in ('diagnostico','practica'):raise HTTPException(400,'Fase inválida')
    if data.topic and data.topic not in TOPICS:raise HTTPException(400,'Tema desconocido')
    if data.kind and data.kind not in ('mcq','numeric','development','graph'):raise HTTPException(400,'Modalidad desconocida')
    sid=s['student_id']
    with database() as c:
        active=c.execute('SELECT * FROM tasks WHERE student_id=? AND finished=0 ORDER BY started_at DESC LIMIT 1',(sid,)).fetchone()
        if active:
            if active['phase']==data.phase:return {'task_id':active['id'],'question':publicq(BANK[active['question_id']]),'deadline':active['deadline_at'],'started':active['started_at'],'time_limit':active['time_limit'],'hints':active['hints']}
            raise HTTPException(409,'Completa la actividad en curso antes de cambiar de fase.')
        q=choose_question(c,sid,data.phase,data.topic,data.kind)
        if q is None:return {'complete':True,'message':'Has completado el diagnóstico de seis competencias.'}
        task_id=secrets.token_urlsafe(24);start=utc();limit=timelimit(q)
        deadline=iso(start+timedelta(seconds=limit))
        c.execute('INSERT INTO tasks(id,student_id,question_id,phase,started_at,deadline_at,time_limit) VALUES(?,?,?,?,?,?,?)',(task_id,sid,q['id'],data.phase,iso(start),deadline,limit))
        event(c,sid,'question_started',task_id,{'question_id':q['id'],'topic':q['topic'],'level':q['level'],'kind':q['kind'],'phase':data.phase,'time_limit':limit})
    return {'task_id':task_id,'question':publicq(q),'deadline':deadline,'started':iso(start),'time_limit':limit,'hints':0}

@app.post('/api/task/{task_id}/hint')
def hint(task_id:str,authorization:str|None=Header(default=None)):
    s=auth(authorization)
    if s['role']!='student':raise HTTPException(403)
    with database() as c:
        task=c.execute('SELECT * FROM tasks WHERE id=? AND student_id=?',(task_id,s['student_id'])).fetchone()
        if not task or task['finished']:raise HTTPException(409,'Pregunta ya cerrada.')
        c.execute('UPDATE tasks SET hints=hints+1 WHERE id=?',(task_id,))
        event(c,s['student_id'],'hint_viewed',task_id,{'count':task['hints']+1})
        return {'hint':BANK[task['question_id']]['hint'],'count':task['hints']+1}

class AnswerRequest(BaseModel):
    task_id:str
    answer:str|int|float|None=None
    client_seconds:float|None=Field(default=None,ge=0,le=36000)
    timed_out:bool=False

def assess(q,answer,timed_out):
    if timed_out:return 0
    if q['kind']=='development':return None
    if q['kind'] in ('mcq','graph'):
        try:return int(int(answer)==q['answer'])
        except (TypeError,ValueError):return 0
    try:
        x=float(str(answer).replace(',','.'))
        return int(math.isfinite(x) and abs(x-q['answer'])<=q['tolerance'])
    except (ValueError,TypeError):return 0

@app.post('/api/answer')
def submit(data:AnswerRequest,authorization:str|None=Header(default=None)):
    s=auth(authorization)
    if s['role']!='student':raise HTTPException(403)
    with database() as c:
        task=c.execute('SELECT * FROM tasks WHERE id=? AND student_id=?',(data.task_id,s['student_id'])).fetchone()
        if not task:raise HTTPException(404,'Actividad no encontrada.')
        q=BANK[task['question_id']]
        if task['finished']:
            old=c.execute('SELECT correct,timed_out,p_before,p_after FROM attempts WHERE task_id=?',(task['id'],)).fetchone()
            return {'correct':None if old['correct'] is None else bool(old['correct']),'timed_out':bool(old['timed_out']),'p_before':old['p_before'],'p_after':old['p_after'],'explanation':q['explanation'],'rubric':q['rubric'],'answer':q['options'][q['answer']] if q['kind'] in ('mcq','graph') else q['answer'],'already_submitted':True}
        done=utc();elapsed=max(0,(done-datetime.fromisoformat(task['started_at'])).total_seconds())
        is_timeout=bool(data.timed_out or done>datetime.fromisoformat(task['deadline_at'])+timedelta(seconds=2))
        correct=assess(q,data.answer,is_timeout)
        before=after=None
        if correct is not None:
            before=p_topic(c,s['student_id'],q['topic'])
            after=bkt(before,bool(correct),task['hints']>0,task['phase']=='diagnostico')
            c.execute('INSERT INTO knowledge(student_id,topic,p,updated_at) VALUES(?,?,?,?) ON CONFLICT(student_id,topic) DO UPDATE SET p=excluded.p,updated_at=excluded.updated_at',(s['student_id'],q['topic'],after,iso(done)))
        text=None if data.answer is None else str(data.answer)[:5000]
        c.execute('UPDATE tasks SET finished=1 WHERE id=?',(task['id'],))
        c.execute('''INSERT INTO attempts(task_id,student_id,question_id,phase,ts_start,ts_end,elapsed_server,elapsed_client,hints,answer,correct,timed_out,p_before,p_after,model_version)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(task['id'],s['student_id'],q['id'],task['phase'],task['started_at'],iso(done),round(elapsed,3),data.client_seconds,task['hints'],text,correct,int(is_timeout),before,after,MODEL['version']))
        event(c,s['student_id'],'answer_submitted',task['id'],{'question_kind':q['kind'],'graph_id':q.get('graph',''),'correct':correct,'timed_out':is_timeout,'elapsed':round(elapsed,2),'hints':task['hints'],'p_before':before,'p_after':after})
    return {'correct':None if correct is None else bool(correct),'timed_out':is_timeout,'p_before':before,'p_after':after,'explanation':q['explanation'],'rubric':q['rubric'],'answer':q['options'][q['answer']] if q['kind'] in ('mcq','graph') else q['answer'],'already_submitted':False}

@app.get('/api/overview')
def overview(authorization:str|None=Header(default=None)):
    s=auth(authorization)
    if s['role']!='student':raise HTTPException(403)
    sid=s['student_id']
    with database() as c:
        student=c.execute('SELECT code,group_name,degree,professor FROM students WHERE id=?',(sid,)).fetchone()
        counts=c.execute('SELECT COUNT(*) n,COUNT(CASE WHEN correct=1 THEN 1 END) right_answers,COUNT(CASE WHEN correct IS NOT NULL THEN 1 END) graded,COUNT(CASE WHEN phase="diagnostico" THEN 1 END) diag FROM attempts WHERE student_id=?',(sid,)).fetchone()
        knowledge={t:round(p_topic(c,sid,t),4) for t in TOPICS}
        logs=c.execute('''SELECT a.ts_end,q.question_id,a.phase,a.correct,a.elapsed_server,a.hints FROM attempts a JOIN tasks q ON q.id=a.task_id WHERE a.student_id=? ORDER BY a.id DESC LIMIT 8''',(sid,)).fetchall()
        trends=[dict(r) for r in logs]
    return {'student':dict(student),'attempts':counts['n'],'correct':counts['right_answers'],'graded':counts['graded'],'diagnostic_count':counts['diag'],'diagnostic_complete':counts['diag']>=len(TOPICS),'knowledge':knowledge,'topics':TOPICS,'recent':trends,'model':MODEL['version']}

class EventRequest(BaseModel):
    event_type:str=Field(min_length=2,max_length=60)
    details:dict=Field(default_factory=dict)
    task_id:str|None=None
@app.post('/api/event')
def log_event(data:EventRequest,authorization:str|None=Header(default=None)):
    s=auth(authorization)
    if s['role']!='student':raise HTTPException(403)
    allowed={'tab_view','mentor_open','mentor_close','feedback_read','timer_expired','page_hidden','page_visible','filter_changed','option_selected','answer_edited','graph_viewed','graph_zoomed','timer_warning'}
    if data.event_type not in allowed:raise HTTPException(400,'Tipo de evento no admitido.')
    with database() as c:
        if data.task_id:
            belongs=c.execute('SELECT 1 FROM tasks WHERE id=? AND student_id=?',(data.task_id,s['student_id'])).fetchone()
            if not belongs:raise HTTPException(403,'Actividad no autorizada')
        event(c,s['student_id'],data.event_type,data.task_id,{str(k)[:60]:str(v)[:200] for k,v in data.details.items() if k in ('page','topic','kind','duration','note','option','seconds_remaining','count','question_id')})
    return {'ok':True}

from question_import import register as register_import
register_import(app,database,auth,BANK,TOPICS,iso)
from exams import register as register_exams
register_exams(app,database,auth,BANK,TOPICS,publicq,p_topic,iso,utc,event)

@app.get('/api/teacher/overview')
def teacher_overview(authorization:str|None=Header(default=None)):
    auth(authorization,True)
    graph_ids=[q['id'] for q in BANK.values() if q['kind']=='graph']
    with database() as c:
        students=[dict(r) for r in c.execute('''SELECT s.id,s.code,s.group_name,s.degree,s.professor,s.passhash IS NOT NULL AS active,COUNT(a.id) answers,
            COALESCE(SUM(CASE WHEN a.correct=1 THEN 1 ELSE 0 END),0) correct,
            COUNT(CASE WHEN a.correct IS NOT NULL THEN 1 END) graded,ROUND(AVG(a.elapsed_server),1) avg_seconds
            FROM students s LEFT JOIN attempts a ON s.id=a.student_id GROUP BY s.id ORDER BY s.group_name,s.code''').fetchall()]
        placeholders=','.join('?' for _ in graph_ids)
        graph=c.execute(f'''SELECT student_id,COUNT(*) n,COALESCE(SUM(correct),0) correct FROM attempts
             WHERE question_id IN ({placeholders}) GROUP BY student_id''',graph_ids).fetchall()
        gmap={x['student_id']:(x['n'],x['correct']) for x in graph}
    for st in students:
        st['graph_attempts'],st['graph_correct']=gmap.get(st['id'],(0,0))
        del st['id']
    return {'students':students,'bank_count':len(BANK),'graph_count':len(graph_ids),'model':MODEL,'groups':GROUPS}

@app.get('/api/teacher/export')
def teacher_export(authorization:str|None=Header(default=None)):
    auth(authorization,True)
    with database() as c:
        answers=[dict(r) for r in c.execute('''SELECT s.code,s.group_name,s.degree,s.professor,a.id attempt_id,a.task_id,a.question_id,a.phase,a.ts_start,a.ts_end,a.elapsed_server,a.elapsed_client,a.hints,a.answer,a.correct,a.timed_out,a.p_before,a.p_after,a.model_version FROM attempts a JOIN students s ON s.id=a.student_id ORDER BY a.id''').fetchall()]
        events=[dict(r) for r in c.execute('''SELECT s.code,s.group_name,s.degree,s.professor,e.ts,e.event_type,e.task_id,e.details FROM events e LEFT JOIN students s ON s.id=e.student_id ORDER BY e.id''').fetchall()]
        skills=[dict(r) for r in c.execute('''SELECT s.code,s.group_name,s.degree,s.professor,k.topic,k.p,k.updated_at FROM knowledge k JOIN students s ON s.id=k.student_id ORDER BY s.code,k.topic''').fetchall()]
        students=[dict(r) for r in c.execute('''SELECT code,group_name,degree,professor,created_at,invite_used,passhash IS NOT NULL AS active FROM students ORDER BY code''').fetchall()]
    arows=[]
    for a in answers:
        q=BANK[a['question_id']];kind=q['kind']
        if a['timed_out']: status='tiempo_agotado'
        elif a['correct'] is None:status='pendiente_revision'
        else:status='correcta' if a['correct'] else 'incorrecta'
        corr=q['options'][q['answer']] if kind in ('mcq','graph') else q['answer']
        display_answer=(q['options'][int(a['answer'])] if kind in ('mcq','graph') and a['answer'] is not None and str(a['answer']).isdigit() and int(a['answer'])<len(q['options']) else a['answer'])
        arows.append([a['code'],a['group_name'],a['degree'],a['professor'],a['attempt_id'],a['task_id'],a['phase'],a['ts_start'],a['ts_end'],a['question_id'],q['topic'],kind,q['level'],q['prompt'],display_answer,corr,status,a['correct'],a['timed_out'],a['hints'],a['elapsed_server'],a['elapsed_client'],a['p_before'],a['p_after'],a['model_version'],q['explanation'],q['origin'],q['reference'],q.get('graph',''),q.get('graph_caption','')])
    # Separate longitudinal summary for plot interpretation, without replacing event-level rows.
    graph_agg={}
    for a in answers:
        q=BANK[a['question_id']]
        if q['kind']!='graph':continue
        k=(a['code'],a['group_name'],a['degree'],a['professor'],q['topic'])
        if k not in graph_agg:graph_agg[k]={'n':0,'correct':0,'seconds':0.,'hints':0}
        stat=graph_agg[k];stat['n']+=1;stat['correct']+=int(a['correct'] or 0)
        stat['seconds']+=float(a['elapsed_server'] or 0);stat['hints']+=int(a['hints'] or 0)
    graph_rows=[[ *k,st['n'],st['correct'],round(st['correct']/st['n']*100,2),
           round(st['seconds']/st['n'],2),round(st['hints']/st['n'],2)] for k,st in sorted(graph_agg.items())]
    sheets=[
    ('Respuestas',['Estudiante','Grupo','Titulación','Profesor','ID intento','ID actividad','Fase','Inicio UTC','Respuesta UTC','ID pregunta','Competencia','Modalidad','Dificultad','Enunciado','Respuesta estudiante','Solución','Resultado','Acierto binario','Tiempo agotado','Pistas','Segundos servidor','Segundos cliente','BKT previo','BKT posterior','Modelo','Explicación','Origen','Fuente','Figura','Interpretación gráfica'],arows),
    ('Eventos',['Estudiante','Grupo','Titulación','Profesor','Fecha UTC','Tipo de evento','ID actividad','Detalles'],[[r[k] for k in ('code','group_name','degree','professor','ts','event_type','task_id','details')] for r in events]),
    ('Análisis_gráficos',['Estudiante','Grupo','Titulación','Profesor','Competencia','Intentos gráficos','Aciertos gráficos','Acierto %','Tiempo medio servidor (s)','Pistas medias'],graph_rows),
    ('Dominio_BKT',['Estudiante','Grupo','Titulación','Profesor','Competencia','P(dominio)','Actualización UTC'],[[r[k] for k in ('code','group_name','degree','professor','topic','p','updated_at')] for r in skills]),
    ('Participantes',['Código','Grupo','Titulación','Profesor','Alta UTC','Invitación utilizada','Cuenta activada'],[[r[k] for k in ('code','group_name','degree','professor','created_at','invite_used','active')] for r in students]),
    ('Metodología',['Parámetro','Valor','Interpretación'],[[k,v,{'prior':'Dominio previo por competencia','learn':'Probabilidad de aprendizaje tras ejercicio (no diagnóstico)','slip':'Error aun sabiendo','guess':'Acierto por conjetura sin pista','guess_with_hint':'Acierto por conjetura tras pista','version':'Modelo no calibrado empíricamente'}[k]] for k,v in MODEL.items()]+[['Nota','No es causal por sí solo','Los grupos deben asignarse bajo un protocolo experimental externo; el registro no identifica efectos causales automáticamente']])]
    data=create_workbook(sheets)
    return StreamingResponse(io.BytesIO(data),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="ADAPTA_ITS_Cohorte_Completa.xlsx"','Cache-Control':'no-store'})

@app.get('/')
def home():return FileResponse(ROOT/'static'/'index.html',headers={'Cache-Control':'no-store'})
@app.get('/static/{file}')
def static(file:str):
    if file not in ('style.css','responsive.css','visual_v8.css','app.js','i18n.js','math.js'):raise HTTPException(404)
    return FileResponse(ROOT/'static'/file)

@app.get('/manifest.webmanifest')
def manifest():
    return FileResponse(ROOT/'static'/'manifest.webmanifest',media_type='application/manifest+json')

@app.get('/icons/{name}')
def icon(name:str):
    if name not in ('icon-180.png','icon-192.png','icon-512.png'):raise HTTPException(404)
    return FileResponse(ROOT/'static'/name,media_type='image/png')

@app.get('/sw.js')
def service_worker():
    return FileResponse(ROOT/'static'/'sw.js',media_type='text/javascript',headers={'Cache-Control':'no-cache','Service-Worker-Allowed':'/'})

@app.get('/figures/{filename}')
def figure(filename:str):
    if not re.fullmatch(r'g\d+\.png',filename):raise HTTPException(404,'Figura no encontrada')
    path=ROOT/'static'/'figures'/filename
    if not path.is_file():raise HTTPException(404,'Figura no encontrada')
    return FileResponse(path,media_type='image/png',headers={'Cache-Control':'public, max-age=86400'})


# HTTPS deployment health probe and defensive response headers.
# Not a substitute for a complete security assessment or institutional DPIA.
@app.get('/healthz',include_in_schema=False)
def healthz():
    with database() as c:
        c.execute('SELECT 1').fetchone()
    return {'status':'ok'}

@app.get('/robots.txt',include_in_schema=False)
def robots():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse('User-agent: *\nDisallow: /\n')

@app.middleware('http')
async def protect_headers(request:Request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
    response.headers['Permissions-Policy']='camera=(), geolocation=(), microphone=()'
    response.headers['Content-Security-Policy']=(
        "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; connect-src 'self'; font-src 'self' https://cdn.jsdelivr.net; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; worker-src 'self'"
    )
    if request.headers.get('x-forwarded-proto','').lower()=='https':
        response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response
