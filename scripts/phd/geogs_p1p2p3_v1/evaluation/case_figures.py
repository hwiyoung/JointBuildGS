"""Actual fixed-case sections and photo/render crops after sealed evaluation.

Only evaluated NPZ arrays supply reference samples; raw UAS is never accessed.
Every consumed array, photograph, render and contract is hash-bound in the receipt.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, __version__ as pillow_version

from render_quality import projected_prism_bbox, read_rgb, sha
from runtime_layout import RuntimeLayout
from supplemental_repeat import SupplementalRepeat
import resource_support as resources

PRIMARY = 'sample0.1_reference0.1'


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def catalogue(records):
    result = {record['path']: record for record in records}
    if len(result) != len(records):
        raise ValueError('Duplicate sealed file paths')
    return result


def checked_file(task, relative, records, used):
    relative_path = Path(relative)
    if relative_path.is_absolute() or '..' in relative_path.parts:
        raise ValueError('Task-relative input path required')
    if relative not in records:
        raise ValueError(f'Input is not sealed: {relative}')
    path = task/relative
    if not path.is_file() or sha(path) != records[relative]['sha256']:
        raise ValueError(f'Sealed input bytes changed: {relative}')
    used[relative] = dict(path=relative, sha256=records[relative]['sha256'], bytes=path.stat().st_size)
    return path


def load_gate(task, runtime_layout=None, repeat_contract=None, resource_contract=None):
    """Validate completed table/candidate seals before reading evaluated arrays."""
    task = Path(task)
    paths = {key: task/relative for key, relative in (
        ('config', 'contracts/execution_v1.json'), ('analysis', 'contracts/evaluation_analysis_v1.json'),
        ('candidate', 'contracts/candidates_sealed_v1.json'), ('summary', 'evaluation/summary/receipt.json'))}
    data = {key: json.loads(path.read_text()) for key, path in paths.items()}
    layout = RuntimeLayout(task, runtime_layout, data['config']['regions'])
    layout.require_scientific_config(paths['config'])
    layout.require_receipt(data['candidate'])
    layout.require_receipt(data['summary'])
    repeat = SupplementalRepeat(task, repeat_contract, layout)
    repeat.require_candidates(data['candidate'])
    repeat.require_receipt(data['summary'])
    resource = resources.make_resource(task, resource_contract, layout, repeat)
    resources.require(resource, data['candidate'])
    resources.require(resource, data['summary'])
    if (data['candidate']['status'] != resources.seal_status(resource) or
            data['summary']['status'] != 'TABLES_AND_ACTUAL_VIEWER_DATA_READY' or
            any(value.get('scientific_verdict') is not None for value in data.values())):
        raise ValueError('Completed technical candidate/evaluation seals are required')
    if (data['candidate']['config_sha256'] != sha(paths['config']) or
            data['summary']['config_sha256'] != sha(paths['config']) or
            data['summary']['candidate_seal_sha256'] != sha(paths['candidate']) or
            data['summary']['analysis_config_sha256'] != sha(paths['analysis'])):
        raise ValueError('Candidate/summary/configuration identity differs')
    used = {str(path.relative_to(task)): dict(path=str(path.relative_to(task)), sha256=sha(path), bytes=path.stat().st_size)
            for path in paths.values()}
    if layout.path:
        used[str(layout.path.relative_to(task))] = dict(path=str(layout.path.relative_to(task)), sha256=layout.digest,
                                                       bytes=layout.path.stat().st_size)
    if repeat.path:
        used[str(repeat.path.relative_to(task))] = dict(path=str(repeat.path.relative_to(task)), sha256=repeat.digest,
                                                       bytes=repeat.path.stat().st_size)
    if resource:
        used[str(resource.path.relative_to(task))] = dict(path=str(resource.path.relative_to(task)), sha256=resource.digest,
                                                         bytes=resource.path.stat().st_size)
    summary_files = catalogue(data['summary']['summary_files'])
    for relative in summary_files:
        checked_file(task, relative, summary_files, used)
    cases_path = checked_file(task, 'evaluation/summary/selected_cases.json', summary_files, used)
    cases = json.loads(cases_path.read_text())
    layout.require_receipt(cases)
    repeat.require_receipt(cases)
    resources.require(resource, cases)
    if cases['analysis_config_sha256'] != sha(paths['analysis']) or cases.get('scientific_verdict') is not None:
        raise ValueError('Selected cases differ from the frozen analysis policy')
    return dict(config=data['config'], candidates=data['candidate'], cases=cases['cases'], used=used, layout=layout, repeat=repeat, resource=resource,
                candidate_files=catalogue(data['candidate']['files']),
                evaluation_files=catalogue(data['summary']['case_figure_input_files']),
                summary_files=summary_files, candidate_seal_sha256=sha(paths['candidate']),
                summary_receipt_sha256=sha(paths['summary']))


def case_prism(case, region_bounds, extent_m=5.):
    if not np.isfinite(extent_m) or extent_m <= 0:
        raise ValueError('Positive fixed case extent required')
    result = {}
    for axis in 'xy':
        center = float(case['center_'+axis+'_m'])
        result[axis] = [max(region_bounds[axis][0], center-extent_m/2),
                        min(region_bounds[axis][1], center+extent_m/2)]
        if not np.isfinite(center) or result[axis][0] >= result[axis][1]:
            raise ValueError('Selected case lies outside the fixed regional prism')
    result['z'] = list(region_bounds['z'])
    return result


def inside(points, bounds):
    points = np.asarray(points)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError('Finite evaluated XYZ samples required')
    return np.all((points >= [bounds[a][0] for a in 'xyz']) & (points < [bounds[a][1] for a in 'xyz']), axis=1)


def choose_photo(evaluation_views, bounds):
    """Maximum image-clipped projected bbox area; ties by source image name."""
    candidates = []
    for index, view in enumerate(sorted(evaluation_views, key=lambda row: row['name'])):
        bbox = projected_prism_bbox(bounds, view['R'], view['t'], view['K'], view['width'], view['height'])
        area = (bbox[2]-bbox[0])*(bbox[3]-bbox[1]) if bbox is not None else 0
        candidates.append(dict(name=view['name'], evaluation_index=index, bbox=bbox, bbox_area_pixels=area))
    candidates.sort(key=lambda row: (-row['bbox_area_pixels'], row['name']))
    return (candidates[0] if candidates and candidates[0]['bbox_area_pixels'] else None), candidates


def load_geometry(task, region, condition, gate, comparison_family=None):
    definitions = [
        ('prior_mesh', 'ALS prior — surface samples'), ('mvs_points', 'Image MVS — point samples'),
        ('D005_Pnative.anchor.raw', 'Exact anchor 8000 — surface samples'),
        ('D005_Pnative.final.raw', 'Native final — surface samples'),
        (condition+'.final.raw', 'Changed final — surface samples')]
    if gate.get('resource'):
        if comparison_family == 'anchor_refinement_512':
            definitions = [('prior_mesh', 'ALS prior — surface samples'), ('mvs_points', 'Image MVS — point samples'),
                ('D005_Pnative.anchor_512.raw', 'Shared exact anchor 8000 — TSDF512'),
                ('D005_Pnative.mesh_512.raw', 'Native final — TSDF512'),
                (condition+'.mesh_512.raw', 'Changed final — TSDF512')]
        else:
            definitions = [('prior_mesh', 'ALS prior — surface samples'), ('mvs_points', 'Image MVS — point samples'),
                ('D005_Pnative.final.raw', 'Native final — primary TSDF1024'),
                (condition+'.final.raw', 'Changed final — primary TSDF1024')]
    result, reference, members = [], None, None
    for name, label in definitions:
        prefix = f'evaluation/geometry/{region}/{name}/{PRIMARY}'
        path = checked_file(task, prefix+'.npz', gate['evaluation_files'], gate['used'])
        metric_path = checked_file(task, prefix+'.json', gate['evaluation_files'], gate['used'])
        metric = json.loads(metric_path.read_text())
        gate['layout'].require_receipt(metric)
        gate['repeat'].require_receipt(metric)
        resources.require(gate.get('resource'), metric)
        if metric['candidate_seal_sha256'] != gate['candidate_seal_sha256']:
            raise ValueError('Evaluated candidate belongs to a different reconstruction seal')
        with np.load(path, allow_pickle=False) as arrays:
            points = arrays['prediction_surface_samples']
            current_reference, current_members = arrays['reference_points'], arrays['reference_original_indices']
        if reference is None:
            reference, members = current_reference, current_members
        elif not np.array_equal(reference, current_reference) or not np.array_equal(members, current_members):
            raise ValueError('Case columns do not share exact evaluated reference samples')
        result.append(dict(id=name, label=label, points=points, surface_kind=metric['surface_kind'],
                           evaluation_status=metric['status'], npz_path=prefix+'.npz', metrics_path=prefix+'.json'))
    return result, reference, members


def section_figure(path, geometries, reference, case, bounds, width_m=.5):
    """Two rows (X/Y slices), five columns, fixed common axes and point sizes."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    reference = np.asarray(reference)[inside(reference, bounds)]
    figure, axes = plt.subplots(2, len(geometries), figsize=(20, 9), squeeze=False,
                                sharex='row', sharey=True, constrained_layout=True)
    records = []
    try:
        for row, axis in enumerate('xy'):
            across = 'yx'[row]
            center = case['center_'+axis+'_m']
            dimension, horizontal = 'xyz'.index(axis), 'xyz'.index(across)
            reference_selected = reference[np.abs(reference[:, dimension]-center) < width_m/2]
            for column, geometry in enumerate(geometries):
                points = geometry['points'][inside(geometry['points'], bounds)]
                selected = points[np.abs(points[:, dimension]-center) < width_m/2]
                plot = axes[row, column]
                plot.scatter(reference_selected[:, horizontal], reference_selected[:, 2], s=3,
                             c='#222222', label='Observed UAS samples', rasterized=True)
                plot.scatter(selected[:, horizontal], selected[:, 2], s=3, c='#d97732',
                             label=geometry['label'], rasterized=True)
                plot.set(xlim=bounds[across], ylim=bounds['z'], xlabel=across.upper()+' (m)', ylabel='Z (m)')
                plot.set_title(geometry['label']+f'\n{axis.upper()}={center:g}m, width={width_m:g}m', fontsize=9)
                plot.set_aspect('equal', adjustable='box')
                plot.grid(alpha=.2)
                if not len(reference_selected):
                    plot.text(.03, .97, 'No observed UAS samples in this section', transform=plot.transAxes,
                              va='top', fontsize=7, wrap=True)
                if not len(selected):
                    message = ('Reconstruction absent' if geometry['evaluation_status']=='RECONSTRUCTION_FAILURE' else
                               'No candidate/source samples in this section')
                    plot.text(.03, .88, message, transform=plot.transAxes, va='top', fontsize=7, wrap=True)
                records.append(dict(candidate=geometry['id'], section_axis=axis, section_center_m=center,
                                    width_m=width_m, horizontal_axis=across, horizontal_bounds=bounds[across],
                                    z_bounds=bounds['z'], reference_samples=len(reference_selected),
                                    prediction_samples=len(selected), surface_kind=geometry['surface_kind'],
                                    evaluation_status=geometry['evaluation_status']))
        axes[0, 0].legend(loc='lower left', fontsize=6, markerscale=2)
        figure.suptitle(f"{case['region']} / {case['condition']} / {case['selection_reason']}\n"
                       f"Selection-cell UAS samples: {case['reference_points']}; wider case-window UAS samples: {len(reference)}. "
                       "Reference gaps remain unassessed; point and surface samples are distinct.\nSample bands, not mesh-plane intersection lines.", fontsize=11)
        figure.savefig(path, dpi=160)
    finally:
        plt.close(figure)
    return records


def write_photo_triptych(photo, native, changed, bbox, directory):
    arrays = (photo, native, changed)
    if any(array.dtype != np.uint8 or array.shape != photo.shape or array.ndim != 3 or array.shape[2] != 3 for array in arrays):
        raise ValueError('Equal original-size uint8 RGB photographs/renders required')
    x0, y0, x1, y1 = bbox
    if not (0 <= x0 < x1 <= photo.shape[1] and 0 <= y0 < y1 <= photo.shape[0]):
        raise ValueError('Invalid fixed photo crop')
    crops = [array[y0:y1, x0:x1] for array in arrays]
    height, width = crops[0].shape[:2]
    panel_width = max(width, 240)
    figure = Image.new('RGB', (3*panel_width, height+38), '#202020')
    draw = ImageDraw.Draw(figure)
    for index, (crop, name, label) in enumerate(zip(crops, ('photo', 'native', 'changed'),
                                                  ('Actual evaluation photograph', 'Native saved RGB render', 'Changed saved RGB render'))):
        target = directory/(name+'_crop.png')
        if target.exists():
            raise FileExistsError(target)
        Image.fromarray(crop).save(target)
        figure.paste(Image.fromarray(crop), (index*panel_width, 38))
        draw.text((index*panel_width+5, 10), label, fill='white')
    target = directory/'photo_render_crop.png'
    if target.exists():
        raise FileExistsError(target)
    figure.save(target)
    return dict(bbox=bbox, crop_shape=list(crops[0].shape), pixel_resize=False,
                exposure_fit=False, prediction_mask=False, black_prediction_pixels_retained=True,
                display_padding_only=panel_width-width, montage=target.name,
                crops=[name+'_crop.png' for name in ('photo', 'native', 'changed')])


def photo_figure(task, region, condition, bounds, gate, directory):
    split_relative = f'inputs/{region}/scene/split_manifest_da3_v2.json'
    split_path = checked_file(task, split_relative, gate['candidate_files'], gate['used'])
    split = json.loads(split_path.read_text())
    selected, options = choose_photo(split['evaluation'], bounds)
    common = dict(selection='largest image-clipped projection bbox area of fixed case prism; ties by name',
                  selection_uses_output_or_reference=False, camera_candidates=options,
                  projection_is_visibility_or_texture_proof=False)
    if selected is None:
        return dict(common, status='NOT_ASSESSED_NO_EVALUATION_CAMERA_PROJECTION')
    view = next(row for row in split['evaluation'] if row['name']==selected['name'])
    photo_relative = f"inputs/{region}/scene/images/{view['name']}"
    photo_path = checked_file(task, photo_relative, gate['candidate_files'], gate['used'])
    if sha(photo_path) != view['sha256']:
        raise ValueError('Selected photo differs from frozen split')
    photo = read_rgb(photo_path)
    if photo.shape != (view['height'], view['width'], 3):
        raise ValueError('Selected photo size differs from frozen camera')
    rendered, record_list = [], []
    for arm in ('D005_Pnative', condition):
        candidates = [row for row in gate['candidates']['candidates'] if row['region']==region and
                      row['condition']==arm and row['variant']=='final' and row['mesh_kind']=='raw']
        if len(candidates) != 1:
            raise ValueError('Exactly one sealed final raw candidate is required per case arm')
        records = [row for row in candidates[0]['render_records'] if row['name']==view['name']]
        if len(records) != 1:
            raise ValueError('Selected evaluation pose has no unique sealed render')
        record = records[0]
        if any(record[key] != value for key, value in (('image_id', view['image_id']), ('camera_id', view['camera_id']),
                                                       ('evaluation_index', selected['evaluation_index']))):
            raise ValueError('Selected photo and render camera identity differ')
        path = checked_file(task, record['render_path'], gate['candidate_files'], gate['used'])
        if sha(path) != record['render_sha256']:
            raise ValueError('Render mapping and candidate file seal differ')
        rendered.append(read_rgb(path))
        record_list.append(dict(condition=arm, **record))
    crop = write_photo_triptych(photo, *rendered, selected['bbox'], directory)
    return dict(common, status='ACTUAL_PHOTO_AND_MATCHED_RENDER_CROPS', selected_camera=selected,
                image_id=view['image_id'], camera_id=view['camera_id'], photo_path=photo_relative,
                R=view['R'], t=view['t'], K=view['K'], render_records=record_list, crop=crop)


def update_viewer_v2(task, gate, case_records):
    original = checked_file(task, 'evaluation/viewer/manifest.json', gate['summary_files'], gate['used'])
    manifest = copy.deepcopy(json.loads(original.read_text()))
    manifest['schema'] = 'geogs_p1p2p3_viewer_cases_v2'
    manifest['previous_manifest_sha256'] = sha(original)
    manifest['case_figure_index_url'] = '../cases_v1/index.json'
    for record in case_records:
        region = next(row for row in manifest['regions'] if row['id']==record['region'])
        prefix = '../'+str(Path(record['path']).relative_to('evaluation'))+'/'
        common = dict(condition_id=record['condition'], case_id=record.get('recorded_case_id', record['id']),
                      selection_reason=record['selection_reason'])
        region.setdefault('sections', []).append(dict(common, id=record['id']+'.sections',
            label=record['label']+' — primary final1024 case sections' if gate.get('resource') else record['label']+' — matched case sections', url=prefix+'sections.png',
            comparison_family='primary_1024' if gate.get('resource') else 'legacy_primary',
            caption='Prior/MVS/native/changed with common observed UAS; final GS surfaces use1024; fixed0.5m sections and identical axes' if gate.get('resource') else 'Five source/condition columns; common observed UAS; fixed 0.5m sections and identical axes'))
        if record.get('paired_section_url'):
            region['sections'].append(dict(common, id=record['id']+'.anchor_refinement_512',
                label=record['label']+' — matched anchor/refinement512', url=prefix+'sections_anchor_refinement512.png',
                comparison_family='anchor_refinement_512',
                caption='Shared exact anchor512 / native final512 / changed final512 with prior/MVS and the same observed UAS; case selected from primary1024 analysis, not re-ranked at512'))
        if record['photo_status']=='ACTUAL_PHOTO_AND_MATCHED_RENDER_CROPS':
            region.setdefault('renders', []).append(dict(common, id=record['id']+'.photo',
                label=record['label']+' — actual photo/native/changed', url=prefix+'photo_render_crop.png',
                domain='case_projected_bbox', stage='case', image_name=record['photo_name'], split='evaluation',
                comparison_family='primary_1024' if gate.get('resource') else 'legacy_primary',
                caption='Same actual photo/camera and fixed case-prism pixel bbox; original pixels, no fit or output mask'))
    destination = task/'evaluation/viewer/manifest_v2.json'
    dump(destination, manifest)
    return str(destination.relative_to(task))


def run(task, output, viewer_manifest_v2=False, runtime_layout=None, repeat_contract=None, resource_contract=None):
    task, output = Path(task), Path(output)
    gate = load_gate(task, runtime_layout, repeat_contract, resource_contract)
    if output.exists() or (viewer_manifest_v2 and (task/'evaluation/viewer/manifest_v2.json').exists()):
        raise FileExistsError('Case figures and viewer v2 require new output paths')
    if output != task/'evaluation/cases_v1':
        raise ValueError('Use the isolated task evaluation/cases_v1 output owner')
    output.mkdir(parents=True)
    figure_config = dict(section_width_m=.5, case_xy_extent_m=5., z_domain='full fixed regional prism',
                         projection_near_m=1e-4, evaluated_points_resampled=False,
                         photo_selection='maximum clipped projected bbox area, then lexicographic source image name',
                         photo_resize=False, exposure_fit=False, output_dependent_masks=False,
                         reference_source='sealed evaluated arrays only; no raw UAS input')
    if gate.get('resource'):
        figure_config.update(primary_comparison_mesh_res=1024, anchor_refinement_mesh_res=512,
            case_selection='unchanged predefined main final1024 case selection; no reranking from512',
            cross_resolution_interpretation='Separate extraction estimands; differences across1024/512 are not attributed solely to training control')
    dump(output/'configuration.json', figure_config)
    records = []
    for index, case in enumerate(gate['cases']):
        region, condition = case['region'], case['condition']
        bounds = case_prism(case, gate['config']['regions'][region]['domain'], figure_config['case_xy_extent_m'])
        directory = output/region/f'case_{index:05d}'
        directory.mkdir(parents=True)
        geometries, reference, members = load_geometry(task, region, condition, gate)
        sections = section_figure(directory/'sections.png', geometries, reference, case, bounds, figure_config['section_width_m'])
        paired_sections, paired_geometries = None, []
        if gate.get('resource'):
            paired_geometries, paired_reference, paired_members = load_geometry(task, region, condition, gate, 'anchor_refinement_512')
            if not np.array_equal(reference, paired_reference) or not np.array_equal(members, paired_members):
                raise ValueError('Primary1024 and paired512 figures do not share the frozen evaluated reference')
            paired_sections = section_figure(directory/'sections_anchor_refinement512.png', paired_geometries,
                paired_reference, case, bounds, figure_config['section_width_m'])
        photo = photo_figure(task, region, condition, bounds, gate, directory)
        metadata = dict(scientific_verdict=None, case=case, case_bounds=bounds,
                        **gate['layout'].binding(),
                        **gate['repeat'].binding(),
                        **resources.binding(gate.get('resource')),
                        fixed_extent_m=5., section_width_m=.5, case_window_reference_samples=int(inside(reference, bounds).sum()),
                        reference_sample_identity='identical frozen evaluated reference coordinates and original indices for all columns',
                        section_representation='Existing evaluated point/surface samples inside fixed-width bands; not triangle-plane intersection curves or vertex proxies.',
                        sections=sections, photo_comparison=photo,
                        anchor_refinement512_sections=paired_sections,
                        anchor_refinement512_column_sources=[{key: geometry[key] for key in ('id', 'npz_path', 'metrics_path', 'surface_kind', 'evaluation_status')} for geometry in paired_geometries],
                        case_selection_source='predefined primary final1024 diagnostics; no512 reranking' if gate.get('resource') else 'predefined primary diagnostics',
                        column_sources=[{key: geometry[key] for key in ('id', 'npz_path', 'metrics_path', 'surface_kind', 'evaluation_status')}
                                        for geometry in geometries],
                        reference_raw_accessed=False, figure_inputs='sealed evaluated arrays and original heldout RGB/render bytes',
                        files=[dict(path=path.name, sha256=sha(path), bytes=path.stat().st_size) for path in sorted(directory.glob('*.png'))])
        dump(directory/'metadata.json', metadata)
        records.append(dict(id=f'case_{index:05d}', region=region, condition=condition,
                            recorded_case_id=(f"{condition}.{case['cell_x']}.{case['cell_y']}.{case['selection_reason']}" if 'cell_x' in case and 'cell_y' in case else f'case_{index:05d}'),
                            label=region+' '+condition+' '+case['selection_reason'], selection_reason=case['selection_reason'],
                            path=str(directory.relative_to(task)), section_url=str((directory/'sections.png').relative_to(output)),
                            metadata_url=str((directory/'metadata.json').relative_to(output)),
                            metadata_sha256=sha(directory/'metadata.json'), section_sha256=sha(directory/'sections.png'),
                            paired_section_url=str((directory/'sections_anchor_refinement512.png').relative_to(output)) if paired_sections is not None else None,
                            paired_section_sha256=sha(directory/'sections_anchor_refinement512.png') if paired_sections is not None else None,
                            photo_status=photo['status'], photo_name=photo.get('selected_camera', {}).get('name'),
                            photo_url=str((directory/'photo_render_crop.png').relative_to(output)) if 'crop' in photo else None))
        print(json.dumps(dict(case=index, region=region, condition=condition, photo_status=photo['status'])), flush=True)
    viewer = update_viewer_v2(task, gate, records) if viewer_manifest_v2 else None
    index_data = dict(schema='jointbuildgs.geogs.actual_case_figures.v1', scientific_verdict=None,
                     **gate['layout'].binding(),
                     **gate['repeat'].binding(),
                     **resources.binding(gate.get('resource')),
                     status='ACTUAL_CASE_FIGURES_READY', cases=records, viewer_manifest_v2=viewer,
                     candidate_seal_sha256=gate['candidate_seal_sha256'], summary_receipt_sha256=gate['summary_receipt_sha256'],
                     inputs=list(gate['used'].values()), script_sha256=sha(__file__),
                     figure_config_sha256=sha(output/'configuration.json'),
                     dependency_sha256={name:sha(Path(__file__).with_name(name)) for name in ('render_quality.py', 'runtime_layout.py', 'supplemental_repeat.py')},
                     versions=dict(numpy=np.__version__, matplotlib=matplotlib.__version__, pillow=pillow_version),
                     raw_reference_accessed=False, original_manifest_overwritten=False)
    dump(output/'index.json', index_data)
    return index_data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--viewer-manifest-v2', action='store_true')
    parser.add_argument('--runtime-layout', type=Path)
    parser.add_argument('--repeat-contract', type=Path)
    parser.add_argument('--resource-contract', type=Path)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists() or Path('/reference').exists() or Path('/artifacts/JointBuildGS').exists():
        raise RuntimeError('Use Docker with the isolated task and no raw reference mount')
    output = args.task/'evaluation/cases_v1'
    already_exists = output.exists()
    try:
        run(args.task, output, args.viewer_manifest_v2, args.runtime_layout, args.repeat_contract, args.resource_contract)
    except Exception as error:
        if not already_exists and output.exists():
            dump(output/'failure_receipt.json', dict(scientific_verdict=None, status='FAILED_CASE_FIGURE_GENERATION',
                exception=repr(error), partial_outputs_preserved=True, raw_reference_accessed=False, script_sha256=sha(__file__)))
        raise


if __name__ == '__main__':
    main()
