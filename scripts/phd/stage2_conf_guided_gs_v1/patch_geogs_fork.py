"""Apply the stage-2 judgment patches to a GeoGS-mvs-pgsr-v1 fork (anchored, idempotent, every anchor must be unique).
Usage: python patch_geogs_fork.py <fork_root>   (build_fork.py copies jbgs_judgment.py into <fork_root> first)
Writes <fork_root>/jbgs_judgment_patch_report.json listing every replacement."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
report = {"root": str(root), "files": {}}
MARK = "# [jbgs_judgment]"


def patch(rel, edits):
    p = root / rel
    s = p.read_text()
    if MARK in s:
        report["files"][rel] = "already patched"
        return
    for i, (old, new) in enumerate(edits):
        if s.count(old) != 1:
            raise SystemExit(f"{rel}: anchor {i} found {s.count(old)} times:\n{old}")
        s = s.replace(old, new)
    p.write_text(s)
    report["files"][rel] = f"{len(edits)} edits"


# ------------------------------------------------------------------------------------------ gaussian_model.py
patch("scene/gaussian_model.py", [
    ("        self.completed_mask = None  # Track completed Gaussians for opacity floor protection\n        self.setup_functions()",
     "        self.completed_mask = None  # Track completed Gaussians for opacity floor protection\n"
     f"        self.origin = None  {MARK} per-disk origin: 0 image/SfM, 1 prior; inherited by children\n"
     f"        self.init_id = None  {MARK} index of the initial disk (-1: none); inherited by children\n"
     "        self.setup_functions()"),
    ("        self.max_radii2D = torch.zeros((self.get_xyz.shape[0]), device=\"cuda\")\n"
     "        self.frozen_mask = torch.zeros((self.get_xyz.shape[0]), dtype=torch.bool, device=\"cuda\")\n\n    def training_setup",
     "        self.max_radii2D = torch.zeros((self.get_xyz.shape[0]), device=\"cuda\")\n"
     "        self.frozen_mask = torch.zeros((self.get_xyz.shape[0]), dtype=torch.bool, device=\"cuda\")\n"
     f"        self.origin = torch.zeros((self.get_xyz.shape[0]), dtype=torch.int8, device=\"cuda\")  {MARK}\n"
     f"        self.init_id = torch.arange(self.get_xyz.shape[0], dtype=torch.int32, device=\"cuda\")  {MARK}\n\n    def training_setup"),
    ("        elements = np.empty(xyz.shape[0], dtype=dtype_full)\n"
     "        attributes = np.concatenate((xyz, normals, f_dc, f_rest, opacities, scale, rotation), axis=1)\n"
     "        elements[:] = list(map(tuple, attributes))\n",
     f"        {MARK} origin (and init_id) stored as extra int32 properties: 4-byte fields keep load_ply's strides valid\n"
     "        if self.origin is not None and self.origin.shape[0] == xyz.shape[0]:\n"
     "            dtype_full = dtype_full + [('origin', 'i4')]\n"
     "            origin_col = self.origin.detach().cpu().numpy().reshape(-1, 1).astype(np.float32)\n"
     "            if self.init_id is not None and self.init_id.shape[0] == xyz.shape[0]:\n"
     "                dtype_full = dtype_full + [('init_id', 'i4')]\n"
     "                origin_col = np.concatenate((origin_col, self.init_id.detach().cpu().numpy().reshape(-1, 1).astype(np.float32)), axis=1)\n"
     "        else:\n"
     "            origin_col = None\n"
     "        elements = np.empty(xyz.shape[0], dtype=dtype_full)\n"
     "        attributes = np.concatenate((xyz, normals, f_dc, f_rest, opacities, scale, rotation), axis=1)\n"
     "        if origin_col is not None:\n"
     "            attributes = np.concatenate((attributes, origin_col), axis=1)\n"
     "        elements[:] = list(map(tuple, attributes))\n"),
    ("    def reset_opacity(self):\n"
     "        opacities_new = self.inverse_opacity_activation(torch.min(self.get_opacity, torch.ones_like(self.get_opacity)*0.01))\n",
     f"    def reset_opacity(self, exempt_mask=None):  {MARK} locked disks keep their opacity\n"
     "        opacities_new = self.inverse_opacity_activation(torch.min(self.get_opacity, torch.ones_like(self.get_opacity)*0.01))\n"
     "        if exempt_mask is not None and exempt_mask.shape[0] == opacities_new.shape[0] and bool(exempt_mask.any()):\n"
     "            opacities_new = opacities_new.clone()\n"
     "            opacities_new[exempt_mask] = self._opacity.detach()[exempt_mask]\n"),
    ("        self.active_sh_degree = self.max_sh_degree\n"
     "        self.frozen_mask = torch.zeros((self.get_xyz.shape[0]), dtype=torch.bool, device=\"cuda\")\n",
     "        self.active_sh_degree = self.max_sh_degree\n"
     "        self.frozen_mask = torch.zeros((self.get_xyz.shape[0]), dtype=torch.bool, device=\"cuda\")\n"
     f"        {MARK} restore origin when present\n"
     "        names = [p.name for p in plydata.elements[0].properties]\n"
     "        if 'origin' in names:\n"
     "            self.origin = torch.tensor(np.asarray(plydata.elements[0]['origin']), dtype=torch.int8, device=\"cuda\")\n"
     "        else:\n"
     "            self.origin = torch.zeros((self.get_xyz.shape[0]), dtype=torch.int8, device=\"cuda\")\n"
     "        if 'init_id' in names:\n"
     "            self.init_id = torch.tensor(np.asarray(plydata.elements[0]['init_id']), dtype=torch.int32, device=\"cuda\")\n"
     "        else:\n"
     "            self.init_id = None\n"),
    ("        if self.completed_mask is not None:\n"
     "            self.completed_mask = self.completed_mask[valid_points_mask]\n",
     "        if self.completed_mask is not None:\n"
     "            self.completed_mask = self.completed_mask[valid_points_mask]\n"
     f"        if self.origin is not None:  {MARK}\n"
     "            self.origin = self.origin[valid_points_mask]\n"
     "        if self.init_id is not None:\n"
     "            self.init_id = self.init_id[valid_points_mask]\n"),
    ("    def densification_postfix(self, new_xyz, new_features_dc, new_features_rest, new_opacities, new_scaling, new_rotation):\n",
     f"    def densification_postfix(self, new_xyz, new_features_dc, new_features_rest, new_opacities, new_scaling, new_rotation, new_origin=None, new_init_id=None):  {MARK}\n"),
    ("        if self.completed_mask is not None:\n"
     "            self.completed_mask = torch.cat((self.completed_mask, torch.zeros((new_xyz.shape[0]), dtype=torch.bool, device=\"cuda\")), dim=0)\n",
     "        if self.completed_mask is not None:\n"
     "            self.completed_mask = torch.cat((self.completed_mask, torch.zeros((new_xyz.shape[0]), dtype=torch.bool, device=\"cuda\")), dim=0)\n"
     f"        if self.origin is not None:  {MARK} children inherit the parent's origin\n"
     "            if new_origin is None:\n"
     "                new_origin = torch.zeros((new_xyz.shape[0]), dtype=torch.int8, device=\"cuda\")\n"
     "            self.origin = torch.cat((self.origin, new_origin.to(torch.int8)), dim=0)\n"
     "        if self.init_id is not None:\n"
     "            if new_init_id is None:\n"
     "                new_init_id = torch.full((new_xyz.shape[0],), -1, dtype=torch.int32, device=\"cuda\")\n"
     "            self.init_id = torch.cat((self.init_id, new_init_id.to(torch.int32)), dim=0)\n"),
    ("        new_opacity = self._opacity[selected_pts_mask].repeat(N,1)\n\n"
     "        self.densification_postfix(new_xyz, new_features_dc, new_features_rest, new_opacity, new_scaling, new_rotation)\n",
     "        new_opacity = self._opacity[selected_pts_mask].repeat(N,1)\n"
     f"        new_origin = self.origin[selected_pts_mask].repeat(N) if self.origin is not None else None  {MARK}\n"
     "        new_init_id = self.init_id[selected_pts_mask].repeat(N) if self.init_id is not None else None\n\n"
     "        self.densification_postfix(new_xyz, new_features_dc, new_features_rest, new_opacity, new_scaling, new_rotation, new_origin=new_origin, new_init_id=new_init_id)\n"),
    ("        new_rotation = self._rotation[selected_pts_mask]\n\n"
     "        self.densification_postfix(new_xyz, new_features_dc, new_features_rest, new_opacities, new_scaling, new_rotation)\n",
     "        new_rotation = self._rotation[selected_pts_mask]\n"
     f"        new_origin = self.origin[selected_pts_mask] if self.origin is not None else None  {MARK}\n"
     "        new_init_id = self.init_id[selected_pts_mask] if self.init_id is not None else None\n\n"
     "        self.densification_postfix(new_xyz, new_features_dc, new_features_rest, new_opacities, new_scaling, new_rotation, new_origin=new_origin, new_init_id=new_init_id)\n"),
])

# ------------------------------------------------------------------------------------------- jbgs_mvs_pgsr.py
patch("jbgs_mvs_pgsr.py", [
    ("def from_environment(dataset, opt, pipe, args):\n    return Controller(dataset, opt, pipe, args)",
     f"def from_environment(dataset, opt, pipe, args):  {MARK} inert unless the MVS-PGSR environment is requested\n"
     "    if 'JBGS_MVS_PGSR_MODE' not in os.environ:\n"
     "        from jbgs_judgment import NullController\n"
     "        return NullController()\n"
     "    return Controller(dataset, opt, pipe, args)"),
])

# ------------------------------------------------------------------------------------------------ jbgs_state.py
patch("jbgs_state.py", [
    ("        'completed_mask': cpu_clone(g.completed_mask),\n",
     "        'completed_mask': cpu_clone(g.completed_mask),\n"
     f"        'origin': cpu_clone(getattr(g, 'origin', None)),  {MARK}\n"
     "        'init_id': cpu_clone(getattr(g, 'init_id', None)),\n"),
])

# ------------------------------------------------------------------------------------------------------ train.py
tp = root / "train.py"
s = tp.read_text()
if MARK not in s:
    def rep(old, new):
        global s
        if s.count(old) != 1:
            raise SystemExit(f"train.py: anchor found {s.count(old)} times:\n{old}")
        s = s.replace(old, new)

    rep("import jbgs_state\nimport jbgs_mvs_pgsr\n",
        f"import jbgs_state\nimport jbgs_mvs_pgsr\nimport jbgs_judgment  {MARK}\n")
    rep("    background = torch.tensor(bg_color, dtype=torch.float32, device=\"cuda\")\n\n    iter_start = torch.cuda.Event(enable_timing=True)\n",
        "    background = torch.tensor(bg_color, dtype=torch.float32, device=\"cuda\")\n"
        f"    {MARK} judgment-guided optimization (ORDER section 4); None keeps the native path\n"
        "    judgment = jbgs_judgment.Judgment(args, opt, scene, gaussians, tb_writer) if args.jbgs_judgment != \"off\" else None\n\n"
        "    iter_start = torch.cuda.Event(enable_timing=True)\n")
    rep("        iter_start.record()\n        gaussians.update_learning_rate(iteration)\n",
        "        iter_start.record()\n        gaussians.update_learning_rate(iteration)\n"
        f"        if judgment is not None and judgment.due_E(iteration):  {MARK} E at 0 and every e_interval\n"
        "            judgment.update_E(iteration, gaussians)\n")
    # wrap the native stage logic in an else-branch
    start = s.index("        # Stage switching (fixed or dynamic)\n")
    end = s.index("        mvs_pgsr_control.training_trace(\n")
    block = s[start:end]
    indented = "".join(("    " + ln if ln.strip() else ln) for ln in block.splitlines(True))
    branch = (f"        if judgment is not None:  {MARK} weighted MVS term + truncated prior term\n"
              "            mvs_term, prior_term, _jstats = judgment.losses(cam_name, render_pkg)\n"
              "            total_loss = rgb_loss + dist_loss + normal_loss + judgment.lambda_mvs * mvs_term + judgment.lambda_prior * prior_term\n"
              "            lod_depth_loss = prior_term\n"
              "            da_depth_loss = mvs_term\n"
              "            current_lod_weight = judgment.lambda_prior\n"
              "            current_da_weight = judgment.lambda_mvs\n"
              "            just_switched = False\n"
              "            stage2_active = True\n"
              "        else:\n")
    s = s[:start] + branch + indented + s[end:]
    rep("        gaussians.optimizer.zero_grad(set_to_none=True)\n        total_loss.backward()\n        mvs_pgsr_control.after_backward(iteration, gaussians)\n        gaussians.optimizer.step()\n",
        "        gaussians.optimizer.zero_grad(set_to_none=True)\n"
        "        total_loss.backward()\n        mvs_pgsr_control.after_backward(iteration, gaussians)\n"
        f"        if judgment is not None:  {MARK} remember locked rows before the Adam step\n"
        "            judgment.before_step(gaussians)\n"
        "        gaussians.optimizer.step()\n"
        f"        if judgment is not None:  {MARK} locked disks keep lock_lr_scale of the step; opacity floor\n"
        "            judgment.after_step(gaussians)\n")
    rep("            training_report(\n                tb_writer,\n                iteration,\n                Ll1,\n",
        f"            if judgment is not None:  {MARK} monitoring, read-outs, snapshots, dumps\n"
        "                if iteration % args.jbgs_log_interval == 0 or iteration == 1:\n"
        "                    judgment.log_scalars(iteration, dict(rgb=rgb_loss.item(), mvs=da_depth_loss.item(), prior=lod_depth_loss.item(),\n"
        "                                                        normal=normal_loss.item(), dist=dist_loss.item(), total=total_loss.item(),\n"
        "                                                        lambda_mvs=current_da_weight, lambda_prior=current_lod_weight), gaussians)\n"
        "                _snap = iteration in args.jbgs_snapshot_iterations\n"
        "                _dump = iteration in args.jbgs_dump_iterations\n"
        "                if iteration % args.jbgs_readout_interval == 0 or _snap or _dump or iteration == opt.iterations:\n"
        "                    judgment.readout(iteration, gaussians, render, pipe, background, snapshot=_snap, dump=_dump)\n\n"
        "            training_report(\n                tb_writer,\n                iteration,\n                Ll1,\n")
    rep("                    gaussians.reset_opacity()\n",
        f"                    gaussians.reset_opacity(exempt_mask=judgment.exempt_mask(gaussians) if judgment is not None else None)  {MARK}\n")
    rep("    jbgs_state.register_args(parser)\n    args = parser.parse_args(sys.argv[1:])\n",
        "    jbgs_state.register_args(parser)\n"
        f"    jbgs_judgment.register_args(parser)  {MARK}\n"
        "    args = parser.parse_args(sys.argv[1:])\n")
    tp.write_text(s)
    report["files"]["train.py"] = "8 edits + stage block wrapped"
else:
    report["files"]["train.py"] = "already patched"

(root / "jbgs_judgment_patch_report.json").write_text(json.dumps(report, indent=1))
print(json.dumps(report, indent=1))
