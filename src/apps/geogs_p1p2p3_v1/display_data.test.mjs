import assert from 'node:assert/strict';
import {pointMetadata, colorProvenance, sourceColor, validateMeshMetadata, meshArrays} from './display_data.mjs';

const metadata = {schema: 'geogs_exact_clipped_display_mesh_v1', display_only: true,
  representation: 'EXACT_EVALUATION_CLIPPED_TRIANGLES', topology_simplified: false, artificial_clip_caps: false,
  distance_mode_requires_points: true, vertex_count: 3, triangle_count: 1,
  vertices_f64: {url: 'P1/vertices.bin', bytes: 72, sha256: 'a'.repeat(64)},
  triangles_u32: {url: 'P1/triangles.bin', bytes: 12, sha256: 'b'.repeat(64)},
  source_mesh: {path: 'source/fuse.ply', sha256: 'c'.repeat(64), scope: 'synthetic_test_only'}};
const vertices = new ArrayBuffer(72), triangles = new ArrayBuffer(12);
[0.1234567890123, 0, 0, 1, 0, 0, 0, 1, 0].forEach((x, i) => new DataView(vertices).setFloat64(i * 8, x, true));
[0, 1, 2].forEach((x, i) => new DataView(triangles).setUint32(i * 4, x, true));
const mesh = meshArrays(metadata, vertices, triangles);
assert.deepEqual([...mesh.index], [0, 1, 2]);
assert.equal(mesh.position[0], Math.fround(0.1234567890123));
assert.throws(() => meshArrays(metadata, vertices.slice(0, 64), triangles), /byte length/);
new DataView(triangles).setUint32(8, 3, true);
assert.throws(() => meshArrays(metadata, vertices, triangles), /absent vertex/);
assert.throws(() => validateMeshMetadata({...metadata, topology_simplified: true}), /simplification/);
assert.throws(() => validateMeshMetadata({...metadata, artificial_clip_caps: true}), /caps/);
assert.throws(() => validateMeshMetadata({...metadata, source_mesh: {}}), /provenance/);
assert.deepEqual(pointMetadata({display_only: true}, 3), {display_sample_count: 3, full_evaluation_sample_count: null,
  original_points_in_roi: null, counts_provenance: 'LOADED_ARRAY_LENGTH_LEGACY_METADATA'});
assert.throws(() => pointMetadata({display_only: true, display_sample_count: 4}, 3), /differs/);
assert.throws(() => pointMetadata({display_only: true, sampling_metadata: {never_used_in_scoring: false}}, 3), /scoring/);
assert.equal(colorProvenance({rgb: [255, 0, 0]}).kind, 'UNKNOWN');
assert.equal(colorProvenance({color_provenance: {kind: 'FIXED_SOURCE_COLOR'}}).label, '소스 구분용 고정색');
assert.deepEqual(sourceColor({color: {rgb_u8: [10, 20, 30]}}, [1, 2, 3]), [10, 20, 30]);
assert.deepEqual(sourceColor({}, [1, 2, 3]), [1, 2, 3]);
console.log('PASS: synthetic exact mesh decoding, byte/count/topology constraints, legacy metadata and explicit color provenance');
