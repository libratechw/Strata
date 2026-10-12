"""Repeat the full IQ3_XXS 64K series with 16 GiB residency and buffered reads.

Run after the primary suite has stopped. Uses the adjacent frozen runner; the
The placement change reduces resident budget from 20 to 16 GiB, retaining OS cache.
"""
import argparse,importlib.util,json,shutil,socket,subprocess,sys,time
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runner',type=Path,required=True);ap.add_argument('--runtime',type=Path,required=True)
    ap.add_argument('--data',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.soak_seconds=3600
    assert not (a.out/'rows.jsonl').exists();a.out.mkdir(exist_ok=True)
    for n in ('configs','servers','requests'):(a.out/n).mkdir(exist_ok=True)
    with socket.socket() as s:assert s.connect_ex(('127.0.0.1',18080))!=0
    spec=importlib.util.spec_from_file_location('frozen_community_bench',a.runner.resolve())
    bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
    bench.write(a.out/'protocol.json',{'model':'iq3_xxs','context':65536,'resident_budget_gib':16,'unbuffered_load':0,
        'sampling':bench.SAMPLING,'reasoning_effort':'xhigh','repetitions':1,'targets':[60000],'depths':[50,90],'server_restart_each_depth':True,
        'reason':'Complete the two outstanding recall cases after available-RAM guard stopped the continuous 16 GiB session',
        'only_change_from_buffered_placement':'16 GiB resident; available RAM guard 1.5 GiB for 15 s; commit guard unchanged','speed_output_cap':512,'old_engine_run':False})
    shutil.copyfile(__file__,a.out/'iq3_direct_supplement.py')
    r=bench.Runner(a);original=bench.subprocess.Popen
    def direct_popen(command,*args,**kwargs):
        if any(str(x).replace('\\','/').endswith('/serve/server.py') for x in command):
            env=kwargs['env'].copy();env['STRATA_UNBUFFERED_LOAD']='0';kwargs['env']=env
            cfg=Path(command[command.index('--config')+1])
            config=json.loads(cfg.read_text(encoding='utf-8'))
            native=config['args']
            native[native.index('--resident-budget-gib')+1]='16'
            bench.write(cfg,config)
            bench.write(cfg.with_suffix('.environment.json'),{k:v for k,v in env.items() if k.startswith('STRATA_')})
        return original(command,*args,**kwargs)
    try:
        for depth in (50,90):
            bench.subprocess.Popen=direct_popen
            try:r.start('iq3_xxs',65536)
            finally:bench.subprocess.Popen=original
            assert abs(r.get('/metrics')['engine']['arena_mib']-16*1024)<2
            r.session=f'iq3_xxs-65536-recall{depth}'
            body,expected=r.make(60000,f'needle-65536-{depth}',2048,depth)
            r.request(f'needle-{depth}',body,'needle',target=60000,rep=depth,expected=expected)
            r.stop()
        bench.write(a.out/'completion.json',{'finished':True,'utc':bench.utc(),'requests':len(r.rows),'failed_requests':sum(not x['ok'] for x in r.rows)})
    except Exception as e:
        bench.write(a.out/'failure.json',{'type':type(e).__name__,'error':str(e)});raise
    finally:
        r.stop();r.monitor.done.set();r.monitor.thread.join(timeout=5)
        with socket.socket() as s:closed=s.connect_ex(('127.0.0.1',18080))!=0
        bench.write(a.out/'cleanup.json',{'owned_server_stopped':r.server is None,'owned_worker_stopped':r.active is None,'port18080_closed':closed})
if __name__=='__main__':main()
