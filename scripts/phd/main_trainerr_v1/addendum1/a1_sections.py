"""Order 7: positions of the sections used in the check figures (three cells) and the check-6 before/after cameras, for redrawing."""
from a1_common import *
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1')
def main():
    from te_figs import section_of
    out = {}
    for cell in ['c1', 'c2', 'c3']:
        stem = STEMS[cell]
        for arm in ARMS:
            z = loadz(O/'checks'/f'{stem}__{arm}.npz', ['cell', 'set', 'xyz']); L = (z['cell'] == int(cell[1])) & (z['set'] == 0)
            p0, p1, half, rule = section_of(cell, stem, z['xyz'][L]); out[f'{cell}_{arm}'] = dict(stem=stem, start_xy=p0.tolist(), end_xy=p1.tolist(), half_width_m=half, thickness_m=2*half, rule=rule)
    cams = dict(check6=dict(projection='orthographic vertex depth splat inside the record range box (region/<stem>.json grid bounds)', views=[dict(azimuth_deg=0, elevation_deg=90, name='top'), dict(azimuth_deg=45, elevation_deg=35), dict(azimuth_deg=225, elevation_deg=35)],
                rule='te_figs.splat: forward = -(cos e cos a, cos e sin a, sin e); right = forward x z_up; image 900x900, extent = max span of the projected vertices'))
    dump(A1D/'figures/sections_and_cameras.json', dict(at=now(), sections=out, cameras=cams, frame='site local frame; EPSG:25832 = local + [690953, 5336071, 604]', scientific_verdict=None)); print('SECTIONS', list(out))
if __name__ == '__main__': main()
