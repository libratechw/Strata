"""Replay the three interrupted IQ3 prefixes without changing their guards.

Each profile starts a fresh server and replays every original request through
the interrupted request. OS caches and desktop load are not controlled.
"""
import argparse,hashlib,importlib.util,json,shutil,socket,subprocess,time
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime','data','original','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.soak_seconds=0
    assert not a.out.exists(),'Keep previous retry evidence'
    a.out.mkdir(parents=True)
    engine=a.runtime/'engine/strata.exe'
    before=hashlib.sha256((a.runtime/'strata-iq2_xs.json').read_bytes()).hexdigest()
    assert hashlib.file_digest(engine.open('rb'),'sha256').hexdigest()=='223289044f377c97e982cdacddb2e17b5726f63a0439765e3fb3e2bcfdf78656'
    shutil.copyfile(__file__,a.out/'retry_post_reboot_0143.py')
    profiles=[('buffered20',20,a.original/'community_bench_0143.py',a.original,3,False),
              ('buffered16-strict',16,a.original/'community_bench_0143.py',a.original/'iq3-buffered16-supplement',8,False),
              ('buffered16-relaxed',16,a.original/'community_bench_0143_relaxed.py',a.original/'iq3-buffered16-relaxed',9,True)]
    outcomes=[]
    for label,budget,runner,source,speed_count,recall in profiles:
        with socket.socket() as s:assert s.connect_ex(('127.0.0.1',18080))!=0,'Port in use'
        folder=a.out/label;folder.mkdir()
        for sub in ('configs','servers','requests'):(folder/sub).mkdir()
        shutil.copyfile(runner,folder/'frozen_runner.py')
        spec=importlib.util.spec_from_file_location('frozen_'+label.replace('-','_'),runner.resolve())
        b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
        args=argparse.Namespace(runtime=a.runtime,data=a.data,out=folder,soak_seconds=0)
        old=json.loads((a.original/'per-request.json').read_text(encoding='utf-8'))
        old=[row for row in old if row['session']==('iq3_xxs-65536-'+label)]
        old={r['label']:r for r in old if r['model']=='iq3_xxs'}
        r=b.Runner(args);original_popen=b.subprocess.Popen
        baseline=r.monitor.last.copy()
        def launch(command,*pos,**kw):
            if any(str(x).replace('\\','/').endswith('/serve/server.py') for x in command):
                cfg=Path(command[command.index('--config')+1]);data=json.loads(cfg.read_text(encoding='utf-8'))
                data['args'][data['args'].index('--resident-budget-gib')+1]=str(budget)
                b.write(cfg,data)
            return original_popen(command,*pos,**kw)
        target_label='needle-50' if recall else ('speed-60000-0' if budget==20 else 'speed-32768-2')
        b.write(folder/'protocol.json',{'placement':label,'resident_budget_gib':budget,'context':65536,
            'available_ram_guard':{'gib':1.5 if recall else 3,'seconds':15 if recall else 5},
            'commit_guard':{'fraction':.95,'seconds':30},'target_original_stop':target_label,
            'sampling':b.SAMPLING,'thinking':'xhigh','original_requests_replayed_in_order':True,
            'fresh_server_each_profile':True,'os_cache_explicitly_cleared':False,'background_load_controlled':False,
            'source_runner_sha256':hashlib.sha256(runner.read_bytes()).hexdigest()})
        try:
            b.subprocess.Popen=launch
            try:r.start('iq3_xxs',65536)
            finally:b.subprocess.Popen=original_popen
            assert abs(r.get('/metrics')['engine']['arena_mib']-budget*1024)<2
            count=0
            for rep in range(3):
                for target in (4096,32768,60000) if rep!=1 else (60000,32768,4096):
                    if count>=speed_count:break
                    body,_=r.make(target,f'speed-65536-{target}-{rep}');body['seed']=2718+rep
                    r.request(f'speed-{target}-{rep}',body,'speed',target=target,rep=rep);count+=1
            if recall:
                r.conversation()
                for depth in (10,50):
                    body,expected=r.make(60000,f'needle-65536-{depth}',2048,depth)
                    r.request(f'needle-{depth}',body,'needle',target=60000,rep=depth,expected=expected)
        except Exception as e:
            b.write(folder/'failure.json',{'type':type(e).__name__,'error':str(e)})
        finally:
            b.subprocess.Popen=original_popen
            r.stop();r.monitor.done.set();r.monitor.thread.join(timeout=5)
            with socket.socket() as s:closed=s.connect_ex(('127.0.0.1',18080))!=0
            b.write(folder/'cleanup.json',{'owned_server_stopped':r.server is None,'owned_worker_stopped':r.active is None,'port18080_closed':closed})
        comparisons=[{'label':row['label'],'same_request_sha256':row['request_sha256']==old[row['label']]['request_sha256']} for row in r.rows]
        assert all(x['same_request_sha256'] for x,row in zip(comparisons,r.rows) if row['group']!='conversation'),'Fresh replay inputs differ'
        target=next((row for row in r.rows if row['label']==target_label),None)
        outcome={'profile':label,'original_failed_label':target_label,'target_attempted':target is not None,
            'target_ok':target['ok'] if target else False,'target_recall_pass':target.get('recall_pass') if target else None,
            'completed_requests':sum(x['ok'] for x in r.rows),'failed_requests':sum(not x['ok'] for x in r.rows),
            'all_inputs_match':all(x['same_request_sha256'] for x in comparisons),'baseline_sample':baseline}
        b.write(folder/'input-comparison.json',comparisons);b.write(folder/'outcome.json',outcome)
        outcomes.append(outcome);print(json.dumps({'event':'profile_done',**outcome}),flush=True)
    unchanged=before==hashlib.sha256((a.runtime/'strata-iq2_xs.json').read_bytes()).hexdigest()
    (a.out/'completion.json').write_text(json.dumps({'finished':True,'profiles':outcomes,'daily_config_unchanged':unchanged},indent=2)+'\n',encoding='utf-8')
    assert unchanged

if __name__=='__main__':main()
