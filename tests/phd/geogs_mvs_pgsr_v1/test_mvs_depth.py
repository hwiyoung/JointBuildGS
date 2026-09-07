import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from src.phd.geogs_mvs_pgsr_v1.mvs_depth import (
    build_neighbor_graph, load_split_manifest, load_view_depth,
    read_colmap_depth, resample_depth_to_camera, resolve_artifact_path,
)


def write_depth(path, array):
    h, w = array.shape
    header = f'{w}&{h}&1&'.encode()
    data = header + np.asarray(array, dtype='<f4').tobytes(order='C')
    path.write_bytes(data)
    return dict(width=w, height=h, channels=1, header_bytes=len(header),
                frame='CAMERA_Z', sha256=hashlib.sha256(data).hexdigest())


def view(name='a', center=0.):
    return dict(name=name, width=7, height=5, camera_model='PINHOLE',
                K=[[4., 0., 3.], [0., 4., 2.], [0., 0., 1.]],
                R=np.eye(3).tolist(), t=[-center, 0., 0.],
                maps={'depth': dict(width=7, height=5, K=[[4., 0., 3.], [0., 4., 2.], [0., 0., 1.]])})


class NativeMVSDepthTests(unittest.TestCase):
    def test_native_layout_odd_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'depth.bin'
            expected = np.arange(35, dtype=np.float32).reshape(5, 7)
            metadata = write_depth(p, expected)
            np.testing.assert_array_equal(read_colmap_depth(p, metadata), expected)

    def test_reject_hash_header_frame_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'depth.bin'; m = write_depth(p, np.ones((5, 7)))
            for field, value in [('sha256', '0'*64), ('width', 8), ('frame', 'RAY_DISTANCE')]:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    read_colmap_depth(p, dict(m, **{field: value}))
            p.write_bytes(p.read_bytes()[:-4]); m['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
            with self.assertRaises(ValueError): read_colmap_depth(p, m)

    def test_nearest_integer_rays_preserve_holes_odd_sizes(self):
        raw = np.arange(15, dtype=np.float32).reshape(3, 5)+10
        raw[1, 2] = 0; raw[0, 0] = -1; raw[2, 3] = np.nan
        native_K = np.array([[5., 0, 2.], [0, 3., 1.], [0, 0, 1.]])
        rgb_K = np.diag([7/5, 5/3, 1.]) @ native_K
        output, valid = resample_depth_to_camera(raw, native_K, rgb_K, 7, 5)
        for y in range(5):
            for x in range(7):
                # Independent analytic coordinate scaling, no matrix call.
                sx, sy = int(np.floor(x*5/7+.5)), int(np.floor(y*3/5+.5))
                ok = sx < 5 and sy < 3 and np.isfinite(raw[min(sy, 2), min(sx, 4)]) and raw[min(sy, 2), min(sx, 4)] > 0
                self.assertEqual(bool(valid[y, x]), ok)
                self.assertEqual(float(output[y, x]), float(raw[sy, sx]) if ok else 0.)
        self.assertEqual(output.dtype, np.float32)

    def test_camera_z_not_ray_length_and_off_axis_intrinsics(self):
        raw = np.full((5, 7), 8., dtype=np.float32)
        K = np.array([[4., 0, 2.25], [0, 5., 1.75], [0, 0, 1.]])
        out, valid = resample_depth_to_camera(raw, K, K, 7, 5)
        np.testing.assert_array_equal(out, raw); self.assertTrue(valid.all())
        ray = np.linalg.inv(K) @ [0., 0., 1.]
        self.assertGreater(np.linalg.norm(ray*float(out[0, 0])), 8.)
        self.assertEqual(float((ray*out[0, 0])[2]), 8.)

    def test_bound_rgb_and_map_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); p=root/'depth.bin'; metadata=write_depth(p, np.ones((5,7)))
            rgb=root/'image.jpg'; rgb.write_bytes(b'frozen image bytes')
            v=view(); v.update(path='/artifacts/JointBuildGS/image.jpg', sha256=hashlib.sha256(rgb.read_bytes()).hexdigest())
            v['maps']['depth'].update(metadata, path='/artifacts/JointBuildGS/depth.bin')
            out, valid, receipt=load_view_depth(v, root)
            self.assertTrue(valid.all()); self.assertEqual(receipt['output_valid_pixels'], 35)
            rgb.write_bytes(b'changed')
            with self.assertRaises(ValueError): load_view_depth(v, root)
            with self.assertRaises(ValueError): resolve_artifact_path('/artifacts/JointBuildGS/../outside', root)

    def test_manifest_hash_and_per_region_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'split.json'; a,b=view('a'),view('b')
            split=dict(all=[a,b],train=[a],evaluation=[b]); p.write_text(json.dumps(split))
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(load_split_manifest(p,digest),split)
            with self.assertRaises(ValueError): load_split_manifest(p,'0'*64)
            split['evaluation']=[a]; p.write_text(json.dumps(split))
            with self.assertRaises(ValueError): load_split_manifest(p,hashlib.sha256(p.read_bytes()).hexdigest())

    def test_neighbor_projection_is_analytic_train_only_and_scale_relative(self):
        # At z=10 and fx=4, a +5 m camera shift projects x two pixels left.
        a,b=view('a'),view('b',5.)
        depths={v['name']:np.full((5,7),10.,dtype=np.float32) for v in [a,b]}
        graph=build_neighbor_graph([b,a],depths,grid_side=7)
        candidate=graph['graph']['a']['candidates'][0]
        self.assertEqual(graph['graph']['a']['selected'],['b'])
        self.assertAlmostEqual(candidate['projected_overlap_fraction'],5/7)
        self.assertEqual(candidate['baseline_m'],5.)
        self.assertEqual(candidate['baseline_depth_ratio'],.5)
        scaled=view('b',50.); depths2={k:v*10 for k,v in depths.items()}
        graph2=build_neighbor_graph([a,scaled],depths2,grid_side=7)
        self.assertEqual(graph2['graph']['a']['selected'],['b'])
        self.assertEqual(graph2['graph']['a']['candidates'][0]['baseline_depth_ratio'],.5)
        with self.assertRaises(ValueError): build_neighbor_graph([a],depths)

    def test_graph_rejects_duplicate_centers_and_no_depth_support(self):
        a,b=view('a'),view('b')
        graph=build_neighbor_graph([a,b],{'a':np.zeros((5,7)), 'b':np.ones((5,7))})
        self.assertEqual(graph['graph']['a']['selected'],[])
        self.assertIn('no_reference_depth_support',graph['graph']['a']['candidates'][0]['exclusion_reasons'])
        self.assertIn('duplicate_center',graph['graph']['b']['candidates'][0]['exclusion_reasons'])


if __name__ == '__main__':
    unittest.main()
