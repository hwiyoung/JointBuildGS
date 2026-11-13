"""r30 PHD-MAIN-TRAINERR-v1 addendum 3: two diagnostic switches for order 7 (work ba-1, ba-2). Defaults = r27/r28 behaviour.

--jbgs_a3_normal off     : the 2DGS normal-consistency term stays off after iteration 7000 (inherited: on when iteration > 7000).
--jbgs_a3_reset_after N  : no opacity reset (and no pre-reset record) at iterations > N (inherited -1 = every reset kept).
Only the two train.py gates call this module; no model, optimizer or random state is touched here.
"""


def register_args(parser):
    parser.add_argument('--jbgs_a3_normal', choices=['inherit', 'off'], default='inherit')
    parser.add_argument('--jbgs_a3_reset_after', type=int, default=-1)


def normal_active(iteration, args):
    """inherited train.py rule: lambda_normal if iteration > 7000 else 0."""
    return iteration > 7000 and getattr(args, 'jbgs_a3_normal', 'inherit') != 'off'


def reset_allowed(iteration, args):
    n = getattr(args, 'jbgs_a3_reset_after', -1)
    return n < 0 or iteration <= n
