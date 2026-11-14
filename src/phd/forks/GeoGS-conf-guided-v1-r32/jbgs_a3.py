"""r30 PHD-MAIN-TRAINERR-v1 addendum 3: diagnostic switches for order 7 (work ba-1, ba-2). Defaults = r27/r28 behaviour.

--jbgs_a3_normal off       : the 2DGS normal-consistency term stays off after iteration 7000 (inherited: on when iteration > 7000).
--jbgs_a3_reset_after N    : no opacity reset (and no pre-reset record) at iterations > N (inherited -1 = every reset kept).
--jbgs_a3_count_check off  : (added for the ba-2 rerun) the FINALTRAIN health stop 'count_gt_3x_6000' is evaluated and written to the
                             monitor row but does not stop training (inherited 'on' = stop). It is a no_grad read of the Gaussian count only.
Only the two train.py gates and the FINALTRAIN monitor call this module; no model, optimizer or random state is touched here.
"""


def register_args(parser):
    parser.add_argument('--jbgs_a3_normal', choices=['inherit', 'off'], default='inherit')
    parser.add_argument('--jbgs_a3_reset_after', type=int, default=-1)
    parser.add_argument('--jbgs_a3_count_check', choices=['on', 'off'], default='on')


def normal_active(iteration, args):
    """inherited train.py rule: lambda_normal if iteration > 7000 else 0."""
    return iteration > 7000 and getattr(args, 'jbgs_a3_normal', 'inherit') != 'off'


def reset_allowed(iteration, args):
    n = getattr(args, 'jbgs_a3_reset_after', -1)
    return n < 0 or iteration <= n


def count_check_active(args):
    """inherited jbgs_finaltrain.py rule: stop when count > 3 x count at 6000 (iterations 7000..15000, every 1000)."""
    return getattr(args, 'jbgs_a3_count_check', 'on') != 'off'
