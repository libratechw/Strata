"""Validate retained long-context requests, timings and launch conditions, no inference."""
import collections,json,statistics,sys
from pathlib import Path

def main():
    report=Path(sys.argv[1]);long=report/'long-context'
    rows=json.loads((long/'per-request.json').read_text(encoding='utf-8'))
    original=json.loads((report/'per-request.json').read_text(encoding='utf-8'))
    summary=json.loads((long/'summary.json').read_text(encoding='utf-8'))
    outputs={item['request_number']:item for item in json.loads((long/'outputs.json').read_text(encoding='utf-8'))}
    groups=collections.defaultdict(list);hashes=collections.defaultdict(set)
    for row in original+rows:
        if row['group']=='speed' and row['ok']:
            hashes[row['context'],row['target'],row['repetition']].add(row['request_sha256'])
    assert all(len(values)==1 for values in hashes.values()),'Inputs differ across models'
    for row in rows:
        assert row['context'] in (131072,262144)
        if row['ok']:
            assert row['finish_reason'] in ('stop','length')
            assert row['engine']['finish'] not in ('disconnect','error','cancelled')
            assert row['reasoning_chars']>0
            if row['group'] in ('speed','needle'):
                assert row['engine']['reused']==0
                assert abs(row['engine']['prompt_tokens']-row['target'])<=20
                assert row['engine']['engine_generated']<=(512 if row['group']=='speed' else 2048)
                assert row['engine']['prompt_tokens']+(512 if row['group']=='speed' else 2048)<=row['context']
            if row['group']=='needle':
                assert row['recall_pass']==(row['expected_code_word'] in outputs[row['number']]['content'])
        if row['group']=='speed':groups[row['session'],row['target']].append(row)
    for group in summary['speed']:
        success=[row for row in groups[group['session'],group['target']] if row['ok']]
        assert group['successful']==len(success)
        if success:
            for key,values in [('pp_tok_s',[(row['engine']['prompt_tokens']-row['engine']['reused'])*1000/row['engine']['prompt_ms'] for row in success]),
                               ('decode_tok_s',[row['engine']['decode_tok_s'] for row in success]),
                               ('ttft_s',[row['ttft_s'] for row in success]),
                               ('latency_s',[row['client_elapsed_s'] for row in success])]:
                assert group[key]=={'median':statistics.median(values),'min':min(values),'max':max(values)}
    for stage in long.glob('*-stage*'):
        protocol=json.loads((stage/'protocol.json').read_text(encoding='utf-8'))
        assert protocol['commit_fraction']==.95 and protocol['commit_seconds']==30
        for loaded in stage.glob('servers/*-loaded.json'):
            engine=json.loads(loaded.read_text(encoding='utf-8'))['metrics']['engine']
            assert engine['version']=='0.1.43' and engine['max_context']==protocol['context']
            budget=protocol['resident_budget_gib']
            if budget is not None:
                # The budget fits whole expert blobs (largest 2.33 MB here), then reports integer MiB.
                assert 0<=budget*1024-engine['arena_mib']<=4
                environments=list(stage.glob('configs/*.actual-environment.json'))
                assert environments
                for env in environments:
                    actual=json.loads(env.read_text(encoding='utf-8'))
                    assert actual['STRATA_RESIDENT_HEADROOM_GIB']=='1' and actual['STRATA_UNBUFFERED_LOAD']=='0'
    cleanup=list(long.glob('*-stage*/cleanup.json'))
    assert cleanup and all(json.loads(path.read_text())['port18080_closed'] for path in cleanup)
    completion=json.loads((long/'completion.json').read_text())
    assert completion['finished'] and completion['daily_config_unchanged']
    result={'checked':True,'cross_model_matching_inputs':True,'speed_successes':sum(row['group']=='speed' and row['ok'] for row in rows),
        'speed_attempts':sum(row['group']=='speed' for row in rows),'recall_passes':sum(row['group']=='needle' and row.get('recall_pass') is True for row in rows),
        'recall_attempts':sum(row['group']=='needle' for row in rows),'failed_requests':sum(not row['ok'] for row in rows),
        'unattempted_cases':sum(len(profile['unattempted']) for profile in completion['profiles']),
        'all_stage_servers_stopped':True,'daily_config_unchanged':True}
    (long/'measurement-contract-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
