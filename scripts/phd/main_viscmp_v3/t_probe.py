"""PHD-MAIN-VISCMP-v3 probe: the distance task's modules load in this container and the stored d_g of one case reproduces (no figure)."""
import time
import numpy as np
import vd_dist as VD
t0 = time.time()
C = VD.Case("B173nb_b10", "ALS")
print("case", time.time() - t0, len(C.gt.Gb), len(C.u.r_P), flush=True)
st = C.stored("samepath_ALS")
print("stored", st["file"], np.median(np.abs(st["rows"])), flush=True)
