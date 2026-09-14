"""Phone-readable Korean evidence/admission/association summary from real receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from PIL import Image, ImageDraw, ImageFont


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_text())
def write(path,obj):
    with Path(path).open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


REASONS={
    'SOURCE_EVIDENCE_NOT_APPROVED_FOR_PROBE':'관측 근거가 수정 허용 기준을 통과하지 못함',
    'NO_LOCAL_GEOMETRY_AND_CONTRIBUTION_ASSOCIATION':'허용된 작은 영역에 국소적으로 기여하는 Gaussian 연결이 없음',
    'ASSOCIATION_EXCEEDS_ID_CAP':'연결된 Gaussian 수가 고정 상한을 초과함',
    'SELECTED_IDS_EXPLAIN_LT_5_PERCENT_TARGET_ALPHA':'연결된 Gaussian이 대상 영상 기여의 5%를 설명하지 못함'}


class Card:
    def __init__(self,font,width=840):
        self.width=width;self.image=Image.new('RGB',(width,5000),'#f2f6f7');self.d=ImageDraw.Draw(self.image)
        self.fonts={n:ImageFont.truetype(str(font),n) for n in (20,23,25,28,31,38,45)};self.y=28
    def text(self,text,size=28,color='#213d49',pad=30,gap=10):
        font=self.fonts[size];line=''
        for char in str(text):
            if char=='\n' or (line and self.d.textlength(line+char,font=font)>self.width-2*pad):
                self.d.text((pad,self.y),line,font=font,fill=color);self.y+=size+12;line='' if char=='\n' else char
            else:line+=char
        if line:self.d.text((pad,self.y),line,font=font,fill=color);self.y+=size+12
        self.y+=gap
    def box(self,title,value,detail=None,color='#0a7776'):
        height=100+(44 if detail else 0);self.d.rounded_rectangle((24,self.y,self.width-24,self.y+height),radius=12,fill='white',outline='#d9e3e6')
        self.d.text((42,self.y+13),title,font=self.fonts[23],fill='#526a74')
        self.d.text((42,self.y+49),str(value),font=self.fonts[31],fill=color)
        if detail:self.d.text((42,self.y+92),detail,font=self.fonts[20],fill='#647681')
        self.y+=height+12
    def picture(self,path,maxheight=800):
        image=Image.open(path).convert('RGB');image.thumbnail((self.width-48,maxheight),Image.Resampling.LANCZOS)
        self.image.paste(image,((self.width-image.width)//2,self.y));self.y+=image.height+14
    def save(self,path):
        self.image.crop((0,0,self.width,self.y+25)).save(path)


def count_text(value):return '미산출' if value is None else f'{value:,}개 영상 표본'


def main():
    if not Path('/.dockerenv').exists():raise RuntimeError('Docker required')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt',type=Path,required=True);p.add_argument('--font',type=Path,required=True)
    p.add_argument('--name',default='mobile_overview');p.add_argument('--screen-root',type=Path)
    p.add_argument('--supplemental-probe',type=Path,help='Explicit optional completed additional probe root containing P2/P3 receipts')
    a=p.parse_args();out=a.attempt/a.name
    if out.exists():raise FileExistsError(out)
    out.mkdir();started=time.time();provenance=[]
    def bound(path,expected=None):
        digest=sha(path)
        if expected is not None and digest!=expected:raise ValueError('Changed sealed input: '+str(path))
        provenance.append(dict(path=str(path),sha256=digest,bytes=Path(path).stat().st_size));return Path(path)
    prep=a.attempt/'prepare_v2';parent=read(bound(prep/'receipt.json'))
    if parent['status']!='PASS_PREPARED_CASES' or parent.get('scientific_verdict') is not None:raise ValueError('Prepared evidence not complete')
    seals={r['path']:r['sha256'] for r in parent['outputs']}
    cases=read(bound(prep/'cases.json',parent['cases_sha256']))
    inventory=read(bound(prep/'candidate_inventory.json',seals['candidate_inventory.json']))
    screenroot=a.screen_root or a.attempt/'screen'
    screen_case_hash=None
    if (a.attempt/'prepare_screen/receipt.json').exists():
        sp=read(bound(a.attempt/'prepare_screen/receipt.json'))
        if sp['status']!='PASS_PREPARED_CASES':raise ValueError('Supplemental preparation failed')
        screen_case_hash=sp['cases_sha256'];bound(a.attempt/'prepare_screen/cases.json',screen_case_hash)
    rows=[]
    for r in cases['regions']:
        rid=r['id'];pr=a.attempt/'probe'/rid;receipt=read(bound(pr/'receipt.json'))
        if (receipt['status']!='PASS_BOUNDED_INFERENCE_DIAGNOSTIC' or receipt.get('scientific_verdict') is not None
                or receipt['cases_sha256']!=sha(prep/'cases.json')):raise ValueError('Original Gaussian probe is not sealed and complete: '+rid)
        results=[]
        for c in r['cases']:
            rel=c['case_id']+'/result.json';results.append(read(bound(pr/rel,receipt['output_sha256'][rel])))
        first=r['cases'][0];result=results[0]
        inputs=bound(prep/first['case_id']/'01_inputs.png',seals[first['case_id']+'/01_inputs.png'])
        admitted=sum(x['admitted_probe_points'] for x in inventory if x['camera'].startswith(rid+'_'))
        candidates=sum(x['candidate_points'] for x in inventory if x['camera'].startswith(rid+'_'))
        screen=None;screenpath=screenroot/rid/'receipt.json'
        if rid in ('P2','P3') and screenpath.exists():
            screen=read(bound(screenpath))
            if (screen['status']!='PASS_ASSOCIATION_ONLY_SCREEN' or screen.get('scientific_verdict') is not None
                    or screen['cases_sha256']!=screen_case_hash or screen['checkpoint_sha256']!=receipt['checkpoint_sha256']
                    or screen.get('modified_gaussians')!=0 or screen.get('after_state_rendered') is not False):raise ValueError('Association-only screen failed identity/completion check: '+rid)
            if len(screen['cases'])!=admitted:raise ValueError('Screen does not cover every already-admitted observation: '+rid)
            if screen['eligible_count']!=sum(x['status']=='ELIGIBLE_FOR_BOUNDED_PROBE' for x in screen['cases']):raise ValueError('Screen count differs')
        eligible=screen['eligible_count'] if screen is not None else 0 if admitted==0 else None
        supplemental=None
        if a.supplemental_probe and (a.supplemental_probe/rid/'receipt.json').exists():
            sr=read(bound(a.supplemental_probe/rid/'receipt.json'))
            if (sr['status']!='PASS_BOUNDED_INFERENCE_DIAGNOSTIC' or sr.get('scientific_verdict') is not None
                    or sr['checkpoint_sha256']!=receipt['checkpoint_sha256']):raise ValueError('Supplemental probe not complete: '+rid)
            supplemental=dict(case_count=len(sr['cases']),modified_cases=sum(x['changed_ids']>0 for x in sr['cases']),
                changed_gaussian_ids_sum_across_separate_cases=sum(x['changed_ids'] for x in sr['cases']),
                cases=[dict(case_id=x['case_id'],status=x['status'],changed_ids=x['changed_ids'],maximum_displacement_m=x['actual_max_displacement_m']) for x in sr['cases']])
        row=dict(region=rid,candidate_observations=candidates,observation_admitted=admitted,
            gaussian_association_eligible_observations=eligible,association_screen_complete=screen is not None or admitted==0,
            original_probe_cases=len(results),original_modified_cases=sum(x['changed_ids']>0 for x in results),
            original_changed_gaussian_ids_sum_across_separate_cases=sum(x['changed_ids'] for x in results),
            first_case=dict(id=first['case_id'],selection=first['selection'],prior_depth_m=first['prior_depth'],mvs_depth_m=first['mvs_depth'],
                depth_difference_m=first['prior_depth']-first['mvs_depth'],source_decision=first['decision'],source_reasons=first['reason_codes'],
                selected_ids=result['selected_ids'],selected_target_alpha_fraction=result['selected_target_alpha_fraction'],
                association_reasons=result['association_reasons'],status=result['status'],changed_ids=result['changed_ids'],
                figure_path=str(inputs)),supplemental_probe=supplemental)
        rows.append(row)
        card=Card(a.font)
        card.text(rid+' · 불일치에서 Gaussian 연결까지',38)
        card.text('원자료에서 판정한 범위와 실제 수정 범위를 나눠 봅니다.',25,'#556c75')
        card.box('① 깊이가 다른 후보',count_text(candidates),'동일 표면의 반복 관측이 포함될 수 있음')
        card.box('② 가시성·같은 이웃·모호성 관측 판정',count_text(admitted)+' 통과')
        card.box('③ 같은 기준의 Gaussian 연결 검사',count_text(eligible)+' 통과' if eligible is not None else '아직 미산출',
                 '7×7 국소성 50% · 대상 기여 5% 기준 유지')
        if admitted>0 and eligible==0:
            card.text(f'관측을 통과한 {admitted}개 표본을 전부 검사했지만, 이번 고정 기준에서 수정 가능한 연결은 0개입니다.',25,'#865b14')
        card.box('④ 원래 3개 사례의 실제 수정',f'{row["original_modified_cases"]}개 사례 / {row["original_changed_gaussian_ids_sum_across_separate_cases"]}개 Gaussian',
                 '사례별 독립 수정 수의 합; 하나의 통합 수정 모델 아님')
        if supplemental is not None:
            card.box('추가로 실행한 제한된 수정',f'{supplemental["modified_cases"]}개 사례 / {supplemental["changed_gaussian_ids_sum_across_separate_cases"]}개 Gaussian')
        card.text('첫 사례의 실제 원사진·두 깊이·깊이차',28)
        card.text(f'Prior {first["prior_depth"]:.3f}m · MVS {first["mvs_depth"]:.3f}m · 차이 {row["first_case"]["depth_difference_m"]:+.3f}m',23)
        card.picture(inputs,730)
        card.text('첫 사례의 연결 결과',31)
        card.text(f'국소성 통과 ID {result["selected_ids"]}개 · 대상 기여 {100*result["selected_target_alpha_fraction"]:.3f}%',25)
        for reason in result['association_reasons']:card.text('• '+REASONS.get(reason,reason),25,'#865b14')
        if result['changed_ids']==0:card.text('이 사례는 실제 수정이 유보됐습니다. 전후 차이 0은 수정 성공이나 주변 보존 성공을 뜻하지 않습니다.',25,'#865b14')
        card.text('관측 통과 수는 변화 면적·고유 표면 수가 아닙니다. Gaussian 연결 통과도 시간 변화·정확도의 확정이 아닙니다.',23,'#556c75')
        card.save(out/(rid+'_overview.png'))
    total=Card(a.font)
    total.text('어디까지 판별됐고, 실제로 바뀌었나',38)
    total.text('Prior–MVS · P1/P2/P3 · 고정 Anchor8k',25,'#556c75')
    observed=sum(row['observation_admitted'] for row in rows)
    if all(row['association_screen_complete'] for row in rows):
        eligible_total=sum(row['gaussian_association_eligible_observations'] for row in rows)
        total.box('전체 관측 통과 → 고정 기준의 Gaussian 연결 통과',f'{observed}개 → {eligible_total}개',
                  '실제 변화영역·업데이트 효과가 검증됐다는 뜻은 아님')
    for row in rows:
        rid=row['region'];total.text(rid,38)
        total.text(f'불일치 후보 {row["candidate_observations"]:,} → 관측 통과 {row["observation_admitted"]}',28)
        value=row['gaussian_association_eligible_observations']
        total.text('Gaussian 연결 통과 '+('미산출' if value is None else str(value))+' / 원래 사례 실제 수정 '+str(row['original_modified_cases'])+'건',28,'#0a7776')
        total.picture(row['first_case']['figure_path'],290)
        first=row['first_case']
        total.text('첫 사례: '+('수정 유보' if first['changed_ids']==0 else str(first['changed_ids'])+'개 Gaussian 수정')+
                   f' · 연결 기여 {100*first["selected_target_alpha_fraction"]:.2f}%',23,'#865b14')
        if row['supplemental_probe'] is not None:
            total.text('추가 실행: 실제 수정 '+str(row['supplemental_probe']['modified_cases'])+'개 사례',23,'#0a7776')
    total.text('관측·연결·수정은 별도 단계입니다. 실제 수정이 없으면 전후 차이 0이며, 이를 수정 효과로 해석하지 않습니다.',25,'#865b14')
    total.text('숫자는 영상 표본 수입니다. 면적·고유 표면 수·실제 시간 변화율이 아닙니다.',23,'#556c75')
    total.text('7×7 관측 창·국소성 50%·깊이 차 0.25m·대상 기여 5%를 고정한 결과입니다. Gaussian 연결이 일반적으로 불가능하다는 결론은 아닙니다.',23,'#556c75')
    total.save(out/'P1_P2_P3_overview.png')
    summary=dict(task_id=cases['task_id'],scientific_verdict=None,regions=rows,
        interpretation='Observation admission, Gaussian association and actual intervention are distinct. No-update differences are not intervention benefits.',
        provenance=provenance,script_sha256=sha(__file__),font_sha256=sha(a.font))
    write(out/'summary.json',summary)
    write(out/'receipt.json',dict(task_id=cases['task_id'],status='PASS_MOBILE_OVERVIEW',scientific_verdict=None,
        script_sha256=sha(__file__),font_sha256=sha(a.font),source_receipts=provenance,
        wall_seconds=time.time()-started,outputs=[dict(path=str(p.relative_to(out)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.iterdir()) if p.is_file()]))
    print(json.dumps(dict(status='PASS_MOBILE_OVERVIEW',output=str(out),regions=len(rows))))


if __name__=='__main__':main()
