"""Collect raw long-context stages without changing source measurements."""
import argparse,json
from pathlib import Path

def collect(sources):
    rows=[];samples=[];stages=[];seen=set()
    folders=sorted((folder for source in sources for folder in source.glob('*-stage*')),
                   key=lambda folder:folder.name)
    for folder in folders:
        if not (folder/'protocol.json').exists():
            # A paused orchestration can leave an unused preparation directory.
            if (folder/'rows.jsonl').exists():raise ValueError(f'Missing protocol for recorded requests: {folder}')
            continue
        protocol=json.loads((folder/'protocol.json').read_text(encoding='utf-8'))
        if folder.name in seen:raise ValueError(f'Duplicate measured stage label: {folder.name}')
        seen.add(folder.name)
        budget=protocol['resident_budget_gib']
        suffix=f'-resident{budget}' if budget is not None else '-native'
        stages.append({'folder':folder.name,'protocol':protocol})
        if (folder/'rows.jsonl').exists():
            for line in (folder/'rows.jsonl').read_text(encoding='utf-8').splitlines():
                row=json.loads(line);row['original_number']=row['number'];row['number']=len(rows)+1
                row['session']+=suffix;row['source_stage']=folder.name
                row['resident_budget_gib']=budget;row['available_floor_mib']=protocol['available_floor_mib']
                row['commit_guard_fraction']=protocol['commit_fraction']
                row['commit_guard_seconds']=protocol['commit_seconds']
                if row.get('output_file'):row['output_file']=folder.name+'/'+row['output_file']
                rows.append(row)
        if (folder/'telemetry.jsonl').exists():
            for line in (folder/'telemetry.jsonl').read_text(encoding='utf-8').splitlines():
                sample=json.loads(line)
                if sample['session']:sample['session']+=suffix
                sample['source_stage']=folder.name
                samples.append(sample)
    if not stages:raise ValueError('No measured stage protocols found')
    return rows,samples,stages

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',nargs='+',type=Path,required=True,help='One or more raw output directories')
    parser.add_argument('--out',type=Path,required=True,help='New combined metrics directory')
    args=parser.parse_args();rows,samples,stages=collect(args.sources)
    args.out.mkdir(parents=True,exist_ok=False)
    for name,values in (('rows.jsonl',rows),('telemetry.jsonl',samples)):
        (args.out/name).write_text(''.join(json.dumps(value,ensure_ascii=False)+'\n' for value in values),encoding='utf-8')
    (args.out/'stage-provenance.json').write_text(json.dumps(stages,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'stages':len(stages),'requests':len(rows),'failed_requests':sum(not row['ok'] for row in rows)}))

if __name__=='__main__':main()
