"""Opt-in LOSSTRAIN observations; no optimizer, protection or density decisions."""

def lt_write(j, name, row):
    with (j.mon / name).open('a') as f:
        f.write(json.dumps(row, allow_nan=False) + '\n')


def lt_reset_observed(j, iteration, periodic):
    """Called only after the original reset executes; never changes its inputs."""
    if periodic:
        j.lt_last_periodic_reset = iteration
    lt_write(j, 'losstrain_resets.jsonl', dict(iteration=iteration, periodic=bool(periodic),
        observation_phase='after original reset', scientific_verdict=None))


def lt_opacity_health(j, iteration, gaussians, camera, phase):
    prior = gaussians.origin == ORIGIN_PRIOR
    opacity = gaussians.get_opacity.detach().reshape(-1).float()
    finite = bool(torch.isfinite(opacity).all())
    med = float(torch.quantile(opacity[prior], .5)) if finite and bool(prior.any()) else None
    reset = getattr(j, 'lt_last_periodic_reset', None)
    offset = None if reset is None else iteration - reset
    grace = j.args.jbgs_lt_opacity_reset_grace
    skip = grace > 0 and offset is not None and 0 < offset < grace
    stop = 'nonfinite opacity' if not finite else ('prior opacity median < 0.05' if not skip and med is not None and med < .05 else None)
    row = dict(iteration=iteration, camera=camera, gaussians=len(opacity), prior_gaussians=int(prior.sum()),
        prior_opacity_median=med, observation_phase=phase, last_periodic_reset=reset,
        iterations_after_reset=offset, opacity_stop_deferred=skip, stop=stop, scientific_verdict=None)
    if iteration == 1 or iteration % 100 == 0 or offset == 1 or stop:
        lt_write(j, 'losstrain_health.jsonl', row)
    if grace and offset == grace:
        if not hasattr(j, 'lt_nojudge_opacity'):
            with open(j.args.jbgs_lt_nojudge_opacity) as f:
                j.lt_nojudge_opacity = json.load(f)
        baseline = j.lt_nojudge_opacity
        assert baseline['observation_phase'] == phase
        reference = baseline['medians'][str(iteration)]
        lt_write(j, 'losstrain_reset_comparison.jsonl', dict(**row, nojudge_prior_opacity_median=reference,
            difference_from_nojudge=None if med is None else med-reference,
            nojudge_source=baseline['source'], nojudge_source_sha256=baseline['source_sha256']))
    if stop:
        raise RuntimeError('LOSSTRAIN_STOP: ' + stop)


def lt_observe(j, iteration, gaussians, total, rgb, depth, package, camera):
    """Called before backward; record-only autograd calls preserve retained grads."""
    if not j.args.jbgs_lt_monitor:
        return
    opacity = gaussians.get_opacity.detach().reshape(-1)
    finite = bool(torch.isfinite(total))
    stop = 'nonfinite loss' if not finite else ('nonfinite opacity' if not bool(torch.isfinite(opacity).all()) else None)
    if stop:
        lt_write(j, 'losstrain_health.jsonl', dict(iteration=iteration, camera=camera,
            observation_phase='before backward', stop=stop, scientific_verdict=None))
        raise RuntimeError('LOSSTRAIN_STOP: ' + stop)
    if not getattr(j.args, 'jbgs_lt_monitor_v2', 0) and not j.args.jbgs_lt_opacity_reset_grace:
        lt_opacity_health(j, iteration, gaussians, camera, 'before backward')
    lo, hi = j.args.jbgs_lt_gradient_from, j.args.jbgs_lt_gradient_to
    if not (lo > 0 and lo <= iteration <= hi):
        return
    vsp = package['viewspace_points']
    retained = vsp.grad.clone() if vsp.grad is not None else None
    values = {}
    try:
        for name, loss in [('rgb', rgb), ('depth', depth)]:
            g, = torch.autograd.grad(loss, gaussians._xyz, retain_graph=True, allow_unused=True)
            norm = torch.zeros(len(opacity), device=opacity.device) if g is None else g.detach().norm(dim=1)
            if not bool(torch.isfinite(norm).all()):
                raise RuntimeError('LOSSTRAIN_STOP: nonfinite diagnostic centre gradient')
            visible = package['visibility_filter'].bool()
            values[name] = dict(all_median=float(torch.quantile(norm, .5)), gaussians=len(norm),
                visible_median=float(torch.quantile(norm[visible], .5)) if bool(visible.any()) else None,
                visible_gaussians=int(visible.sum()), positive_gaussians=int((norm > 0).sum()))
    finally:
        vsp.grad = retained
    lt_write(j, 'losstrain_gradients.jsonl', dict(iteration=iteration, camera=camera, values=values,
        definition='Euclidean norm per Gaussian centre, including zeros; each iteration median; depth includes lambda; visible median supplementary',
        scientific_verdict=None))


def lt_track_birth(j, gaussians):
    """Sidecar only: wrappers delegate unchanged density operations and arguments."""
    j.lt_initial_survivor = np.ones(len(gaussians.get_xyz), dtype=bool)
    original_postfix, original_prune = gaussians.densification_postfix, gaussians.prune_points

    def postfix(*args, **kwargs):
        before = len(gaussians.get_xyz)
        result = original_postfix(*args, **kwargs)
        added = len(gaussians.get_xyz) - before
        j.lt_initial_survivor = np.concatenate((j.lt_initial_survivor, np.zeros(added, dtype=bool)))
        assert len(j.lt_initial_survivor) == len(gaussians.get_xyz)
        return result

    def prune(*args, **kwargs):
        mask = args[0] if args else kwargs['mask']
        keep = ~mask.detach().cpu().numpy().astype(bool)
        result = original_prune(*args, **kwargs)
        j.lt_initial_survivor = j.lt_initial_survivor[keep]
        assert len(j.lt_initial_survivor) == len(gaussians.get_xyz)
        return result

    gaussians.densification_postfix, gaussians.prune_points = postfix, prune


def lt_monitor_initialize(j, gaussians, scene):
    lt_track_birth(j, gaussians)
    with np.load(j.mon / 'init_points.npz') as z:
        planted = z['planted'].astype(bool)
        assert np.array_equal(z['xyz'][planted], j.init_xyz.detach().cpu().numpy())
        loc = z['location'][planted].astype(np.int64)
    # Evaluation geometry is read only into this CPU diagnostic sidecar. No value
    # from it enters a loss, protection, density decision, opacity or PSNR halt.
    with np.load(j.args.jbgs_lt_diagnostic_cells) as z:
        cell = z['cell']
    j.lt_initial_cell = np.full(len(loc), 6, dtype=np.int8)
    valid = (loc >= 0) & (loc < len(cell))
    j.lt_initial_cell[valid] = cell[loc[valid]]
    with open(j.args.jbgs_lt_nojudge_inventory) as f:
        j.lt_baseline = json.load(f)
    cams = scene.getTrainCameras()
    j.lt_diagnostic_cameras = [cams[i % len(cams)] for i in range(5, 30, 5)]
    assert sorted(c.image_name for c in j.lt_diagnostic_cameras) == j.lt_baseline['legacy5_camera_names']
    j.lt_reference_psnr = {x['iteration']: x['psnr_db'] for x in j.lt_baseline['train_psnr_legacy5']}
    assert set(j.lt_reference_psnr) == {7000, 15000, 30000}


def lt_whole_stop(finite, median, offset):
    if not finite:
        return 'nonfinite opacity'
    if offset is not None and offset >= 100 and median is not None and median < .05:
        return 'whole-population opacity median < 0.05 after reset+100'
    return None


def lt_psnr_stop(iteration, value, references):
    if not math.isfinite(value):
        return 'nonfinite training PSNR'
    if iteration in references and references[iteration] - value > 3.:
        return 'training PSNR more than 3 dB below same-iteration nojudge'
    return None


def lt_population_summary(opacity, origin, ids, initial_cell, initial_survivor=None):
    def summary(mask):
        return dict(count=int(mask.sum()), opacity_median=float(np.median(opacity[mask])) if mask.any() else None)
    prior = origin == 1
    cell = np.full(len(ids), 6, dtype=np.int8)
    valid = (ids >= 0) & (ids < len(initial_cell))
    cell[valid] = initial_cell[ids[valid]]
    groups = dict(all=summary(np.ones(len(ids), bool)), prior_lineage=summary(prior),
        image_lineage=summary(origin == 0),
        prior_gt_correct=summary(prior & np.isin(cell, [0, 2, 4])),
        prior_gt_incorrect=summary(prior & np.isin(cell, [1, 3, 5])),
        prior_gt_unknown=summary(prior & (cell == 6)))
    if initial_survivor is not None:
        assert len(initial_survivor) == len(opacity)
        groups.update(initial_prior=summary(initial_survivor & prior),
            initial_image=summary(initial_survivor & (origin == 0)), density_born=summary(~initial_survivor))
        assert sum(groups[k]['count'] for k in ['initial_prior', 'initial_image', 'density_born']) == len(opacity)
    return groups


def lt_five_psnr(j, gaussians, render, pipe, background):
    """Exactly the historical five-view calculation; observation preserves RNG."""
    import random
    from utils.image_utils import psnr
    state = (random.getstate(), np.random.get_state(), torch.get_rng_state(), torch.cuda.get_rng_state_all())
    values = []
    try:
        with torch.no_grad():
            for cam in j.lt_diagnostic_cameras:
                pkg = render(cam, gaussians, pipe, background)
                image = pkg['render'].clamp(0., 1.)
                gt = cam.original_image[0:3].cuda().clamp(0., 1.)
                values.append(dict(camera=cam.image_name, psnr_db=float(psnr(image, gt).mean().double())))
                del pkg, image, gt
    finally:
        random.setstate(state[0]); np.random.set_state(state[1])
        torch.set_rng_state(state[2]); torch.cuda.set_rng_state_all(state[3])
    return float(np.mean([x['psnr_db'] for x in values])), values


def lt_monitor_step(j, iteration, gaussians, camera, render, pipe, background, pre_reset=False):
    opacity = gaussians.get_opacity.detach().reshape(-1).float()
    finite = bool(torch.isfinite(opacity).all())
    median = float(torch.quantile(opacity, .5)) if finite and len(opacity) else None
    reset = getattr(j, 'lt_last_periodic_reset', None)
    offset = None if reset is None else iteration - reset
    stop = lt_whole_stop(finite, median, offset)
    phase = 'immediately before actual periodic reset, after density' if pre_reset else 'after optimizer and opacity floors, before density/reset'
    row = dict(iteration=iteration, camera=camera, observation_phase=phase, last_periodic_reset=reset,
        iterations_after_reset=offset, gaussians=len(opacity), whole_opacity_median=median,
        prior_opacity_is_record_only=True, stop=stop, scientific_verdict=None)
    if iteration == 1 or iteration % 100 == 0 or stop:
        lt_write(j, 'losstrain_health_v2.jsonl', row)
    if stop and not finite:
        raise RuntimeError('LOSSTRAIN_STOP: ' + stop)
    due = pre_reset or iteration % 1000 == 0 or offset in [100, 500] or bool(stop)
    if not due:
        return
    groups = lt_population_summary(opacity.cpu().numpy(), gaussians.origin.detach().cpu().numpy(),
        gaussians.init_id.detach().cpu().numpy().astype(np.int64), j.lt_initial_cell, j.lt_initial_survivor)
    value, per_view = lt_five_psnr(j, gaussians, render, pipe, background)
    stop = stop or lt_psnr_stop(iteration, value, j.lt_reference_psnr)
    reference = j.lt_reference_psnr.get(iteration)
    row.update(groups=groups, train_psnr_legacy5=value, psnr_per_view=per_view,
        nojudge_train_psnr_legacy5=reference, nojudge_unsaved_statistics='기록 없음',
        nojudge_psnr_status='same iteration available' if reference is not None else '기록 없음',
        psnr_drop_db=None if reference is None else reference-value, stop=stop)
    lt_write(j, 'losstrain_observations_v2.jsonl', row)
    if iteration in [15000, 30000] and not pre_reset:
        np.savez_compressed(j.mon / f'losstrain_birth_{iteration}.npz', initial_survivor=j.lt_initial_survivor)
    if stop:
        raise RuntimeError('LOSSTRAIN_STOP: ' + stop)
