"""pool.json -> data/splits/{pool,train,val,pilot}.jsonl. Сид фиксирован."""
import json, re, random, collections as C
random.seed(42)
M = {'лимит/число': r'не (более|менее|больше|меньше|длиннее|короче)|\d+\s*[-–]?\s*\d*\s*(слов|предложен|знак|символ|абзац|пункт|строк|минут|страниц|статей|вариант)',
'учти/используй/включи': r'\bучти\b|\bучитывай|упомян|опирайс|используй|включи|добавь|укажи|сделай так|обязательно|нужно чтобы|чтобы (в|он|она|это|там|было|я|мы|тебе)',
'запрет/исключение': r'\bбез\b\s+\w+|\bне\s+(используй|упоминай|пиши|надо|нужно|должен|должна|говори)|\bтолько\b|исключительно',
'формат/стиль/тон': r'в стиле|в форме|в формате|в виде|таблиц|список|маркирован|нумерован|кратко|подробно|простым языком|в тоне|\bтон\b|саркастич|официальн|шутлив|юмор|эмоциональн|развёрнут|коротк',
'роль': r'представь|\bты\s+[—-]|веди себя|отвечай как|выступи|возьми на себя роль|запомни, что ты|тебе нужно всегда отвечать',
'условие/требование': r'услови|требован|ограничен|главное|важно|необходимо',
'адресат': r'для (детей|школьник|студент|начинающ|пожил|подрост|менеджер|руководител|ребенк|ребёнк)|целев\w+ аудитори|понятн\w+ (ребенк|ребёнк|даже)',
'фон говорящего': r'\bмне\b.{0,50}\b(лет|работаю|учусь|живу|нужно|надо)\b|\bя\s+(работаю|учусь|живу|являюсь|готовлю|планирую|хочу|только что)\b|моей? (компани|семь|дочер|сын|мам|жен|муж|подруг)|наша компания'}
def head(s): s = s.strip(); return s if len(s) <= 500 else s[:300] + ' … ' + s[-200:]
pool = json.load(open('pool.json', encoding='utf-8'))
pool.sort(key=lambda p: p['instruction'])
for i, p in enumerate(pool):
    p['id'] = f'px{i:04d}'
    h = head(p['instruction']); p['flags'] = [k for k, r in M.items() if re.search(r, h, re.I)]
# 80/20 по стратам (тип задачи x группа)
strata = C.defaultdict(list)
for p in pool: strata[(p['task_type'], p['group'])].append(p)
for k in sorted(strata, key=str):
    g = strata[k]; random.shuffle(g)
    nv = round(len(g) * 0.2) if len(g) >= 3 else 0
    for j, p in enumerate(g): p['split'] = 'val' if j < nv else 'train'
train = [p for p in pool if p['split'] == 'train']; val = [p for p in pool if p['split'] == 'val']
# пилот: по 30 из групп 0/1/2 (с разбросом по типам) + 10 без маркеров
def pick(src, n):
    by = C.defaultdict(list)
    for p in src: by[p['task_type']].append(p)
    for v in by.values(): random.shuffle(v)
    out = []; keys = sorted(by)
    while len(out) < n and any(by.values()):
        for t in keys:
            if by[t] and len(out) < n: out.append(by[t].pop())
    return out
pilot = []
for g in (0, 1, 2): pilot += pick([p for p in train if p['group'] == g], 30)
ids = {p['id'] for p in pilot}
pilot += pick([p for p in train if not p['flags'] and p['id'] not in ids], 10)
for p in pilot: p['pilot'] = True
def dump(name, rows):
    with open(f'splits/{name}.jsonl', 'w', encoding='utf-8') as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + '\n')
import os; os.makedirs('splits', exist_ok=True)
dump('pool', pool); dump('train', train); dump('val', val); dump('pilot', pilot)
print('pool', len(pool), 'train', len(train), 'val', len(val), 'pilot', len(pilot))
print('val groups', C.Counter(p['group'] for p in val), 'train groups', C.Counter(p['group'] for p in train))
print('pilot groups', C.Counter(p['group'] for p in pilot), 'no-flag in pilot', sum(1 for p in pilot if not p['flags']))
print('pool with flags', sum(1 for p in pool if p['flags']), 'task types', len({p['task_type'] for p in pool}))
lens = sorted(len(p['instruction']) for p in pool); print('len chars: median', lens[len(lens)//2], 'p95', lens[int(len(lens)*.95)], 'max', lens[-1])
