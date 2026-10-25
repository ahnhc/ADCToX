import argparse, concurrent.futures, datetime, hashlib, json, os, pathlib, subprocess, sys, threading, time
ROOT=pathlib.Path('/home/hyeongchanahn/CONI/adctox')
os.chdir(ROOT)
sys.path.insert(0,str(ROOT/'ml'))
import relabel_v5 as R
import relabel_v5_gpt as G
BASE=ROOT/'data/curated/concept_organs/v5'
LOCK=threading.Lock()

def errors(stage,items,txt):
 try:
  rows=[json.loads(l) for l in txt.splitlines() if l.strip()]
  bad=G.problems(stage,[(i.get('record') or i)['id'] for i in items],txt)
  for row,item in zip(rows,items):
   if stage=='audit':
    if not isinstance(row.get('reason'),str) or not row['reason'].strip() or len(row['reason'])>300: bad.append('reason missing or >300 characters')
    if row.get('verdict')=='ok': continue
    lab=row.get('corrected',{})
   else: lab=row
   if not isinstance(lab.get('basis'),str) or not lab['basis'].strip() or len(lab['basis'])>200: bad.append('basis missing or >200 characters')
   if not isinstance(lab.get('no_axis'),bool):bad.append('no_axis must be boolean')
   for key in ['primary','involved']:
    if not isinstance(lab.get(key),list) or len(lab[key])!=len(set(lab[key])):bad.append('invalid or duplicate axis list')
   if stage=='adjudicate':
    d=row.get('decisions')
    if not isinstance(d,dict) or not set(item['contested_organs'])<=set(d):bad.append('missing contested decisions')
    elif any(not isinstance(v,str) or not v.strip() or len(v)>200 for v in d.values()):bad.append('invalid decision text')
  return bad
 except Exception as exc:return [f'{type(exc).__name__}: {exc}']

def run(a,f):
 items=json.loads(f.read_text());out=BASE/a.stage/'out'/f.with_suffix('.jsonl').name
 if out.exists() and not errors(a.stage,items,out.read_text()):return 'skip'
 out.parent.mkdir(exist_ok=True,parents=True)
 retry_note=''
 for attempt in range(1,a.retries+1):
  stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
  prefix=BASE/'provenance'/f'{a.stage}_{f.stem}_{stamp}'
  raw=pathlib.Path(str(prefix)+'.response.txt')
  prompt=G.instructions(a.stage)+'\n\n'+G.ask(a.stage,items)+'\n\nThis is one isolated labeling call. Use only these instructions and this batch. Do not access files, other labels, tools, or other agents. Return only the requested JSON lines as your final answer. No Markdown fences.'+retry_note
  cmd=['codex','exec','--ephemeral','--ignore-user-config','--json','-m',a.model,'-c',f'model_reasoning_effort="{a.effort}"','-s','read-only','-o',str(raw),'-']
  t=time.monotonic();usage={};bad=[];events=[];code=None
  try:
   p=subprocess.run(cmd,input=prompt,text=True,capture_output=True,timeout=1800,cwd=ROOT)
   code=p.returncode
   pathlib.Path(str(prefix)+'.events.jsonl').write_text(p.stdout)
   pathlib.Path(str(prefix)+'.stderr.txt').write_text(p.stderr)
   for line in p.stdout.splitlines():
    try:events.append(json.loads(line))
    except ValueError:pass
   if any(e.get('type')=='item.completed' and e.get('item',{}).get('type') not in ['agent_message','reasoning'] for e in events):bad.append('model used a tool; isolated output rejected')
   for e in events:
    if e.get('type')=='turn.completed':usage=e.get('usage',{})
   txt=raw.read_text() if raw.exists() else ''
   bad+=errors(a.stage,items,txt)
   if code:bad.append(f'CLI exited {code}')
  except Exception as exc:bad=[f'{type(exc).__name__}: {str(exc)[:200]}'];txt=''
  log=dict(stage=a.stage,batch=f.name,model=a.model,effort=a.effort,attempt=attempt,seconds=round(time.monotonic()-t,1),ok=not bad,problems=bad[:5],input=usage.get('input_tokens'),output=usage.get('output_tokens'),cached_input=usage.get('cached_input_tokens'),reasoning_output=usage.get('reasoning_output_tokens'),timestamp_utc=stamp,transport='codex-exec-fresh-ephemeral',provenance=str(prefix.relative_to(BASE)),raw_response=str(raw.relative_to(BASE)),prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),response_sha256=hashlib.sha256(txt.encode()).hexdigest(),exit_code=code)
  with LOCK:
   with (BASE/'runs.jsonl').open('a') as h:h.write(json.dumps(log)+'\n')
   if not bad:
    tmp=out.with_suffix('.tmp');tmp.write_text(txt.strip()+'\n');tmp.replace(out)
   print(json.dumps({k:log[k] for k in ['stage','batch','ok','seconds','problems']}),flush=True)
  if not bad:return 'ok'
  retry_note='\n\nFormat checks for this batch failed: '+ '; '.join(bad[:5])+'. Generate the full answer again. Each basis must be at most 200 characters, each decision at most 200, each audit reason at most 300.'
  time.sleep(min(30,attempt*5))
 return 'failed'

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--stage',required=True);ap.add_argument('--model',default='gpt-6.1-sol');ap.add_argument('--effort',default='high');ap.add_argument('--workers',type=int,default=32);ap.add_argument('--limit',type=int);ap.add_argument('--retries',type=int,default=3);a=ap.parse_args()
 fs=sorted((BASE/a.stage/'in').glob('*.json'))[:a.limit];counts={}
 with concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
  for v in ex.map(lambda f:run(a,f),fs):counts[v]=counts.get(v,0)+1
 print(json.dumps(dict(stage=a.stage,batches=len(fs),**counts)),flush=True)
 if counts.get('failed'):sys.exit(1)
if __name__=='__main__':main()
