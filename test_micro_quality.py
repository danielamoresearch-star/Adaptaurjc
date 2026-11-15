"""FastAPI smoke tests for privacy, inactivity and educational analytics."""
import os,tempfile,io,zipfile,xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path
os.environ['ADAPTA_TEACHER_PASSWORD']='quality-test-private-password-2026'
os.environ['ADAPTA_DB']=str(Path(tempfile.mkdtemp())/'quality.sqlite3')
from fastapi.testclient import TestClient
import server

client=TestClient(server.app)
def check(response,expected=200):
 assert response.status_code==expected,(response.status_code,response.text[:400])
 return response.json() if response.headers.get('content-type','').startswith('application/json') else response

assert check(client.get('/healthz'))['status']=='ok'
teacher=check(client.post('/api/teacher/login',json={'password':os.environ['ADAPTA_TEACHER_PASSWORD']}))['token']
TH={'Authorization':'Bearer '+teacher}
enrol=check(client.post('/api/teacher/enroll',headers=TH,json={
 'quantity':1,'degree':'Economía','professor':'Docente de prueba','assignment':'balanced'
}))['enrollments'][0]
student=check(client.post('/api/student/login',json={
 'code':enrol['code'],'invitation':enrol['invite'],'password':'safe-test-password-2026'
}))['token']
SH={'Authorization':'Bearer '+student}

assert check(client.get('/api/me',headers=SH))['role']=='student'
assert check(client.get('/api/micro/catalog',headers=SH))['curriculum']['micro1']['es']
progress=check(client.get('/api/micro/progress?course=micro1',headers=SH))
assert progress['diagnostic_count']==0 and len(progress['units'])==3
assert check(client.post('/api/session/activity',headers=SH))['idle_timeout_seconds']==900

# Usage data requires an authenticated student; never accept arbitrary users.
session_id='ABCdefghiJKL0123456789'
check(client.post('/api/micro/usage/pulse',headers=SH,json={
 'course':'micro1','session_id':session_id,'visible':True}))
check(client.post('/api/micro/usage/pulse',headers=SH,json={
 'course':'micro1','session_id':session_id,'visible':True}))

# A student cannot fetch the teacher's research workbook.
check(client.get('/api/micro/teacher/export.xlsx',headers=SH),403)
resp=check(client.get('/api/micro/teacher/export.xlsx',headers=TH))
with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
 for name in z.namelist():
  if name.endswith('.xml') or name.endswith('.rels'):ET.fromstring(z.read(name))
 workbook=z.read('xl/workbook.xml').decode()
 for sheet in ['Resumen alumnos','Por unidad','Preguntas','Examenes','Sesiones',
  'Lecturas','Tutor','Diccionario','KPI sesiones','KPI por tema']:
  assert sheet in workbook,sheet
 assert len([n for n in z.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')])==10

status=check(client.get('/api/micro/teacher/storage',headers=TH))
assert 'persistent_disk_verified' in status
backup=check(client.get('/api/micro/teacher/backup.sqlite3',headers=TH))
assert backup.content.startswith(b'SQLite format 3'),backup.content[:32]
check(client.get('/api/micro/teacher/backup.sqlite3',headers=SH),403)

for asset in ['session_idle.js','micro_learning_ui.js','quality.css','icons.js']:
 check(client.get('/static/'+asset))

# Expiry must be checked on the server and expired sessions must be removed.
expired=server.iso(server.utc()-timedelta(minutes=16))
future=server.iso(server.utc()+timedelta(minutes=20))
with server.database() as db:
 db.execute('UPDATE sessions SET last_active_at=?,expires_at=? WHERE token_hash=?',
    (expired,future,server.sha(student)))
check(client.get('/api/me',headers=SH),401)
with server.database() as db:
 assert not db.execute('SELECT 1 FROM sessions WHERE token_hash=?',(server.sha(student),)).fetchone()
check(client.post('/api/session/activity',headers=SH),401)

# Teacher access must remain active and be independent of student idle renewal.
assert check(client.get('/api/me',headers=TH))['role']=='teacher'
print('PASS: teacher backup; storage status; ten-sheet XLSX; curricular separation; session renewal; 15min server expiry; student/teacher permissions; responsive static assets')
