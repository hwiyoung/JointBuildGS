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
    if not j.args.jbgs_lt_opacity_reset_grace:
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
