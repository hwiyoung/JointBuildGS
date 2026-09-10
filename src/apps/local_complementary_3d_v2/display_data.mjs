// Display contracts only. These helpers neither sample surfaces nor compute scores.
const requireValue = (value, message) => { if (!value) throw Error(message); };
const count = value => Number.isSafeInteger(value) && value >= 0;
const rgb = value => Array.isArray(value) && value.length === 3 && value.every(x => Number.isFinite(x) && x >= 0 && x <= 255);

export function pointMetadata(input, actualCount) {
  requireValue(input.display_only === true, 'DISPLAY_ONLY point contract missing');
  if (input.display_sample_count !== undefined) requireValue(count(input.display_sample_count) && input.display_sample_count === actualCount, 'Declared display sample count differs from loaded points');
  for (const key of ['full_evaluation_sample_count', 'original_points_in_roi']) {
    if (input[key] !== undefined && input[key] !== null) requireValue(count(input[key]), 'Invalid point metadata count: ' + key);
  }
  if (input.sampling_metadata?.never_used_in_scoring !== undefined) requireValue(input.sampling_metadata.never_used_in_scoring === true, 'Display samples may not be used in scoring');
  return {display_sample_count: actualCount,
    full_evaluation_sample_count: input.full_evaluation_sample_count ?? null,
    original_points_in_roi: input.original_points_in_roi ?? null,
    counts_provenance: input.display_sample_count === undefined ? 'LOADED_ARRAY_LENGTH_LEGACY_METADATA' : 'LOADED_ARRAY_LENGTH_AND_EXPORTED_METADATA'};
}

export function colorProvenance(input) {
  const provenance = input?.color_provenance;
  const labels = {FIXED_SOURCE_COLOR: '소스 구분용 고정색', NEAREST_ORIGINAL_MESH_VERTEX_COLOR: '원 메시 최근접 정점에서 옮긴 색상', ORIGINAL_POINT_RGB: '원 점자료 RGB'};
  const kind = provenance?.kind || 'UNKNOWN';
  return {kind, label: labels[kind] || '색상 출처 미기재 / 확인 불가', description: provenance?.description || null, metadata: provenance || null};
}

export function sourceColor(input, fallback) {
  const value = Array.isArray(input?.color) ? input.color : input?.color?.rgb_u8 || input?.color?.rgb;
  return rgb(value) ? value : fallback;
}

export function validateMeshMetadata(input) {
  requireValue(input?.schema === 'geogs_exact_clipped_display_mesh_v1' && input.display_only === true &&
    input.representation === 'EXACT_EVALUATION_CLIPPED_TRIANGLES', 'Exact clipped display mesh contract missing');
  requireValue(input.topology_simplified === false && input.artificial_clip_caps === false &&
    input.distance_mode_requires_points === true, 'Mesh display must preserve clipped triangles without simplification or caps');
  requireValue(count(input.vertex_count) && input.vertex_count > 0 && count(input.triangle_count) && input.triangle_count > 0, 'Invalid mesh vertex/triangle counts');
  for (const [key, bytes] of [['vertices_f64', input.vertex_count * 24], ['triangles_u32', input.triangle_count * 12]]) {
    const item = input[key];
    requireValue(item && typeof item.url === 'string' && item.url && /^[0-9a-f]{64}$/i.test(item.sha256 || '') && item.bytes === bytes, 'Invalid exact mesh binary metadata: ' + key);
  }
  requireValue(input.source_mesh && typeof input.source_mesh.path === 'string' && /^[0-9a-f]{64}$/i.test(input.source_mesh.sha256 || '') && input.source_mesh.scope, 'Original mesh provenance missing');
  return input;
}

export function meshArrays(input, verticesBuffer, trianglesBuffer) {
  validateMeshMetadata(input);
  requireValue(verticesBuffer.byteLength === input.vertices_f64.bytes && trianglesBuffer.byteLength === input.triangles_u32.bytes, 'Mesh binary byte length differs from metadata');
  const position = new Float32Array(input.vertex_count * 3), index = new Uint32Array(input.triangle_count * 3);
  const vertices = new DataView(verticesBuffer), triangles = new DataView(trianglesBuffer);
  for (let i = 0; i < position.length; i++) {
    const value = vertices.getFloat64(i * 8, true);
    requireValue(Number.isFinite(value), 'Nonfinite exact mesh vertex');
    position[i] = value;
    requireValue(Number.isFinite(position[i]), 'Mesh vertex exceeds GPU float32 range');
  }
  for (let i = 0; i < index.length; i++) {
    index[i] = triangles.getUint32(i * 4, true);
    requireValue(index[i] < input.vertex_count, 'Mesh triangle references an absent vertex');
  }
  return {position, index};
}
