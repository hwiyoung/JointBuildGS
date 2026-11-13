"""Concept video, another case (2026-11-13, user '그 이야기로 만들어' = B0_b10 x LoD2, the wall hidden by the courtyard tree, 'LoD2 fills the wall the photos
do not see'). Run with TL_CASE=B0_b10__LoD2 (launch.py mounts the case roots); writes /cfg/trainlog_v1.json + trainlog_v1.lock.json and /docs/camera_choice.json.
Config = the B173 trainlog_v1.json (configs/phd/main_trainlog_v1, read only) with only the case fields replaced:
  target       FINALTRAIN B0_b10 ft_LoD2_s0 (its command + --jbgs_trainlog on, as the B173 run), its stage1 target dir and targets
  scope        the PROCFIG-v1 freeze.py rule on this building: GTJUDGE addendum10 c2_outline.geojson (LoD2 GroundSurface XY, DEBY_LOD2_4959323), 1 m buffer,
               ground = survey DTM 0.5 m cell at the c2 case-box XY centre, z_min = ground + 0.3, z_max = top of the LoD2 prior inside the buffer + 2,
               zoom_box_xy = the c2 panel-1 box (placeholder; the video zones are set later)
  coordinates  unchanged (same CRS, shift and gravity up)
  renders.view_camera.azimuth_deg = direction from the scope centre to the chosen photo camera (rounded), elevation 35 (the B173 value)
camera_choice.json: train1 = DJI_20241217101357_0031_D = the photo with the most counted rows of the wall among cameras within 70 m
(figures_concept_v2/step6_find/B0_b10__LoD2_look.json best_view_A); train2 = the next such camera (0030). Training rules, judgment, targets, mesh and score
rules are unchanged. scientific_verdict: null"""
from common import *
from shapely.geometry import shape, mapping, Point
from shapely import vectorized
assert TL_CASE == 'B0_b10__LoD2', TL_CASE

def main():
    assert not (C/'trainlog_v1.json').exists(), 'case config already written'
    base = json.loads(Path('/repo/configs/phd/main_trainlog_v1/trainlog_v1.json').read_text()); c = json.loads(json.dumps(base))
    ad = Path('/repo/docs/experiments/phd/main_gtjudge_v1/tables/addendum10'); outline = ad/'c2_outline.geojson'; boxfile = ad/'c2_boxes.json'
    feature = json.loads(outline.read_text())['features'][0]; poly = shape(feature['geometry']); buf = poly.buffer(1)
    box = json.loads(boxfile.read_text())['panel1_box_corners_local_xy']; centre = np.mean(box, axis=0); assert poly.covers(Point(centre)), 'case-box centre outside the outline'
    survey = PH/'main_design_realchange_survey_v1/PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1/derived.npz'; dtm = loadz(survey, ['dtm'])['dtm']
    ix = int(np.floor((centre[0]+SHIFT[0]-690700)/.5)); iy = int(np.floor((centre[1]+SHIFT[1]-5335820)/.5)); ground = float(dtm[iy, ix]-SHIFT[2]); assert np.isfinite(ground)
    prior = S1/'defs'/SITE/f'prior_{PRIOR}.npz'; v = loadz(prior, ['V'])['V']; inside = vectorized.contains(buf, v[:, 0], v[:, 1]); top = float(v[inside, 2].max())
    c['scope'] = dict(building_id=feature['properties']['building_id'], footprint=feature['geometry'], buffered_footprint=mapping(buf), xy_buffer_m=1, z_min=ground+.3, z_max=top+2,
                      ground_z=ground, old_roof_max_z=top, ground_rule='PROCFIG-v1 freeze.py rule: survey DTM 0.5 m cell at the case-box XY centre; no LoD2 Z',
                      ground_cell_iy_ix=[iy, ix], ground_query_xy=centre.tolist(), zoom_box_xy=box)
    c['scope_source'] = f'{outline} (+ {boxfile}); rule of scripts/phd/main_procfig_v1/freeze.py'
    orig = FT/'runs'/SITE/f'ft_{PRIOR}_s0/attempt1'
    c['target'] = dict(site=SITE, prior=PRIOR, case=CASE, seed=0, iterations=30000, run=RUN, original_run=str(orig), original_command=str(orig/'command.json'),
                       change_vs_original='same argv as original command.json plus --jbgs_trainlog on (launch.train_args), as the B173 run; output under the case root',
                       target_dir=str(FT/'stage1'/STEM), targets=str(FT/'targets'/f'{STEM}.npz'), gpu=1, docker_image=base['target'].get('docker_image'), renderer=base['target'].get('renderer'))
    views = {x['name']: x for x in json.loads((GT/'views'/f'{SITE}.json').read_text())['views']}
    look = json.loads((Path('/repo/docs/experiments/phd/main_trainlog_v1/figures_concept_v2/step6_find')/f'{STEM}_look.json').read_text())
    cams = ['DJI_20241217101357_0031_D', 'DJI_20241217101355_0030_D']; assert look['best_view_A']['name'] == cams[0]
    E = np.asarray(views[cams[0]]['W2C'], float); Cc = -E[:3, :3].T@E[:3, 3]; ctr = np.asarray(buf.centroid.coords[0]); az = float(np.degrees(np.arctan2(Cc[1]-ctr[1], Cc[0]-ctr[0])) % 360)
    c['renders'] = dict(base['renders']); c['renders']['view_camera'] = dict(base['renders']['view_camera'], azimuth_deg=round(az))
    c['case'] = dict(stem=STEM, created_at=now(), reason="user 2026-11-13 '그 이야기로 만들어': B0 x LoD2, the courtyard wall hidden by a tree (image depth absent, LoD2 right)",
                     base_config=dict(path='/repo/configs/phd/main_trainlog_v1/trainlog_v1.json', sha256=sha('/repo/configs/phd/main_trainlog_v1/trainlog_v1.json')),
                     changed_fields=['target', 'scope', 'scope_source', 'renders.view_camera.azimuth_deg', 'case', 'payload_root', 'write_roots'], view_azimuth_rule='scope centre -> train1 camera, rounded',
                     runtime_lock='not sealed for the case (train_entry TRAINLOG_REQUIRE_RUNTIME off); the fork r27 files are bound by input_binding.json at training start')
    c['payload_root'] = f'PH/main_trainlog_v1/PHD-MAIN-TRAINLOG-v1/concept_v2/case_{STEM}'
    c['write_roots'] = ['scripts/phd/main_trainlog_v1', f'docs/experiments/phd/main_trainlog_v1/figures_concept_v2/case_{STEM}', c['payload_root']]
    c['created_at'] = now(); c['scientific_verdict'] = None
    dump(C/'trainlog_v1.json', c); dump(C/'trainlog_v1.lock.json', dict(at=now(), config_sha256=sha(C/'trainlog_v1.json'), phase='before the case training', scientific_verdict=None))
    dump(D/'camera_choice.json', dict(at=now(), rule=__doc__.split('camera_choice.json: ')[1].split(' Training rules')[0], chosen=[dict(name=n) for n in cams], source=str(Path('/repo/docs/experiments/phd/main_trainlog_v1/figures_concept_v2/step6_find')/f'{STEM}_look.json'), scientific_verdict=None))
    print('CASE_CONFIG', STEM, feature['properties']['building_id'], round(ground, 2), round(top, 2), round(az, 1), sha(C/'trainlog_v1.json'), flush=True)

if __name__ == '__main__': main()
