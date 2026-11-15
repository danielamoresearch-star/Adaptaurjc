"""Derived, noncausal engagement KPIs from validated MICRO ADAPTA-ITS logs."""
from collections import defaultdict
from datetime import datetime,timedelta
from statistics import mean,median
from micro_course import CURRICULUM

def parsed(x):
 try:return datetime.fromisoformat(x) if x else None
 except (TypeError,ValueError):return None

def avg(values):
 v=[float(x) for x in values if x is not None]
 return round(mean(v),2) if v else None

def med(values):
 v=[float(x) for x in values if x is not None]
 return round(median(v),2) if v else None

def rate(a,b):
 return round(100*a/b,2) if b else None

def build_kpi_sheets(students,attempts,sessions,studies,tutor,mastery,now):
 by_attempt=defaultdict(list);by_sessions=defaultdict(list);by_reads=defaultdict(list)
 by_tutor=defaultdict(list);by_mastery={}
 for r in attempts:
  if r.get('course') in CURRICULUM:by_attempt[(r['student_id'],r['course'])].append(r)
 for r in sessions:
  if r.get('course') in CURRICULUM:by_sessions[(r['student_id'],r['course'])].append(r)
 for r in studies:
  if r.get('course') in CURRICULUM:by_reads[(r['student_id'],r['course'])].append(r)
 for r in tutor:
  if r.get('course') in CURRICULUM:by_tutor[(r['student_id'],r['course'])].append(r)
 for r in mastery:
  by_mastery[(r['student_id'],r['course'],r['unit'])]=r
 headers=['Usuario','Grupo','Docente','Grado','Asignatura',
  'Sesiones registradas','Minutos activos medidos','Duración media sesión (seg)',
  'Mediana sesión (seg)','Sesiones >=5 min','Días con actividad',
  'Retorno a partir del día siguiente (1/0)','Retorno a partir del día 7 (1/0)',
  'Ejercicios iniciados','Ejercicios terminados','Tasa finalización (%)',
  'Tasa acierto (%)','Variación acierto últimas 5 vs primeras 5 (pp)',
  'Tasa recuperación tras error (%)','Preguntas únicas','Reintentos',
  'Unidades practicadas','Cobertura temario (%)','Diagnóstico completado (%)',
  'Mediana tiempo pregunta (seg)','Consultas apuntes','Minutos lectura registrados',
  'Preguntas NOVA','Consultas NOVA con sección localizada (%)',
  'Nº modalidades practicadas','Posterior medio (%)',
  'Observaciones para mejora longitudinal']
 rows=[];unit_rows=[]
 unit_headers=['Usuario','Grupo','Docente','Grado','Asignatura',
  'Unidad','Nombre unidad','Ejercicios intentados','Ejercicios finalizados',
  'Tasa finalización (%)','Aciertos','Fallos','Tasa acierto (%)',
  'Tasa acierto primera mitad (%)','Tasa acierto segunda mitad (%)',
  'Cambio tasa acierto (pp)','Tiempo mediano pregunta (seg)',
  'Repeticiones mismo ítem','Consultas apuntes','Tiempo apuntes (min)',
  'Interacciones tutor','Posterior inicial (%)','Posterior final (%)',
  'Cambio posterior (pp)','Advertencia metodológica']
 for student in students:
  base=[student['code'],student['group_name'],student['professor'],student['degree']]
  sid=student['id']
  for course,info in CURRICULUM.items():
   key=(sid,course);name='Microeconomía I' if course=='micro1' else 'Microeconomía II'
   attempts_c=sorted(by_attempt[key],key=lambda x:x.get('started_at') or '')
   sessions_c=by_sessions[key];notes_c=by_reads[key];tutor_c=by_tutor[key]
   finished=[a for a in attempts_c if a.get('finished_at')]
   scored=[a for a in finished if a.get('correct') in (0,1)]
   first=[int(a['correct']) for a in scored[:5]]
   last=[int(a['correct']) for a in scored[-5:]]
   longitudinal=rate(sum(last),5)-rate(sum(first),5) if len(scored)>=10 else None
   completed_units={a['unit'] for a in finished if a.get('unit') is not None}
   diagnostic_units={a['unit'] for a in finished if a.get('phase')=='diagnostic' and a.get('unit') is not None}
   days={d.date() for d in
    [parsed(x.get('opened_at')) for x in sessions_c]+
    [parsed(x.get('finished_at')) for x in finished]+
    [parsed(x.get('viewed_at')) for x in notes_c] if d}
   first_day=min(days) if days else None
   observed_days=(now.date()-first_day).days if first_day else -1
   # Return is observed if any distinct active day occurs >=24h/7d after first day.
   # Not defined until observation window allows it.
   retention1=int(any((d-first_day).days>=1 for d in days)) if observed_days>=1 else None
   retention7=int(any((d-first_day).days>=7 for d in days)) if observed_days>=7 else None
   by_question=defaultdict(int)
   for a in finished:by_question[a['question_id']]+=1
   recovery_den=0;recovery_num=0
   for a,b in zip(scored,scored[1:]):
    if a['correct']==0 and a.get('unit')==b.get('unit'):
     recovery_den+=1;recovery_num+=int(b['correct']==1)
   posterior=[by_mastery[(sid,course,u)]['posterior'] for u in range(1,len(info['es'])+1)
    if (sid,course,u) in by_mastery]
   row=base+[name,len(sessions_c),
    round(sum(float(s.get('active_seconds') or 0) for s in sessions_c)/60,2) if sessions_c else None,
    avg([s.get('active_seconds') for s in sessions_c]),
    med([s.get('active_seconds') for s in sessions_c]),
    sum(1 for s in sessions_c if (s.get('active_seconds') or 0)>=300),
    len(days),retention1,retention7,len(attempts_c),len(finished),
    rate(len(finished),len(attempts_c)),rate(sum(a['correct']==1 for a in scored),len(scored)),
    longitudinal,rate(recovery_num,recovery_den),len(by_question),
    sum(v-1 for v in by_question.values() if v>1),
    len(completed_units),rate(len(completed_units),len(info['es'])),
    rate(len(diagnostic_units),len(info['es'])),
    med([a.get('elapsed_sec') for a in finished]),len(notes_c),
    round(sum(n.get('seconds') or 0 for n in notes_c)/60,2),
    len(tutor_c),rate(sum(t.get('matched')==1 for t in tutor_c),len(tutor_c)),
    len({a.get('modality') for a in scored if a.get('modality')}),
    round(100*mean(posterior),2) if posterior else None,
    'Variación descriptiva; no atribuir causalidad ni equiparar posterior con nota']
   rows.append(row)
   for unit,title in enumerate(info['es'],1):
    unit_a=[a for a in attempts_c if a.get('unit')==unit]
    unit_f=[a for a in unit_a if a.get('finished_at')]
    unit_s=[a for a in unit_f if a.get('correct') in (0,1)]
    half=len(unit_s)//2
    first_half=unit_s[:half] if half>=3 else []
    second_half=unit_s[half:] if half>=3 else []
    first_rate=rate(sum(a['correct']==1 for a in first_half),len(first_half))
    last_rate=rate(sum(a['correct']==1 for a in second_half),len(second_half))
    diff=round(last_rate-first_rate,2) if first_rate is not None and last_rate is not None else None
    counted=defaultdict(int)
    for a in unit_f:counted[a['question_id']]+=1
    note_unit=[n for n in notes_c if n.get('unit')==unit]
    tutor_unit=[t for t in tutor_c if t.get('unit')==unit]
    first_bkt=next((a['p_before'] for a in unit_s if a.get('p_before') is not None),None)
    last_bkt=by_mastery.get((sid,course,unit),{}).get('posterior')
    unit_rows.append(base+[name,unit,title,len(unit_a),len(unit_f),
     rate(len(unit_f),len(unit_a)),sum(a['correct']==1 for a in unit_s),
     sum(a['correct']==0 for a in unit_s),rate(sum(a['correct']==1 for a in unit_s),len(unit_s)),
     first_rate,last_rate,diff,med([a.get('elapsed_sec') for a in unit_f]),
     sum(v-1 for v in counted.values() if v>1),len(note_unit),
     round(sum(n.get('seconds') or 0 for n in note_unit)/60,2),
     len(tutor_unit),round(100*first_bkt,2) if first_bkt is not None else None,
     round(100*last_bkt,2) if last_bkt is not None else None,
     round(100*(last_bkt-first_bkt),2) if last_bkt is not None and first_bkt is not None else None,
     'No confundir correlación temporal con aprendizaje causal'])
 return [('KPI sesiones',headers,rows),('KPI por tema',unit_headers,unit_rows)]
