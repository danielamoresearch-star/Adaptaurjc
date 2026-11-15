"""Learning evidence and source-grounded tutor for MICRO ADAPTA-ITS.

Bayesian knowledge tracing is operational from the first response. A two-hidden-layer
MLP is fitted only after enough consent-governed observations and only if a
held-out-student validation split improves predictive log loss. The MLP estimates
response likelihoods for the Bayesian update; these are *unvalidated instructional
estimates*, not calibrated psychological measures.
"""
import math,re,unicodedata,json,collections,time
import numpy as np

PRIOR=0.24
LEARN=0.08
_FIXED_SLIP=0.12
_FIXED_GUESS=0.25
_MODEL_CACHE={}

def clip(x,lo=0.001,hi=0.999):
 return min(hi,max(lo,float(x)))

def bayesian_update(p,correct,slip=_FIXED_SLIP,guess=_FIXED_GUESS,learn=True):
 """Posterior under a two-state knowledge-tracing emission model."""
 p=clip(p);slip=clip(slip,0.02,0.45);guess=clip(guess,0.02,0.49)
 if correct:
  post=p*(1-slip)/(p*(1-slip)+(1-p)*guess)
 else:
  post=p*slip/(p*slip+(1-p)*(1-guess))
 return clip(post+(1-post)*LEARN if learn else post)

def model_features(prior,level,elapsed,past_accuracy,experience,note_reads):
 return [
  clip(prior),min(1.,max(0.,level/3.)),
  min(1.,max(0.,math.log1p(max(0.,elapsed))/math.log1p(600.))),
  clip(past_accuracy,0,1),
  min(1.,math.log1p(max(0,experience))/math.log1p(80.)),
  min(1.,max(0,note_reads)/10.)
 ]

def sigmoid(x):
 return 1/(1+np.exp(-np.clip(x,-25,25)))

class TwoHiddenMLP:
 """Tiny deterministic NumPy sigmoid MLP, with 16 and 8 hidden neurons."""
 def __init__(self):
  rng=np.random.default_rng(703)
  self.w1=rng.normal(0,.19,(6,16));self.b1=np.zeros(16)
  self.w2=rng.normal(0,.22,(16,8));self.b2=np.zeros(8)
  self.w3=rng.normal(0,.16,(8,1));self.b3=np.zeros(1)
 def predict(self,X):
  h1=np.tanh(X@self.w1+self.b1)
  h2=np.tanh(h1@self.w2+self.b2)
  return sigmoid(h2@self.w3+self.b3).reshape(-1)
 def train(self,X,y,epochs=120):
  n=len(y)
  for step in range(epochs):
   h1=np.tanh(X@self.w1+self.b1);h2=np.tanh(h1@self.w2+self.b2)
   o=sigmoid(h2@self.w3+self.b3).reshape(-1)
   d3=(o-y).reshape((-1,1))/n
   dw3=h2.T@d3+.003*self.w3;db3=d3.sum(0)
   d2=(d3@self.w3.T)*(1-h2*h2)
   dw2=h1.T@d2+.003*self.w2;db2=d2.sum(0)
   d1=(d2@self.w2.T)*(1-h1*h1)
   dw1=X.T@d1+.003*self.w1;db1=d1.sum(0)
   lr=.06/(1+step/60)
   for w,g in [(self.w1,dw1),(self.w2,dw2),(self.w3,dw3),(self.b1,db1),(self.b2,db2),(self.b3,db3)]:
    np.clip(g,-2,2,out=g);w-=lr*g

def log_loss(p,y):
 p=np.clip(np.array(p),1e-5,1-1e-5)
 return float(np.mean(-(y*np.log(p)+(1-y)*np.log(1-p))))

def trained_network(c,course):
 """Student-separated holdout, no current attempt in training (called before insertion)."""
 count=c.execute("""SELECT count(*) n,count(distinct a.student_id) students
                    FROM micro_activities a JOIN students s ON a.student_id=s.id
                    WHERE a.course=? AND a.finished_at IS NOT NULL
                      AND a.features_json IS NOT NULL AND s.group_name IN ('B','D')""",(course,)).fetchone()
 n,n_students=count['n'],count['students']
 if n<160 or n_students<16:return None,'BKT: cold start, insufficient labeled students'
 cached=_MODEL_CACHE.get(course)
 if cached and n<cached[0]+40:return cached[1],cached[2]
 records=c.execute("""SELECT a.student_id,a.features_json,a.correct
                      FROM micro_activities a JOIN students s ON a.student_id=s.id
                      WHERE a.course=? AND a.finished_at IS NOT NULL
                        AND a.features_json IS NOT NULL AND s.group_name IN ('B','D')
                      ORDER BY a.finished_at DESC LIMIT 6000""",(course,)).fetchall()
 X=[];y=[];mask=[];student_ids=[]
 for row in records:
  try:
   features=json.loads(row['features_json'])
   if not isinstance(features,list) or len(features)!=6:continue
   X.append(features);y.append(int(row['correct']))
   mask.append(int(row['student_id'])%5!=0);student_ids.append(int(row['student_id']))
  except (ValueError,TypeError):pass
 if len(X)<160:return None,'BKT: insufficient features'
 X=np.array(X,dtype=float);y=np.array(y,dtype=float);mask=np.array(mask,dtype=bool)
 if sum(~mask)<25 or len(set(y[mask]))<2 or len(set(np.array(student_ids)[~mask]))<5 or len(set(np.array(student_ids)[mask]))<10:
  return None,'BKT: insufficient independent student holdout'
 model=TwoHiddenMLP()
 model.train(X[mask],y[mask])
 score=log_loss(model.predict(X[~mask]),y[~mask])
 baseline=log_loss(np.repeat(np.mean(y[mask]),sum(~mask)),y[~mask])
 bkt_p=np.clip(X[~mask,0]*(1-_FIXED_SLIP)+(1-X[~mask,0])*_FIXED_GUESS,.001,.999)
 bkt_score=log_loss(bkt_p,y[~mask])
 nn_brier=float(np.mean((model.predict(X[~mask])-y[~mask])**2))
 bkt_brier=float(np.mean((bkt_p-y[~mask])**2))
 if score>=min(baseline,bkt_score)-.002 or nn_brier>bkt_brier+.002:
  _MODEL_CACHE[course]=(n,None,'BKT: neural pilot did not beat both baseline and BKT on held-out students')
  return None,'BKT: neural pilot did not beat both baseline and BKT on held-out students'
 version='BKT+MLP16x8 pilot (held-out logloss %.3f vs BKT %.3f)'%(score,bkt_score)
 _MODEL_CACHE[course]=(n,model,version)
 return model,version

def posterior_update(c,course,p,correct,features,diagnostic=False):
 if diagnostic:return bayesian_update(p,correct,learn=False),'BKT diagnostic'
 model,version=trained_network(c,course)
 if model is None:return bayesian_update(p,correct),'BKT v2'
 x=np.array([features],dtype=float)
 mastered=x.copy();mastered[0,0]=.98
 unmastered=x.copy();unmastered[0,0]=.02
 # Emission probabilities constrained to distinguish the mastered state.
 p1=clip(float(model.predict(mastered)[0]),.65,.97)
 p0=clip(float(model.predict(unmastered)[0]),.08,.45)
 p1=max(p1,p0+.20)
 return bayesian_update(p,correct,slip=1-p1,guess=p0),version

STOPWORDS={
 'es':{'en','de','la','el','las','los','un','una','por','para','que','como','es','son','me','explica','porqué','porque','del','y','con','al','sobre','este','esta','tengo','duda','no','entiendo','pregunta','ejemplo','puedes','más','que'},
 'en':{'how','the','what','why','which','where','an','a','or','to','i','is','are','please','and','in','on','for','with','about','does','do','me','this','my','explain'}
}
def tokens(s,lang):
 s=unicodedata.normalize('NFD',s.lower())
 s=''.join(c for c in s if unicodedata.category(c)!='Mn')
 return [w for w in re.findall(r'[a-z]{3,}',s) if w not in STOPWORDS.get(lang,STOPWORDS['es'])]

def grounded_tutor(lesson,question,lang='es',last_failed=None):
 """Local bag-of-terms retrieval. No invented claims and no raw internet content."""
 segments=[]
 for section in lesson.get('sections',[]):
  head=section.get('heading','')
  for p in section.get('parts',[]):
   txt=p.get('text','')
   if txt and len(txt)>=30:segments.append((head,txt,p.get('figure_id')))
 query=collections.Counter(tokens(question,lang))
 if not query:
  return {'answer':('Pregunta por un concepto concreto de estos apuntes.' if lang=='es' else 'Ask about a specific concept from these notes.'),
          'source':lesson.get('title',''),'matched':False}
 doc_freq=collections.Counter()
 for _,t,_ in segments:doc_freq.update(set(tokens(t,lang)))
 results=[]
 for head,txt,fid in segments:
  term=collections.Counter(tokens(head+' '+txt[:2200],lang))
  overlap=sum(query[k]*(1+math.log(1+len(segments)/(1+doc_freq[k])))*min(term.get(k,0),3) for k in query)
  if overlap:results.append((overlap,head,txt,fid))
 if not results:
  return {'answer':('No encuentro una explicación suficientemente relacionada en los apuntes de este tema. Prueba a preguntar por una fórmula o término concreto.' if lang=='es' else 'I cannot find a sufficiently related explanation in these course notes. Try naming a specific formula or term.'),
          'source':lesson.get('title',''),'matched':False}
 _,head,txt,fid=max(results,key=lambda x:x[0])
 prefix='Según los apuntes, en «%s»: '%head if lang=='es' else 'According to the course notes, under "%s": '%head
 answer=prefix+txt[:850].strip()
 if len(txt)>850:answer+='…'
 return {'answer':answer,'source':lesson.get('title',''),'section':head,
         'figure_id':fid,'matched':True,'method':'lexical retrieval (local, grounded in uploaded notes)'}
