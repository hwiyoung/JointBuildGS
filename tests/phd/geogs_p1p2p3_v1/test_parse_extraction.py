import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_p1p2p3_v1/parse_extraction.py'
spec = importlib.util.spec_from_file_location('geogs_extraction_parser', MODULE)
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


def native_log(resolution=1024, depth=97.8818534916439, clusters=50):
    voxel = depth / resolution
    return ('The estimated bounding radius is 16.11\n'
            'reconstruct radiance fields: 0%\rreconstruct radiance fields: 100%\n'
            f'The estimated bounding radius is {depth / 2:.2f}\n'
            'Running tsdf volume integration ...\n'
            f'voxel_size: {voxel}\nsdf_trunc: {5 * voxel}\ndepth_truc: {depth}\n'
            f'post processing the mesh to have {clusters} clusterscluster_to_kep\n')


class ExtractionParserTests(unittest.TestCase):
    def test_real_default_float_values_and_all_registered_resolutions(self):
        for resolution in (512, 1024, 2048):
            with self.subTest(resolution=resolution):
                result = parser.parse_extraction_text(native_log(resolution), resolution)
                self.assertEqual(result['depth_trunc_m'], 97.8818534916439)
                self.assertEqual(result['voxel_size_m'], result['depth_trunc_m'] / resolution)
                self.assertEqual(result['sdf_trunc_m'], 5 * result['voxel_size_m'])
                self.assertEqual(result['camera_radius_last_printed_m'], 48.94)
                self.assertEqual(result['tsdf_block_count'], 1)

    def test_missing_parameter_or_tsdf_block_is_rejected(self):
        for removed in ('Running tsdf volume integration ...\n', 'depth_truc: 97.8818534916439\n',
                        'post processing the mesh to have 50 clusterscluster_to_kep\n'):
            with self.subTest(removed=removed):
                with self.assertRaises(ValueError):
                    parser.parse_extraction_text(native_log().replace(removed, ''), 1024)

    def test_duplicate_block_or_parameter_cannot_select_a_favorable_last_value(self):
        for added in ('Running tsdf volume integration ...\n', 'depth_truc: 97.8818534916439\n',
                      'post processing the mesh to have 50 clusterscluster_to_kep\n'):
            with self.subTest(added=added):
                with self.assertRaises(ValueError):
                    parser.parse_extraction_text(native_log() + added, 1024)

    def test_nonfinite_zero_negative_or_invalid_numeric_values_are_rejected(self):
        for token in ('nan', 'inf', '-inf', '0', '-1', 'not-a-float'):
            with self.subTest(token=token):
                changed = native_log().replace('depth_truc: 97.8818534916439', 'depth_truc: ' + token)
                with self.assertRaises(ValueError):
                    parser.parse_extraction_text(changed, 1024)

    def test_resolution_or_default_sdf_relation_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            parser.parse_extraction_text(native_log(512), 1024)
        changed = native_log().replace('sdf_trunc: 0.47793873775216744', 'sdf_trunc: 0.5')
        with self.assertRaises(ValueError):
            parser.parse_extraction_text(changed, 1024)

    def test_cluster_change_or_last_camera_radius_disagreement_is_rejected(self):
        with self.assertRaises(ValueError):
            parser.parse_extraction_text(native_log(clusters=49), 1024)
        with self.assertRaises(ValueError):
            parser.parse_extraction_text(native_log().replace('radius is 48.94', 'radius is 48.93'), 1024)

    def test_metadata_before_the_integration_block_is_not_runtime_evidence(self):
        changed = native_log().replace('depth_truc: 97.8818534916439\n', '')
        with self.assertRaises(ValueError):
            parser.parse_extraction_text('depth_truc: 97.8818534916439\n' + changed, 1024)

    def test_raw_log_and_exact_helper_bytes_are_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'render.log'
            contents = native_log().encode('utf-8')
            path.write_bytes(contents)
            result = parser.parse_extraction_log(path, 1024)
            self.assertEqual(result['source_log_sha256'], hashlib.sha256(contents).hexdigest())
            self.assertEqual(result['parser_sha256'], hashlib.sha256(MODULE.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
