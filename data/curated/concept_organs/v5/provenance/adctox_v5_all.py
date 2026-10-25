"""Dispatch fresh independent labeling sessions; no labels are synthesized here."""
import concurrent.futures, json, pathlib, threading, time, types
import adctox_v5_fresh as F
BASE=F.BASE
condition=threading.Condition()
active=0
control=BASE/'provenance/concurrency.json'

def run_task(task):
 global active
 while True:
  with condition:
   desired=json.loads(control.read_text()).get('workers',256)
   if active<desired:
    active+=1;break
   condition.wait(1)
 try:return task[0].stage,F.run(*task)
 finally:
  with condition:active-=1;condition.notify_all()

def main():
 stages=[f'pass{k}' for k in range(1,6)]
 queues=[sorted((BASE/s/'in').glob('*.json')) for s in stages]
 tasks=[]
 for index in range(max(map(len,queues))):
  for stage,files in zip(stages,queues):
   if index<len(files):tasks.append((types.SimpleNamespace(stage=stage,model='gpt-6.1-sol',effort='high',retries=5),files[index]))
 counts={s:{} for s in stages}
 with concurrent.futures.ThreadPoolExecutor(512) as ex:
  for stage,result in ex.map(run_task,tasks):
   c=counts[stage];c[result]=c.get(result,0)+1
 print(json.dumps({'all_passes':counts}),flush=True)
 if any(c.get('failed') for c in counts.values()):raise SystemExit(1)
if __name__=='__main__':main()
