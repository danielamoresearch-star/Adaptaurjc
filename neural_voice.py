"""Optional server-side neural narration. Requires OPENAI_API_KEY and explicit student click."""
import os,json,urllib.request,urllib.error
from fastapi import Header,HTTPException
from fastapi.responses import Response
from pydantic import BaseModel,Field
class Narration(BaseModel):
 text:str=Field(min_length=1,max_length=1200)
 language:str='es'
def register(app,auth):
 @app.post('/api/voice/neural')
 def neural_voice(data:Narration,authorization:str|None=Header(default=None)):
  auth(authorization)
  key=os.getenv('OPENAI_API_KEY','').strip()
  if not key:raise HTTPException(503,'Voz neuronal no configurada; se utilizará la voz del navegador.')
  lang='es' if data.language.startswith('es') else 'en'
  payload={'model':'tts-1-hd','voice':'nova','input':data.text,'response_format':'mp3','speed':1.0}
  req=urllib.request.Request('https://api.openai.com/v1/audio/speech',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
  try:
   with urllib.request.urlopen(req,timeout=25) as res:audio=res.read(2500000)
  except (urllib.error.URLError,TimeoutError) as e:raise HTTPException(502,'Proveedor de voz temporalmente no disponible')
  return Response(content=audio,media_type='audio/mpeg',headers={'Cache-Control':'no-store'})
