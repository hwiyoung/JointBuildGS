import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import laspy
import numpy as np
from PIL import Image

from scripts.phd.geogs_mvs_pgsr_v1.viewer.baselines import (
    colorize_photos, colmap_depth_points, recover_uas_rgb,
)
from tests.phd.geogs_mvs_pgsr_v1.test_mvs_depth import write_depth


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def camera_fixture(root):
    region = root/'inputs/P1'
    (region/'scene/images').mkdir(parents=True)
    (region/'prior/raw_depth').mkdir(parents=True)
    image = region/'scene/images/a.JPG'
    rgb = np.zeros((5, 7, 3), np.uint8)
    yy, xx = np.indices((5, 7))
    rgb[:, :, 0] = xx*20; rgb[:, :, 1] = yy*30; rgb[:, :, 2] = 150
    Image.fromarray(rgb).save(image, format='PNG')
    depth = region/'prior/raw_depth/a.npy'
    np.save(depth, np.full((5, 7), 2., np.float32))
    view = dict(name='a.JPG', sha256=sha(image), width=7, height=5,
                camera_model='PINHOLE', K=[[2., 0., 3.], [0., 2., 2.], [0., 0., 1.]],
                R=np.eye(3).tolist(), t=[0., 0., 0.])
    split = region/'scene/split_manifest_da3_v2.json'
    split.write_text(json.dumps(dict(train=[view])))
    (region/'input_manifest.json').write_text(json.dumps(dict(files=[
        dict(path='scene/split_manifest_da3_v2.json', sha256=sha(split)),
        dict(path='prior/raw_depth/a.npy', sha256=sha(depth)),
    ])))
    return region, view, rgb


class BaselineRGBTests(unittest.TestCase):
    def test_native_uas_recovers_paired_unsorted_rows_and_high_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); raw = root/'raw.las'
            header = laspy.LasHeader(point_format=3, version='1.2')
            header.scales = [0.0001]*3; header.offsets = [690973., 5336107., 0.]
            las = laspy.LasData(header)
            las.x = 690973. + np.arange(6)*.1
            las.y = 5336107. + np.arange(6)*.2
            las.z = 560. + np.arange(6)*.3
            raw_rgb = np.array([[0, 256, 65280], [257, 512, 768], [1024, 1280, 1536],
                                [1792, 2048, 2304], [2560, 2816, 3072], [3328, 3584, 3840]], np.uint16)
            las.red, las.green, las.blue = raw_rgb.T
            las.write(raw)
            rows = np.array([5, 1, 4, 0], np.int64)
            shift = np.array([690953., 5336071., 604.])
            expected = np.column_stack((las.x, las.y, las.z))[rows] - shift
            reference = root/'reference.npz'
            np.savez(reference, uas_xyz=expected, uas_raw_rows=rows)
            xyz, rgb, meta = recover_uas_rgb(reference, raw, shift.tolist(), 4)
            np.testing.assert_array_equal(xyz, expected.astype(np.float32))
            np.testing.assert_array_equal(rgb, (raw_rgb[rows]//256).astype(np.uint8))
            self.assertEqual(meta['selected_uas_raw_rows'], rows.tolist())
            self.assertEqual(meta['rgb16_low_byte_nonzero_channels'], 1)
            self.assertEqual(meta['coordinate_max_abs_error_m'], 0.)
            self.assertFalse(meta['full_raw_sha256_recomputed'])
            # Reference geometry is checked against the same source rows.
            expected[0, 0] += .01
            np.savez(reference, uas_xyz=expected, uas_raw_rows=rows)
            with self.assertRaisesRegex(ValueError, 'coordinates differ'):
                recover_uas_rgb(reference, raw, shift.tolist(), 4)

    def test_photo_rgb_calibration_bilinear_sampling_occlusion_and_holes(self):
        with tempfile.TemporaryDirectory() as tmp:
            region, _, _ = camera_fixture(Path(tmp))
            # Projection gives (u,v)=(3.5,2.5); the second point is behind the prior.
            points = np.array([[.5, .5, 2.], [0., 0., 3.], [20., 0., 2.], [-2., -1., 2.]])
            depth = region/'prior/raw_depth/a.npy'
            prior = np.load(depth); prior[1, 1] = 0; np.save(depth, prior)
            manifest = json.loads((region/'input_manifest.json').read_text())
            manifest['files'][1]['sha256'] = sha(depth)
            (region/'input_manifest.json').write_text(json.dumps(manifest))
            rgb, meta = colorize_photos(points, region)
            np.testing.assert_array_equal(rgb[0], [70, 75, 150])
            np.testing.assert_array_equal(rgb[1:], np.full((3, 3), 160))
            self.assertEqual(meta['color']['coverage'], .25)
            self.assertEqual(meta['assignment_view_indices'], [0, -1, -1, -1])
            self.assertEqual(meta['camera_membership'], 'train only')

    def test_photo_fails_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            region, _, _ = camera_fixture(Path(tmp))
            (region/'scene/images/a.JPG').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'source changed'):
                colorize_photos(np.array([[0., 0., 2.]]), region)

    def test_colmap_backprojection_odd_raster_and_camera_pose_preserve_holes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); region, view, image_rgb = camera_fixture(root)
            (root/'contracts').mkdir()
            (root/'contracts/execution_v1.json').write_text(json.dumps(dict(regions=dict(
                P1=dict(domain=dict(x=[-10.,10.], y=[-10.,10.], z=[0.,10.]))))))
            depth_path = root/'a.bin'
            depth = np.full((5, 7), 2., np.float32); depth[0, 0] = 0.; depth[1, 1] = np.nan
            metadata = write_depth(depth_path, depth); metadata['K'] = view['K']
            view['t'] = [-1., 0., 0.]
            view.update(local_depth='a.bin', maps=dict(depth=metadata))
            bindings = root/'bindings.json'
            bindings.write_text(json.dumps(dict(region='P1', train=[view])))
            xyz, rgb, meta = colmap_depth_points(bindings, root, region, 100)
            self.assertEqual(len(xyz), 33)
            for point, color, (view_id, u, v) in zip(xyz, rgb, meta['selected_view_u_v']):
                self.assertEqual(view_id, 0)
                np.testing.assert_array_equal(point, [u-2., v-2., 2.])
                np.testing.assert_array_equal(color, image_rgb[v, u])
            self.assertNotIn([0, 0, 0], meta['selected_view_u_v'])
            self.assertNotIn([0, 1, 1], meta['selected_view_u_v'])


if __name__ == '__main__':
    unittest.main()
