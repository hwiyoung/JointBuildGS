"""Factual stop handover with recomputable records, no scientific interpretation."""
import shutil,csv,datetime as dt,zipfile
import numpy as np
from common import *
ROOT=OUT/'r8_recorded_continue';D=ROOT/'stop_diagnostic';OLD=OUT/'r8_lod2_cause'
def read(p):return json.loads(Path(p).read_text())
def lines(p):return [json.loads(x) for x in Path(p).read_text().splitlines()]
def main():
    c=read(CFG/'r8_record_continue.json');stop=read(ROOT/'STOP_LoD2.json');model=Path(c['model']);audit=read(D/'audit.json');render=read(D/'renders/summary.json');b=read(c['boundaries'])
    assert audit['status']=='PASS_SAVED_STOP_STATE' and audit['original_checkpoint_unchanged'];assert render['exact_tile_measurements']==203
    backward=read(ROOT/'verification/backward/result.json');assert backward['status']=='PASS' and backward['optimization_steps']==0
    for lock in ['r8_record_prepare.lock.json','r8_record_runtime.lock.json','r8_record_diagnostics.lock.json']:
        for p,h in read(CFG/lock)['files'].items():assert sha(p)==h,p
    fw=lines(model/'recording/forward_100.jsonl');after=lines(model/'recording/after_iteration_100.jsonl')
    original_trace={r['iteration']:r for r in lines(OUT/'r8/runs/tg_B173nb_b10_LoD2_s0_r8/model/jbgs_trace.jsonl')}
    camera_comparison=[dict(iteration=r['iteration'],recorded=r['camera'],original=original_trace[r['iteration']]['camera'],equal=r['camera']==original_trace[r['iteration']]['camera']) for r in fw if r['iteration'] in original_trace]
    dump(D/'camera_order_comparison.json',dict(rows=camera_comparison,full_unsampled_sequence='not inferred from every100 records',scientific_verdict=None))
    for row in fw:
        assert sum(np.asarray(row['counts']).reshape(-1))==row['gaussians'] and row['invalid_position_count']==0
        assert int(np.asarray(row['overlaps_by_cell']).sum())==row['overlaps']
        assert row['binning_bytes']<=row['free_bytes_before_binning']*.5
    for row in after:assert int(np.asarray(row['counts']).sum())==row['gaussians'] and row['invalid_position_count']==0
    expected=list(range(7100,stop['completed_iteration']//100*100+1,100))
    assert [r['iteration'] for r in after]==expected
    assert [r['iteration'] for r in fw]==expected
    checkpoints=[]
    for receipt in sorted((model/'jbgs_complete').glob('iteration_*/receipt.json')):
        rr=read(receipt);d=receipt.parent;i=rr['iteration'];assert sha(d/'checkpoint.pth')==rr['checkpoint_sha256'];assert sha(d/'point_cloud.ply')==rr['ply_sha256']
        gradient=model/'recording/pre_densification'/f'iteration_{i}/receipt.json';gg=read(gradient);assert sha(gradient.parent/'gradient.npz')==gg['gradient_sha256']
        checkpoints.append(dict(iteration=i,complete_gaussians=rr['gaussians'],pre_densification_gaussians=gg['gaussians'],gradient_accum_nonzero=gg['accum_nonzero'],denom_positive=gg['denom_positive'],checkpoint_sha256=rr['checkpoint_sha256']))
    assert [r['iteration'] for r in checkpoints]==list(range(8000,min(15000,stop['completed_iteration'])+1,1000))
    cross=read(D/'renders/cross.json')['rows'];assert len(cross)==203*64
    for v in render['views']:assert sum(r['overlaps'] for r in cross if r['camera']==v['camera'])==v['overlaps']
    counts=read(D/'counts.json')['rows'];assert sum(r['count'] for r in counts)==stop['gaussians']
    totals=[sum(r['count'] for r in counts if r['tag']==t) for t in range(4)]
    groups=['배경','패치','풀림: 100회 자손','풀림: 그 밖'];s=stop['guard_stats']
    dump(D/'render_views.json',dict(rows=render['views'],scientific_verdict=None));dump(D/'top5.json',dict(rows=render['top5'],scientific_verdict=None))
    for name,rows in [('render_views',render['views']),('render_cross',cross),('top5',render['top5']),('checkpoints',checkpoints)]:
        with (D/(name+'.csv')).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    dump(D/'checkpoints.json',dict(rows=checkpoints,scientific_verdict=None))
    verification=dict(at=stamp(),status='PASS_RECORDS_AND_DELIVERY_INPUTS',forward_records=len(fw),after_iteration_records=len(after),complete_checkpoints=len(checkpoints),
        stopped_state_count=stop['gaussians'],render_exact_tile_views=203,full_render_views=render['full_renders'],count_and_overlap_sums_equal=True,
        original_checkpoint_unchanged=True,original_r8_source_and_runtime_hashes_equal=True,scientific_verdict=None)
    verification['camera_order_equal_in_shared_every100_records']=all(r['equal'] for r in camera_comparison)
    dump(ROOT/'verification/final.json',verification)
    # Resolve concrete lines from the exact executed source.
    code=ROOT/'runtime/rasterizer/cuda_rasterizer/rasterizer_impl.cu';text=code.read_text().splitlines()
    line=lambda word:next(i+1 for i,x in enumerate(text) if word in x)
    notes=[f'# r8 LoD2 기록하며 이어 학습 — 중단 기록', '',f'기록 시각: {stamp()}. 새 계산에는 [이 발주에서 냄]을 적용한다. `scientific_verdict: null`.', '',
        f'- 상태: **{stop["status"]}**. {stop["completed_iteration"]:,}회까지 완료했고 {stop["attempted_iteration"]:,}회에서 멈췄다. 자동 재시도하지 않았다.',
        '- 15,000·30,000회에 도달하지 않아 해당 채점·그림과 7장 틀은 없음. r8 항공 LiDAR는 완료 상태로 보존했고 나머지 여섯 판은 시작하지 않았다.',
        f'- 중단 영상: `{stop["camera"]}`. 저장 가우시안 {stop["gaussians"]:,}개. 저장 단계 `{stop["phase"]}`.',
        f'- 원래 7,000회 완전 상태 SHA-256 `{c["checkpoint_sha256"]}`를 재확인했다. 모델·Adam·난수·영상 순서·목표 계보를 복원했다.', '', '## 멈춤과 보존', '',
        f'- 정렬 버퍼 요구량 {s[2]:,} bytes = {s[2]/2**30:.6f} GiB; 할당 직전 GPU 여유 {s[3]:,} bytes = {s[3]/2**30:.6f} GiB; 절반 {s[3]/2**31:.6f} GiB.',
        f'- 해당 영상의 실제 가우시안–타일 겹침 {s[1]:,}개. 검사식 `required<BinningState>(N) > 0.5 × cudaMemGetInfo.free`는 엄격한 초과다. PyTorch 예약 캐시는 여유량에 더하지 않았다.',
        f'- 실행 CUDA 사본 `{code}`의 {line("size_t binning_chunk_size")}: 버퍼 필요량, {line("cudaMemGetInfo(&jbgs_free")}: 여유량, {line("bool jbgs_stop")}: 비교, {line("throw std::runtime_error")}: 할당 전 멈춤. 원본 정렬은 uint32 ID 두 벌·uint64 key 두 벌(24N bytes), CUB 작업 공간과 정렬 여백을 더한다.',
        f'- r8 수 검사 기준은 6,000회의 {c["count_at_6000"]:,}개 × 3 = {3*c["count_at_6000"]:,}개다. 검사 주기와 불투명도 초기화 유예는 그대로다.',
        f'- 중단 PLY·완전 체크포인트·누적 기울기·출신 snapshot·중단 영상의 개별 겹침 수를 `{stop["stop_dir"]}`에 저장했다. 체크포인트 반복은 {stop["completed_iteration"]:,}이며, 일반 복원 가능 표시는 `{stop["ordinary_resume_ready"]}`이다.',
        ('- 학습 forward에서 버퍼 할당 전에 멈춘 상태는 시도한 반복 직전의 영상 선택·난수·학습률·SH 차수로 복원 경계를 맞췄다. 모델 및 Adam 업데이트는 그 반복에서 실행되지 않았다.' if stop['phase']=='training_forward_before_optimizer' else '- 반복 도중/건강 검사 단계의 실제 상태를 저장했다. 복원 경계 표시는 receipt의 phase와 ordinary_resume_ready를 따른다.'), '',
        '## 고정한 자리 칸', '',f'지역 높이(m): 지면 {b["height_local_m"][0]:.9f}, 지붕 최고+10 m {b["height_local_m"][1]:.9f}, 학습 카메라 높이 중앙값 {b["height_local_m"][2]:.9f}. 지면과 카메라의 중간값은 쓰지 않았다.',
        '가로는 평가 상자 안 / 밖 50 m 안 / 50~200 m / 200 m 넘음. 높이는 지면 아래 / 지면~지붕+10 m / 지붕+10 m~카메라 / 카메라 위다. 기존 원인 점검 boundaries의 바이트를 그대로 썼다.', '',
        '| 출신 | 중단 상태 수 |','|---|---:|']
    notes += [f'| {name} | {n:,} |' for name,n in zip(groups,totals)]
    notes += ['', '## 상태와 기울기 저장', '', '| 반복 | 밀도 제어 직전 수 | 완전 상태 수 | 누적 기울기 0 아님 |','|---|---:|---:|---:|']
    notes += [f'| {r["iteration"]:,} | {r["pre_densification_gaussians"]:,} | {r["complete_gaussians"]:,} | {r["gradient_accum_nonzero"]:,} |' for r in checkpoints]
    notes += ['',f'100회마다 forward {len(fw)}줄, 반복 후 {len(after)}줄. 출신 4 × 가로 4 × 높이 4 칸의 수 합과 겹침 합을 검증했다. 기울기 자격은 저장된 누적값/denom을 r8 문턱 {c["densify_grad_threshold"]}과 비교했다. 누적 기울기는 밀도 제어 직전, 완전 상태는 직후이므로 두 수를 구분한다.', '',
        '## 중단 상태 원인 점검 자료', '',f'- 학습 영상 203장 모두의 겹침 수를 실제 CUDA 전처리로 계산했다. 전체 forward 완료 {render["full_renders"]}/203장. 할당 전 검사로 끝난 영상은 렌더 완료로 세지 않았다.',
        '- 중단 뒤 저장 모델의 읽기 전용 렌더는 최적화 0회이며, Adam·학습 기울기 메모리를 사용하지 않는다. 이 읽기 전용 실행은 여유량 95%를 할당 용량 확인선으로 사용했다. 학습의 절반 초과 멈춤값은 0.5로 유지했고 학습을 재시도하지 않았다. 중단 영상의 개별 가우시안 겹침 배열도 저장된 배열과 재현 비교했다.',
        '- 출신×자리별 수·긴 축 중앙값·불투명도 중앙값: `recorded_r8_lod2/tables/counts.csv`. 영상×출신×자리별 겹침: `render_cross.csv`. 기울기 자격: `gradient.csv`.',
        '- 이전 원인 점검의 12상태를 다시 학습하거나 다시 계산하지 않고 보관된 표를 비교 칸으로 사용했다. 중단 상태와 합친 수 막대·영상 부하 곡선은 같은 축이다.', '',
        '| 부하 순위 | 영상 | 겹침 | 버퍼 GiB | 전체 렌더 |','|---|---|---:|---:|---|']
    notes += [f'| {i+1} | {r["camera"]} | {r["overlaps"]:,} | {r["binning_bytes"]/2**30:.6f} | {r["full_render_completed"]} |' for i,r in enumerate(render['top5'])]
    notes += ['', '## 구현·검증·재계산 경계', '', '- r22 원본은 변경하지 않았다. 별도 실행 사본에서 반복 시작 관측, training forward 관측, 밀도 제어 직전 저장, 추가 정렬 버퍼 멈춤만 연결했다. 손실·목표·가중치·학습률·밀도 제어·기존 건강 검사는 r8 그대로다.',
        '- 고정 3장 × 검사 활성/비활성에서 원본의 모든 출력 텐서·겹침·버퍼 크기가 바이트 단위로 같았다. CUDA 역전파 소스는 원본과 같다. 버퍼 경계 동일값 통과/초과 멈춤과 강제 멈춤의 개별 겹침 일치도 통과했다.',
        f'- 저장 모델 역전파 3장 × 6개 매개변수 비교도 통과했다(최적화 0회). 최대 절대 차이 {max(r["recording_vs_original"]["max_abs"] for r in backward["rows"]):.12g}; 최대 상대 L2 {max(r["recording_vs_original"]["relative_l2"] for r in backward["rows"]):.12g}. 원본 반복의 최대 상대 L2 {max(r["original_repeat"]["relative_l2"] for r in backward["rows"]):.12g}도 함께 기록한다. 허용오차는 절대 1e-7·상대 1e-4였다. 바이트 일치는 forward 출력에 대한 검사다.',
        '- 최초 잠금: `r8_record_prepare.lock.json`; 빌드·검증 후 실행 잠금: `r8_record_runtime.lock.json`. 실행 환경은 고정 geogs Docker 이미지와 GPU 1 RTX 3090이다.',
        '- 학습 GPU peak 값은 이번 이어 학습 프로세스 시작 이후의 누적 최대다. 100회 forward 기록과 반복 후 기록은 각각 그 시점의 allocated/reserved/free도 포함한다. 중단 뒤 읽기 전용 렌더의 peak는 영상마다 초기화했다.',
        '- 같은 씨앗의 새 학습을 반복한 실험은 수행하지 않았다. 비결정적 CUDA 연산의 완전 재현성을 주장하지 않는다.',
        '- ZIP에는 표·그림·JSON·설정·실행 코드·검증 및 큰 자료의 경로와 SHA-256을 넣는다. 원본/추가 완전 체크포인트와 대형 개별 겹침 배열은 외부 payload로 남는다. 재계산에는 그 payload와 고정 Docker 이미지가 필요하다. ZIP 무결성은 과학적 판정이 아니다.', '',
        '![100회 기록](recorded_r8_lod2/figures/continuation_records.png)', '', '![높이 분포](recorded_r8_lod2/figures/height_comparison.png)', '', '![기울기 자격](recorded_r8_lod2/figures/gradient_eligibility.png)', '']
    report=DOC/'이어학습_기록_r8_LoD2.md';report.write_text('\n'.join(notes))
    promoted=DOC/'recorded_r8_lod2';promoted.mkdir(exist_ok=False);shutil.copytree(ROOT/'figures',promoted/'figures');(promoted/'tables').mkdir()
    for p in D.iterdir():
        if p.is_file() and p.suffix in ['.json','.csv']:shutil.copy2(p,promoted/'tables'/p.name)
    payload=[]
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and p.suffix in ['.pth','.ply','.npz','.so']:
            payload.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
    dump(ROOT/'external_payloads.json',dict(files=payload,original_checkpoint=dict(path=c['checkpoint'],sha256=c['checkpoint_sha256']),scientific_verdict=None))
    # Compact handover: no duplicated multi-GB optimizer or Gaussian payloads.
    files=[]
    for p in [report,*promoted.rglob('*')]:
        if p.is_file():files.append((p,'docs/'+str(p.relative_to(DOC))))
    for p in sorted(CFG.glob('r8_record*.json')):files.append((p,'configs/'+p.name))
    for p in sorted((REPO/'scripts/phd/main_target_v1').glob('r8_record*.py')):files.append((p,'scripts/'+p.name))
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and p.suffix in ['.json','.jsonl','.patch','.log'] and 'figures' not in p.parts and 'stop_diagnostic' not in p.parts:
            files.append((p,'evidence/'+str(p.relative_to(ROOT))))
    for relative in ['runtime/train_recorded.py','runtime/rasterizer/cuda_rasterizer/rasterizer_impl.cu','runtime/rasterizer/ext.cpp']:
        files.append((ROOT/relative,'evidence/'+relative))
    license_path=ROOT/'runtime/rasterizer/LICENSE.md'
    if license_path.exists():files.append((license_path,'evidence/runtime/rasterizer/LICENSE.md'))
    tag=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M');zip_path=OUT/'handover'/f'PHD-MAIN-TARGET-v1_이어학습기록r8LoD2_{tag}.zip'
    sums={name:sha(p) for p,name in files};assert len(sums)==len(files)
    with zipfile.ZipFile(zip_path,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,name in files:z.write(p,name)
        z.writestr('SHA256SUMS',''.join(f'{h}  {name}\n' for name,h in sums.items()))
    import hashlib
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None
        for name,h in sums.items():assert hashlib.sha256(z.read(name)).hexdigest()==h,name
    delivery=dict(at=stamp(),zip=str(zip_path),bytes=zip_path.stat().st_size,sha256=sha(zip_path),members_verified=len(sums),external_payloads=len(payload),training=stop['status'],verification=verification,scientific_verdict=None)
    dump(ROOT/'delivery.json',delivery);dump(DOC/'delivery_receipt_recorded_r8_lod2.json',delivery);print('RECORDED_R8_DELIVERED',json.dumps(delivery),flush=True)
if __name__=='__main__':main()
