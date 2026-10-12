"""Validate recorded measurement contracts, without running inference."""
import argparse,collections,json
from pathlib import Path
OUT=None
def load(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('out',type=Path)
    OUT=parser.parse_args().out
    rows=[json.loads(x) for x in (OUT/'rows.jsonl').read_text(encoding='utf-8').splitlines()] if (OUT/'rows.jsonl').exists() else load('per-request.json')
    assert load('protocol.json')['engine']['version']=='0.1.43'
    assert len({x['number'] for x in rows})==len(rows)
    core=[x for x in rows if x['group']=='speed'];groups=collections.defaultdict(list)
    hashes=collections.defaultdict(set)
    for row in rows:
        assert row['context'] in (65536,131072)
        assert not (row['model']=='iq3_xxs' and row['context']==131072)
        if row['ok']:
            assert row['engine']['finish'] not in ('cancelled','error')
            assert row['finish_reason'] in ('stop','length')
            assert row['reasoning_chars']>0
            if row['group'] in ('speed','soak','placement_trial'):
                assert row['engine']['reused']==0
                assert abs(row['engine']['prompt_tokens']-row['target'])<=20
                assert row['engine']['engine_generated']<=512
        if row['group']=='speed':
            groups[row['session'],row['target']].append(row)
            hashes[row['context'],row['target'],row['repetition']].add(row['request_sha256'])
    assert len(groups)==15 and len(core)==45
    assert all(len(x)==3 and {r['repetition'] for r in x}=={0,1,2} for x in groups.values())
    assert all(len(x)==1 for x in hashes.values()),'Mismatched input/sampling across models'
    assert all(x['ok'] for x in core)
    assert load('soak-completion.json')['completed'] and load('soak-completion.json')['elapsed_seconds']>=3600
    assert all(x['ok'] for x in rows if x['group']=='soak')
    assert load('cleanup.json')['port18080_closed'] and load('iq3-buffered16-cleanup.json')['port18080_closed']
    assert load('iq3-recall-restart-cleanup.json')['port18080_closed']
    assert load('daily-config-verification.json')['unchanged']
    needles=[x for x in rows if x['group']=='needle']
    assert len(needles)==9
    result={'checked':True,'speed_requests':len(core),'speed_groups':len(groups),'matched_inputs':True,
        'soak':load('soak-completion.json'),'recall_passes':sum(x.get('recall_pass') is True for x in needles),
        'recall_completed_cases':len(needles),'recall_attempts':len(needles)+sum(x['group']=='recall_trial' for x in rows),
        'all_speed_attempts':sum(x['group'] in ('speed','placement_trial') for x in rows),
        'failed_requests':sum(not x['ok'] for x in rows),
        'conversation_turns':sum(x['group']=='conversation' for x in rows)}
    (OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()
