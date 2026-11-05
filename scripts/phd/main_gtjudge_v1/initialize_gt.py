"""Actual target-file initialization check; reuse inherited validation, no training."""
import sys
from common import *
site,prior=sys.argv[1:];stage_lock(3);stem=f'{site}__{prior}'
src=R/'scripts/phd/main_finaltrain_v1/initialize_check.py'
text=src.read_text().replace("'--jbgs_target','on'","'--jbgs_targets',str(O/'targets_gt'/f'{stem}.npz'),'--jbgs_target','on'")
import common,numpy as np
common.np=np;common.S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
exec(compile(text,str(src),'exec'),{'__file__':str(src),'__name__':'initialize_gt'})
