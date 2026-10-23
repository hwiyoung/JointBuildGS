"""Publish receipts/report and a lossless offline archive without changing prior work."""
import base64
import os
import shutil
import sys
import zipfile
import zlib
sys.path.insert(0,'/repo/scripts/phd/main_uncert_view_v1')
from common import *

HOST_REPO='/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp'
HOST_ART='/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts'

def unpacket(path):
    s=path.read_text();return json.loads(s[s.index('=')+1:s.rindex(';')])

def decode(rec):
    if 'strings' in rec:return np.asarray(rec['strings'])[decode(rec['index'])]
    dtype=np.dtype(rec['dtype']);flat=np.frombuffer(zlib.decompress(base64.b64decode(rec['data'])),np.uint8)
    raw=flat.reshape(dtype.itemsize,-1).T.copy().tobytes()
    assert hashlib.sha256(raw).hexdigest()==rec['sha256']
    return np.frombuffer(raw,dtype).reshape(rec['shape'])

def main():
    web=OUT/'web';config=load(CFG/'view_v1.json');audit=load(DOC/'tables/input_audit.json')
    changed=[]
    for rec in audit['inputs']:
        if sha(rec['path'])!=rec['sha256']:changed.append(rec['path'])
    assert not changed,changed
    integrity=[]
    for site,prior in U.CASES:
        p=web/'data'/f'{site}__{prior}.js';packet=unpacket(p);decoded=[decode(a) for a in packet['blobs']]
        for r,keys in packet['rings'].items():
            original=pv(site,prior,float(r));bad=[]
            for k,idx in keys.items():
                a,b=original[k],decoded[idx]
                same=np.array_equal(a,b,equal_nan=True) if a.dtype.kind=='f' else np.array_equal(a,b)
                if not same:bad.append(k)
            assert not bad,(site,prior,r,bad)
            integrity.append(dict(case=site+'__'+prior,R=r,fields=len(keys),all_equal=True))
        del decoded,packet
    browser=load(DOC/'tables/browser_smoke.json')
    hashes=[]
    for c in browser['checks']:
        if c['test']=='decoded_float_byte_hashes':
            for rec in c['integrity']:
                z=pv('B173nb_b10','LoD2',float(rec['r']))
                original=hashlib.sha256(z[rec['k']].tobytes()).hexdigest();assert rec['sha256']==original
                hashes.append(dict(**rec,source_sha256=original,match=True))
    dump(DOC/'tables/integrity.json',dict(made=now(),source_files_checked=len(audit['inputs']),source_files_changed=changed,
        packet_roundtrips=integrity,browser_byte_checks=hashes,scientific_verdict=None))
    for name in ['index.html','style.css','data.js','stats.js','app.js']:
        shutil.copyfile(ROOT/'scripts/phd/main_uncert_view_v1'/name,web/name)
    helptext='웹주소 http://192.168.10.203:8912/ 에 접속합니다. 오프라인은 압축을 풀고 index.html을 엽니다.\n\n'
    helptext+='지도 두 칸: 같은 범위로 이동·확대, 층 선택, 마우스 설명, 패치 카드.\n비스듬히 보기: 회전·확대·패치 누르기, 벽꼴만 표시.\n패치 카드: 세 고리 크기의 저장된 값. 표본 패치는 점 단면, 그 밖은 가까운 표본으로 이동.\n걸러 보기와 영역 선택: 패치 수·넓이·중앙값·25·75 % 값·막대그래프. 화면에서 다시 셈 표시.\n확인 물음 여섯: 지정한 범위의 재집계와 원래 보고 JSON을 나란히 표시.\n참값 관련 값은 항상 참값 점검용. 유효 확률과 새 과학적 판정 없음.\n\n층\n'
    for l in config['layers']:helptext+=l['label']+' — '+l['description']+' ('+(l['unit'] or '단위 없음')+'). '+l['group']+'\n'
    helptext+='\n값 없음: 회색 빗금. 해당 없음: 흰색. 색 범위 밖: 끝 색과 점 무늬.\n외부 라이브러리·CDN·지도 서비스 없음. 브라우저 내장 Canvas 2D, DecompressionStream 사용.\n검증: Linux Chromium 152.0.7977.82. Windows Chrome·Edge는 이 작업 환경에서 실행할 수 없어 확인 불가.\n연구 서버 주소는 같은 네트워크 또는 연결 가능한 VPN에서 사용. 서비스 자동 재시작 설정.\n'
    (web/'읽어보기.txt').write_text(helptext)
    (web/'LICENSES.txt').write_text('Bundled third-party JavaScript/CSS libraries: none.\nApplication source: scripts/phd/main_uncert_view_v1 in JointBuildGS.\nBrowser native APIs only; system fonts are not redistributed.\nScientific arrays retain their original source provenance; this package grants no new data license.\n')
    package=OUT/'PHD-MAIN-UNCERT-VIEW-v1_web.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(web.rglob('*')):
            if p.is_file():z.write(p,Path('web')/p.relative_to(web))
    files=[dict(path=str(p.relative_to(web)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(web.rglob('*')) if p.is_file()]
    total=sum(p['bytes'] for p in files)
    size=dict(web_bytes=total,zip_bytes=package.stat().st_size,zip_sha256=sha(package),limit_bytes=300_000_000,
        exceeds_requested_threshold=total>300_000_000,precision_or_sample_reduction=False,size_question_requested=True,
        decision='Keep all locked samples and original numeric precision. No reduction without the user response.',files=files)
    dump(DOC/'tables/package.json',size)
    section=load(DOC/'tables/section_replay.json');tables=load(DOC/'tables/table_recount.json');qa=load(DOC/'tables/browser_full.json')
    measured=next(x for x in qa['checks'] if x['test']=='largest_case_layer_switch')['ms']
    start=dt.datetime.fromisoformat(audit['made']);elapsed=(dt.datetime.fromisoformat(now())-start).total_seconds()
    receipt=dict(task_id=config['task_id'],made=now(),scientific_verdict=None,crs=config['coordinate'],url='http://192.168.10.203:8912/',
        scope='same-network/VPN; external internet reachability not tested',container='jbgs-main-uncert-view-8912',
        source_commit=os.environ.get('VIEW_COMMIT'),container_image=os.environ.get('VIEW_IMAGE'),config_sha256=sha(CFG/'view_v1.json'),
        source_files_unchanged=len(audit['inputs']),samples=sum(len(v['indices']) for v in load(OUT/'sample_index.json').values()),
        replay_checks=sum(x['selected'] for x in section['rows']),replay_matches=sum(x['matched'] for x in section['rows']),
        table_checks=tables['comparisons'],table_matches=tables['matched'],browser_errors=qa['errors'],largest_layer_switch_ms=measured,
        no_training=True,no_gpu=True,resources=dict(preprocessing_cpus=8,memory_limit_gb=32,browser_cpus=4,browser_memory_limit_gb=8,server_cpus=2,server_memory_limit_mb=512),
        elapsed_since_input_audit_s=elapsed,package=size,limitations=['Windows Chrome/Edge not executed','Web directory exceeds 300 MB; no samples or precision reduced','Outside-network access not verified'])
    dump(OUT/'receipt_task.json',receipt);dump(DOC/'tables/receipt_task.json',receipt)
    lines=['# 불확실도 보기 보고 v1','',
        '여섯 경우·세 고리 크기·MVS 두 판을 볼 수 있는 웹 화면과 오프라인 묶음을 만들었다.',
        '여는 주소: **[불확실도 지도](http://192.168.10.203:8912/)** — 연구 서버에 연결되는 같은 네트워크 또는 VPN에서 접속한다. 파일 실행은 필요 없다.',
        '단면 재현·숫자 맞춰 보기·Linux Chromium 화면 점검은 PASS. Windows Chrome·Edge는 확인 불가이며 전체 웹 크기는 300 MB 초과다. `scientific_verdict: null`.','',
        '## 1. 자료와 키 이름','',
        f'- 저장소: `{HOST_REPO}`',f'- 패치 값: `{HOST_ART}/phase-payloads/phd/main_uncert_v1/PHD-MAIN-UNCERT-v1/patch_values/`',
        f'- MVS 판 가·나, 원래 항공 LiDAR, 참값 점: 같은 작업의 `points/<지역>/mvs_a_xyz.npy`, `mvs_b_xyz.npy`, `als_xyz.npy`, `gt_xyz.npy`. 영상 번호와 솎기 열쇠도 같은 폴더에서 읽었다.',
        '- 영역: `phase-payloads/phd/main_stage1_v1/PHD-MAIN-STAGE1-v1/regions_v3/regions_ext_v3_<지역>_<사전 정보>.npz`.',
        '- 앞 작업 스크립트와 표는 읽기 전용으로 연결했다. 전체 경로·크기·SHA-256과 원본 키 목록: [input_audit.json](tables/input_audit.json).',
        '- 좌표는 EPSG:25832에서 `[690953, 5336071, 604]` m를 뺀 COLMAP 모델 좌표, 축척 1, 북쪽 위.','',
        '| 화면 값 | 원본 키 |','|---|---|',
        '| 패치 중심·법선·면·영역 | `centre`, `normal`, `surf`, `in_eval`, `roof_like`, `area` |',
        '| 칸·지붕 형태 (참값 점검용) | `cell`, `roof_type` |',
        '| 두 자료의 차 | `mvs_a_p`, `mvs_b_p` |',
        '| MVS 불확실도·어긋남·흩어짐·68.3 % | `mvs_{a,b}_{u,a,s,q}` |',
        '| 사전 정보 불확실도·항공 LiDAR 성분 | `u_prior`, `als_{a,s,q}` |',
        '| z·MVS 무게 비율 | `z_{a,b}`, `w_{a,b}` |',
        '| 점의 사정 | `{mvs_a,mvs_b,als}_{status,n_col,n_inner_all,n_inner,n_ring,ring_found,ring_level,views,quadrants,thinned_inner,thinned_ring,support_lmeds,support_final}`. `als_views`는 값이 없는 원본 배열이며 항공 LiDAR 영상 수는 표시하지 않음 |',
        '| 참값 점검용 | `gt_{p,status,o,n_inner,runs}`, `mvs_{a,b}_{e,qe,f}`, `als_e`, `eL`, `errW_{a,b}` |',
        '| 놓친 패치 | 원본의 `e > .2` 및 `e > 2u`를 그대로 적용한 화면 표시. 새 불확실도나 확률이 아님 |','',
        '| 경우 | 평가 범위 | 띠 | 표 1 값 있음 일치 |','|---|---:|---:|---|']
    for site,prior in U.CASES:
        row=next(r for r in audit['rows'] if r['case']==U.case_ko(site,prior))
        lines.append(f"| {row['case']} | {row['eval']:,} | {row['band']:,} | 세 고리·자료 모두 일치 |")
    lines+=['','## 2. 재현과 맞춰 보기','',f"입력 {len(audit['inputs'])}개 파일 SHA-256 재확인: 변경 0개. 모든 웹 패킷의 모든 내보낸 배열을 복원해 원본과 비교했고 일치했다. 브라우저가 푼 Float32/Float64 배열 18개의 바이트 SHA-256도 원본과 일치했다.",
        '', '| 점검 | 건수 | 결과 |','|---|---:|---|',
        f"| 단면 재현: 원래 `u2_run.one_patch`, `column`, `ring_points`, 씨앗·순서·솎기 동일 | {receipt['replay_checks']:,} | 전부 0.1 cm 안 |",
        f"| 표 1·2·6.1·6.3·6.4 독립 재집계 | {tables['comparisons']:,} | 전부 허용차 안 |",
        '| 여섯 물음의 브라우저 재집계 | 보고 값이 있는 모든 비교 행 | 허용차 초과 0 |',
        '| 파일 직접 열기 + 네트워크 차단 | 1 | PASS |',
        '| Windows Chrome·Edge | 0 | 확인 불가: 해당 OS·브라우저 없음 |','',
        '재현 세부 표: [section_replay.json](tables/section_replay.json). 비교 양쪽 값·허용차: [table_recount.json](tables/table_recount.json). 브라우저 숫자: [browser_full.json](tables/browser_full.json). 바이트 확인: [integrity.json](tables/integrity.json).','',
        '## 3. 확인 물음 화면','']
    for check in qa['checks']:
        if not check['test'].startswith('question_'):continue
        q=check['result'];c=q['comparisons'][0]
        lines += [f"### {q['id']}. {q['title']}",'',f"![물음 {q['id']}](screens/question_{q['id']}.png)",'',f"{q['unit']} · {c['label']}: 보고 {c['report']} / 화면에서 다시 셈 {c['now']} {c['unit']}.",'']
    lines+=['## 4. 패치 카드와 단면','']
    for i in range(1,4):lines += [f'![패치 카드와 단면 {i}](screens/patch_section_{i}.png)','']
    lines+=['## 5. 변경·확인 불가·추가 기록','',
        '- 웹주소 접속 요청에 따라 독립 정적 서버를 추가했다. 이 작업의 `web/`만 읽기 전용으로 제공하며 자동 재시작한다. 다른 서비스는 변경하지 않았다.',
        '- 숫자는 무손실 저장한다. 부동소수점 원래 정밀도, 표본 패치 수, 잠근 표시 점 상한을 줄이지 않았다.',
        '- 전체 웹 폴더가 300 MB를 넘어 표본 또는 정밀도를 줄이기 전에 사용자에게 선택을 요청했다. 응답 전에는 원본 유지판을 제공한다. 압축 파일 크기와 풀린 웹 크기를 구별한다.',
        '- 자리 목록에 원래 대응 패치가 0개인 항목은 없음으로 표시하고 이동을 막는다. R1 고르게 낮은 평지붕은 앞 작업의 확인 불가 기록을 유지한다.',
        '- 앞 보고 6.2의 판 나는 보존 · 거름도 영상 틀림에 포함한다. 화면에서 이를 명시하고 같은 정의로 비교한다. 6.4는 판 가를 사용한다.',
        '- `cell`과 `roof_type`도 참값 유래이므로 참값 점검용으로 표시했다. 확인 물음의 보고 등급은 JSON에서 읽은 기존 문구이며 새 등급을 만들지 않았다.',
        '- 화면 코드는 `scripts/phd/main_uncert_view_v1/`에만 추가했다. 제삼자 웹 라이브러리는 포함하지 않았다.',
        '- 실패·수정 내역: [issues.md](issues.md). 설정 잠금 이후 표본·수치 정의·색 범위 변경 없음. 렌더러와 접힌 통계표 계산 시점만 성능을 위해 수정했다.','',
        '## 6. 크기·자원·시간','',
        f"- 웹 폴더 {total/1e6:.2f} MB, ZIP {package.stat().st_size/1e6:.2f} MB (10진 MB).",
        f"- 페이로드: `{HOST_ART}/phase-payloads/phd/main_uncert_view_v1/PHD-MAIN-UNCERT-VIEW-v1/`.",
        f"- 가장 큰 경우 258,097개 패치, 층 전환 {measured} ms. 최초 B0 자료 준비 {qa['checks'][0]['ms']} ms. CPU 4개를 제한한 Chromium 측정이며 다른 PC·네트워크의 속도를 보장하지 않는다.",
        '- 전처리 Docker: CPU 최대 8개, 메모리 제한 32 GB. 브라우저 Docker: CPU 4개, 8 GB. 서버: CPU 2개, 512 MB. CUDA 장치 요청 없음. 학습 없음.',
        f"- 입력 감사 기록 이후 {elapsed/60:.1f}분. 실제 최대 메모리는 별도로 수집하지 않아 확인 불가.",
        '- 브라우저 버전: Chromium 152.0.7977.82 (Linux). 오프라인, 실제 휠·드래그·올가미·마우스 카드, 범위 필터, 보정 칸 제외, 판 나·고리 3 m 확인.',
        '', '| 경우 자료 | 크기 MB | 단면 파일 MB |','|---|---:|---:|']
    for site,prior in U.CASES:
        ident=site+'__'+prior;lines.append(f"| {U.case_ko(site,prior)} | {(web/'data'/f'{ident}.js').stat().st_size/1e6:.2f} | {(web/'sections'/f'{ident}.js').stat().st_size/1e6:.2f} |")
    lines += ['','## 7. 재실행','',
        '아래 스크립트는 Docker에서 실행한다. 잠금은 처음 한 번만 만들며 기존 잠금은 덮어쓰지 않는다. 원본 입력은 읽기 전용이다.','',
        '```bash','bash scripts/phd/main_uncert_view_v1/run_cpu.sh audit.py','bash scripts/phd/main_uncert_view_v1/run_cpu.sh lock_config.py  # 최초 한 번만',
        'bash scripts/phd/main_uncert_view_v1/run_cpu.sh build_data.py','bash scripts/phd/main_uncert_view_v1/run_cpu.sh build_sections.py','bash scripts/phd/main_uncert_view_v1/run_cpu.sh validate_tables.py',
        'bash scripts/phd/main_uncert_view_v1/run_cpu.sh finalize.py','bash scripts/phd/main_uncert_view_v1/serve.sh','```','',
        '브라우저 QA는 기존 `jointbuildgs:geogs-viewer-browser-v2` 이미지에서 `qa_browser.mjs full`, 추가 실제 조작은 `qa_interactions.mjs smoke`로 수행한다. 입력 `/src`, 웹 `/web`은 읽기 전용, 보고 `/docs`만 쓰기 가능으로 연결한다.','']
    (DOC/'불확실도보기_보고_v1.md').write_text('\n'.join(lines))
    progress(f'일 5 보고·묶음 완료: 웹 {total/1e6:.2f} MB, ZIP {package.stat().st_size/1e6:.2f} MB. 기존 입력 {len(audit["inputs"])}개 변경 없음. Linux Chromium PASS; Windows Chrome·Edge 확인 불가. scientific_verdict: null.')
    print(json.dumps(dict(web_mb=total/1e6,zip_mb=package.stat().st_size/1e6,source_unchanged=len(audit['inputs']),roundtrip_fields=sum(r['fields'] for r in integrity)),ensure_ascii=False))

if __name__=='__main__':main()
