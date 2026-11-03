import json,re,collections
C={e['id']:e for e in json.load(open('claude_300.json',encoding='utf-8'))}
S={e['id']:e for e in json.load(open('../data/gold_v3/annot_start.json',encoding='utf-8'))}
def n(s): return re.sub(r'\W+',' ',s.lower()).strip()
def cl(x):
    c=x['context']; cn=x['constraints']
    return dict(ind=bool(x.get('indivisible')), tasks=[n(t) for t in x['tasks']],
        tc=[n(t) for t in cn.get('task_constraints',[])], fc=[n(t) for t in cn.get('format_constraints',[])],
        role=bool(c.get('role')), bg=len(c.get('background',[])), mat=bool(c.get('data') or c.get('text')))
def ov(a,b):
    A=set(a);B=set(b)
    return 1.0 if not A and not B else len(A&B)/max(1,len(A|B))
rows=[]; agg=collections.defaultdict(lambda: collections.defaultdict(list))
for i,e in C.items():
    s=S[i]; a=cl(e); b=cl(s); src=s['source']
    m=dict(ind=a['ind']==b['ind'], ntask=len(a['tasks'])==len(b['tasks']), task_eq=a['tasks']==b['tasks'],
      ntc=len(a['tc'])==len(b['tc']), nfc=len(a['fc'])==len(b['fc']), fc_eq=a['fc']==b['fc'], role=a['role']==b['role'], mat=a['mat']==b['mat'], nbg=a['bg']==b['bg'])
    for k,v in m.items(): agg[src][k].append(v); agg['ВСЕ'][k].append(v)
    rows.append((i,src,m,a,b))
out=["# Сверка разметки Claude с исходными (annot_start.json)\n"]
names=dict(ind="неделимость совпала", ntask="число задач", task_eq="тексты задач (норм.) совпали", ntc="число ограничений задачи", nfc="число формат-ограничений", fc_eq="формат-ограничения совпали (текст)", role="наличие роли", mat="наличие материала", nbg="число фрагментов фона")
for src in ['старая разметка','черновик GPT','ВСЕ']:
    out.append(f"\n## {src} (n={len(agg[src]['ind'])})\n\n| метрика | согласие |\n|---|---|")
    for k,nm in names.items():
        v=agg[src][k]; out.append(f"| {nm} | {sum(v)}/{len(v)} = {100*sum(v)/len(v):.0f}% |")
# расхождения
def line(i,src,m,a,b,e,s,keys):
    return f"- **{i}** [{src}] " + "; ".join(keys)
out.append("\n## Расхождения по неделимости\n")
for i,src,m,a,b in rows:
    if not m['ind']:
        out.append(f"- **{i}** [{src}]: Claude={'неделим' if a['ind'] else 'делим'}, исходная={'неделим' if b['ind'] else 'делим'}. Текст: {C[i]['text'][:110]!r}")
out.append("\n## Расхождения по числу задач (оба делимы)\n")
for i,src,m,a,b in rows:
    if m['ind'] and not a['ind'] and not m['ntask']:
        out.append(f"- **{i}** [{src}]: Claude {len(a['tasks'])} ↔ исходная {len(b['tasks'])}. Claude: {C[i]['tasks']} | исходная: {S[i]['tasks']}")
out.append("\n## Расхождения по формат-ограничениям\n")
for i,src,m,a,b in rows:
    if m['ind'] and not a['ind'] and not m['nfc']:
        out.append(f"- **{i}** [{src}]: Claude fc={C[i]['constraints']['format_constraints']} | исходная fc={S[i]['constraints']['format_constraints']}")
open('compare.md','w',encoding='utf-8').write("\n".join(out))
print("\n".join(out[:50]))
print(len(out))
