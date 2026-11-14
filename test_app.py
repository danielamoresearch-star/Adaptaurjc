import os,tempfile,sys,io,zipfile,json,xml.etree.ElementTree as ET
from pathlib import Path
os.environ['ADAPTA_TEACHER_PASSWORD']='secure-secret-for-local-tests-2026'
os.environ['ADAPTA_DB']=str(Path(tempfile.mkdtemp())/'test.sqlite3')
sys.path.insert(0,str(Path(__file__).parent))
from fastapi.testclient import TestClient
import server
c=TestClient(server.app)
def ok(r):
 assert r.status_code==200,(r.status_code,r.text[:300]);return r.json()
T=ok(c.post('/api/teacher/login',json={'password':os.environ['ADAPTA_TEACHER_PASSWORD']}))['token']
th={'Authorization':'Bearer '+T}
inv=ok(c.post('/api/teacher/enroll',headers=th,json={'quantity':8,'degree':'ADE','professor':'Profesor de pruebas','assignment':'balanced'}))['enrollments']
assert len(inv)==8
assert all(sum(x['group']==g for x in inv)==2 for g in 'ABCD')
r=c.post('/api/student/login',json={'code':'UINVALID','password':'1234567890123'})
assert r.status_code==401
student=inv[0]
S=ok(c.post('/api/student/login',json={'code':student['code'],'invitation':student['invite'],'password':'safe-student-password'}))['token']
sh={'Authorization':'Bearer '+S}
assert c.post('/api/student/login',json={'code':student['code'],'invitation':student['invite'],'password':'badbadbadbad'}).status_code==401
assert ok(c.get('/api/overview',headers=sh))['attempts']==0
seen=set()
for i in range(6):
    t=ok(c.post('/api/task',headers=sh,json={'phase':'diagnostico'}))
    q=t['question'];seen.add(q['topic']);assert 'answer' not in q and 'explanation' not in q
    # Attempt to submit as correct is unknown to UI but is known to test fixture
    correct=server.BANK[q['id']]['answer']
    result=ok(c.post('/api/answer',headers=sh,json={'task_id':t['task_id'],'answer':correct,'client_seconds':23}))
    assert result['correct'] is True
    replay=ok(c.post('/api/answer',headers=sh,json={'task_id':t['task_id'],'answer':0,'client_seconds':99}))
    assert replay['already_submitted']
assert len(seen)==6
assert ok(c.get('/api/overview',headers=sh))['diagnostic_complete']
for kind in ['mcq','numeric','development','graph']:
    t=ok(c.post('/api/task',headers=sh,json={'phase':'practica','kind':kind,'topic':'Oferta y demanda'}))
    assert t['question']['kind']==kind
    h=ok(c.post(f"/api/task/{t['task_id']}/hint",headers=sh))
    assert h['count']==1
    q=server.BANK[t['question']['id']]
    answer='Ensayo sobre los efectos de los impuestos, la oferta y la demanda, con discusión de elasticidades.' if kind=='development' else q['answer']
    r=ok(c.post('/api/answer',headers=sh,json={'task_id':t['task_id'],'answer':answer,'client_seconds':29}))
    assert (r['correct'] is None if kind=='development' else r['correct']==True)
t=ok(c.post('/api/task',headers=sh,json={'phase':'practica','kind':'numeric'}))
r=ok(c.post('/api/answer',headers=sh,json={'task_id':t['task_id'],'timed_out':True}))
assert r['timed_out'] and not r['correct']
assert c.get('/api/teacher/export',headers=sh).status_code==403
summary=ok(c.get('/api/teacher/overview',headers=th))
assert len(summary['students'])==8
assert summary['students'][0]['answers']>=0
resp=c.get('/api/teacher/export',headers=th)
assert resp.status_code==200,len(resp.content)
with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
    names=z.namelist();assert 'xl/workbook.xml' in names
    for name in names:
        if name.endswith('.xml') or name.endswith('.rels'):ET.fromstring(z.read(name))
    w=z.read('xl/workbook.xml').decode();assert 'Respuestas' in w and 'Dominio_BKT' in w and 'Eventos' in w and 'Análisis_gráficos' in w
assert len(server.BANK)==198
print('PASS: 8 estudiantes creados y equilibrados; 6 diagnósticos; BKT, 4 modalidades, pista, timeout, acceso protegido, Excel con 6 hojas; 198 preguntas.')


# Responsive/PWA public assets without exposing /api to service worker caches.
manifest=c.get('/manifest.webmanifest');assert manifest.status_code==200
m=json.loads(manifest.content);assert m['display']=='standalone' and m['start_url']=='/'
for asset in ('/static/responsive.css','/static/visual_v8.css','/sw.js','/icons/icon-192.png','/icons/icon-512.png'):
    assert c.get(asset).status_code==200,asset
assert b'/api/' in c.get('/sw.js').content and b"startsWith('/api/')" in c.get('/sw.js').content
print('PASS: PWA manifest, responsive CSS, SW, icons; the SW excludes API requests from caching.')
