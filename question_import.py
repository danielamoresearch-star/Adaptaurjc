"""Teacher-only staging of structured question imports. Scanned images require OCR externally."""
import csv,io,json,secrets,zipfile,xml.etree.ElementTree as ET
from fastapi import UploadFile,File,Header,HTTPException
from pydantic import BaseModel
MAX_BYTES=8*1024*1024
COLUMNS=('topic','kind','level','prompt','options','answer','explanation','hint','unit','reference')
def parse_file(name,raw):
 ext=name.rsplit('.',1)[-1].lower()
 if ext=='csv':
  text=raw.decode('utf-8-sig');return list(csv.DictReader(io.StringIO(text)))
 if ext=='xlsx':
  from openpyxl import load_workbook
  wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
  ws=wb.active;rows=ws.iter_rows(values_only=True)
  head=[str(x or '').strip().lower() for x in next(rows)]
  return [dict(zip(head,[str(v) if v is not None else '' for v in row])) for row in rows]
 if ext=='docx':
  with zipfile.ZipFile(io.BytesIO(raw)) as z:root=ET.fromstring(z.read('word/document.xml'))
  ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
  paragraphs=[''.join(n.itertext()).strip() for n in root.findall('.//w:p',ns)]
  text='\n'.join(p for p in paragraphs if p)
 elif ext=='pdf':
  from pypdf import PdfReader
  text='\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(raw)).pages[:80])
 else:raise HTTPException(400,'Formato permitido: CSV, XLSX, DOCX o PDF')
 if len(text.strip())<30:raise HTTPException(422,'No se detectó texto. Si el documento está escaneado, aplica OCR antes de importarlo.')
 # Portable, explicit field syntax for text-based documents.
 blocks=[b.strip() for b in text.replace('\r','').split('---') if b.strip()]
 out=[]
 for b in blocks:
  d={}
  for line in b.splitlines():
   if ':' in line:
    k,v=line.split(':',1);k=k.strip().lower()
    if k in COLUMNS:d[k]=v.strip()
  if d:out.append(d)
 return out
def normalize(r,topics):
 topic=str(r.get('topic','')).strip()
 if topic not in topics:raise ValueError('Tema desconocido: '+topic)
 kind=str(r.get('kind','mcq')).strip().lower()
 if kind not in ('mcq','numeric'):raise ValueError('Tipo no admitido (mcq/numeric)')
 prompt=str(r.get('prompt','')).strip()
 explanation=str(r.get('explanation','')).strip()
 if len(prompt)<12 or len(explanation)<12:raise ValueError('Enunciado y explicación deben tener al menos 12 caracteres')
 level=int(r.get('level',2))
 if level not in (1,2,3):raise ValueError('Nivel fuera de rango')
 options=r.get('options',[])
 if isinstance(options,str):
  try:options=json.loads(options)
  except ValueError:options=[x.strip() for x in options.split('|') if x.strip()]
 if kind=='mcq':
  if len(options)<2 or len(options)>6:raise ValueError('Test requiere 2-6 opciones separadas por |')
  answer=int(r.get('answer',-1))
  if not 0<=answer<len(options):raise ValueError('Respuesta debe ser índice 0 a n-1')
 else:
  options=[];answer=float(str(r.get('answer','')).replace(',','.'))
 return {'topic':topic,'kind':kind,'level':level,'prompt':prompt,'options':options,'answer':answer,'explanation':explanation,'hint':str(r.get('hint','')), 'unit':str(r.get('unit','')), 'reference':str(r.get('reference','')),'origin':'teacher-import-reviewed','tolerance':.02}
def register(app,db,auth,bank,topics,iso):
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS imported_questions(id INTEGER PRIMARY KEY, payload TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)')
  for row in c.execute('SELECT id,payload FROM imported_questions WHERE approved=1'):
   q=json.loads(row['payload']);q['id']=row['id']+1000000;bank[q['id']]=q
 class Approval(BaseModel):ids:list[int]
 @app.post('/api/teacher/import/questions')
 async def upload_questions(file:UploadFile=File(...),authorization:str|None=Header(default=None)):
  auth(authorization,True)
  if not file.filename or file.filename.rsplit('.',1)[-1].lower() not in ('csv','xlsx','docx','pdf'):raise HTTPException(400,'Extensión no permitida')
  raw=await file.read(MAX_BYTES+1)
  if len(raw)>MAX_BYTES:raise HTTPException(413,'Archivo superior a 8 MB')
  try:rows=parse_file(file.filename,raw)
  except HTTPException:raise
  except Exception as e:raise HTTPException(422,'No se pudo interpretar el documento: '+str(e)[:120])
  if len(rows)>1000:raise HTTPException(400,'Máximo 1000 preguntas por archivo')
  valid=[];errors=[]
  for idx,r in enumerate(rows,1):
   try:valid.append(normalize(r,topics))
   except Exception as e:errors.append({'row':idx,'error':str(e)[:160]})
  with db() as c:
   ids=[]
   for q in valid:
    cur=c.execute('INSERT INTO imported_questions(payload,approved,created_at) VALUES(?,0,?)',(json.dumps(q,ensure_ascii=False),iso()))
    ids.append(cur.lastrowid)
  return {'staged':len(ids),'ids':ids,'errors':errors[:100],'notice':'Preguntas pendientes de aprobación docente. No entran en exámenes hasta aprobarlas.'}
 @app.get('/api/teacher/import/questions')
 def pending(authorization:str|None=Header(default=None)):
  auth(authorization,True)
  with db() as c:
   rows=c.execute('SELECT id,payload FROM imported_questions WHERE approved=0 ORDER BY id DESC LIMIT 1000').fetchall()
  return {'questions':[{'id':r['id'],**json.loads(r['payload'])} for r in rows]}
 @app.post('/api/teacher/import/approve')
 def approve(data:Approval,authorization:str|None=Header(default=None)):
  auth(authorization,True)
  if len(data.ids)>1000:raise HTTPException(400,'Demasiadas preguntas')
  with db() as c:
   for id in set(data.ids):
    r=c.execute('SELECT payload FROM imported_questions WHERE id=? AND approved=0',(id,)).fetchone()
    if r:
     q=json.loads(r['payload']);q['id']=id+1000000
     c.execute('UPDATE imported_questions SET approved=1 WHERE id=?',(id,))
     bank[q['id']]=q
  return {'approved':len(set(data.ids))}
