"""Verify the request package, freeze rules before numerical work, record inventory."""
import json
import platform
import stat
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from common import TASK, OUT, DOC, CFG, LT, SITES, RESULTS, save, sha, now

archive = Path('/attachments/PHD-MAIN-FLOATDIAG-v1_발주묶음_v3.1.zip')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    expected = {}
    for line in z.read('SHA256SUMS').decode().splitlines():
        digest, name = line.split(maxsplit=1)
        expected[name.lstrip('*')] = digest
    members = []
    for info in z.infolist():
        # This archive stores UTF-8 Korean names without the ZIP UTF-8 flag.
        name = info.filename if info.flag_bits & 0x800 else info.filename.encode('cp437').decode('utf-8')
        p = PurePosixPath(name)
        assert len(p.parts) == 1 and not p.is_absolute() and not stat.S_ISLNK(info.external_attr >> 16)
        data = z.read(info)
        import hashlib
        digest = hashlib.sha256(data).hexdigest()
        if p.name != 'SHA256SUMS':
            assert expected[p.name] == digest, p.name
        dest = DOC/'request'/p.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            assert dest.read_bytes() == data
        else:
            dest.write_bytes(data)
        members.append(dict(name=p.name, bytes=len(data), sha256=digest,
                            role='task_instruction' if p.name=='본실험_뜬면진단_발주문_v3.1.md' else 'reference_data_only'))
archive_record = dict(task_id=TASK, time=now(), archive_sha256=sha(archive),
     crc='PASS', internal_sha256='PASS', members=members, scientific_verdict=None)
if (DOC/'provenance/request_archive.json').exists():
    archive_record['time'] = json.loads((DOC/'provenance/request_archive.json').read_text())['time']
save(DOC/'provenance/request_archive.json', archive_record)
cases = [
    ('B173-뜬면-1','B173nb_b10',[149.40,114.75,165.15,143.25],[156.74,129.41]),
    ('B173-뜬면-2','B173nb_b10',[133.65,84.25,153.90,118.75],[145.17,100.08]),
    ('B0-뜬면-1','B0_b10',[107.61,-7.84,121.61,21.66],[113.88,2.30]),
    ('R1-뜬면-1','R1rep_b10',[-15.85,21.45,11.65,51.95],[-2.08,39.31]),
    ('R1-뜬면-2','R1rep_b10',[-16.35,29.95,-4.10,59.45],[-9.76,46.27]),
    ('R1-보존띠-1','R1rep_b10',[-12.85,14.20,32.65,42.70],[10.28,21.61]),
    ('B173-날개','B173nb_b10',[136.63,96.32,146.68,99.34],[141.655,97.83]),
]
cfg = dict(task_id=TASK, revision='v3.1', frozen_at=now(), scientific_verdict=None,
    crs='EPSG:25832', local_origin_m=[690953,5336071,604], prior='ALS', sites=SITES,
    diagnostic_results=RESULTS,
    case_selection=dict(source='4.1; Appendix C is a reference only, rerun the frozen selection rule',
        grid_m=.25, grid_origin='minimum XY of all stage-1 patch centres within each unit',
        closing_iterations=2, connectivity=1, closing_structure='scipy default cross',
        minimum_float_area_m2=10, largest_components_per_unit=2, crop_margin_m=3,
        references=[dict(id=n,site=s,bbox=b,centre=c) for n,s,b,c in cases],
        section_half_width_m=.375, section_extension_m=4,
        wing_section=dict(start=[146.68,96.32],end=[136.63,99.34],half_width_m=.6),
        photo_rule=dict(main_coverage_min=.9, main='minimum angle from vertical',
                        oblique_coverage_min=.5, oblique='maximum angle from vertical',
                        visibility='projected patch centres inside image and unoccluded by model rendered depth',
                        occlusion_depth_tolerance_m=.25)),
    cameras=dict(projection='orthographic for mesh; perspective Gaussian camera with matching framing',
        azimuth_deg=[0,90,180,270,45,225,0], elevation_deg=[30,30,30,30,10,10,90],
        up=[0,0,1], target='centre of fixed reference-based 3D crop',
        crop_z='minimum GT z - 2 to maximum GT z + 8',
        distance='2.5 * crop bounding sphere radius; same for every result',
        ortho_extent='2.2 * crop bounding sphere radius', perspective_fov_deg=45,
        orbit_elevation_deg=20, orbit_frames=36, image_pixels=[720,600],
        lighting=dict(ambient=.65,directional=.35,direction=[.3,-.4,.85])),
    colours=dict(classes=['#2e8b57','#d9534f','#4a7ec7','#e8a33d','#9a9a9a'],
        results=['#888888','#e07b00','#7a3fb0','#1f8a8a','#2b3f8f'],
        lineage=dict(densified='#7a3fb0',initial_prior='#e8a33d',initial_image='#4a7ec7',unrecorded='#9a9a9a'),
        mesh=dict(floating='#d9534f',within_tau='#929292',other='#b8d6ed',no_gt='#dddddd'),
        depth_range_m=[-2,8], force_log10_range=[-8,-.3], depth_colormap='turbo'),
    definitions=dict(float_patch='eligible cell 0..3 and abs(z-p_gt)>tau and not no_surface and side==2 and z>p_gt+tau',
        opacity_min=.1, gaussian_top_extra_m=.25, force_dead_peak_fraction=.01,
        minimum_sample_patches=100, patch_height_coordinate='normal displacement; convert centre + z*normal before using world z'),
    gate=dict(required_sites=['R1rep_b10','B173nb_b10'], result='lt_dynnow_ALS_s0',
        all_own_depth_terms_dead_min_fraction=.7, missing_mvs='prior term only',
        lineage_record_only=True, gradient_ratio_record_only=True, low_ratio_notice=.1),
    loss=dict(lambda_depth=.0025, uniform_density_per_m=.1,
        fx_wide2=dict(outlier='gauss',outlier_sigma_m=2.,farpull_lambda=0.),
        fx_farpull=dict(outlier='uniform',farpull_lambda=.05,farpull_k=5.),
        defaults=dict(outlier='uniform',outlier_sigma_m=2.,farpull_lambda=0.,farpull_k=5.),
        prior_validity='v_prior_now', seeds=[0], iterations=30000,
        implementation='Appendix D.1, stable logsumexp; farpull all present sources > k*sigma then nearest absolute distance',
        cpu_check=dict(residual_m=[0,.01,.1,.3,1,3,6],sigma_m=[.03,.2],validity=[.5,.98],
            finite_difference_step_m=1e-6,relative_tolerance=1e-4)),
    stops=dict(appendix_C_tolerance_pp=.5,psnr_tolerance_db=.1,
        default_r18_equivalence_required=True, loss_check_required=True,
        health=dict(opacity_median_min=.05,after_reset_grace_iterations=100,psnr_deficit_max_db=3.,
            psnr_iterations=[7000,15000,30000],nonfinite_or_execution_error=True)),
    resources=dict(heavy_host_available_GiB=56,heavy_container_GiB=40,stable_seconds=60,
        tsdf_lock=str(LT/'checks/tsdf.lock'), do_not_stop_LOSSTRAIN=True),
    delivery=dict(first='PHD-MAIN-FLOATDIAG-v1_가_눈으로.zip',max_zip_bytes=400000000,
        max_viewer_bytes=150000000,max_glb_bytes=4000000,max_glb_faces=150000,
        max_reference_points=200000,max_web_image_bytes=1500000,max_gif_bytes=8000000),
    authority='User explicitly selected only 본실험_뜬면진단_발주문_v3.1.md; all other attachment members are reference data')
if (CFG/'floatdiag_v1.json').exists():
    cfg['frozen_at'] = json.loads((CFG/'floatdiag_v1.json').read_text())['frozen_at']
save(CFG/'floatdiag_v1.json',cfg)
lock = dict(frozen_at=now(),sha256=sha(CFG/'floatdiag_v1.json'),
    stage='before first scientific calculation',scientific_verdict=None)
if (CFG/'floatdiag_v1.lock.json').exists():
    lock['frozen_at'] = json.loads((CFG/'floatdiag_v1.lock.json').read_text())['frozen_at']
save(CFG/'floatdiag_v1.lock.json',lock)
save(DOC/'provenance/initial_environment.json',dict(at=now(),python=platform.python_version(),
    commit=subprocess.check_output(['git','-C','/repo','rev-parse','HEAD'],text=True).strip(),
    branch=subprocess.check_output(['git','-C','/repo','branch','--show-current'],text=True).strip(),
    source_losstrain_config_sha256=sha('/repo/configs/phd/main_losstrain_v1/losstrain_v1.json'),
    scientific_verdict=None))
(DOC/'progress.md').write_text('# PHD-MAIN-FLOATDIAG-v1\n\n'+now()+': PREPARING_A1.\n\n'
    '발주문 v3.1과 참고 자료의 역할을 구분하고 설정을 첫 계산 전에 잠갔다. '
    '부록 C 검증, 사례 선택, 실제 메시 출처 검증을 진행한다. 학습 0회. scientific_verdict: null.\n')
(DOC/'issues.md').write_text('# PHD-MAIN-FLOATDIAG-v1 issues\n\n'
    'FD-001: ZIP에 UTF-8 이름 표시가 없어 최초 검증이 파일명 KeyError로 종료됐다. '
    '내용 추출과 과학 계산 전에 종료됐으며, ZIP 표시에 따라 이름을 UTF-8로 복원해 SHA256SUMS와 비교하도록 수정했다. 원 로그는 외부 logs/에 보존한다.\n\n'
    'FD-002: 연결된 worktree의 Git 메타데이터가 컨테이너에 없어 준비 영수증 생성이 종료됐다. '
    '원래 경로에 메타데이터를 읽기 전용으로 연결하고 GIT_OPTIONAL_LOCKS=0을 적용했다. '
    '이미 저장된 설정과 잠금 시각은 그대로 보존했다. 과학 계산과 학습은 시작하지 않았다.\n')
print('request CRC/SHA256 PASS; configuration frozen',sha(CFG/'floatdiag_v1.json'))
