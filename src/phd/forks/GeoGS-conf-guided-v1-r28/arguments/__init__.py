#
# Copyright (C) 2023, Inria
# GRAPHDECO research group, https://team.inria.fr/graphdeco
# All rights reserved.
#
# This software is free for non-commercial, research and evaluation use 
# under the terms of the LICENSE.md file.
#
# For inquiries contact  george.drettakis@inria.fr
#

from argparse import ArgumentParser, Namespace
import sys
import os

class GroupParams:
    pass

class ParamGroup:
    def __init__(self, parser: ArgumentParser, name : str, fill_none = False):
        group = parser.add_argument_group(name)
        for key, value in vars(self).items():
            shorthand = False
            if key.startswith("_"):
                shorthand = True
                key = key[1:]
            t = type(value)
            value = value if not fill_none else None 
            if shorthand:
                if t == bool:
                    group.add_argument("--" + key, ("-" + key[0:1]), default=value, action="store_true")
                else:
                    group.add_argument("--" + key, ("-" + key[0:1]), default=value, type=t)
            else:
                if t == bool:
                    group.add_argument("--" + key, default=value, action="store_true")
                else:
                    group.add_argument("--" + key, default=value, type=t)

    def extract(self, args):
        group = GroupParams()
        for arg in vars(args).items():
            if arg[0] in vars(self) or ("_" + arg[0]) in vars(self):
                setattr(group, arg[0], arg[1])
        return group

class ModelParams(ParamGroup): 
    def __init__(self, parser, sentinel=False):
        self.sh_degree = 3
        self._source_path = ""
        self._model_path = ""
        self._images = "images"
        self._resolution = -1
        self._white_background = False
        self.data_device = "cuda"
        self.eval = False
        self.render_items = ['RGB', 'Alpha', 'Normal', 'Depth', 'Edge', 'Curvature']

        # Add building-specific parameters
        self.building_mode = ""
        self.building_data_path = ""
        self.boundary_tolerance = 2

        # Depth loss scheme parameter
        self.depth_loss_scheme = "original"  # "original" or "dynamic"

        super().__init__(parser, "Loading Parameters", sentinel)

    def extract(self, args):
        g = super().extract(args)
        g.source_path = os.path.abspath(g.source_path)
        
        print(f"ModelParams.extract: args building_mode = {args.building_mode}")
        print(f"ModelParams.extract: args building_data_path = {args.building_data_path}")

        if hasattr(g, 'building_data_path') and g.building_data_path:
            g.building_data_path = os.path.abspath(g.building_data_path)
            print(f"ModelParams.extract: absolute building_data_path = {g.building_data_path}")
            if not os.path.exists(g.building_data_path):
                print(f"Warning: Building data path does not exist: {g.building_data_path}")
        else:
            print("ModelParams.extract: building_data_path not found in args or is empty")
        
        if hasattr(g, 'building_mode'):
            print(f"ModelParams.extract: g has building_mode = {g.building_mode}")
            valid_modes = ["default", "building_enhanced", "building_only"]
            if g.building_mode not in valid_modes:
                print(f"Warning: Invalid building mode '{g.building_mode}'. Using 'default' instead.")
                g.building_mode = "default"
        else:
            print("ModelParams.extract: building_mode not found in g")

        # Validate depth loss scheme
        if hasattr(g, 'depth_loss_scheme') and g.depth_loss_scheme not in ["original", "dynamic"]:
            print(f"Warning: Invalid depth_loss_scheme '{g.depth_loss_scheme}'. Using 'original' instead.")
            g.depth_loss_scheme = "original"
                
        return g

class PipelineParams(ParamGroup):
    def __init__(self, parser):
        self.convert_SHs_python = False
        self.compute_cov3D_python = False
        self.depth_ratio = 0.0
        self.debug = False
        super().__init__(parser, "Pipeline Parameters")

class OptimizationParams(ParamGroup):
    def __init__(self, parser):
        self.iterations = 30_000
        self.position_lr_init = 0.00016
        self.position_lr_final = 0.0000016
        self.position_lr_delay_mult = 0.01
        self.position_lr_max_steps = 30_000
        self.feature_lr = 0.0025
        self.opacity_lr = 0.05
        self.scaling_lr = 0.005
        self.rotation_lr = 0.001
        self.percent_dense = 0.01
        self.lambda_dssim = 0.2
        self.lambda_dist = 0.0
        # self.lambda_normal = 0.05
        self.lambda_normal = 0.05
        self.opacity_cull = 0.05

        self.densification_interval = 100
        self.opacity_reset_interval = 3000
        self.densify_from_iter = 500
        self.densify_until_iter = 15_000
        self.densify_grad_threshold = 0.0002

        # Add building-specific loss weights
        self.lambda_building_depth = 0.05  # Weight for building depth loss
        self.lambda_building_normal = 0.00  # Weight for building normal loss

        # Depth only mode specific parameters
        self.dynamic_weight_update_interval = 200  # Update dynamic weights every N iterations
        self.base_rgb_weight = 1.0      # Base weight for RGB loss in dynamic scheme
        self.base_depth_weight = 0.05    # Base weight for depth loss in dynamic scheme

        # Uncertainty weighting parameters for depth_loss_scheme="dynamic"
        self.use_uncertainty = False           # Enable uncertainty weighting (new method)
        self.loss_scale_depth = 0.05           # λ_d: depth loss scale alignment factor (only used when use_loss_normalization=False)
        self.s_init_rgb = 0.7                  # s_c initial value (positive → initially weaken RGB)
        self.s_init_depth = -3.0               # s_d initial value (negative → initially strengthen Depth)
        self.logs_lr_mult = 0.1                # Learning rate multiplier for s_* parameters
        self.logs_clamp_min = -5.0             # Lower bound for s_* values
        self.logs_clamp_max = 5.0              # Upper bound for s_* values
        self.warmup_iterations = 1000          # RGB-only warmup iterations before uncertainty kicks in

        # Normalization and update frequency for uncertainty weighting (old dual-uncertainty mode)
        self.use_loss_normalization = True     # Normalize losses to same scale (recommended)
        self.loss_norm_ema_decay = 0.99        # EMA decay for loss normalization (0.9-0.999)
        self.uncertainty_update_interval = 200 # Update s parameters every N iterations (1=every iter)

        # Depth-only dynamic weighting (similar to train_2dgs.py Mode 2, but for depth)
        # Uses Kendall's uncertainty with sigma constraint: depth_loss = λ * (L/σ + log(σ))
        self.sigma_depth_min = 0.05       # Min sigma (max effective weight = loss_scale_depth/0.05 = 1.0)
        self.sigma_depth_max = 25.0        # Max sigma (min effective weight = loss_scale_depth/2.0 = 0.025)
        self.sigma_depth_init = 0.0       # Initial log_sigma (exp(0)=1.0 → weight=0.05/1.0=0.05)
        self.sigma_depth_lr_mult = 0.1    # Learning rate multiplier for log_sigma_depth parameter

        # ========== Adaptive Depth Weight Decay (Dynamic Mode with Dual-Gate Control) ==========
        # Phase 1: Convergence Detection
        self.depth_convergence_window = 1200       # Convergence detection window (iterations)
        self.depth_convergence_threshold = 0.02    # Trigger convergence if median change < 2%

        # Phase 2: Decay Control
        self.depth_initial_weight = 0.05           # Initial depth weight (from iter 0)
        self.depth_min_weight = 0.02              # Minimum depth weight (safety lower bound)
        self.depth_decay_check_interval = 200      # Check decay conditions every N iterations
        self.depth_decay_factor = 0.95              # Multiplicative decay factor (weight *= 0.9)

        # Phase 3: Hysteresis Mechanism (Anti-jitter)
        self.depth_hysteresis_count = 2            # Require N consecutive passes before decay

        # Phase 4: Dual-Gate Conditions
        self.depth_monitor_window = 200            # Monitoring window for depth/RGB trends (iterations)
        self.depth_guard_threshold = 0.01          # Depth guard gate: allow depth rise ≤ 1%
        self.rgb_benefit_threshold = -0.01        # RGB benefit gate: require RGB drop > 1% to continue decay
        self.rgb_stable_threshold = 0.01           # RGB stable threshold: rise ≤ 1% considered stable

        # Dynamic weighting for default 2DGS mode (micro-tuning normal loss only)
        self.use_dynamic_weights = False  # Enable dynamic weighting for normal loss micro-tuning
        self.sigma_normal_min = 0.5       # Minimum sigma value (allows 2x weight increase)
        self.sigma_normal_max = 2.0       # Maximum sigma value (allows 0.5x weight decrease)
        self.dynamic_weight_start_iter = 7000  # Start micro-tuning when normal loss activates (align with original 2DGS)

        super().__init__(parser, "Optimization Parameters")

def get_combined_args(parser : ArgumentParser):
    cmdlne_string = sys.argv[1:]
    cfgfile_string = "Namespace()"
    args_cmdline = parser.parse_args(cmdlne_string)

    try:
        cfgfilepath = os.path.join(args_cmdline.model_path, "cfg_args")
        print("Looking for config file in", cfgfilepath)
        with open(cfgfilepath) as cfg_file:
            print("Config file found: {}".format(cfgfilepath))
            cfgfile_string = cfg_file.read()
    except TypeError:
        print("Config file not found at")
        pass
    args_cfgfile = eval(cfgfile_string)

    merged_dict = vars(args_cfgfile).copy()
    for k,v in vars(args_cmdline).items():
        if v != None:
            merged_dict[k] = v
    return Namespace(**merged_dict)
