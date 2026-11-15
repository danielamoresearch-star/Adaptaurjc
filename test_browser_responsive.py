"""End-to-end simulated device checks with Playwright.
Runs against a temporary local SQLite database and a disposable student account.
These are browser-engine/viewport tests, not physical-device certification.
"""
import os,sys,tempfile,subprocess,time,json,urllib.request,urllib.error,contextlib
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
base='http://127.0.0.1:18764'
env=dict(os.environ)
env['ADAPTA_DB']=str(Path(tempfile.mkdtemp(prefix='adapta-browser-'))/'test.sqlite3')
env['ADAPTA_TEACHER_PASSWORD']='browser-ci-student-test-secure-2026'
server=subprocess.Popen([sys.executable,'-m','uvicorn','server:app','--host','127.0.0.1','--port','18764'],
    cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
def api(path,method='GET',obj=None,token=None):
 headers={'Content-Type':'application/json'}
 if token:headers['Authorization']='Bearer '+token
 request=urllib.request.Request(base+path,data=json.dumps(obj).encode('utf8') if obj is not None else None,
    headers=headers,method=method)
 with urllib.request.urlopen(request,timeout=12) as r:return json.load(r)
def wait():
 for _ in range(120):
  if server.poll() is not None:raise RuntimeError('Local server process exited before tests')
  try:
   if api('/healthz')['status']=='ok':return
  except Exception:time.sleep(.25)
 raise RuntimeError('Local test server did not start')

try:
 wait()
 teacher=api('/api/teacher/login','POST',{'password':env['ADAPTA_TEACHER_PASSWORD']})['token']
 invite=api('/api/teacher/enroll','POST',{'quantity':1,'degree':'ADE','professor':'Docente CI',
            'assignment':'fixed','fixed_group':'B'},teacher)['enrollments'][0]
 # Use a different test student per browser context to avoid interference.
 with sync_playwright() as p:
  profiles=[
   ('Android 390px','chromium',390,844,True),
   ('iPhone 375px','webkit',375,812,True),
   ('Tablet 768px','chromium',768,1024,True),
   ('Desktop 1440px','chromium',1440,900,False)]
  browsers={}
  for label,engine,w,h,mobile in profiles:
   if engine not in browsers:browsers[engine]=getattr(p,engine).launch(headless=True)
   context=browsers[engine].new_context(viewport={'width':w,'height':h},
      is_mobile=mobile,device_scale_factor=2 if mobile else 1,
      has_touch=mobile,locale='es-ES',ignore_https_errors=True)
   page=context.new_page()
   # Third-party models/audio/CDNs must have a visible fallback when unavailable.
   page.route('**/cdn.jsdelivr.net/**',lambda route:route.abort())
   page.goto(base,wait_until='domcontentloaded',timeout=20000)
   page.locator('#accessCode').fill(invite['code'])
   page.locator('#accessPassword').fill('browser-test-student-password-2026')
   page.locator('#accessInvite').fill(invite['invite'])
   page.locator('#loginBtn').click()
   page.get_by_role('heading',name='Selecciona tu asignatura').wait_for(timeout=15000)
   overflow=page.evaluate('document.documentElement.scrollWidth - window.innerWidth')
   assert overflow<12,(label,'horizontal-overflow',overflow)
   side=page.locator('.side-nav button[data-page="courses"]')
   assert side.count()==1,(label,'course navigation missing')
   assert page.locator('.mobile-dock button[data-page="courses"]').count()==1
   card=page.locator('.micro-course-card.micro1')
   card.click()
   page.get_by_role('heading',name='Microeconomía I').first.wait_for(timeout=10000)
   assert page.locator('#mlStartDiagnostic').count()==1,(label,'diagnostic not available')
   assert page.locator('[data-mltab="notes"]').count()>=1
   assert page.locator('[data-mltab="tutor"]').count()>=1
   for button in page.locator('.ml-bottom button').all():
    size=button.bounding_box()
    if size:assert size['height']>=43,(label,'touch target too small',size)
   wdiff=page.evaluate('document.documentElement.scrollWidth - window.innerWidth')
   assert wdiff<12,(label,'course horizontal-overflow',wdiff)
   print('PASS',label,'selector, diagnostic, notes, tutor, no horizontal overflow',flush=True)
   context.close()
  for browser in browsers.values():browser.close()
finally:
 server.terminate()
 with contextlib.suppress(Exception):server.wait(timeout=5)
