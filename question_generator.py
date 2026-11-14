"""Banco paramétrico reproducible; variantes automáticas, no revisión individual."""
import json
from pathlib import Path

NEW_TOPICS=['Oligopolios','Competencia monopolística','Teoría de juegos']
def generate_bank(base, target=10000):
    bank=list(base)
    seen={(q['topic'],q['prompt']) for q in bank}
    next_id=max(q['id'] for q in bank)+1
    topics=list(dict.fromkeys(q['topic'] for q in bank))+[t for t in NEW_TOPICS if t not in {q['topic'] for q in bank}]
    i=0
    while len(bank)<target:
        topic=topics[i%len(topics)]
        k=i//len(topics)
        a=40+((k*7)%160)
        b=1+(k%9)
        c=1+((k//9)%13)
        d=1+((k//117)%11)
        if topic=='Oferta y demanda':
            p=a; q=20+b*p
            prompt=f'En el mercado Qd={q+b*p}−{b}P y Qs={q-c*p}+{c}P. Calcula el precio de equilibrio.'
            ans=p; exp=f'Igualando oferta y demanda, ({b}+{c})P=({b}+{c})×{p}; P={p}.'
        elif topic=='Elasticidad':
            ans=round(b/c,4)
            prompt=f'Si el precio cae un {c}% y la cantidad demandada aumenta un {b}%, calcula el valor absoluto de la elasticidad arco aproximada (cociente de variaciones porcentuales).'
            exp=f'Elasticidad aproximada en valor absoluto = {b}/{c} = {ans}.'
        elif topic=='Teoría del consumidor':
            ans=a
            prompt=f'Un consumidor tiene renta M={a*b} y precio Px={b}. Si solo compra X, ¿cuántas unidades adquiere?'
            exp=f'X=M/Px={a*b}/{b}={a}.'
        elif topic=='Producción y costes':
            ans=b+2*c*a
            prompt=f'Una empresa tiene CT(Q)={d}+{b}Q+{c}Q². Calcula el coste marginal cuando Q={a}.'
            exp=f'CMg(Q)={b}+2×{c}Q; CMg({a})={ans}.'
        elif topic=='Competencia perfecta':
            ans=a
            prompt=f'En competencia perfecta P={b*a}, CMg(Q)={b}Q y el precio cubre el coste variable medio. Calcula Q óptima interior.'
            exp=f'P=CMg implica {b*a}={b}Q y Q={a}.'
        elif topic=='Monopolio':
            ans=a
            prompt=f'Un monopolista enfrenta P(Q)={2*b*a+c}−{b}Q y coste marginal constante {c}. Calcula Q óptima interior.'
            exp=f'IMg={2*b*a+c}−{2*b}Q; igualando a {c}, Q={a}.'
        elif topic=='Oligopolios':
            ans=a
            prompt=f'Duopolio Cournot: P={3*b*a+c}−{b}(q1+q2), costes marginales iguales a {c}. Calcula la producción de cada empresa en equilibrio simétrico.'
            exp=f'En Cournot simétrico q=(A−c)/(3b)=({3*b*a+c}−{c})/(3×{b})={a}.'
        elif topic=='Competencia monopolística':
            ans=a
            prompt=f'Una empresa diferenciada tiene demanda P={2*b*a+c}−{b}Q y CMg={c}. Calcula la producción que maximiza beneficio a corto plazo.'
            exp=f'IMg={2*b*a+c}−{2*b}Q; IMg=CMg implica Q={a}.'
        else:
            ans=a
            prompt=f'Juego simultáneo de dos empresas. Para la empresa A, el beneficio de cooperar es {a} si B coopera y {a-d} si B compite; el beneficio de competir es {a+b} si B coopera y {a+c} si B compite. Si B coopera, ¿cuál es el beneficio de A al cooperar?'
            exp=f'La celda (A coopera, B coopera) asigna a A el beneficio {a}.'
        key=(topic,prompt)
        if key not in seen:
            seen.add(key)
            bank.append(dict(id=next_id,topic=topic,level=1+(k%3),kind='numeric',prompt=prompt,answer=ans,explanation=exp,hint='Identifica la función relevante, sustituye los datos y verifica el resultado.',options=[],unit='',tolerance=0.02,origin='parametric-generated',reference='',rubric=''))
            next_id+=1
        i+=1
        if i>target*20:raise RuntimeError('No se alcanzó la diversidad requerida')
    assert len(bank)==target and len({q['id'] for q in bank})==target
    return bank
