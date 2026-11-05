"""The six checks requested in section 7, with no new scoring or model execution."""
from common import *

def main():
    c=cfg();lock=json.loads((C/'recount_v1.initial.lock.json').read_text());first=json.loads((O/'first_calculation.json').read_text());inputs=json.loads((D/'provenance/inputs.lock.json').read_text())
    assert lock['locked_at']<first['at'] and inputs['at']<first['at']
    checks=[dict(check='설정을 첫 계산 전에 잠갔다',status='PASS',locked_at=lock['locked_at'],first_calculation_at=first['at'],config_sha256=lock['config_sha256'])]
    rep=json.loads((D/'tables/reproduction.json').read_text())['rows']
    assert len(rep)==6*9*6
    maximum=max(r['delta_pp'] for r in rep if r['delta_pp'] is not None)
    assert maximum<=.1 and all(r['n_gt']==r['release_n_gt'] for r in rep)
    checks.append(dict(check='채점 기준 칸·완전성 RELEASE table4 τ 1배 0.1%p 내 일치',status='PASS',comparisons=len(rep),max_delta_pp=maximum))
    summaries=json.loads((D/'tables/judgment_summary.json').read_text())['rows'];nonempty=empty=0;max_sum_error=0.
    for site in SITES:
        for prior in PRIORS:
            stem=f'{site}__{prior}';z=loadz(O/'scenes'/stem/'reference_rows.npz');saved=loadz(cells_path(site,prior),['score_cell_1p0','row_owner'])
            assert np.array_equal(z['case_id'],saved['score_cell_1p0']);assert np.array_equal(z['row_owner'],saved['row_owner'])
            core=loadz(JA/'core_points'/f'{stem}.npz',['source_index','patch_id']);t=loadz(FT/'targets'/f'{stem}.npz',['judge_region','patch_id']);ix=core['source_index'];assert np.array_equal(t['patch_id'][ix],core['patch_id'])
            owned=z['row_owner']>=0;assert np.array_equal(z['judge_region'][owned],t['judge_region'][ix][z['row_owner'][owned]])
            # Explicit independent four-rule predicate; free-space and unknown never pass.
            exact=owned&(((z['case_id']==0)&(z['judge_region']==0))|((z['case_id']==1)&(z['judge_region']==2))|((z['case_id']==2)&(z['judge_region']==1))|((z['case_id']==4)&(z['judge_region']==4)))
            assert np.array_equal(z['judgment_correct'],exact)
            total=next(r for r in summaries if (r['site'],r['prior'],r['rule'],r['case_id'])==(site,prior,'본 방법','all'))
            assert total['n_correct']==int(exact.sum())
            matrix=json.loads((D/'tables'/stem/'judgment_matrix.json').read_text())['rows']
            for r in matrix:
                assert sum(r[name+'_n'] for name in REGIONS.values())==r['n_gt']
                if r['n_gt']:
                    nonempty+=1;err=abs(sum(r[name+'_pct'] for name in REGIONS.values())-100);max_sum_error=max(max_sum_error,err);assert err<1e-9
                else:
                    empty+=1;assert all(r[name+'_pct'] is None for name in REGIONS.values())
    checks.append(dict(check='판단은 네 경우의 정확 일치만 맞음',status='PASS',scenes=6,free_space_and_unknown_never_correct=True))
    checks.append(dict(check='판단 표 비어 있지 않은 행 비율 합 100%',status='PASS',nonempty_rows=nonempty,empty_rows_not_applicable=empty,max_sum_error_pp=max_sum_error))
    runtime=json.loads((D/'provenance/docker_runtime.json').read_text());assert runtime['device_requests'] in [None,[]]
    assert runtime['read_only_rootfs'] and runtime['network_mode']=='none' and runtime['runtime']=='runc'
    assert not any(c['execution'][k] for k in ['training','render','mesh_generation'])
    checks.append(dict(check='학습·렌더·메시 재생성 없음',status='PASS',execution=c['execution'],runtime_evidence='provenance/docker_runtime.json',note='new work is table aggregation, cached-surface closest-point query and section intersection, static plotting'))
    writable=[m['Destination'] for m in runtime['mounts'] if m['RW']]
    assert set(writable)=={'/recount','/cfg','/docs'}
    boundary=json.loads((D/'provenance/write_boundary.json').read_text());assert boundary['new_paths_outside_scope']==[] and boundary['changed_prior_tracked_paths']==[]
    checks.append(dict(check='지정한 네 폴더 밖에 쓰지 않음',status='PASS',writable_container_mounts=writable,host_edit_scope='scripts/phd/main_recount_v1 plus other three authorized folders',boundary_evidence='provenance/write_boundary.json',note='Git metadata for authorized final commit/push is operational metadata'))
    dump(D/'validation.json',dict(at=now(),status='PASS',checks=checks,scientific_verdict=None))
    print(json.dumps(dict(status='PASS',checks=6,maximum_delta_pp=maximum,nonempty_rows=nonempty,empty_rows=empty),ensure_ascii=False))

if __name__=='__main__':main()
