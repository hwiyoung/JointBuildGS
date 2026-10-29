"""Freeze the user freespace order and prevent the old queue starting more arms."""
import signal
from runtime import *


def main():
    root=OUT/'freespace_v1';root.mkdir(exist_ok=True)
    request=Path('/home/innopam/.codex/attachments/f93920c6-93c1-4598-96a9-fb404979a909/Pasted text.txt')
    target=DOC/'request/freespace_v1_order.md'
    assert not target.exists();target.write_bytes(request.read_bytes())
    cfg=dict(task_id=TASK,amendment='freespace_v1',at=now(),scientific_verdict=None,
        request_sha256=sha(target),base_result='lt_dynnow_ALS_s0',base_iteration=30000,
        sites=['B173nb_b10','R1rep_b10'],prior='ALS',seed=0,iterations=30000,
        c_per_m=.1,start_iteration=500,end_iteration=30000,
        depth='native rasterizer median allmap[5]; baseline training depth remains unchanged',
        sources='Exact lt_losses source eligibility, per-patch sigma / ray-normal cosine clamped at 0.25, validity clamped identically to lt_term; no new depth data',
        source_eligibility='prior: valid loc and finite positive P; MVS: same prior-eligible pixel plus finite positive M and A>0 and finite vm, matching lt_losses',
        G='detached product of (1-r_s); empty source set zero',
        margin='sigma*sqrt(2*log(V/((1-V)*c*sigma*sqrt(2*pi)))); log<=0 means f contribution zero',
        f='max V_s at nearest projected pixel when camera z < D_s-m_s; outside scope or protected zero',
        F='one native rasterization of f as three identical colour channels, black background; detached xyz/scaling/rotation; opacity live',
        loss='mean over all image pixels of G*F',
        scope='Exact previous pruning XY union of ALS triangles buffered 1 m; frozen_mask excluded',
        pressure='P_i=sum_views sum_pixels G*w_i*f_i; recovered exactly by colour adjoint times f_i',
        rank='strict Pr(P_floating > P_roof_or_wall), uniform pairs, ties count zero; roof and wall separately also reported',
        rank_min=.8,expected_floating=13934,
        calibration='For each floating Gaussian, mean absolute dL/dopacity_logit over all 203 training views, then median over the 13934 Gaussians. Record pooled view-Gaussian medians separately. Zero b is UNAVAILABLE and forbids training.',
        lambda_rule=['a/b','4*a/b'],lambda_values=None,
        save_iterations=[7000,15000,30000],log_every=100,
        farpull_lambda=0,pruning='off',multiview='off',appearance='off',
        r1_selection='Among B173 arms with cell2 >=65.4 choose lower floating cell0..3; if neither, larger cell2; tie choose lambda1; only complete scored arms eligible',
        selection=dict(floating_lt_pct=5.,cell2_ge_pct=65.4,cell1_ge_pct=57.5),
        deadlines_kst=dict(preflight='2026-10-30T03:30:00+09:00',b173='2026-10-30T07:30:00+09:00',cutoff='2026-10-30T11:30:00+09:00'),
        inherited_plan_sha256=sha(CFG/read(CFG/'active_plan.json')['config']),
        source_sha256={str(p.relative_to(REPO)):sha(p) for p in sorted((REPO/'src/phd/forks/GeoGS-conf-guided-v1-r18').rglob('*.py'))},
        software_image=subprocess.check_output(['docker','image','inspect',IMAGE,'--format','{{.Id}}'],text=True).strip(),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
    for site in cfg['sites']:
        support=OUT/'evidence_prune_v1'/site
        cfg.setdefault('support_sha256',{})[site]={n:sha(support/n) for n in ['support.json','prior.npz','diagnostic_labels.npz','delete_mask.npz','preflight.json']}
    p=CFG/'farpull_v1_freespace_v1.json';save(p,cfg,True)
    save(p.with_suffix('.lock.json'),dict(at=now(),sha256=sha(p),scientific_verdict=None),True)
    # Pause only the scheduler, never its already-running Docker child. A
    # suspended scheduler cannot launch another unapproved residual arm.
    proc=read(OUT/'checks/mv_followups_process.json',{});pid=proc.get('pid')
    if pid and Path(f'/proc/{pid}/cmdline').exists():
        assert str(SCRIPTS/'mv_followups.py').encode() in Path(f'/proc/{pid}/cmdline').read_bytes()
        children=Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
        os.kill(pid,signal.SIGSTOP)
        save(root/'legacy_scheduler_yield.json',dict(at=now(),pid=pid,state='SCHEDULER_PAUSED',
            running_children_preserved=children,reason='User prohibits starting unstarted R1 multiview and remaining old arms',
            no_compute_child_signalled=True,automatic_resume=False,scientific_verdict=None),True)
    text='''# 빈 공간 손실 진행

발주 수신 및 설정 잠금. 구현·단위 점검 → B173 203장 사전 검사 → 관문 통과 시 λ₁·λ₄ 학습.
기존 B0 학습은 30,000회 저장 완료. 이미 시작한 B0 후처리 자식 프로세스는 유지했다.
잔여 학습을 시작하는 기존 스케줄러만 일시 정지했다. R1 다시점과 미시작 잔여 판은 시작하지 않는다.
지우기 사진별 CPU 진단과 MESHPATCH 작업은 유지한다.
중앙 깊이는 원 렌더러 allmap[5]에서 읽으며, 기존 판 4 깊이 손실의 기대 깊이는 그대로다.
기울기 무게는 사진별 절댓값을 가우시안마다 평균한 뒤 뜬 가우시안의 중앙값으로 정한다. 전체 사진×가우시안 중앙값도 함께 기록한다.
학습 상태: NOT_STARTED_PREFLIGHT_PENDING. scientific_verdict: null.
'''
    (DOC/'freespace_v1').mkdir(exist_ok=True)
    (DOC/'freespace_v1/진행.md').write_text(text)
    progress=DOC/'진행.md';progress.write_text(text+'\n---\n\n'+progress.read_text())
    print('Frozen',sha(p),now())


if __name__=='__main__':main()
