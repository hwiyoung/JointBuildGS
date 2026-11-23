"""Order 1 check: per scene, the patch judgement in the 판 0 target equals the 나5 columns (joined patches); differences counted with their reason. CPU.
usage: df_check1.py <stem>"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
def main(stem):
    pi = loadz(O/'patchinfo'/f'{stem}.npz'); m = pi['joined']; A = pi['area']; lo = pi['judge_lo']; reg = pi['region']
    # expected judgement code from the 나5 columns (lo), FINALTRAIN code space; 9 resolved by the undecided rule -> compare after resolving
    same = m & ((reg == lo) | (lo == 9))
    why = dict(no_scene_image_height=m & pi['no_scene_height'], no_scene_u=m & pi['no_scene_u'])
    other = m & ~same & ~why['no_scene_image_height'] & ~why['no_scene_u']
    rows = [dict(stem=STEM_KO[stem], joined_patches=int(m.sum()), joined_area_m2=float(A[m].sum()), equal_patches=int(same.sum()), equal_area_pct=100*float(A[same].sum()/A[m].sum()),
                 undecided_rule_patches=int((m & (lo == 9)).sum()),
                 differ_no_scene_image_height=int(why['no_scene_image_height'].sum()), differ_no_scene_image_height_area_m2=float(A[why['no_scene_image_height']].sum()),
                 differ_no_scene_u=int(why['no_scene_u'].sum()), differ_other=int(other.sum()), unjoined_patches=int((~m).sum()), unjoined_area_m2=float(A[~m].sum()),
                 unjoined_in_eval=int((~m & pi['in_eval']).sum()), unjoined_in_eval_area_m2=float(A[~m & pi['in_eval']].sum()),
                 rule='같음 = 판 0 목표 파일의 판정 번호가 나5 열(combo_D_judgment, none_significant, mix_large)로 낸 번호와 같음; 미판정은 본 방법 판 규칙으로 풂')]
    table(f'check1_{stem}', rows, D/'tables/pre'); print('CHECK1', json.dumps(rows[0], ensure_ascii=False), flush=True)
if __name__ == '__main__': main(sys.argv[1])
