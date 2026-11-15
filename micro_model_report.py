"""Teacher-only predictive validity diagnostics for the BKT/MLP pilot.

Use student-disjoint holdout and compare a frequency baseline, analytical BKT
and the MLP against future observed correctness. This validates a proxy
prediction, NOT the latent mastery state or causal effectiveness.
"""
import json,math,collections
import numpy as np
from fastapi import Header
from micro_intelligence import TwoHiddenMLP,log_loss,PRIOR,_FIXED_SLIP,_FIXED_GUESS

def brier(p,y):
 p=np.asarray(p,dtype=float);y=np.asarray(y,dtype=float)
 return float(np.mean((p-y)**2))
def metrics(p,y):
 return {'log_loss':round(log_loss(p,y),4),'brier':round(brier(p,y),4)}
def report(db,course):
 with db() as c:
  rows=c.execute("""SELECT a.student_id,a.features_json,a.correct
   FROM micro_activities a JOIN students s ON a.student_id=s.id
   WHERE a.course=? AND a.finished_at IS NOT NULL AND a.features_json IS NOT NULL
   AND s.group_name IN ('B','D') ORDER BY a.finished_at DESC LIMIT 6000""",(course,)).fetchall()
 X=[];y=[];ids=[]
 for r in rows:
  try:
   features=json.loads(r['features_json'])
   if len(features)!=6 or any(not math.isfinite(float(v)) for v in features):continue
   if r['correct'] not in (0,1):continue
   X.append([float(v) for v in features]);y.append(r['correct']);ids.append(int(r['student_id']))
  except (ValueError,TypeError,KeyError):continue
 count=len(y);students=len(set(ids));status='insufficient_data'
 base={'course':course,'observations':count,'students':students,'status':status,
  'needed':'At least 160 labeled responses, 16 distinct students and five held-out students',
  'scope':'B/D treatment groups only; correctness prediction, not causal learning effectiveness',
  'models':None,'recommended_model':'BKT baseline'}
 if count<160 or students<16:return base
 X=np.asarray(X,dtype=float);y=np.asarray(y,dtype=float);ids=np.asarray(ids)
 mask=np.asarray(ids%5!=0,dtype=bool)
 held=len(set(ids[~mask]));train=len(set(ids[mask]))
 if len(y[~mask])<25 or len(set(y[mask]))<2 or held<5 or train<10:return dict(base,
  status='insufficient_disjoint_holdout',training_students=train,held_out_students=held)
 model=TwoHiddenMLP();model.train(X[mask],y[mask])
 test=y[~mask]
 nn=np.clip(model.predict(X[~mask]),.001,.999)
 baseline=np.clip(np.repeat(np.mean(y[mask]),sum(~mask)),.001,.999)
 bk=np.clip(X[~mask,0]*(1-_FIXED_SLIP)+(1-X[~mask,0])*_FIXED_GUESS,.001,.999)
 results={'historical_mean':metrics(baseline,test),'BKT':metrics(bk,test),'MLP_16_8':metrics(nn,test)}
 ml_good=results['MLP_16_8']['log_loss']<min(results['BKT']['log_loss'],results['historical_mean']['log_loss'])-.002 and results['MLP_16_8']['brier']<=results['BKT']['brier']+.002
 calibration=[]
 for lo,hi in ((0,.2),(.2,.4),(.4,.6),(.6,.8),(.8,1.01)):
  group=(nn>=lo)&(nn<hi)
  n=int(group.sum())
  if n>=10:calibration.append({'band':[lo,min(hi,1.0)],'n':n,'predicted':round(float(nn[group].mean()),3),'observed':round(float(test[group].mean()),3)})
 return {'course':course,'status':'eligible_pilot_predictor' if ml_good else 'use_BKT_baseline',
  'observations':count,'students':students,'training_students':train,'held_out_students':held,
  'held_out_observations':len(test),'models':results,'calibration_bins':calibration,
  'recommended_model':'MLP pilot' if ml_good else 'BKT baseline',
  'scope':'Only held-out student response correctness; not calibrated mastery, not randomized treatment effect',
  'warning':'Even favorable prediction metrics do not establish an educational benefit; use prospective evaluation and an independent external exam.'}

def register(app,db,auth):
 @app.get('/api/micro/teacher/model-validation')
 def model_validation(authorization:str|None=Header(default=None)):
  auth(authorization,True)
  return {'reports':[report(db,course) for course in ('micro1','micro2')],
    'evaluation':'Held-out students, predictive log loss, Brier, and limited calibration bins',
    'caveat':'Predicted correctness differs from latent topic mastery. Publishable causal claims require a controlled study.'}
