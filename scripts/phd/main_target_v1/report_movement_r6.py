from report_r6 import movement,OUT
for prior in ['ALS','LoD2']:
 run=OUT/'r6/runs'/f'tg_B173nb_b10_{prior}_s0_r6';rows,events=movement(prior,run);print('MOVEMENT_R6',prior,rows,events,flush=True)
