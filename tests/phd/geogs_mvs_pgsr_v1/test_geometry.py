"""Analytic camera/plane checks for the declared PGSR loss adaptation."""

import math
import unittest

import torch

from src.phd.geogs_mvs_pgsr_v1.geometry import pgsr_geometry_losses


def rotation_y(angle):
    return torch.tensor([[math.cos(angle), 0., math.sin(angle)], [0., 1., 0.],
                         [-math.sin(angle), 0., math.cos(angle)]], dtype=torch.float64)


def render_plane(height, width, intrinsics, rotation, translation):
    """Intersect a fixed world plane and evaluate an analytic world texture."""
    yy, xx = torch.meshgrid(torch.arange(height, dtype=torch.float64),
                            torch.arange(width, dtype=torch.float64), indexing="ij")
    pixels = torch.stack((xx, yy, torch.ones_like(xx)), -1)
    rays_world = (pixels @ torch.linalg.inv(intrinsics).T) @ rotation
    origin = -translation @ rotation
    world_normal = torch.tensor([-.18, .12, -1.], dtype=torch.float64)
    plane_distance = torch.tensor(5., dtype=torch.float64)
    depth = -(world_normal @ origin + plane_distance) / (rays_world * world_normal).sum(-1)
    world_points = origin + depth[..., None] * rays_world
    x, y = world_points[..., 0], world_points[..., 1]
    gray = .5 + .15 * torch.sin(5*x) + .12 * torch.cos(4*y) + .08 * torch.sin(3*x + 2*y)
    rgb = torch.stack((gray, gray, gray))
    normals = torch.nn.functional.normalize(world_normal, dim=0)[:, None, None].expand(3, height, width).clone()
    return depth, normals, torch.ones_like(depth), rgb


def fixture(near_height=48, near_width=64):
    height, width = 48, 64
    K_ref = torch.tensor([[80., 0., 31.5], [0., 81., 23.5], [0., 0., 1.]], dtype=torch.float64)
    K_near = torch.tensor([[80., 0., (near_width-1)/2], [0., 81., (near_height-1)/2], [0., 0., 1.]], dtype=torch.float64)
    R_ref, R_near = rotation_y(.12), rotation_y(.09)
    t_ref = torch.tensor([.05, -.02, .1], dtype=torch.float64)
    t_near = torch.tensor([-.2, .01, .1], dtype=torch.float64)
    depth, normal, alpha, rgb = render_plane(height, width, K_ref, R_ref, t_ref)
    near_depth, _, near_alpha, near_rgb = render_plane(near_height, near_width, K_near, R_near, t_near)
    args = [depth, normal, alpha, rgb, K_ref, R_ref, t_ref]
    kwargs = dict(depth_near=near_depth, alpha_near=near_alpha, rgb_near=near_rgb,
                  K_near=K_near, R_near=R_near, t_near=t_near, max_samples=512,
                  microbatch_size=64, seed=23)
    return args, kwargs


class GeometryLossTests(unittest.TestCase):
    def test_tilted_textured_plane_and_nonidentity_cameras(self):
        args, kwargs = fixture()
        result = pgsr_geometry_losses(*args, **kwargs)
        self.assertLess(result["svgeo"].item(), 1e-10)
        self.assertLess(result["mvgeom"].item(), 1e-3)
        self.assertLess(result["mvrgb"].item(), 2e-3)
        self.assertGreater(result["counts"]["mv_valid"], 300)
        self.assertGreater(result["counts"]["ncc_valid"], 200)

    def test_wrong_depth_has_finite_nonzero_gradients_for_each_mv_term(self):
        args, kwargs = fixture()
        args[0] = (args[0] + .18).requires_grad_()
        args[1] = args[1].clone().requires_grad_()
        kwargs["depth_near"] = kwargs["depth_near"].clone().requires_grad_()
        result = pgsr_geometry_losses(*args, **kwargs)
        self.assertGreater(result["counts"]["ncc_valid"], 100)
        for name in ("mvgeom", "mvrgb"):
            grads = torch.autograd.grad(result[name], [args[0], args[1]], retain_graph=True, allow_unused=True)
            self.assertTrue(torch.isfinite(result[name]))
            self.assertGreater(result[name].item(), 1e-5)
            self.assertIsNotNone(grads[0])
            self.assertTrue(torch.isfinite(grads[0]).all())
            self.assertGreater(grads[0].abs().sum().item(), 1e-6)
            if name == "mvrgb":
                self.assertTrue(torch.isfinite(grads[1]).all())
                self.assertGreater(grads[1].abs().sum().item(), 1e-6)
        near_grad = torch.autograd.grad(result["mvgeom"], kwargs["depth_near"])[0]
        self.assertTrue(torch.isfinite(near_grad).all())
        self.assertGreater(near_grad.abs().sum().item(), 1e-6)

    def test_single_view_normal_error_has_geometry_gradient(self):
        args, _ = fixture()
        args[0] = args[0].clone().requires_grad_()
        args[1] = (args[1] + torch.tensor([.1, .03, 0.], dtype=torch.float64)[:, None, None]).requires_grad_()
        result = pgsr_geometry_losses(*args)
        grads = torch.autograd.grad(result["svgeo"], (args[0], args[1]))
        self.assertGreater(result["svgeo"].item(), .01)
        for grad in grads:
            self.assertTrue(torch.isfinite(grad).all())
            self.assertGreater(grad.abs().sum().item(), 1e-6)

    def test_sign_equivalent_plane_normals(self):
        args, kwargs = fixture()
        original = pgsr_geometry_losses(*args, **kwargs)
        args[1] = -args[1]
        flipped = pgsr_geometry_losses(*args, **kwargs)
        for key in ("svgeo", "mvgeom", "mvrgb"):
            torch.testing.assert_close(original[key], flipped[key])

    def test_capped_private_rng_and_microbatch_equivalence(self):
        args, kwargs = fixture()
        state_before = torch.random.get_rng_state().clone()
        first = pgsr_geometry_losses(*args, **kwargs)
        self.assertTrue(torch.equal(torch.random.get_rng_state(), state_before))
        kwargs["microbatch_size"] = 127
        second = pgsr_geometry_losses(*args, **kwargs)
        self.assertEqual(first["counts"]["mv_sampled"], kwargs["max_samples"])
        self.assertEqual(first["counts"], second["counts"])
        for key in ("svgeo", "mvgeom", "mvrgb"):
            torch.testing.assert_close(first[key], second[key], rtol=1e-10, atol=1e-12)

    def test_invalid_support_empty_masks_and_constant_texture(self):
        args, kwargs = fixture()
        args[0] = args[0].clone()
        args[0][4:9, 5:10] = float("nan")
        args[0] = args[0].requires_grad_()
        args[3] = torch.full_like(args[3], .5)
        kwargs["rgb_near"] = torch.full_like(kwargs["rgb_near"], .5)
        result = pgsr_geometry_losses(*args, **kwargs)
        self.assertEqual(result["counts"]["ncc_valid"], 0)
        for key in ("svgeo", "mvgeom", "mvrgb"):
            self.assertTrue(torch.isfinite(result[key]))
        sum(result[key] for key in ("svgeo", "mvgeom", "mvrgb")).backward()
        self.assertTrue(torch.isfinite(args[0].grad).all())
        args[2] = torch.zeros_like(args[2])
        empty = pgsr_geometry_losses(*args, **kwargs)
        self.assertEqual(empty["counts"]["reference_valid"], 0)
        for key in ("svgeo", "mvgeom", "mvrgb"):
            self.assertEqual(empty[key].item(), 0.)
            self.assertTrue(empty[key].requires_grad)

    def test_occluded_neighbor_and_grazing_normals_are_excluded(self):
        args, kwargs = fixture()
        kwargs["alpha_near"] = torch.zeros_like(kwargs["alpha_near"])
        occluded = pgsr_geometry_losses(*args, **kwargs)
        self.assertEqual(occluded["counts"]["mv_valid"], 0)
        self.assertEqual(occluded["counts"]["ncc_valid"], 0)
        kwargs["alpha_near"] = torch.ones_like(kwargs["alpha_near"])
        kwargs["grazing_cos_min"] = .9999
        grazing = pgsr_geometry_losses(*args, **kwargs)
        self.assertLess(grazing["counts"]["reference_valid"], occluded["counts"]["reference_valid"])

    def test_different_image_dimensions_and_float32(self):
        args, kwargs = fixture(52, 70)
        args = [item.float() for item in args]
        kwargs = {key: value.float() if isinstance(value, torch.Tensor) else value for key, value in kwargs.items()}
        result = pgsr_geometry_losses(*args, **kwargs)
        self.assertGreater(result["counts"]["ncc_valid"], 100)
        for key in ("svgeo", "mvgeom", "mvrgb"):
            self.assertTrue(torch.isfinite(result[key]))
        self.assertLess(result["mvgeom"].item(), 1e-3)


if __name__ == "__main__":
    unittest.main()
