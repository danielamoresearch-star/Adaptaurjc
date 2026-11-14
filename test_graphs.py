"""Integration checks for Matplotlib figure questions, server scoring, events, and spreadsheet export."""
import os, tempfile, sys, io, zipfile, xml.etree.ElementTree as ET, json
from pathlib import Path
os.environ['ADAPTA_TEACHER_PASSWORD']='test-only-very-long-secure-pass'
os.environ['ADAPTA_DB']=str(Path(tempfile.mkdtemp())/'data.sqlite3')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
import server
app=TestClient(server.app)
def post(path,data,h=None):
    r=app.post('/api/'+path,json=data,headers=h or {})
    assert r.status_code==200,(path,r.status_code,r.text[:300]);return r.json()
def get(path,h=None):
    r=app.get(path if path.startswith('/') else '/api/'+path,headers=h or {})
    assert r.status_code==200,(path,r.status_code,r.text[:300]);return r
teacher=post('teacher/login',{'password':os.environ['ADAPTA_TEACHER_PASSWORD']})
th={'Authorization':'Bearer '+teacher['token']}
rec=post('teacher/enroll',{'quantity':1,'degree':'ADE','professor':'Docente','assignment':'fixed','fixed_group':'C'},th)['enrollments'][0]
stu=post('student/login',{'code':rec['code'],'password':'long-student-password-2026','invitation':rec['invite']})
sh={'Authorization':'Bearer '+stu['token']}
for _ in range(6):
    t=post('task',{'phase':'diagnostico'},sh)
    bank=server.BANK[t['question']['id']]
    r=post('answer',{'task_id':t['task_id'],'answer':bank['answer'],'client_seconds':18},sh)
    assert r['correct'] is True
assert get('overview',sh).json()['diagnostic_complete']
q_ids=[q['id'] for q in server.BANK.values() if q['kind']=='graph']
assert len(q_ids)==36,len(q_ids)
for qid in q_ids:
    q=server.BANK[qid]
    assert len(q['options'])==4 and len(set(q['options']))==4
    assert q['options'][q['answer']]
    assert q['graph_alt'] and q['graph_caption']
    path=Path(__file__).parent/'static'/q['graph'].lstrip('/')
    # graph served at /figures/ rather than /static/figures/
    actual=Path(__file__).parent/'static'/'figures'/Path(q['graph']).name
    assert actual.is_file() and actual.read_bytes()[:8]==b'\x89PNG\r\n\x1a\n',str(actual)
r=get('/figures/g163.png');assert r.headers['content-type'].startswith('image/png')
assert app.get('/figures/../../server.py').status_code!=200

t=post('task',{'phase':'practica','kind':'graph','topic':'Elasticidad'},sh)
q=t['question'];assert q['kind']=='graph' and q['graph'].startswith('/figures/')
assert 'answer' not in q and 'explanation' not in q
for name,details in [('graph_viewed',{'question_id':q['id']}),('graph_zoomed',{'question_id':q['id']}),('option_selected',{'question_id':q['id'],'option':1,'count':1}),('timer_warning',{'question_id':q['id'],'seconds_remaining':25})]:
    post('event',{'event_type':name,'task_id':t['task_id'],'details':details},sh)
assert app.post('/api/event',json={'event_type':'freeform','details':{}},headers=sh).status_code==400
correct=server.BANK[q['id']]['answer']
r=post('answer',{'task_id':t['task_id'],'answer':correct,'client_seconds':21.5},sh)
assert r['correct'] is True
teacher_data=get('teacher/overview',th).json()
assert teacher_data['bank_count']==198 and teacher_data['graph_count']==36
assert teacher_data['students'][0]['graph_attempts']==1
assert teacher_data['students'][0]['graph_correct']==1
xlsx=get('teacher/export',th).content
with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
    names=z.namelist();assert len([n for n in names if n.startswith('xl/worksheets/sheet')])==6
    for n in names:
        if n.endswith(('.xml','.rels')):ET.fromstring(z.read(n))
    workbook=z.read('xl/workbook.xml').decode();assert 'Análisis_gráficos' in workbook
    xml=z.read('xl/worksheets/sheet1.xml').decode();assert 'Interpretación' in xml and 'g' in xml
    events=z.read('xl/worksheets/sheet2.xml').decode()
    assert 'graph_zoomed' in events and 'option_selected' in events
print('PASS: 36 PNG de Matplotlib; preguntas sin soluciones públicas; ampliación y selección registradas; respuesta corregida; panel docente; Excel de 6 hojas.')
