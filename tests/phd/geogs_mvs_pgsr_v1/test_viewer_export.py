"""Display geometry tests: native color transfer, cropping, sampling, and IDs."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
from plyfile import PlyData, PlyElement


MODULE = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_mvs_pgsr_v1/viewer/export_geometry.py'
SPEC = importlib.util.spec_from_file_location('viewer_export_geometry', MODULE)
export = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export)


def read_array(root, record):
    path = root / record['url']
    assert path.stat().st_size == record['bytes']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
    return np.fromfile(path, dtype=record['dtype']).reshape(record['shape'])


def write_mesh(path, xyz, rgb, faces):
    dtype = [('x', 'f8'), ('y', 'f8'), ('z', 'f8')]
    if rgb is not None:
        dtype += [('red', 'u1'), ('green', 'u1'), ('blue', 'u1')]
    vertices = np.zeros(len(xyz), dtype=dtype)
    for index, name in enumerate(('x', 'y', 'z')):
        vertices[name] = np.asarray(xyz)[:, index]
    if rgb is not None:
        for index, name in enumerate(('red', 'green', 'blue')):
            vertices[name] = np.asarray(rgb)[:, index]
    triangles = np.zeros(len(faces), dtype=[('vertex_indices', 'i4', (3,))])
    triangles['vertex_indices'] = faces
    PlyData([PlyElement.describe(vertices, 'vertex'), PlyElement.describe(triangles, 'face')],
            text=False, byte_order='<').write(path)


class ViewerExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_triangle_boundary_interpolates_rgb_and_does_not_add_caps(self):
        path = self.root / 'triangle.ply'
        write_mesh(path, [[-1, 0, 0], [1, 0, 0], [1, 2, 0]],
                   [[0, 0, 0], [200, 0, 0], [200, 200, 0]], [[0, 1, 2]])
        source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        dest = self.root / 'out'
        result = export.export_native_mesh(path, dest, {'min': [0, -1, -1], 'max': [2, 3, 1]},
                                           expected_sha=source_sha, point_cap=2000)
        xyz, rgb, faces = [read_array(dest, result['mesh'][key]) for key in ('xyz', 'rgb', 'indices')]
        self.assertEqual(len(faces), 2)
        self.assertEqual(xyz.dtype, np.dtype('<f4'))
        self.assertTrue(np.all(xyz[:, 0] >= 0))
        boundary = {tuple(point): tuple(color) for point, color in zip(xyz, rgb) if point[0] == 0}
        self.assertEqual(boundary, {(0., 0., 0.): (100, 0, 0), (0., 1., 0.): (100, 100, 0)})
        tri = xyz[faces]
        area = .5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum()
        self.assertAlmostEqual(float(area), 1.5)
        self.assertFalse(result['sampling']['added_clip_cap_faces'])
        samples = read_array(dest, result['points']['xyz'])
        colors = read_array(dest, result['points']['rgb'])
        np.testing.assert_allclose(colors[:, 0], (samples[:, 0] + 1) * 100, atol=.501)
        np.testing.assert_allclose(colors[:, 1], samples[:, 1] * 100, atol=.501)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source_sha)

    def test_area_uniform_seeded_sampling_and_full_mesh_preserved(self):
        path = self.root / 'two.ply'
        write_mesh(path, [[0, 0, 0], [1, 0, 0], [0, 1, 0], [10, 0, 0], [12, 0, 0], [10, 2, 0]],
                   [[200, 0, 0]] * 3 + [[0, 100, 200]] * 3, [[0, 1, 2], [3, 4, 5]])
        outputs = []
        for label in ('first', 'second'):
            dest = self.root / label
            result = export.export_native_mesh(path, dest, None, point_cap=10000)
            outputs.append((result, read_array(dest, result['points']['xyz']), read_array(dest, result['points']['rgb'])))
        np.testing.assert_array_equal(outputs[0][1], outputs[1][1])
        np.testing.assert_array_equal(outputs[0][2], outputs[1][2])
        small = outputs[0][1][:, 0] < 5
        self.assertTrue(.18 < small.mean() < .22)
        np.testing.assert_array_equal(outputs[0][2][small], np.tile([200, 0, 0], (int(small.sum()), 1)))
        self.assertEqual(outputs[0][0]['mesh']['triangle_count'], 2)
        self.assertEqual(outputs[0][0]['mesh']['vertex_count'], 6)

    def test_point_crop_cap_and_raw_id_correspondence(self):
        xyz = np.column_stack((np.arange(10), np.zeros(10), np.zeros(10)))
        rgb = np.column_stack((np.arange(10) * 20, np.arange(10), np.zeros(10)))
        dest = self.root / 'points'
        result = export.export_points(xyz, rgb, dest, bounds={'min': [2, -1, -1], 'max': [8, 1, 1]},
                                      point_cap=3, source_indices=np.arange(10) + 100)
        ids = read_array(dest, result['points']['source_indices'])
        np.testing.assert_array_equal(ids, [102, 104, 107])
        np.testing.assert_array_equal(read_array(dest, result['points']['xyz']), xyz[ids - 100])
        np.testing.assert_array_equal(read_array(dest, result['points']['rgb']), rgb[ids - 100])
        self.assertEqual(result['sampling']['cropped_count'], 6)

    def test_gaussian_sh_dc_formula_and_no_opacity_filter(self):
        path = self.root / 'gs.ply'
        fields = [(key, 'f4') for key in ('x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2', 'opacity')]
        data = np.zeros(4, dtype=fields)
        data['x'] = [0, 1, 2, 3]
        data['f_dc_0'] = [-4, -1, 0, 1]
        data['f_dc_1'] = [4, 1, 0, -1]
        data['opacity'] = [-1000, 0, 1000, 1]
        PlyData([PlyElement.describe(data, 'vertex')], text=False).write(path)
        dest = self.root / 'gs'
        result = export.export_gaussians(path, dest, {'min': [0, -1, -1], 'max': [3, 1, 1]}, point_cap=3)
        ids = read_array(dest, result['points']['source_indices'])
        np.testing.assert_array_equal(ids, [0, 1, 2])
        expected = np.rint(np.clip(.5 + export.SH_C0 * np.column_stack(
            [data[key][:3] for key in ('f_dc_0', 'f_dc_1', 'f_dc_2')]).astype(np.float64), 0, 1) * 255).astype('u1')
        np.testing.assert_array_equal(read_array(dest, result['points']['rgb']), expected)
        self.assertEqual(result['geometry_kind'], 'GAUSSIAN_CENTERS')
        self.assertFalse(result['sampling']['opacity_filter'])
        self.assertIsNone(result['mesh'])

    def test_missing_rgb_requires_declared_colorizer_after_clipping(self):
        path = self.root / 'prior.ply'
        write_mesh(path, [[-1, 0, 0], [1, 0, 0], [1, 2, 0]], None, [[0, 1, 2]])
        box = {'min': [0, -1, -1], 'max': [2, 3, 1]}
        with self.assertRaisesRegex(ValueError, 'colorizer is required'):
            export.export_native_mesh(path, self.root / 'missing', box)
        self.assertFalse((self.root / 'missing').exists())
        calls = []
        def colorizer(xyz):
            calls.append(xyz.copy())
            return np.column_stack([xyz[:, 0] * 100, xyz[:, 1] * 100, np.zeros(len(xyz))]), {
                'kind': 'CALIBRATED_PHOTO_PROJECTION', 'label': 'Current-photo projected color, not prior sensor RGB'}
        result = export.export_native_mesh(path, self.root / 'colored', box, point_cap=30, colorizer=colorizer)
        self.assertEqual(len(calls), 1)
        self.assertTrue(np.all(calls[0][:, 0] >= 0))
        self.assertEqual(result['color']['kind'], 'CALIBRATED_PHOTO_PROJECTION')
        self.assertFalse(result['color']['native_vertex_rgb'])

    def test_native_rgb_is_never_overridden_by_colorizer(self):
        path = self.root / 'native.ply'
        write_mesh(path, [[0, 0, 0], [1, 0, 0], [1, 2, 0]], [[0, 0, 0], [200, 0, 0], [0, 100, 0]], [[0, 1, 2]])
        def forbidden(_):
            self.fail('Native RGB must not be replaced')
        result = export.export_native_mesh(path, self.root / 'native', None, point_cap=30, colorizer=forbidden)
        self.assertEqual(result['color']['kind'], 'NATIVE_VERTEX_RGB')

    def test_source_identity_and_output_replacement_fail_closed(self):
        path = self.root / 'native.ply'
        write_mesh(path, [[0, 0, 0], [1, 0, 0], [1, 2, 0]], [[0, 0, 0], [200, 0, 0], [0, 100, 0]], [[0, 1, 2]])
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            export.export_native_mesh(path, self.root / 'bad', None, expected_sha='0' * 64, point_cap=10)
        self.assertFalse((self.root / 'bad').exists())
        dest = self.root / 'existing'
        dest.mkdir()
        with self.assertRaises(FileExistsError):
            export.export_points(np.zeros((1, 3)), np.zeros((1, 3)), dest)

    def test_invalid_colors_and_constant_native_rgb_rejected(self):
        for rgb in (np.array([[np.nan, 0, 0]]), np.array([[256, 0, 0]])):
            with self.assertRaises(ValueError):
                export.export_points(np.zeros((1, 3)), rgb, self.root / 'invalid')
        path = self.root / 'flat_color.ply'
        write_mesh(path, [[0, 0, 0], [1, 0, 0], [1, 2, 0]], [[100, 100, 100]] * 3, [[0, 1, 2]])
        with self.assertRaisesRegex(ValueError, 'constant'):
            export.export_native_mesh(path, self.root / 'flat', None, point_cap=10)


if __name__ == '__main__':
    unittest.main()
