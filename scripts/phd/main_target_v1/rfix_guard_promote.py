"""Promote the guarded-training provenance alongside the native comparison build."""
import csv,shutil
from r8_screen_prepare import R,O,C,j,sha,dump,local
ROOT=O/'rfix';DEST=R/'docs/experiments/phd/main_target_v1/rfix'
def main():
 evidence=j(ROOT/'guard_binding/result.json');assert all(r['instruction_listing_equal'] for r in evidence['native_kernels'])
 p=ROOT/'provenance.json';data=j(p);base=next(r for r in data['rows'] if r['implementation']=='target_r22').copy();base.update(implementation='r8_LoD2_recorded_resume_actual_guard_build',original_source='/out/r8_recorded_continue/runtime/rasterizer',original_extension_sha256=evidence['actual_recorded_renderer_sha256'],comparison_reference='The measured original A/B used the unchanged installed native binary, not this observation wrapper. Native source and sm_86 instruction listings are identical; the distinct actual training guard build is disclosed separately.');assert not any(r['implementation']==base['implementation'] for r in data['rows']);data['rows'].append(base);dump(p,data)
 for src,name in [(local(evidence['actual_recorded_training_renderer']),'recorded_guard.so'),(C/'r8_record_runtime.lock.json','previous_runtime.lock.json'),(O/'r8_recorded_continue/runtime/recording_only.patch','previous_recording_only.patch')]:shutil.copyfile(src,ROOT/'guard_binding'/name)
 rows=evidence['native_kernels'];dest=DEST/'tables/recorded_guard_native_kernels';dump(dest.with_suffix('.json'),dict(rows=rows,scientific_verdict=None));keys=list(rows[0])
 with dest.with_suffix('.csv').open('w',newline='') as f:w=csv.DictWriter(f,keys);w.writeheader();w.writerows(rows)
 dest.with_suffix('.md').write_text('\n'.join(['| '+' | '.join(keys)+' |','|'+'|'.join(['---']*len(keys))+'|']+['| '+' | '.join(str(r[k]) for k in keys)+' |' for r in rows])+'\n')
 (DEST/'실행빌드_기록감시.md').write_text(f'''# r8 LoD2 기록용 실행 빌드 구분

`r8_LoD2_stop` 저장 상태의 기록용 이어 학습은 `{evidence['actual_recorded_training_renderer']}`를 실제로 사용했다. SHA256은 `{evidence['actual_recorded_renderer_sha256']}`다. 기존 `r8_record_runtime.lock.json`의 봉인과 현재 바이트가 같다.

이번 203장·30장 대조의 원본 A/B는 이전 모의와 같은 설치된 기본 `diff_surfel_rasterization._C`를 사용했다. 이 기본 빌드와 실제 기록용 감시 빌드를 같은 바이너리라고 표시하지 않는다. 감시 빌드는 할당 직전 메모리 확인과 0.5 중단 장치, 기록 인터페이스를 추가한 빌드다. 현재 대조의 원본 바이너리 선택과 수치 기준은 바꾸지 않았다.

기록용 감시 빌드의 `forward.cu`, `backward.cu`, `auxiliary.h`, `config.h`는 기본 소스와 바이트 단위로 같다. sm_86의 렌더 두 함수와 전처리 두 함수도 명령어 목록/인코딩이 정확히 같다. [함수별 표](tables/recorded_guard_native_kernels.md)에 해시를 뒀다. 이 코드 대조는 기울기 같음 기준 미달을 대신하지 않는다.

이 실제 감시 바이너리의 추가 출처 확인은 첫 rfix 렌더 뒤에 했다. 기존 감시 빌드의 앞선 잠금과 이번 사후 대조 시각을 구분한다. 새로 고친 렌더러나 새 학습 상태를 만든 기록이 아니다. `scientific_verdict: null`.
''')
 print('GUARD_PROVENANCE_PROMOTED',flush=True)
if __name__=='__main__':main()
