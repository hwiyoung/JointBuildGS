"""Read-only source/patch/build-command audit; never apply a renderer patch."""
import csv,subprocess
from r8_screen_prepare import R,O,j,sha,dump
ROOT=O/'rfix';DEST=R/'docs/experiments/phd/main_target_v1/rfix'

def main():
 rows=[];builds=[]
 for label in ['target','imageonly','geogs']:
  base=ROOT/'inventory'/label/'source';fixed=ROOT/'builds'/label/'source';patch=ROOT/'builds'/label/'renderer.patch'
  result=subprocess.run(['git','apply','--check',str(patch)],cwd=base,capture_output=True,text=True);assert result.returncode==0,result.stderr
  refs=[('original','cuda_rasterizer/auxiliary.h','p_view.z <= 0.2f','center near culling; XY clause commented'),('original','cuda_rasterizer/forward.cu','if (d == 0.0)','AABB denominator exact-zero check'),('original','cuda_rasterizer/forward.cu','if (alpha < 1.0f / 255.0f)','native alpha threshold'),('original','cuda_rasterizer/backward.cu','atomicAdd(&dL_dtransMat[global_id * 9 + 0]','native atomic gradient addition'),('fixed','cuda_rasterizer/rasterizer_impl.cu','rf_count<<<','replace tiles_touched only'),('fixed','cuda_rasterizer/rasterizer_impl.cu','if (!rf_tile(','skip impossible tile before duplicate'),('fixed','cuda_rasterizer/rfix_tiles.cuh','bool rf_pixel(','original pixel predicate'),('fixed','cuda_rasterizer/rfix_tiles.cuh','bool rf_possible_interval(','conservative rejection'),('fixed','cuda_rasterizer/rfix_tiles.cuh','bool rf_tile(','any possible pixel retains tile')]
  for kind,name,needle,purpose in refs:
   p=(base if kind=='original' else fixed)/name;found=[i for i,line in enumerate(p.read_text().splitlines(),1) if needle in line];assert found,(label,name,needle)
   rows.append(dict(build=label,version=kind,file=name,lines=found,purpose=purpose,sha256=sha(p)))
  ninja=ROOT/'builds'/label/'extension/build.ninja';setup=base/'setup.py'
  builds.append(dict(label=label,patch_apply_check='PASS_CHECK_ONLY_UNAPPLIED',patch_sha256=sha(patch),original_setup_sha256=sha(setup),original_setup=setup.read_text(),fixed_build_ninja_sha256=sha(ninja),fixed_build_ninja=ninja.read_text(),original_versions=j(ROOT/'inventory'/label/'manifest.json')))
 dest=DEST/'tables';dest.mkdir(parents=True,exist_ok=True);dump(dest/'code_references.json',dict(rows=rows,scientific_verdict=None))
 keys=list(rows[0]);fmt=lambda x:__import__('json').dumps(x,ensure_ascii=False) if isinstance(x,list) else str(x)
 with (dest/'code_references.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,keys);w.writeheader();w.writerows({k:fmt(v) for k,v in r.items()} for r in rows)
 (dest/'code_references.md').write_text('\n'.join(['| '+' | '.join(keys)+' |','|'+'|'.join(['---']*len(keys))+'|']+['| '+' | '.join(fmt(r[k]) for k in keys)+' |' for r in rows])+'\n')
 dump(ROOT/'code_audit.json',dict(builds=builds,refs=rows,scientific_verdict=None));print('RFIX_CODE_AUDIT_PASS',len(rows),flush=True)

if __name__=='__main__':main()
