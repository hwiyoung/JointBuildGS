"""Record exact upstream function and currently used mesh extraction paths."""
import ast,json
from pathlib import Path
from patch_units import sha,dump,locked
R=Path('/repo');O=Path('/out');D=Path('/docs');UP=O/'received/geogs_original'
def function(p,name):
    t=p.read_text();n=next(x for x in ast.parse(t).body if isinstance(x,ast.FunctionDef) and x.name==name)
    return dict(path=str(p),sha256=sha(p),start=n.lineno,end=n.end_lineno,source=ast.get_source_segment(t,n))
def main():
    locked();a=function(UP/'utils/mesh_utils.py','post_process_mesh');b=function(R/'src/phd/forks/GeoGS-conf-guided-v1-r17/utils/mesh_utils.py','post_process_mesh')
    assert a['source']==b['source']
    files=['scripts/phd/main_stage1_v1/gpu_s1.py','scripts/phd/main_losstrain_v1/gpu_post.py','scripts/phd/main_losstrain_v1/tiled_post.py','src/phd/streamed_tsdf.py','scripts/phd/main_stage3_v1/gpu_s3.py','scripts/phd/main_baselines_v1/gpu_bl.py']
    rows=[]
    for rel in files:
        p=R/rel;t=p.read_text();lines=[dict(line=i,text=s.strip()) for i,s in enumerate(t.splitlines(),1) if any(k in s for k in ['post_process_mesh','ext.reconstruction','mesh_tsdf.ply','tiled_post.extract','tiled_post','G.post(','remove_degenerate','merge_close','remove_duplicated','virtual'])]
        rows.append(dict(path=rel,sha256=sha(p),matches=lines))
    out=dict(task_id='PHD-MAIN-MESHPATCH-v1',status='PASS_CODE_PARTIAL_PAPER',upstream_commit='db40c95c657ec03ff21c83cb99cf39f4e90247a6',post_process_identical=True,original_function=a,fork_function=b,
        num_cluster_cli_default=50,function_default=1000,minimum_triangle_threshold=50,
        tie_rule='Keep all components at or above the 50th-largest triangle count, so ties can retain more than 50 components.',
        fewer_than_50_components='Original function indexes [-50] and raises IndexError; no silent alteration is authorized.',
        virtual_cameras_upstream=True,scoring_mesh='Training-view bounded TSDF; no GeoGS component filtering; virtual-view mesh is a separate output.',
        tiled_tsdf='LOSSTRAIN uses gpu_s1.post with extract_mesh_bounded replaced by tiled_post.extract. No post_process_mesh call in this wrapper.',
        source_records=rows,paper_access='Publisher full text returned HTTP 403. Exact crop and post rules are confirmed in the original code and README; paper full-text phrasing is unavailable.',scientific_verdict=None,provenance='[이 발주에서 냄]')
    dump(D/'tables/task1_code_audit.json',out)
    text='''# 일 1: 원본 코드와 채점 메시 확인

[이 발주에서 냄] scientific_verdict: null

| 물음 | 확인한 내용 | 근거 |
|---|---|---|
| 메시 정리는 원본에 있나 | 있다. 포크 r17의 함수 본문은 원본과 문자 단위로 같다. 실행 옵션의 기본값은 50, 함수 자체의 기본값은 1000이다. 이번 호출은 50을 명시한다. | 원본 `utils/mesh_utils.py` 23–44줄, `render.py` 39·131줄 |
| 가상 시점은 원본에 있나 | 있다. `--skip_virtual_cams`를 주지 않으면 보완용 카메라가 만들어졌을 때 학습 카메라와 합친다. 포크가 추가한 기능이 아니다. | 원본 `render.py` 46·100–114줄 |
| 지금 채점 메시는 무엇인가 | 학습 카메라만 사용한 `mesh_tsdf.ply`다. 삼각형 수에 따른 덩어리 정리는 호출하지 않는다. 가상 시점의 `mesh_virtual.ply`는 별도 파일이다. | `gpu_s1.py` 217–230줄, `gpu_s3.py`, `gpu_bl.py` |
| 조각 TSDF는 무엇을 바꾸나 | LOSSTRAIN은 `gpu_s1.post`의 TSDF 함수만 조각 실행으로 교체한다. 같은 학습 카메라의 저장 렌더를 합치며 덩어리 정리는 추가하지 않는다. | `gpu_post.py` 23–35줄, `tiled_post.py` |
| 2DGS·GeoGS·고친 GeoGS도 같은가 | 비교방법의 후처리는 `gpu_s1.post`를 호출한다. 학습 카메라 TSDF와 별도 가상 시점 파일의 구분이 같다. | `gpu_bl.py` 1–12·92–94줄 |
| GeoGS 안내서의 평가 메시 | `fuse_post.ply`를 건물 범위로 자른 뒤 점군 변환과 평가를 실행한다. | 원본 README 133–136줄 |

원본 커밋: `db40c95c657ec03ff21c83cb99cf39f4e90247a6`.

원본 함수는 50번째로 큰 덩어리의 삼각형 수를 문턱으로 삼는다. 같은 크기의 덩어리가 있으면 50개보다 많이 남을 수 있다. 전체 덩어리가 50개 미만이면 원본 함수가 오류를 내므로, 해당 대상은 기록하고 멈춘다. 규칙을 임의로 고치지 않는다.

출처: [원본 render.py](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/render.py), [원본 함수](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/utils/mesh_utils.py), [원본 안내서](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/README.md).

[논문](https://www.sciencedirect.com/science/article/pii/S0924271626003588) 전문은 HTTP 403으로 읽지 못했다. 논문 전문에 적힌 세부 문장은 확인 불가다. 위 정리와 자르기 규칙의 근거는 원본 코드와 안내서다.
'''
    (D/'tables/task1_code_audit.md').write_text(text)
    dump(O/'status/task1.json',dict(stage='complete_with_paper_limitation',scientific_verdict=None))
    print('code audit written; upstream function identical',flush=True)
if __name__=='__main__':main()
