"""Bounded profile of one already-selected public curve figure; measurements stay read-only."""
import cProfile,pstats,faulthandler,time
from common import *
from evaluate import join
from figures import plotting,curve_figure
from cameras import Cameras

def main():
    plt=plotting();cam=Cameras();d,p=join('LoD2','full')
    record=load(D/'figures/full/curve_DEBY_LOD2_4959326_LoD2_1.json')
    i=int(np.flatnonzero(p['point_id']==record['point_id'])[0]);prof=cProfile.Profile()
    faulthandler.dump_traceback_later(30,repeat=True)
    start=time.monotonic();prof.enable()
    curve_figure(plt,cam,d,p,i,O/'tmp/profile_curve','same saved public example; rendering profile only')
    prof.disable();faulthandler.cancel_dump_traceback_later()
    prof.dump_stats(str(O/'inspection/figure_profile.pstats'))
    pstats.Stats(prof).sort_stats('cumulative').print_stats(30)
    print('profile elapsed seconds',time.monotonic()-start,flush=True)
if __name__=='__main__':main()
