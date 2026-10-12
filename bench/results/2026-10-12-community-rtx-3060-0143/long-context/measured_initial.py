"""Fill long-context speed/recall cells using the frozen 0.1.43 protocol."""
import argparse,hashlib,importlib.util,json,shutil,socket,time
from pathlib import Path

ENGINE_SHA='223289044f377c97e982cdacddb2e17b5726f63a0439765e3fb3e2bcfdf78656'

def write(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('runtime','data','runner','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();a.runtime=a.runtime.resolve();a.data=a.data.resolve();a.runner=a.runner.resolve()
    assert not a.out.exists(),'Preserve existing measurements'
    with socket.socket() as s:assert s.connect_ex(('127.0.0.1',18080))!=0,'Existing service on port 18080'
    assert hashlib.file_digest((a.runtime/'engine/strata.exe').open('rb'),'sha256').hexdigest()==ENGINE_SHA
    daily=a.runtime/'strata-iq2_xs.json';before=hashlib.sha256(daily.read_bytes()).hexdigest()
    a.out.mkdir(parents=True);shutil.copyfile(__file__,a.out/Path(__file__).name)
    profiles=[('q2_0',262144),('iq2_xs',262144),('iq3_xxs',131072),('iq3_xxs',262144)]
    write(a.out/'protocol.json',{'profiles':profiles,'version':'0.1.43','engine_sha256':ENGINE_SHA,
        'source_runner_sha256':hashlib.sha256(a.runner.read_bytes()).hexdigest(),
        'speed_lengths_128k':[4096,32768,120000],'speed_lengths_262k':[4096,32768,120000,260000],
        'repetitions':3,'speed_cap':512,'recall_cap':2048,'recall_depths':[10,50,90],
        'thinking':'xhigh','sampling':{'temperature':1,'top_p':.95,'top_k':20,'min_p':0,'presence_penalty':0,'repetition_penalty':1},
        'available_guards':[{'mib':1024,'seconds':15},{'mib':500,'seconds':15}],
        'commit_guard':{'fraction':.95,'seconds':30},'request_deadline':None,
        'residency':'primary: native Q2/IQ2, IQ3 16 GiB; failed primary cases may retry resident 24 GiB Q2/IQ2 or 12 GiB IQ3',
        'no_prior_engine_run':True,'no_soak_repeated':True,'retry_only_unfinished_cases':True})
    outcomes=[]
    for model,ctx in profiles:
        lengths=[4096,32768,120000]+([260000] if ctx==262144 else [])
        tasks=[]
        for rep in range(3):
            for length in lengths if rep!=1 else reversed(lengths):
                tasks.append({'label':f'speed-{length}-{rep}','group':'speed','target':length,'rep':rep})
        for depth in (10,50,90):tasks.append({'label':f'needle-{depth}','group':'needle','target':lengths[-1],'rep':depth})
        pending=tasks.copy();attempts=[]
        primary_budget=16 if model=='iq3_xxs' else None
        stages=[(1024,primary_budget),(500,primary_budget),(500,12 if model=='iq3_xxs' else 24)]
        for stage,(floor,budget) in enumerate(stages):
            if not pending:break
            folder=a.out/f'{model}-{ctx}-stage{stage}';folder.mkdir()
            for sub in ('configs','servers','requests'):(folder/sub).mkdir()
            text=a.runner.read_text(encoding='utf-8')
            assert 'mem.available<3*1024**3' in text and 't-self.low>=5:' in text
            text=text.replace('mem.available<3*1024**3',f'mem.available<{floor}*1024**2')
            text=text.replace('t-self.low>=5:', 't-self.low>=15:')
            text=text.replace('available RAM <3 GiB for >=5 s',f'available RAM <{floor} MiB for >=15 s')
            frozen=folder/'frozen_runner.py';frozen.write_text(text,encoding='utf-8')
            spec=importlib.util.spec_from_file_location('long_frozen',frozen)
            b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
            args=argparse.Namespace(runtime=a.runtime,data=a.data,out=folder,soak_seconds=0)
            r=b.Runner(args);original_popen=b.subprocess.Popen
            def launch(command,*pos,**kw):
                if budget is not None and any(str(x).replace('\\','/').endswith('/serve/server.py') for x in command):
                    config=Path(command[command.index('--config')+1]);cfg=json.loads(config.read_text())
                    if '--resident-budget-gib' in cfg['args']:
                        cfg['args'][cfg['args'].index('--resident-budget-gib')+1]=str(budget)
                    else:cfg['args']+=['--resident-experts','--resident-budget-gib',str(budget)]
                    b.write(config,cfg)
                    kw['env'].update(STRATA_RESIDENT_HEADROOM_GIB='1',STRATA_UNBUFFERED_LOAD='0')
                return original_popen(command,*pos,**kw)
            write(folder/'protocol.json',{'model':model,'context':ctx,'stage':stage,'resident_budget_gib':budget,
                'available_floor_mib':floor,'available_seconds':15,'commit_fraction':.95,'commit_seconds':30,
                'planned':pending.copy(),'fresh_server':True,'os_cache_cleared':False})
            stopped=False;error=None
            try:
                b.subprocess.Popen=launch
                try:r.start(model,ctx)
                finally:b.subprocess.Popen=original_popen
                for task in pending.copy():
                    depth=task['rep'] if task['group']=='needle' else None
                    maximum=2048 if depth else 512
                    tag=f'needle-{ctx}-{depth}' if depth else f'speed-{ctx}-{task["target"]}-{task["rep"]}'
                    body,expected=r.make(task['target'],tag,maximum,depth)
                    if not depth:body['seed']=2718+task['rep']
                    row=r.request(task['label'],body,task['group'],target=task['target'],rep=task['rep'],expected=expected)
                    # Ordinary failures remain recorded; only resource stops retry.
                    pending.remove(task)
            except b.ProtectionError as e:
                stopped=True;error=str(e)
            except Exception as e:
                error=f'{type(e).__name__}: {e}'
            finally:
                b.subprocess.Popen=original_popen
                r.stop();r.monitor.done.set();r.monitor.thread.join(timeout=5)
                with socket.socket() as s:closed=s.connect_ex(('127.0.0.1',18080))!=0
                write(folder/'cleanup.json',{'owned_server_stopped':r.server is None,'owned_worker_stopped':r.active is None,'port18080_closed':closed})
            outcome={'folder':folder.name,'protection_stop':stopped,'error':error,'requests':len(r.rows),
                'successful':sum(row['ok'] for row in r.rows),'pending':pending.copy()}
            write(folder/'completion.json',outcome);attempts.append(outcome)
            print(json.dumps({'event':'stage_complete',**outcome}),flush=True)
            write(a.out/'progress.json',{'completed_profiles':outcomes,'current_profile':[model,ctx],'stages':attempts})
            if not stopped:break
            # A lower available-RAM floor cannot fix a commit stop; change residency next.
            if stage==0 and error and 'commit' in error:stages[1]=stages[2]
        outcomes.append({'model':model,'context':ctx,'attempts':attempts,'unattempted':pending})
        write(a.out/'progress.json',{'completed_profiles':outcomes})
    unchanged=before==hashlib.sha256(daily.read_bytes()).hexdigest()
    write(a.out/'completion.json',{'finished':True,'profiles':outcomes,'daily_config_unchanged':unchanged})
    assert unchanged

if __name__=='__main__':main()
