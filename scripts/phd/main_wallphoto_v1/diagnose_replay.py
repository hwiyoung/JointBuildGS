"""Record independent-replay failures without altering stored measurements or gates."""
from common import *
from cameras import Cameras
from wall_report import point_sets
from verify_image_score import reference
from curves import compute


def main():
    folder = O / 'validation' / 'independent_replay_diagnostic'
    folder.mkdir(parents=True, exist_ok=True)
    cam = Cameras()
    rng = np.random.default_rng(20261028)
    rows = []
    for tile, p in point_sets('pilot'):
        ids = np.flatnonzero((p['selected_count'] >= 3) & (p['texture'] >= 5))
        if not len(ids):
            continue
        i = int(rng.choice(ids))
        expected = reference(cam, p, i)
        stored = p['curve'][i].astype(float)
        valid = np.isfinite(expected) & np.isfinite(stored)
        finite_mismatch = np.flatnonzero(np.isfinite(expected) != np.isfinite(stored))
        difference = abs(expected[valid] - stored[valid])
        one = {k: v[i:i+1] for k, v in p.items()}
        replay, timing = compute(one, one, 'cpu', chunk_points=1)
        fresh = replay['curve'][0]
        fresh_valid = np.isfinite(fresh) & np.isfinite(stored)
        row = dict(
            tile=tile, point_id=p['point_id'][i], row=i,
            max_difference=float(difference.max()) if len(difference) else None,
            finite_disagreement=int(len(finite_mismatch)),
            finite_mismatch_indices=finite_mismatch,
            finite_mismatch_heights=p['heights'][i][finite_mismatch],
            selected_images=p['selected_images'][i],
            pyramid_levels=p['pyramid_levels'][i],
            stored_texture=p['texture'][i],
            production_replay_finite_disagreement=int((np.isfinite(fresh) != np.isfinite(stored)).sum()),
            production_replay_max_difference=float(abs(fresh[fresh_valid]-stored[fresh_valid]).max()) if fresh_valid.any() else None,
            production_replay_float16_equal=bool(np.array_equal(fresh.astype(np.float16), p['curve'][i], equal_nan=True)),
            threshold_unchanged=0.01, scientific_verdict=None)
        rows.append(row)
        np.savez_compressed(folder / f'{tile}__point_{i}.npz',
            heights=p['heights'][i], expected=expected, stored=stored, fresh=fresh,
            valid_images=p['valid_images_per_height'][i],
            zero_variance=p['zero_variance_images_per_height'][i],
            **{f'point_{k}': v for k,v in one.items()})
        dump(folder / 'diagnostic.json', dict(at=now(), rows=rows, environment=env(), scientific_verdict=None))
        print(json.dumps(clean(row), ensure_ascii=False), flush=True)
        if len(rows) == 4:
            break


if __name__ == '__main__':
    main()
