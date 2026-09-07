"""Native CUDA model/Adam restart and protection semantics on a small fixture."""
import argparse
import json
import os
from pathlib import Path
import random
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np
import torch
from arguments import OptimizationParams
from scene.gaussian_model import GaussianModel
from utils.graphics_utils import BasicPointCloud
import jbgs_state
from train import attenuate_building_xyz_lr, attenuate_building_other_lr


def model(opt):
    g = GaussianModel(3)
    xyz = np.array([[0., 0., 2.], [0.2, 0., 2.], [0., 0.2, 2.]], dtype=np.float32)
    g.create_from_pcd(BasicPointCloud(xyz, np.full_like(xyz, .5), np.zeros_like(xyz)), 1.)
    g.training_setup(opt)
    return g


def update(g):
    draws = (random.random(), float(np.random.rand()), torch.rand(1), torch.rand(1, device='cuda'))
    g.optimizer.zero_grad(set_to_none=True)
    loss = sum((p.square() + p * torch.rand_like(p)).sum() for group in g.optimizer.param_groups for p in group['params'])
    loss.backward()
    g.optimizer.step()
    return draws


def tensors(value):
    if torch.is_tensor(value):
        return [value.detach().clone()]
    if isinstance(value, dict):
        return sum((tensors(v) for v in value.values()), [])
    if isinstance(value, (list, tuple)):
        return sum((tensors(v) for v in value), [])
    return []


class RestartTests(unittest.TestCase):
    def test_native_adam_rng_camera_stack_and_hooks_restart(self):
        self.assertTrue(torch.cuda.is_available())
        parser = argparse.ArgumentParser()
        group = OptimizationParams(parser)
        opt = group.extract(parser.parse_args([]))
        with tempfile.TemporaryDirectory(dir=os.environ.get('JBGS_TEST_TMP', '/tmp')) as temporary:
            directory = Path(temporary)
            args = SimpleNamespace(model_path=str(directory / 'resumed'), stage_switch_iter=8000,
                                   lambda_lod_anchor=.005, lod2_building_xyz_lr_scale=.01,
                                   protect_bldg_lr_scale=.01, protect_bldg=True,
                                   jbgs_release_protection=False, jbgs_input_manifest=None)
            Path(args.model_path).mkdir()
            cams = [SimpleNamespace(image_name=n) for n in ['c', 'a', 'b']]
            test = [SimpleNamespace(image_name='holdout')]
            scene = SimpleNamespace(getTrainCameras=lambda: cams, getTestCameras=lambda: test)
            g = model(opt)
            for _ in range(7):
                update(g)
            g.set_frozen_mask(torch.tensor([True, False, True], device='cuda'))
            attenuate_building_xyz_lr(g, g.frozen_mask, .01)
            attenuate_building_other_lr(g, g.frozen_mask, .01)
            runtime = {k: 0 for k in jbgs_state.RUNTIME_KEYS}
            runtime.update(da_depth_history=[.7, .5], da_monitor_depth=[.3], da_monitor_rgb=[.2],
                           da_weight=.045125, da_phase=2, da_consecutive=1, freeze_done=False,
                           dynamic_switch_triggered=False, dynamic_switch_iter=None,
                           dynamic_switch_forced=False, lod_loss_history=[], da_locked_weight=None,
                           da_last_check=7800)
            env = dict(runtime, args=args, gaussians=g, scene=scene, opt=opt,
                       building_freeze_mask=g.frozen_mask, viewpoint_stack=[cams[2], cams[0]], iteration=8000)
            state = jbgs_state.capture_state(env)
            path = directory / 'checkpoint.pth'
            torch.save(state, path)
            expected_draws = update(g)
            expected_tensors = tensors(g.capture())
            restored_model = model(opt)
            cams.reverse()
            restored = jbgs_state.restore_state(path, dict(env, gaussians=restored_model), globals())
            self.assertEqual([c.image_name for c in cams], ['c', 'a', 'b'])
            self.assertEqual([c.image_name for c in restored['viewpoint_stack']], ['b', 'c'])
            self.assertEqual(restored['da_depth_history'], [.7, .5])
            self.assertEqual(restored['da_weight'], .045125)
            actual_draws = update(restored_model)
            self.assertEqual(expected_draws[:2], actual_draws[:2])
            for a, b in zip(expected_draws[2:], actual_draws[2:]):
                self.assertTrue(torch.equal(a, b))
            actual_tensors = tensors(restored_model.capture())
            self.assertEqual(len(expected_tensors), len(actual_tensors))
            for a, b in zip(expected_tensors, actual_tensors):
                self.assertTrue(torch.equal(a, b))
            native_grad = torch.autograd.grad(restored_model._xyz.sum(), restored_model._xyz)[0]
            self.assertTrue(torch.allclose(native_grad[:, 0], torch.tensor([.01, 1., .01], device='cuda')))
            args.model_path = str(directory / 'released')
            Path(args.model_path).mkdir()
            args.jbgs_release_protection = True
            args.lod2_building_xyz_lr_scale = args.protect_bldg_lr_scale = 1.
            released_model = model(opt)
            released = jbgs_state.restore_state(path, dict(env, gaussians=released_model), globals())
            self.assertIsNone(released_model.frozen_mask)
            self.assertIsNone(released['building_freeze_mask'])
            self.assertFalse(released['freeze_done'])
            released_grad = torch.autograd.grad(released_model._xyz.sum(), released_model._xyz)[0]
            self.assertTrue(torch.equal(released_grad, torch.ones_like(released_grad)))


if __name__ == '__main__':
    unittest.main()
