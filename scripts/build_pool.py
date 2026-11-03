"""Один проход по POLLUX test.json -> data/pool.json (запросы, у которых есть критерий №6)."""
import json, collections as C
dec = json.JSONDecoder()
WORK = {'Формальный учет требований из запроса пользователя': 'c6',
        'Соответствие структуре': 'c40',
        'Соответствие структуре плана': 'c48',
        'Оформление ответа согласно заданной структуре': 'c54'}
META = ('task_type', 'task_subtype', 'task_subsubtype', 'difficulty', 'domain', 'is_provocative')
inst = {}; scores = C.defaultdict(list); has6 = set(); buf = ''; n = 0
with open('test.json', encoding='utf-8') as f:
    while True:
        chunk = f.read(1 << 22); buf += chunk; i = 0
        while True:
            while i < len(buf) and buf[i] in ' \n\r\t,[': i += 1
            if i >= len(buf) or buf[i] == ']': break
            try: o, j = dec.raw_decode(buf, i)
            except json.JSONDecodeError: break
            i = j; n += 1
            k = o['instruction']
            if k not in inst: inst[k] = {m: o[m] for m in META}
            c = WORK.get(o['criteria_name'])
            if c:
                scores[k].append((c, o['model_id'], o['criteria_score']))
                if c == 'c6': has6.add(k)
        buf = buf[i:]
        if not chunk: break
def mean(x): return sum(x) / len(x) if x else None
pool = []
for k in inst:
    if k not in has6: continue
    s = scores[k]; per_crit = {}
    for c in ('c6', 'c40', 'c48', 'c54'):
        v = [x[2] for x in s if x[0] == c and x[2] is not None]
        if v: per_crit[c] = mean(v)
    overall = mean(list(per_crit.values()))
    grp = None if overall is None else (2 if overall >= 2 else (1 if overall >= 1 else 0))
    pool.append(dict(instruction=k, **inst[k], crit=per_crit, score=overall, group=grp))
json.dump(pool, open('pool.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('rows', n, 'unique', len(inst), 'pool', len(pool), 'groups', C.Counter(p['group'] for p in pool))
