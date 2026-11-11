"""Check: full-resolution photo camera (FINALTRAIN inherited Cameras) vs the training camera (GTJUDGE views) for the same image."""
from a1_common import *
def main():
    cam = cameras('B0_b10'); views = {v['name']: v for v in train_views('B0_b10')}; rows = []
    for j, n in enumerate(cam.names):
        if n not in views: rows.append(dict(name=n, in_views=False)); continue
        E = np.asarray(views[n]['W2C']); Ct = -E[:3, :3].T@E[:3, 3]; Cp = cam.centres[j]
        rows.append(dict(name=n, member=cam.members[j], centre_diff_m=float(np.linalg.norm(Ct-Cp)), rot_diff=float(np.abs(E[:3, :3]-cam.R[j]).max()), K_train=np.asarray(views[n]['K']).round(2).tolist()[0], full_p=cam.p[:4].round(2).tolist(), w=cam.w, h=cam.h))
    d = np.array([r.get('centre_diff_m', np.nan) for r in rows]); print('n', len(rows), 'centre diff max', np.nanmax(d), 'rot max', max(r.get('rot_diff', 0) for r in rows)); print(rows[0]); print([r for r in rows if r['name'] == 'DJI_20241217093905_0026_D'])
    atable('camera_check', rows)
if __name__ == '__main__': main()
