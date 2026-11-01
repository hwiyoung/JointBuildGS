"""Apply opt-in r7 hooks to the authorized copy; preserve r20 bytes."""
from pathlib import Path
R=Path(__file__).resolve().parents[3];F=R/'src/phd/forks/GeoGS-conf-guided-v1-r21'
def edit(name,a,b,count=1):
    p=F/name;s=p.read_text();assert s.count(a)==count,(name,a,s.count(a));p.write_text(s.replace(a,b))
def main():
    edit('jbgs_target.py',"choices=['r4n','r6']","choices=['r4n','r6','r7']")
    edit('jbgs_target.py',"    if args.jbgs_target=='on' and args.jbgs_target_rev=='r6':","    if args.jbgs_target=='on' and args.jbgs_target_rev=='r7':\n        from jbgs_target_r7 import TargetR7\n        return TargetR7(args,scene,g)\n    if args.jbgs_target=='on' and args.jbgs_target_rev=='r6':")
    edit('train.py','args.jbgs_target_rev == "r6"','args.jbgs_target_rev in ["r6", "r7"]',3)
    reset='                    gaussians.reset_opacity(exempt_mask=judgment.exempt_mask(gaussians) if judgment is not None else None)  # [jbgs_judgment]'
    edit('train.py',reset,reset+'\n                    if target_control is not None and args.jbgs_target_rev == "r7":\n                        target_control.last_opacity_reset = iteration')
    edit('jbgs_state.py',"getattr(args, 'jbgs_target_rev', None) == 'r6'","getattr(args, 'jbgs_target_rev', None) in ['r6', 'r7']")
    edit('jbgs_target_r6.py',"args.jbgs_target_rev!='r6'","args.jbgs_target_rev not in ['r6','r7']")
    edit('jbgs_target_r6.py',"    control.n6000=saved['n6000'];", "    if args.jbgs_target_rev=='r7':control.last_opacity_reset=saved.get('last_opacity_reset',-1)\n    control.n6000=saved['n6000'];")
    print('R21_HOOKS_READY')
if __name__=='__main__':main()
