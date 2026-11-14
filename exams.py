"""Exams: server-side authorization, immutable question selection and scoring."""
import json, secrets, sqlite3, math
from datetime import datetime,timezone,timedelta
from fastapi import HTTPException,Header
from pydantic import BaseModel,Field

def register(app,db,auth,bank,topics,publicq,p_topic,iso,utc,event):
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS exam_specs(
          id TEXT PRIMARY KEY, creator_id INTEGER, creator_role TEXT NOT NULL,
          title TEXT NOT NULL, topics_json TEXT NOT NULL, kinds_json TEXT NOT NULL,
          question_count INTEGER NOT NULL, duration_minutes INTEGER NOT NULL,
          adaptive INTEGER NOT NULL, published INTEGER NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS exam_runs(
          id TEXT PRIMARY KEY, spec_id TEXT NOT NULL, student_id INTEGER NOT NULL,
          questions_json TEXT NOT NULL, started_at TEXT NOT NULL, deadline_at TEXT NOT NULL,
          submitted_at TEXT, answers_json TEXT NOT NULL DEFAULT '{}',
          score REAL, correct_count INTEGER, graded_count INTEGER,
          UNIQUE(spec_id,student_id),FOREIGN KEY(spec_id) REFERENCES exam_specs(id));
        CREATE TABLE IF NOT EXISTS exam_news(
          id TEXT PRIMARY KEY,topic TEXT NOT NULL,title TEXT NOT NULL,source TEXT NOT NULL,
          published_date TEXT NOT NULL,url TEXT NOT NULL,prompt TEXT NOT NULL,
          options_json TEXT NOT NULL,correct_index INTEGER NOT NULL,
          explanation TEXT NOT NULL,reviewed_at TEXT NOT NULL);
        """)
    class Spec(BaseModel):
        title:str=Field(min_length=3,max_length=120)
        topics:list[str]=Field(min_length=1,max_length=9)
        kinds:list[str]=Field(min_length=1,max_length=4)
        question_count:int=Field(ge=1,le=100)
        duration_minutes:int=Field(ge=5,le=180)
        adaptive:bool=True
        published:bool=False
    class News(BaseModel):
        topic:str
        title:str=Field(min_length=5,max_length=180)
        source:str=Field(min_length=3,max_length=120)
        published_date:str
        url:str
        prompt:str=Field(min_length=15,max_length=2000)
        options:list[str]=Field(min_length=2,max_length=6)
        correct_index:int
        explanation:str=Field(min_length=15,max_length=3000)
    class Answer(BaseModel):
        answer:str|int|float|None=None
    def user(header):return auth(header)
    def spec_row(c,id):
        r=c.execute('SELECT * FROM exam_specs WHERE id=?',(id,)).fetchone()
        if not r:raise HTTPException(404,'Examen no encontrado')
        return r
    def allowed(r,s):
        return s['role']=='teacher' or (r['published'] or (r['creator_role']=='student' and r['creator_id']==s['student_id']))
    def choices(c,spec,sid):
        ts=json.loads(spec['topics_json']);ks=json.loads(spec['kinds_json'])
        candidates=[q for q in bank.values() if q['topic'] in ts and q['kind'] in ks and q['kind']!='development']
        # News is entered by a teacher with source metadata; not automatically fact-checked.
        if 'news' in ks:
            for r in c.execute('SELECT * FROM exam_news').fetchall():
                if r['topic'] in ts:
                    candidates.append({'id':'news:'+r['id'],'topic':r['topic'],'kind':'news','level':2,
                      'prompt':r['prompt'],'options':json.loads(r['options_json']),'answer':r['correct_index'],
                      'explanation':r['explanation'],'origin':'teacher-reviewed-news','reference':r['url'],
                      'news_title':r['title'],'news_source':r['source'],'news_date':r['published_date']})
        if len(candidates)<spec['question_count']:raise HTTPException(400,'No hay suficientes preguntas en las modalidades seleccionadas.')
        rng=secrets.SystemRandom()
        if spec['adaptive']:
            # Freeze the adaptive blueprint at exam start, never alter the exam after answers.
            def score(q):
                p=p_topic(c,sid,q['topic']);desired=1 if p<.46 else 2 if p<.78 else 3
                return abs(q['level']-desired)*2+rng.random()
            candidates.sort(key=score)
            # Avoid domination by a single topic.
            selected=[];bytopic={t:[] for t in ts}
            for q in candidates:bytopic[q['topic']].append(q)
            while len(selected)<spec['question_count']:
                advanced=False
                for t in ts:
                    if bytopic[t] and len(selected)<spec['question_count']:
                        selected.append(bytopic[t].pop(0));advanced=True
                if not advanced:break
        else:
            selected=rng.sample(candidates,spec['question_count'])
        return [q['id'] for q in selected]
    def question(c,qid):
        if isinstance(qid,int):return bank[qid]
        r=c.execute('SELECT * FROM exam_news WHERE id=?',(qid.removeprefix('news:'),)).fetchone()
        if not r:raise HTTPException(409,'Noticia del examen no disponible')
        return {'id':qid,'topic':r['topic'],'kind':'news','level':2,'prompt':r['prompt'],
          'options':json.loads(r['options_json']),'answer':r['correct_index'],
          'explanation':r['explanation'],'origin':'teacher-reviewed-news','reference':r['url'],
          'news_title':r['title'],'news_source':r['source'],'news_date':r['published_date']}
    def visible(q):
        d={k:q[k] for k in ('id','topic','kind','level','prompt','options','unit','graph','graph_alt','graph_caption','reference','news_title','news_source','news_date') if k in q}
        return d
    @app.post('/api/exams')
    def create_exam(data:Spec,authorization:str|None=Header(default=None)):
        s=user(authorization)
        if len(set(data.topics))!=len(data.topics) or any(t not in topics for t in data.topics):raise HTTPException(400,'Temas inválidos')
        if len(set(data.kinds))!=len(data.kinds) or any(k not in ('mcq','graph','numeric','news') for k in data.kinds):raise HTTPException(400,'Modalidades inválidas')
        if s['role']=='student' and data.published:raise HTTPException(403,'Solo el profesor publica exámenes')
        if s['role']=='student' and data.question_count>50:raise HTTPException(400,'Autoevaluación: máximo 50 preguntas')
        eid=secrets.token_urlsafe(14)
        with db() as c:
            c.execute('INSERT INTO exam_specs VALUES(?,?,?,?,?,?,?,?,?,?,?)',(eid,s['student_id'] if s['role']=='student' else None,s['role'],data.title,json.dumps(data.topics,ensure_ascii=False),json.dumps(data.kinds),data.question_count,data.duration_minutes,int(data.adaptive),int(data.published and s['role']=='teacher'),iso()))
        return {'id':eid,'title':data.title}
    @app.get('/api/exams')
    def list_exams(authorization:str|None=Header(default=None)):
        s=user(authorization)
        with db() as c:
            if s['role']=='teacher':rows=c.execute('SELECT * FROM exam_specs ORDER BY created_at DESC').fetchall()
            else:rows=c.execute("SELECT * FROM exam_specs WHERE published=1 OR (creator_role='student' AND creator_id=?) ORDER BY created_at DESC",(s['student_id'],)).fetchall()
            return {'exams':[{'id':r['id'],'title':r['title'],'topics':json.loads(r['topics_json']),'kinds':json.loads(r['kinds_json']),'question_count':r['question_count'],'duration_minutes':r['duration_minutes'],'adaptive':bool(r['adaptive']),'published':bool(r['published'])} for r in rows]}
    @app.post('/api/exams/{exam_id}/start')
    def start_exam(exam_id:str,authorization:str|None=Header(default=None)):
        s=user(authorization)
        if s['role']!='student':raise HTTPException(403,'Los exámenes se realizan desde una cuenta de alumno')
        with db() as c:
            spec=spec_row(c,exam_id)
            if not allowed(spec,s):raise HTTPException(403)
            run=c.execute('SELECT * FROM exam_runs WHERE spec_id=? AND student_id=?',(exam_id,s['student_id'])).fetchone()
            if not run:
                ids=choices(c,spec,s['student_id']);now=utc()
                rid=secrets.token_urlsafe(16)
                c.execute('INSERT INTO exam_runs(id,spec_id,student_id,questions_json,started_at,deadline_at) VALUES(?,?,?,?,?,?)',(rid,exam_id,s['student_id'],json.dumps(ids),iso(now),iso(now+timedelta(minutes=spec['duration_minutes']))))
                event(c,s['student_id'],'exam_started',details={'exam_id':exam_id})
                run=c.execute('SELECT * FROM exam_runs WHERE id=?',(rid,)).fetchone()
            ids=json.loads(run['questions_json'])
            return {'run_id':run['id'],'title':spec['title'],'deadline':run['deadline_at'],'started':run['started_at'],
                'finished':run['submitted_at'] is not None,'questions':[visible(question(c,i)) for i in ids],
                'answers':json.loads(run['answers_json'])}
    def finish(c,run):
        ids=json.loads(run['questions_json']);answers=json.loads(run['answers_json'])
        correct=0;graded=0;details=[]
        for qid in ids:
            q=question(c,qid);a=answers.get(str(qid));ok=False
            if q['kind'] in ('mcq','graph','news'):
                try:ok=int(a)==q['answer']
                except (ValueError,TypeError):pass
            elif q['kind']=='numeric':
                try:ok=math.isfinite(float(str(a).replace(',','.'))) and abs(float(str(a).replace(',','.'))-q['answer'])<=q.get('tolerance',.02)
                except (ValueError,TypeError):pass
            graded+=1;correct+=int(ok)
            details.append({'id':qid,'correct':bool(ok),'answer':q['options'][q['answer']] if q['kind'] in ('mcq','graph','news') else q['answer'],'explanation':q['explanation']})
        score=round(10*correct/graded,2) if graded else 0
        c.execute('UPDATE exam_runs SET submitted_at=?,score=?,correct_count=?,graded_count=? WHERE id=?',(iso(),score,correct,graded,run['id']))
        event(c,run['student_id'],'exam_submitted',details={'exam_id':run['spec_id'],'score':score,'correct':correct,'total':graded})
        return {'score':score,'correct':correct,'total':graded,'details':details}
    @app.put('/api/exams/runs/{run_id}/answers/{qid}')
    def save_answer(run_id:str,qid:str,data:Answer,authorization:str|None=Header(default=None)):
        s=user(authorization)
        if s['role']!='student':raise HTTPException(403)
        with db() as c:
            run=c.execute('SELECT * FROM exam_runs WHERE id=? AND student_id=?',(run_id,s['student_id'])).fetchone()
            if not run:raise HTTPException(404)
            if run['submitted_at']:raise HTTPException(409,'Examen finalizado')
            if iso()>run['deadline_at']:finish(c,run);raise HTTPException(409,'Tiempo agotado. Examen cerrado.')
            ids=json.loads(run['questions_json'])
            if qid not in {str(x) for x in ids}:raise HTTPException(403)
            q=question(c,next(x for x in ids if str(x)==qid))
            val=data.answer
            if val is not None and len(str(val))>200:raise HTTPException(400,'Respuesta demasiado larga')
            answers=json.loads(run['answers_json']);answers[qid]=val
            c.execute('UPDATE exam_runs SET answers_json=? WHERE id=?',(json.dumps(answers),run_id))
            return {'ok':True}
    @app.post('/api/exams/runs/{run_id}/finish')
    def finish_exam(run_id:str,authorization:str|None=Header(default=None)):
        s=user(authorization)
        if s['role']!='student':raise HTTPException(403)
        with db() as c:
            run=c.execute('SELECT * FROM exam_runs WHERE id=? AND student_id=?',(run_id,s['student_id'])).fetchone()
            if not run:raise HTTPException(404)
            if run['submitted_at']:
                return {'score':run['score'],'correct':run['correct_count'],'total':run['graded_count'],'details':[],'already_finished':True}
            return finish(c,run)
    @app.post('/api/exams/news')
    def add_news(data:News,authorization:str|None=Header(default=None)):
        auth(authorization,True)
        from urllib.parse import urlparse
        p=urlparse(data.url)
        if p.scheme!='https' or not p.hostname or p.username or p.password:raise HTTPException(400,'Se requiere enlace HTTPS a la fuente primaria')
        if data.topic not in topics or not (0<=data.correct_index<len(data.options)):raise HTTPException(400,'Datos incorrectos')
        try:datetime.strptime(data.published_date,'%Y-%m-%d')
        except ValueError:raise HTTPException(400,'Fecha AAAA-MM-DD')
        nid=secrets.token_urlsafe(12)
        with db() as c:c.execute('INSERT INTO exam_news VALUES(?,?,?,?,?,?,?,?,?,?,?)',(nid,data.topic,data.title,data.source,data.published_date,data.url,data.prompt,json.dumps(data.options,ensure_ascii=False),data.correct_index,data.explanation,iso()))
        return {'id':nid,'reviewed_by':'teacher','notice':'Registro introducido por el docente; el enlace y los hechos requieren comprobación editorial independiente.'}
    @app.get('/api/exams/news')
    def news_list(authorization:str|None=Header(default=None)):
        auth(authorization,True)
        with db() as c:return {'news':[dict(r) for r in c.execute('SELECT id,topic,title,source,published_date,url,reviewed_at FROM exam_news ORDER BY reviewed_at DESC')]}
