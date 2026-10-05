// Resolves declared surface variants only; artifact availability never selects a resolution.
export function resolutionModes(manifest) {
  if (manifest.resolution_modes === undefined) return [];
  const modes = manifest.resolution_modes;
  if (!Array.isArray(modes) || !modes.length || new Set(modes.map(mode => mode.id)).size !== modes.length) throw Error('Invalid resolution modes');
  for (const mode of modes) {
    if (!mode || typeof mode.id !== 'string' || !mode.id || !Number.isInteger(mode.mesh_res) || mode.mesh_res <= 0 ||
        !/^anchor(?:_\d+)?$/.test(mode.anchor_variant || '') || !/^(?:final|mesh_\d+)$/.test(mode.final_variant || '')) throw Error('Invalid resolution mode: ' + mode?.id);
    const variants = {1024: ['anchor', 'final'], 512: ['anchor_512', 'mesh_512']}[mode.mesh_res];
    if (!variants || mode.id !== String(mode.mesh_res) || mode.anchor_variant !== variants[0] || mode.final_variant !== variants[1]) throw Error('Resolution and surface variants disagree: ' + mode.id);
  }
  if (manifest.default_resolution !== undefined && !modes.some(mode => mode.id === manifest.default_resolution)) throw Error('Unknown default resolution');
  return modes;
}

export function resolvePanels(spec, condition, surface, prior, resolution) {
  if (!['raw', 'post'].includes(surface)) throw Error('Unknown surface representation: ' + surface);
  const ids = {...spec.panel_candidates, vanilla: condition?.parent_candidate_id || spec.panel_candidates.vanilla, changed: condition?.candidate_id || null};
  for (const key of ['anchor', 'vanilla', 'changed']) {
    if (!ids[key]) continue;
    if (resolution) {
      const match = /^(.*)\.(?:anchor(?:_\d+)?|final|mesh_\d+)\.(?:raw|post)$/.exec(ids[key]);
      if (!match) throw Error('Cannot resolve declared surface variant: ' + ids[key]);
      ids[key] = `${match[1]}.${key === 'anchor' ? resolution.anchor_variant : resolution.final_variant}.${surface}`;
    } else if (/\.(raw|post)$/.test(ids[key])) ids[key] = ids[key].replace(/\.(raw|post)$/, '.' + surface);
  }
  if (prior === 'points') ids.prior = 'als_points';
  else if (spec.candidates.some(candidate => candidate.id === 'prior_mesh')) ids.prior = 'prior_mesh';
  return ids;
}
