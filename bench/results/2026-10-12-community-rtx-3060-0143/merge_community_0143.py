"""Combine four raw series into the report's core and retained trial groups.

No inference or input changes. The core IQ3 series uses relaxed 16 GiB speed,
conversation and depth-10 recall, plus fresh-server depth-50/90 recall.
"""
import argparse,json
from pathlib import Path

SERIES=(('primary','-buffered20'),('strict','-buffered16-strict'),
        ('relaxed','-buffered16-relaxed'),('recall','-restarted'))
SOURCE_NAMES={'primary':'primary','strict':'buffered16-strict',
              'relaxed':'buffered16','recall':'recall-restart'}

def load_lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name,_ in SERIES:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True,help='New output directory')
    args=parser.parse_args();rows=[];telemetry=[]
    for name,suffix in SERIES:
        source=getattr(args,name)
        for row in load_lines(source/'rows.jsonl'):
            row['original_number']=row['number'];row['number']=len(rows)+1
            row['source_series']=SOURCE_NAMES[name]
            if row['model']=='iq3_xxs':
                row['session']+=suffix
                if name in ('primary','strict'):
                    row['group']={'speed':'placement_trial','needle':'recall_trial',
                                  'conversation':'conversation_trial'}.get(row['group'],row['group'])
                elif name=='relaxed' and row['group']=='needle' and row['repetition'] in (50,90):
                    row['group']='recall_trial'
            if row.get('output_file'):
                # Names identify the original series; this output contains metrics only.
                row['output_file']=SOURCE_NAMES[name]+'-'+row['output_file']
            rows.append(row)
        for sample in load_lines(source/'telemetry.jsonl'):
            if sample['session'] and sample['session'].startswith('iq3_xxs-65536'):
                sample['session']+=suffix
            telemetry.append(sample)
    args.out.mkdir(parents=True,exist_ok=False)
    for filename,values in (('rows.jsonl',rows),('telemetry.jsonl',telemetry)):
        (args.out/filename).write_text(''.join(json.dumps(value,ensure_ascii=False)+'\n'
            for value in values),encoding='utf-8')
    (args.out/'merge-provenance.json').write_text(json.dumps({
        'source_series':SOURCE_NAMES,'requests':len(rows),
        'core_iq3':'relaxed speed/conversation/depth10; recall restart depth50/90',
        'output_file':'provenance label; generated outputs remain in source directories'
    },indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'requests':len(rows),'core_speed':sum(r['group']=='speed' for r in rows),
        'core_recall':sum(r['group']=='needle' for r in rows)}))

if __name__=='__main__':main()
