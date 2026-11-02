"""Generate unapplied unified diffs; read training sources, never write them."""
import ast,difflib,json,re,subprocess,datetime
from r8_screen_prepare import R,O,C,local,sha,dump
def main():
 cfg=json.loads((C/'screen_sim.json').read_text());d=R/'docs/experiments/phd/main_target_v1/screen_sim/patches';d.mkdir(parents=True,exist_ok=True)
 sources={k:next(r['source'] for r in cfg['states'] if r['key']==s) for k,s in [('r15','base_ALS_30000'),('r22','r8_ALS_30000'),('image_only_2DGS','image_only_2DGS_30000'),('GeoGS','GeoGS_ALS_30000')]};sources['CDGS_prepared_only']='/ph/main_baselines_v1/PHD-MAIN-BASELINES-v1/sources/cdgs-release-adapters-v2';records=[]
 for name,src in sources.items():
  root=local(src);changed={};hashes={}
  for f in ['scene/gaussian_model.py','arguments/__init__.py','train.py']:
   old=(root/f).read_text();hashes[f]=sha(root/f);new=old
   if f.startswith('scene/'):
    start=new.index('    def densify_and_prune(');end=new.index('\n    def ',start+5);part=new[start:end]
    pre='''        # Screen-only pruning must read the history BEFORE postfix clears it.
        # Threshold is supplied explicitly; no value is chosen by this patch.
        if max_screen_size is not None:
            if not (0 < float(max_screen_size) < float("inf")):
                raise ValueError("screen_prune_px must be finite and positive")
            screen_prune = self.max_radii2D > max_screen_size
'''
    if 'self.density_exempt()' in part:pre+='''            exempt = self.density_exempt()
            if exempt is not None:
                screen_prune = torch.logical_and(screen_prune, ~exempt)
'''
    elif 'self.frozen_mask' in part:pre+='''            if self.frozen_mask is not None:
                screen_prune = torch.logical_and(screen_prune, ~self.frozen_mask)
'''
    pre+='''            if screen_prune.any():
                self.prune_points(screen_prune)

'''
    needle='        grads = self.xyz_gradient_accum / self.denom';assert part.count(needle)==1;part=part.replace(needle,pre+needle)
    assert part.count('            big_points_vs = self.max_radii2D > max_screen_size')==1;part=part.replace('            big_points_vs = self.max_radii2D > max_screen_size\n','')
    needle='torch.logical_or(torch.logical_or(prune_mask, big_points_vs), big_points_ws)';assert needle in part;part=part.replace(needle,'torch.logical_or(prune_mask, big_points_ws)');new=new[:start]+part+new[end:]
   elif f.startswith('arguments/'):
    start=new.index('class OptimizationParams(');part=new[start:];needle='        self.opacity_reset_interval = 3000';assert needle in part;part=part.replace(needle,needle+'\n        self.screen_prune_px = 0.0  # type declaration only; parser default below is None')
    matches=list(re.finditer(r'^        super\(\).__init__\(parser, .*\)$',part,re.M));assert len(matches)==1;match=matches[0];part=part[:match.end()]+'\n        parser.set_defaults(screen_prune_px=None)  # user must choose after simulation'+part[match.end():];new=new[:start]+part
   else:
    needle='size_threshold = 20 if iteration > opt.opacity_reset_interval else None';assert new.count(needle)==1;new=new.replace(needle,'size_threshold = opt.screen_prune_px if iteration > opt.opacity_reset_interval else None')
    match=re.search(r'^def training\(dataset, opt, .*\):\n',new,re.M);assert match
    pre='''    if opt.screen_prune_px is None or not (0 < float(opt.screen_prune_px) < float("inf")):
        raise ValueError("Choose --screen_prune_px explicitly after the screen-size simulation")
''';new=new[:match.end()]+pre+new[match.end():]
   assert old!=new;ast.parse(new);changed[f]=(old,new)
  patch=''.join(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+f,tofile='b/'+f,n=5)) for f,(old,new) in changed.items());p=d/(name+'.patch');assert not p.exists();p.write_text(patch)
  check=subprocess.run(['git','apply','--check',str(p)],cwd=root,capture_output=True,text=True);assert check.returncode==0,(name,check.stderr)
  assert all(sha(root/f)==h for f,h in hashes.items());records.append(dict(implementation=name,source=src,executed=name!='CDGS_prepared_only',source_hashes=hashes,patch_sha256=sha(p),syntax='PASS (AST only)',apply_check='PASS (not applied)',threshold_px=None,applied=False,protection='existing density_exempt preserved' if 'self.density_exempt()' in changed['scene/gaussian_model.py'][0] else 'none',scientific_verdict=None))
 dump(d/'index.json',dict(at=datetime.datetime.now().astimezone().isoformat(),patches=records,training=False,scientific_verdict=None))
 (d/'설계와_단위점검.md').write_text('''# 화면 크기 검사 수정안 — 미적용

문턱은 비워 두었다. 다섯 패치는 원본에 적용하지 않았으며, 문법과 `git apply --check`만 확인했다. 실제 학습 및 단위 실행은 하지 않았다. CDGS는 준비된 어댑터이며 완료 학습 구현으로 표시하지 않는다.

화면 크기 검사만 복제·분할 전에 한다. 아직 살아 있는 원본 행과 누적 반지름이 그대로 대응하므로, 기록을 복사한 뒤 자식·부모 삭제 인덱스를 다시 연결할 필요가 없다. 화면 크기로 지울 부모는 자식을 만들지 않는다. 이후 기존 복제·분할과 불투명도·세계 크기 검사는 기존 순서를 따른다. 기존 보호 마스크도 유지하므로 보호된 기준선 사전 정보에는 그 예외가 남는다. 이 예외는 방법 간 규칙 비교에서 별도로 공개해야 한다.

`--screen_prune_px`는 float이며 기본값은 None이다. 미래 실행은 양의 유한 값을 명시하지 않으면 학습 진입 시 실패한다. 켜지는 시점은 기존대로 첫 불투명도 초기화 이후이다. 이번 203장 가로는 모두 1024 px이며 후보는 20, 102.4, 256, 512 px이다. 어떤 값을 고를지는 이 패치가 정하지 않는다.

단위 점검 설계(미실행):

1. 반지름이 문턱 바로 아래·같음·바로 위인 세 원본과 정상 불투명도·세계 크기를 둔다. 다음 밀도 제어에서 위인 행만 제거되어야 한다.
2. 큰 반지름 행의 누적 기울기를 복제 및 분할 문턱 위로 각각 둔다. 두 경우 모두 그 부모와 그 부모에서 새로 생길 자식이 남지 않아야 한다.
3. 큰 행 하나와 여러 정상 행을 넣고 정상 행의 복제·분할 마스크를 고정한다. 정상 행의 최종 수와 출신 ID 수는 수정 전 실행과 같아야 한다. 큰 행을 먼저 제거하면 난수 소비 순서가 달라질 수 있으므로 자식 좌표의 바이트 동일성을 요구하지 않는다.
4. 기존 보호 마스크가 있는 구현에서는 보호된 큰 행을 남기고, 보호되지 않은 큰 행을 지워야 한다. r22의 배경·패치·풀림 꼬리표는 추가 예외를 만들지 않아야 한다.
5. 검사 직전 기록은 양수, 검사 뒤 postfix 기록은 0인 입력에서 큰 행 삭제를 확인한다. 복제할 점이 0개인 경우에도 같다.
6. 불투명도와 세계 크기만으로 지워지는 행은 기존과 동일해야 한다. 켜지는 반복 전에는 화면·세계 크기 검사가 이전과 같이 꺼져 있어야 한다.
7. 문턱 누락·0·음수·NaN·무한대는 학습 시작 전에 실패해야 한다. 선택할 문턱을 각 구현에 동일하게 전달한다.

scientific_verdict: null
''');print('UNAPPLIED_PATCHES',len(records))
if __name__=='__main__':main()
