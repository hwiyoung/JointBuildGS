"""Synthetic byte/identity checks; no reference, model parsing, image scoring or GPU."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO/'scripts/phd/geogs_p1p2p3_v1/evaluation'))
import run_evaluation as evaluation


class RegionalConsumedInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.task = Path(self.temp.name)
        self.cfg = dict(regions={region:dict(expected_test=2) for region in ('P1', 'P2')})
        self.seal = dict(files=[], candidates=[])
        self.seal_sha = 'a'*64
        self.surface = self.bind('runs/P1/D005_Pnative/model/mesh/ours_30000/fuse.ply', b'SYNTHETIC RAW')
        self.post = self.bind('runs/P1/D005_Pnative/model/mesh/ours_30000/fuse_post.ply', b'SYNTHETIC POST')
        self.prior = self.bind('inputs/P1/surface/als_surface.ply', b'SYNTHETIC ALS')
        self.other_region = self.bind('runs/P2/D005_Pnative/model/mesh/ours_30000/fuse.ply', b'OTHER REGION')
        self.checkpoint = self.bind('runs/P1/D005_Pnative/model/chkpnt30000.pth', b'NEVER PARSE A CHECKPOINT')
        views, renders = [], []
        for index in range(2):
            name = f'photo_{index}.png'
            photo = self.bind('inputs/P1/scene/images/'+name, ('PHOTO '+str(index)).encode())
            render = self.bind(f'runs/P1/D005_Pnative/model/test/ours_30000/renders/{index:05d}.png',
                               ('RENDER '+str(index)).encode())
            views.append(dict(name=name, image_id=100+index, camera_id=3, sha256=photo['sha256']))
            renders.append(dict(name=name, evaluation_index=index, image_id=100+index, camera_id=3,
                                render_path=render['path'], render_sha256=render['sha256']))
        self.split = dict(train=[], evaluation=views)
        self.split_path = 'inputs/P1/scene/split_manifest_da3_v2.json'
        self.bind(self.split_path, json.dumps(self.split).encode())
        self.seal['candidates'] = [
            dict(region='P1', condition='D005_Pnative', variant='final', kind='raw',
                 surface=copy.deepcopy(self.surface), render_records=renders),
            dict(region='P1', condition='D005_Pnative', variant='final', kind='post',
                 surface=copy.deepcopy(self.post), render_records=[]),
            dict(region='P2', condition='D005_Pnative', variant='final', kind='raw',
                 surface=copy.deepcopy(self.other_region), render_records=[])]

    def bind(self, relative, content):
        path = self.task/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        row = dict(path=relative, bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        self.seal['files'].append(row)
        return row

    def verify(self, stage='geometry', seal=None, region='P1'):
        return evaluation.verify_stage_inputs(self.task, self.cfg, self.seal if seal is None else seal,
                                              self.seal_sha, region, stage)

    def assert_proof(self, proof, stage, paths):
        self.assertEqual(proof['policy'], 'REGIONAL_CONSUMED_INPUTS_v1')
        self.assertEqual(proof['region'], 'P1')
        self.assertEqual(proof['stage'], stage)
        self.assertEqual(proof['candidate_seal_sha256'], self.seal_sha)
        self.assertEqual(proof['files_count'], len(paths))
        self.assertEqual({row['path'] for row in proof['files']}, paths)
        self.assertEqual(proof['verified_bytes'], sum(row['bytes'] for row in proof['files']))
        self.assertEqual(len(proof['manifest_sha256']), 64)
        for row in proof['files']:
            self.assertEqual(set(row), {'path', 'bytes', 'sha256'})
            self.assertEqual(row, next(item for item in self.seal['files'] if item['path']==row['path']))

    def test_geometry_proof_has_only_regional_surfaces_and_als(self):
        # Excluded catalogue members may be absent: a geometry stage must not open them.
        needed = {row['path'] for row in (self.surface, self.post, self.prior)}
        for row in self.seal['files']:
            if row['path'] not in needed:
                (self.task/row['path']).unlink()
        proof = self.verify()
        self.assert_proof(proof, 'geometry', needed)
        self.assertEqual(proof, self.verify())

    def test_geometry_same_size_tamper_missing_and_unbound_fail(self):
        path = self.task/self.surface['path']
        original = path.read_bytes()
        for failure in ('same_size_tamper', 'missing', 'unbound'):
            with self.subTest(failure=failure):
                seal = copy.deepcopy(self.seal)
                path.write_bytes(original)
                if failure == 'same_size_tamper':
                    path.write_bytes(b'X'*len(original))
                elif failure == 'missing':
                    path.unlink()
                else:
                    seal['files'] = [row for row in seal['files'] if row['path']!=self.surface['path']]
                with self.assertRaises((ValueError, OSError)):
                    self.verify(seal=seal)

    def test_geometry_surface_record_and_catalogue_cannot_disagree(self):
        for field, value in (('bytes', 999), ('sha256', '0'*64), ('path', '../outside.ply')):
            with self.subTest(field=field):
                seal = copy.deepcopy(self.seal)
                seal['candidates'][0]['surface'][field] = value
                with self.assertRaises(ValueError):
                    self.verify(seal=seal)

    def test_unknown_region_or_stage_fails_before_payload_access(self):
        for row in self.seal['files']:
            (self.task/row['path']).unlink()
        for region, stage in (('P4', 'geometry'), ('P1', 'training'), ('P1', '../geometry')):
            with self.subTest(region=region, stage=stage), self.assertRaises(ValueError):
                self.verify(stage=stage, region=region)

    def test_render_proof_binds_split_evaluation_photos_and_registered_pngs_only(self):
        needed = {self.split_path}
        needed.update('inputs/P1/scene/images/'+view['name'] for view in self.split['evaluation'])
        needed.update(row['render_path'] for row in self.seal['candidates'][0]['render_records'])
        for row in self.seal['files']:
            if row['path'] not in needed:
                (self.task/row['path']).unlink()
        self.assert_proof(self.verify('renders'), 'renders', needed)

    def test_render_mapping_missing_duplicate_identity_and_hash_fail(self):
        for failure in ('missing', 'duplicate', 'image_id', 'camera_id', 'evaluation_index', 'render_sha256'):
            with self.subTest(failure=failure):
                seal = copy.deepcopy(self.seal)
                records = seal['candidates'][0]['render_records']
                if failure == 'missing':
                    records.pop()
                elif failure == 'duplicate':
                    records.append(copy.deepcopy(records[0]))
                else:
                    records[0][failure] = '0'*64 if failure == 'render_sha256' else -1
                with self.assertRaises(ValueError):
                    self.verify('renders', seal=seal)

    def test_split_or_photo_tamper_and_unbound_photo_fail(self):
        photo_path = 'inputs/P1/scene/images/'+self.split['evaluation'][0]['name']
        originals = {name:(self.task/name).read_bytes() for name in (self.split_path, photo_path)}
        for failure in ('split_tamper', 'photo_tamper', 'unbound_photo', 'split_photo_sha_disagrees'):
            with self.subTest(failure=failure):
                for name, data in originals.items():
                    (self.task/name).write_bytes(data)
                seal = copy.deepcopy(self.seal)
                if failure == 'split_tamper':
                    (self.task/self.split_path).write_bytes(b'{}')
                elif failure == 'photo_tamper':
                    (self.task/photo_path).write_bytes(b'X'*len(originals[photo_path]))
                elif failure == 'unbound_photo':
                    seal['files'] = [row for row in seal['files'] if row['path']!=photo_path]
                else:
                    changed = copy.deepcopy(self.split)
                    changed['evaluation'][0]['sha256'] = '0'*64
                    content = json.dumps(changed).encode()
                    (self.task/self.split_path).write_bytes(content)
                    record = next(row for row in seal['files'] if row['path']==self.split_path)
                    record.update(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
                with self.assertRaises((ValueError, OSError)):
                    self.verify('renders', seal=seal)

    def test_operational_receipt_metadata_accepts_completion_and_proof_only(self):
        class NoScoring:
            metadata = dict(synthetic_fixture=True)
            def score(self, *args, **kwargs):
                raise AssertionError('The empty synthetic split must not invoke scoring')

        metadata = dict(completion_contract_sha256='b'*64,
                        evaluation_scope='PRIMARY18_SUPPLEMENTAL_INCOMPLETE',
                        input_verification=self.verify('renders'))
        output = self.task/'synthetic_empty_render_receipt'
        result = evaluation.evaluate_render_set(dict(train=[], evaluation=[]), [], [[0, 1]]*3,
            self.task/'absent_photos', NoScoring(), output, 'P1', 'D005_Pnative', 'final', 0,
            self.seal_sha, runtime_metadata=metadata)
        for key, value in metadata.items():
            self.assertEqual(result[key], value)
        self.assertIsNone(result['scientific_verdict'])
        with self.assertRaisesRegex(ValueError, 'Only operational runtime layout metadata'):
            evaluation.evaluate_render_set(dict(train=[], evaluation=[]), [], [[0, 1]]*3,
                self.task/'absent_photos', NoScoring(), self.task/'must_not_be_created',
                'P1', 'D005_Pnative', 'final', 0, self.seal_sha,
                runtime_metadata=dict(metadata, invented_quality_override=True))
        self.assertFalse((self.task/'must_not_be_created').exists())

    def test_load_seal_default_hashes_full_catalogue_explicit_mode_returns_regional_proof(self):
        from tests.phd.geogs_p1p2p3_v1 import test_evaluation_completion as fixtures
        fixture = fixtures.CompletionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        resource_path = fixture.task/'contracts/extraction_resource_v3.json'
        resource = evaluation.resources.make_resource(fixture.task, resource_path, fixture.layout, fixture.repeat)
        seal = fixture.manifest()
        seal.update(status=evaluation.resources.seal_status(resource),
                    config_sha256=evaluation.sha(fixture.task/'contracts/execution_v1.json'),
                    **fixture.layout.binding(), **resource.binding())
        needed = {row['path'] for row in (self.surface, self.post, self.prior)}
        for row in self.seal['files']:
            if row['path'] in needed:
                path = fixture.task/row['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((self.task/row['path']).read_bytes())
                seal['files'].append(copy.deepcopy(row))
        seal['candidates'] = copy.deepcopy(self.seal['candidates'][:2])
        fixture.save(fixture.task/'contracts/candidates_sealed_v1.json', seal)
        # Exact frozen failed-run identities exist only as catalogue metadata here.
        # Legacy verification must still try their bytes and reject their absence.
        with self.assertRaises((ValueError, OSError)):
            evaluation.load_seal(fixture.task, fixture.layout, fixture.repeat, resource)
        result = evaluation.load_seal(fixture.task, fixture.layout, fixture.repeat, resource,
                                      stage_inputs=('P1', 'geometry'))
        self.assertEqual(len(result), 4)
        self.assertEqual(result[1], seal)
        self.assertEqual(result[2], evaluation.sha(fixture.task/'contracts/candidates_sealed_v1.json'))
        self.assertEqual({row['path'] for row in result[3]['files']}, needed)
        self.assertEqual(result[3]['files_count'], 3)
        self.assertEqual(result[3]['candidate_seal_sha256'], result[2])
