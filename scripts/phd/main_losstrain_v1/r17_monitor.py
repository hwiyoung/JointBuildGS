"""Opt-in LOSSTRAIN observations; no optimizer, protection or density decisions."""

def lt_observe(j, iteration, gaussians, total, rgb, depth, package, camera):
    """Called before backward; record-only autograd calls preserve retained grads."""
    if not j.args.jbgs_lt_monitor:
        return
    def write(name, row):
        with (j.mon / name).open('a') as f:
            f.write(json.dumps(row, allow_nan=False) + '\n')
    prior = gaussians.origin == ORIGIN_PRIOR
    opacity = gaussians.get_opacity.detach().reshape(-1)
    med = float(torch.quantile(opacity[prior], .5)) if bool(prior.any()) else None
    finite = bool(torch.isfinite(total))
    stop = 'nonfinite loss' if not finite else ('prior opacity median < 0.05' if med is not None and med < .05 else None)
    if iteration == 1 or iteration % 100 == 0 or stop:
        write('losstrain_health.jsonl', dict(iteration=iteration, camera=camera, gaussians=len(opacity),
            prior_gaussians=int(prior.sum()), prior_opacity_median=med,
            loss_total=float(total.detach()) if finite else None, stop=stop, scientific_verdict=None))
    if stop:
        raise RuntimeError('LOSSTRAIN_STOP: ' + stop)
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
    write('losstrain_gradients.jsonl', dict(iteration=iteration, camera=camera, values=values,
        definition='Euclidean norm per Gaussian centre, including zeros; each iteration median; depth includes lambda; visible median supplementary',
        scientific_verdict=None))
