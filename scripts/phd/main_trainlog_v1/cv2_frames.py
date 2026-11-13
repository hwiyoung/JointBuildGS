"""PHD-MAIN-TRAINLOG-v1 concept video v2, first cut r5 (request 2026-11-12; r2-r5 2026-11-13: sections show results only, + GT, unfiltered mesh, fewer symbols; r5: timeline facts). CPU, no training; draws saved states only (nothing interpolated).
One frame per time point (input, 0, 100, 300, 1,000, 2,000, 3,000, 5,000, 7,000, 10,000, 15,000, 30,000), 1920 x 1080, white.
  top      'B173 · 반복 N / 30,000' and the 12-point dot row (current dark, past grey)
  upper    ① 2x2 for the real training camera DJI_20241217091247_0146_D (cropped to the building-scope pixels): photo, render (renders/<n>/train1_rgb.png,
           the r27 renderer, full scene and SH as in training), depth target (FT stage-1 map of this camera) and render depth (the mesh-input render of this
           camera: gtj/renders/..tl_<n>/0077.npz, surf_depth, building box), both turned into the height of the 3-D point of each pixel above the scope
           ground_z and coloured with one fixed 7-step scale (this camera's building-scope target heights, 2-98 %); dotted = boundary between judgment classes
           inside zones 1-2; red thin outline = render point farther than TAU from the target point along the same pixel ray.
           ② discs and coloured mesh from one fixed oblique ORTHOGRAPHIC view (PROCFIG-v1 rank-1 direction, azimuth 180, elevation 35 = renders/cameras.json basis).
           discs = building-scope Gaussians, SH-0 colour, alpha = opacity (opacity < 0.01 not drawn), 1-sigma ellipse of their own rotation and scales (minor axis >= 0.6 px),
           far first; mesh = the original-rule mesh (203 views, TSDF 0.05 / 0.25 m, cleanup) coloured by cv2_meshcol.py, headlight shade 0.72 + 0.28 |n.f|.
  zones    one row per zone: ②-k discs zoom, ②-k mesh zoom (contents whose centre is inside the zone box; own orthographic view at elevation 35 and the azimuth
           that puts the zone line left-to-right on screen, so zoom and section read in the same direction), ③-k sections of this method and of the comparison
           run (band of 1 m around the zone line), ③-k comparison mesh zoom.
           r2 rule (user, 2026-11-13): a section shows the processing result only = Gaussian centres in the band in purple shaded by opacity and the mesh cut on
           the band centre plane (blue); no GT, prior, image depth or targets in the iteration frames. All data only in the input frame: ③ this method = GT dense
           points (black), prior ALS surface cut (orange dashed), image depth = FT patch MVS mean points (green), judgment target +-1.96 sigma quads coloured by
           judgment; ③ comparison = that run's own inputs only (judgment off: prior and image depth, both its targets; image-only 2DGS: none, panel empty).
           section height range (all frames, same axes as the input frame) = targets above 5 m (-1 m) to the prior or target top (+0.8 m).
           input frame ②: prior surface at alpha 0.6 over the image-depth points. Legend line lists only what the frame draws.
           r3 rule (user, 2026-11-13): the sections add GT dense points as a light grey reference and show the result UNFILTERED (cv2_sec3.py): all Gaussians
           of the saved state in the band (no building-scope mask, any opacity; colour Purples 0.3 + 0.7 x opacity so that opacity 0 stays visible), the cut of
           the uncut mesh, and 3 m drawn beyond each line end (light dotted lines at s = 0 and L). Height axis: the r2 range (section_height_limits_m) keeps
           13 % of the panel above/below for everything outside it, compressed linearly to the overall min/max of all states (light band, dashed break,
           end ticks give the real heights). Same axes in every frame and in both sections of a zone.
           r4 rule (user, 2026-11-13: 'too many symbols, the intent is unclear'): iteration-frame sections = GT as a wide light grey band + the uncut mesh cut
           as a thin blue line on top, nothing else (Gaussian centres removed: ② shows the Gaussians; floaters stay visible through the uncut mesh). Height
           axis = plain linear from the overall min of all drawn layers (mesh of every state, GT, prior, targets) to the overall max, except zone 2 where the
           linear part stops at 25 m (the building) and one compressed band above holds the early-state pieces up to the overall max. ① render depth: no red
           outline; ① depth target: judgment boundaries only in the input frame. Legend lists only what the frame draws.
           r5 (user, 2026-11-13): timeline facts from the r27 fork (train.py 1173: densification and opacity reset only while iteration < densify_until_iter
           15,000; opacity_reset_interval 3,000; saved *_pre_reset states 3,000 / 6,000 / 9,000 / 12,000): a small mark at each reset (3,000, 6,000, 9,000,
           12,000; placed by linear interpolation between the frame dots), '≈' on the line between 15,000 and 30,000 (frames skip 15,000 iterations), the
           note '가우시안 늘리기 끝' under 15,000, and '· 불투명도 초기화 직후' in the 3,000 frame title. No frames added after 15,000 (user decision).
           camera height colours: this camera's building-scope target heights, 2-98 %, 7 steps (static.json colour_range).
           zone 1 glass skylight in the concept-v1 zoom (ZONE1_RULE: B173_sawtooth direction, placed on this camera's target map; 12 m line, box 12 x 8 m), comparison = judgment off
                  (main_stage3_v1 nojudge_ALS_s0 = RESCORE baseline_30000; saved 15,000 and 30,000)
           zone 2 changed wing roof = PROCFIG-v1 section line (proc_section_data.json, 27.2 m), box = trainlog_v1.json scope zoom_box_xy, comparison = image-only
                  2DGS (main_baselines_v1 imgonly_2dgs_s0; saved 7,000 and 30,000)
           comparison state = the nearest saved iteration <= the frame's; none before the first saved one (section and mesh panels left empty, '비교: 저장 상태 없음').
Modes: setup (static layers -> concept_v2/static.npz, static.json) | frames [labels] | table (numbers) | contact (one sheet of all frames).
r2 / r3 write concept_v2/frames_<rev>/, docs contact_sheet_<rev>.png and frames_json_<rev>/; the first cut (frames/, contact_sheet.png, frames_json/) and r2 are kept.
r6 (user 2026-11-13 '응 진행하자'): CV2_VARIANT=r6 = r5 with the zone-1 comparison = image-only 2DGS (main_baselines_v1 imgonly_2dgs_s0, saved 7,000 and 30,000) as in zone 2,
because the 'judgment off' run is the stage-3 r15 fork (rho_truncated prior term, separate MVS term), not this method (FINALTRAIN r23) minus the judgment;
static.json and sections_r3 are read unchanged (both already hold the 2DGS cuts of zone 1); frames_r6/, contact_sheet_r6, frames_json_r6/, numbers_r6.*.
r6test (user 2026-11-13 '시험 장면 만들어'): CV2_VARIANT=z1b = zone 1 moved to the line chosen by cv2_zone1b.py (same direction, length and box rule; place chosen BY
SCORE = largest 30,000 band completeness difference this method - judgment off); static_z1b.*, sections_z1b/, frames_r6test/; all other rules as r5.
GT is used only for colour ranges, colouring, section drawing and the numbers. scientific_verdict: null"""
import os, sys, time
from common import *
from derive_states import scope_mask
import shapely
from shapely.geometry import Polygon
import open3d as o3d
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.collections import EllipseCollection, LineCollection, PolyCollection
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, FancyArrowPatch
from PIL import Image
FONT = '/fonts/NotoSansCJK-Regular.ttc'; fm.fontManager.addfont(FONT); plt.rcParams['font.family'] = fm.FontProperties(fname=FONT).get_name(); plt.rcParams['axes.unicode_minus'] = False
V2 = O/'concept_v2'; FIGD = D/'figures_concept_v2'
# test variant (2026-11-13, user '시험 장면 만들어'): CV2_VARIANT=z1b moves zone 1 to the line chosen by cv2_zone1b.py (concept_v2/zone1b_line.json) and writes
# its own static_z1b.*, sections_z1b/ and frames_r6test/; without it every path and rule is the r5 one (r1-r5 outputs are not touched).
# r6 (2026-11-13, user '응 진행하자'): CV2_VARIANT=r6 = the r5 zone 1 (static.json, sections_r3, read only) with the zone-1 comparison = image-only 2DGS (as zone 2);
# writes frames_r6/, contact_sheet_r6, frames_json_r6/, numbers_r6.* only.
VAR = os.environ.get('CV2_VARIANT', ''); assert VAR in ('', 'z1b', 'r6'), VAR
REV = {'': 'r5', 'z1b': 'r6test', 'r6': 'r6'}[VAR]; FR = V2/f'frames_{REV}'; Z1B = V2/'zone1b_line.json'; IS_Z1B = VAR == 'z1b'
STJ = V2/('static_z1b.json' if IS_Z1B else 'static.json'); STN = V2/('static_z1b.npz' if IS_Z1B else 'static.npz'); SECD = V2/('sections_z1b' if IS_Z1B else 'sections_r3'); SECJ = V2/f'{SECD.name}.json'
EXT = 3.0; STRIP = .13; STRIPC = '#E9E6DC'; GTL = '#B4B2A9'; GTB = '#D3D1C7'; ZTOP = {1: None, 2: 25.0}
RESETS = [3000, 6000, 9000, 12000]; DENSIFY_END = 15000; RESC = '#D85A30'
CAM = 'DJI_20241217091247_0146_D'; CAM_FILE = '0077.npz'; TAU = 0.211856; NEAR = .10; BAND = .5; NBIN = 7; OPMIN = .01
STATES = ['0', '100', '300', '1000', '2000', '3000', '5000', '7000', '10000', '15000', '30000']; FRAMES = ['input']+STATES
COMP = {1: dict(run='nojudge', name='판단 끈 학습', saved=[15000, 30000]), 2: dict(run='2dgs', name='사진만 쓴 2DGS', saved=[7000, 30000])}
if VAR == 'r6': COMP[1] = dict(COMP[2])   # r6: the 'judgment off' run is the stage-3 r15 fork, not this method minus the judgment -> zone 1 also against image-only 2DGS
ZNAME = {1: '유리 채광창', 2: '바뀐 날개 지붕'}
JC = {0: '#7FA7D9', 2: '#D85A30', 1: '#1D9E75', 4: '#E8B931'}; JN = {0: '일치', 2: '보정', 1: '보존', 4: '결측'}
NAVY = '#16263d'; GTC = '#1b1b1b'; PRC = '#E07B00'; MVC = '#2E9E4F'; MSC = '#1F5FBF'; RED = '#D62728'; EMPTY = '#F4F3EF'
PRIOR_RGB = np.array(to_rgb('#F2B872')); PRIOR_ALPHA = .6
RECT_V1 = (520, 20, 760, 260)   # concept draft v1 zoom (u0, v0, u1, v1): roof end, changed green roof, top end of the glass skylight
ZONE1_RULE = ('glass skylight in the concept-v1 zoom pixels (520,20)-(760,260): the thesis section B173_sawtooth lies on the same skylight but outside these pixels '
              '(checked: 0 % of its pixels inside), so the line keeps the B173_sawtooth direction (the skylight long axis) and is placed by the target map of this camera: '
              'lateral position = median offset of the 3-D target points of the judgment-0 (agree) pixels inside the zoom (the glass panels), start = their largest '
              'along-axis position + 1.0 m (the glass top end), running 12 m (= B173_sawtooth L) into the skylight; box = line x +-4 m (spots_v5 window rule)')
W_, H_ = 1920, 1080

# ---------------------------------------------------------------- geometry helpers
def line_frame(o, t):
    t = np.asarray(t, float)[:2]; t /= np.linalg.norm(t); return np.asarray(o, float)[:2], t, np.array([-t[1], t[0]])
def sv(P, z):  # along-line s and signed offset v of xy points
    q = np.asarray(P, float)[:, :2]-z['o']; return q@z['t'], q@z['n']
def cut(V, F, z):
    """Mesh cut by the vertical plane through the zone line: segments in (s, height above ground)."""
    vv = (V[:, :2]-z['o'])@z['n']; sg = np.sign(vv[F]); T = F[(sg.min(1) < 0) & (sg.max(1) > 0)]
    if not len(T): return np.zeros((0, 2, 2))
    E = []
    for a, b in [(0, 1), (1, 2), (2, 0)]:
        va, vb = vv[T[:, a]], vv[T[:, b]]; m = (va*vb) < 0; w = np.where(m, va/np.where(m, va-vb, 1), np.nan); E.append(V[T[:, a]]+w[:, None]*(V[T[:, b]]-V[T[:, a]]))
    E = np.stack(E, 1); ok = np.isfinite(E[:, :, 0]); keep = ok.sum(1) == 2; E, ok = E[keep], ok[keep]
    P = E[ok].reshape(-1, 2, 3); s = (P[:, :, :2]-z['o'])@z['t']; seg = np.stack([s, P[:, :, 2]-z['ground']], 2)
    inside = (seg[:, :, 0] >= -.5).all(1) & (seg[:, :, 0] <= z['L']+.5).all(1); return seg[inside]
def rot(q):
    r, x, y, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]; z_ = w
    return np.stack([np.stack([1-2*(y*y+z_*z_), 2*(x*y-r*z_), 2*(x*z_+r*y)], -1), np.stack([2*(x*y+r*z_), 1-2*(x*x+z_*z_), 2*(y*z_-r*x)], -1),
                     np.stack([2*(x*z_-r*y), 2*(y*z_+r*x), 1-2*(x*x+y*y)], -1)], 1)
def basis(up, az, el=35.):
    """render_states.view_camera / proto_v2.basis: rows r (screen right), u (screen up), f (forward)."""
    up = np.asarray(up, float); up /= np.linalg.norm(up); east = np.array([1., 0, 0]); east -= (east@up)*up; east /= np.linalg.norm(east); north = np.cross(up, east)
    a, e = np.radians(az), np.radians(el); out = np.cos(e)*(np.cos(a)*east+np.sin(a)*north)+np.sin(e)*up; f = -out; r = np.cross(f, up); r /= np.linalg.norm(r); return np.stack([r, np.cross(r, f), f])
def zone_az(t): return float(np.degrees(np.arctan2(-t[0], t[1])) % 360)   # screen right = +t (section x grows to the right)
def in_zone(P, z, zr):
    return shapely.contains_xy(z['poly'], P[:, 0], P[:, 1]) & (P[:, 2] >= zr[0]) & (P[:, 2] <= zr[1])

class Static:
    def __init__(self):
        self.c = cfg(); sc = self.c['scope']; self.ground = sc['ground_z']; self.zr = (sc['z_min'], sc['z_max'])
        cams = json.loads((O/'renders/cameras.json').read_text()); vb = cams['view']; self.B = np.asarray(vb['basis'], float); self.ctr = np.asarray(vb['center'], float)
        tr = [v for v in cams['training'] if v['name'] == CAM][0]; self.K = np.asarray(tr['K'], float); self.E = np.asarray(tr['W2C'], float); self.W, self.H = tr['width'], tr['height']
        self.sec = sec = json.loads(Path('/repo/configs/phd/main_stage1_v1/sections_v1.json').read_text())['sections']['B173_sawtooth']; pf = json.loads((PF/'figures/proc_section_data.json').read_text())
        sj = STJ; z1src = ZONE1_RULE
        if sj.exists():   # zone 1 line as fixed by setup() (zone1_line)
            z1 = json.loads(sj.read_text())['zones']['1']; o1, t1, n1 = line_frame(z1['line_origin_xy'], z1['line_unit_xy']); L1 = z1['line_length_m']
            if IS_Z1B: z1src = z1['source']
        elif IS_Z1B:   # z1b test: the line chosen by cv2_zone1b.py
            z1 = json.loads(Z1B.read_text()); o1, t1, n1 = line_frame(z1['line_origin_xy'], z1['line_unit_xy']); L1 = float(z1['line_length_m']); z1src = z1['rule']
        else: o1, t1, n1 = line_frame(sec['centre'][:2], sec['t']); L1 = float(sec['L'])   # placeholder until setup() fixes it
        poly1 = Polygon([o1+a*t1+b*n1 for a, b in [(0, -4), (L1, -4), (L1, 4), (0, 4)]])
        o2, t2, n2 = line_frame(pf['line']['A_local_xyz'], np.asarray(pf['line']['Aprime_local_xyz'])-np.asarray(pf['line']['A_local_xyz']))
        self.zones = {1: dict(o=o1, t=t1, n=n1, L=L1, poly=poly1, ground=self.ground, source=z1src),
                      2: dict(o=o2, t=t2, n=n2, L=float(pf['line']['length_m']), poly=Polygon(sc['zoom_box_xy']), ground=self.ground,
                              source='PROCFIG-v1 proc_section_data.json line A-Aprime; box = trainlog_v1.json scope zoom_box_xy')}
        self.cam_cache = {}
    def proj(self, P, B=None, ctr=None): q = (np.asarray(P, float)-(self.ctr if ctr is None else ctr))@(self.B if B is None else B).T; return q[:, 0], q[:, 1], q[:, 2]
    def zview(self, k):
        z = self.zones[k]; B = basis(self.c['coordinates']['up'], zone_az(z['t'])); return B, np.r_[np.asarray(z['poly'].centroid.coords[0]), self.ground+12.]
    def pix(self, P):
        Xc = np.asarray(P, float)@self.E[:3, :3].T+self.E[:3, 3]; return self.K[0, 0]*Xc[:, 0]/Xc[:, 2]+self.K[0, 2], self.K[1, 1]*Xc[:, 1]/Xc[:, 2]+self.K[1, 2], Xc[:, 2]
    def backproject(self, depth):
        v, u = np.mgrid[0:self.H, 0:self.W].astype(float); d = np.c_[((u-self.K[0, 2])/self.K[0, 0]).ravel(), ((v-self.K[1, 2])/self.K[1, 1]).ravel(), np.ones(u.size)]
        R, t = self.E[:3, :3], self.E[:3, 3]; P = (d*depth.reshape(-1, 1)-t)@R; return P.reshape(self.H, self.W, 3), np.linalg.norm(d, axis=1).reshape(self.H, self.W)

# ---------------------------------------------------------------- setup: static layers
def setup():
    assert VAR != 'r6', 'r6 reads the r5 static layers; setup would overwrite static.json'
    S = Static(); c = S.c; t0 = time.monotonic(); rec = dict(at=now(), rule=__doc__, scientific_verdict=None)
    inp = loadz(O/'concept/inputs.npz'); assert str(inp['name']) == CAM and np.allclose(inp['K'], S.K) and np.allclose(inp['W2C'], S.E)
    tg = loadz(FT/'targets'/f'{STEM}.npz', ['target', 'normal', 'sigma', 'judge_region', 'area', 'region', 'centre', 'mvs_mean_m'])
    td = inp['target_depth'].astype(float); tw = inp['target_weight'].astype(float); own = inp['target_owner'].astype('i8')
    tok = np.isfinite(td) & (td > 0) & (tw > 0); Pt, rn = S.backproject(np.where(tok, td, 0.)); ht = np.where(tok, Pt[..., 2]-S.ground, np.nan)
    cls = np.full(td.shape, -2, 'i1'); cls[tok & (own < 0)] = -1; m = tok & (own >= 0); cls[m] = tg['judge_region'][own[m]]
    # zone 1 line (ZONE1_RULE)
    sec = S.sec; t = np.asarray(sec['t'][:2], float); t /= np.linalg.norm(t); n = np.array([-t[1], t[0]]); c0 = np.asarray(sec['centre'][:2], float)
    u0, v0, u1, v1 = RECT_V1; rm = np.zeros_like(tok); rm[v0:v1, u0:u1] = True; g0 = tok & rm & (cls == 0); q = Pt[g0][:, :2]-c0
    n_c = float(np.median(q@n)); s_top = float((q@t).max())+1.0; o1, t1, n1 = line_frame(c0+n_c*n+s_top*t, -t); L1 = float(sec['L'])
    zone1_rec = dict(rule=ZONE1_RULE, sawtooth_centre_xy=c0.tolist(), sawtooth_unit_xy=t.tolist(), agree_pixels_used=int(g0.sum()), lateral_offset_m=n_c, start_along_axis_m=s_top,
                     zoom_v1_class_pixels={str(int(k)): int((cls[rm & tok] == k).sum()) for k in np.unique(cls[rm & tok])})
    if IS_Z1B:   # z1b test: Static() already holds the cv2_zone1b.py line; the r5 rule values above are kept only as the record of what was moved
        zb = json.loads(Z1B.read_text()); o1, t1, n1, L1 = S.zones[1]['o'], S.zones[1]['t'], S.zones[1]['n'], S.zones[1]['L']
        zone1_rec = dict(rule=zb['rule'], selection=zb['selection'], zone1b_line_sha256=sha(Z1B), r5_rule=zone1_rec)
    S.zones[1].update(o=o1, t=t1, n=n1, L=L1, poly=Polygon([o1+a*t1+b*n1 for a, b in [(0, -4), (L1, -4), (L1, 4), (0, 4)]]))
    # crop of the camera = building-scope target pixels
    insc = tok.copy(); insc[tok] = scope_mask(Pt[tok], c); vv, uu = np.nonzero(insc); pad = 10
    crop = [int(max(uu.min()-pad, 0)), int(max(vv.min()-pad, 0)), int(min(uu.max()+pad+1, S.W)), int(min(vv.max()+pad+1, S.H))]
    g = loadz(GT/'reference'/SITE/'dense.npz', ['xyz']); gx = g['xyz'].astype(float); gin = scope_mask(gx, c); gs = gx[gin]
    lo, hi = np.percentile(ht[insc], [2, 98]); bins = np.linspace(lo, hi, NBIN+1)   # heights of this camera's building-scope target points
    gt_lohi = np.percentile(gs[:, 2]-S.ground, [2, 98]).tolist()                       # (GT dense in scope, walls included: 2-98 % recorded only)
    zmask = {}; zrec = {}
    pr = loadz(S1/'defs'/SITE/'prior_ALS.npz', ['V', 'F']); PV, PFc = pr['V'].astype(float), pr['F'].astype('i8')
    valid = (tg['region'] >= 0) & np.isfinite(tg['target']).all(1) & np.isfinite(tg['normal']).all(1) & np.isfinite(tg['sigma']) & (tg['sigma'] > 0) & np.isin(tg['judge_region'], [0, 1, 2, 4])
    mv = np.isfinite(tg['mvs_mean_m']); MP = tg['centre'][mv]+tg['normal'][mv]*tg['mvs_mean_m'][mv][:, None]
    out = dict(crop=np.array(crop), bins=bins, ht=ht.astype('f4'), cls=cls, tok=tok, rn=rn.astype('f4'), mvs_xyz=MP.astype('f4'))
    for k, z in S.zones.items():
        zp = tok & shapely.contains_xy(z['poly'], Pt[..., 0], Pt[..., 1]) & (Pt[..., 2] >= S.zr[0]) & (Pt[..., 2] <= S.zr[1]); zmask[k] = zp; out[f'zmask{k}'] = zp
        s, v = sv(gs, z); b = (np.abs(v) <= BAND) & (s >= 0) & (s <= z['L']); out[f'gt{k}'] = np.c_[s[b], gs[b, 2]-S.ground].astype('f4')
        out[f'prior{k}'] = cut(PV, PFc, z).astype('f4')
        s, v = sv(MP, z); b = (np.abs(v) <= BAND) & (s >= 0) & (s <= z['L']) & (MP[:, 2] >= S.zr[0]-1) & (MP[:, 2] <= S.zr[1]+1); out[f'mvs{k}'] = np.c_[s[b], MP[b, 2]-S.ground].astype('f4')
        T = tg['target'][valid]; s, v = sv(T, z); b = (np.abs(v) <= BAND) & (s >= 0) & (s <= z['L']); ix = np.flatnonzero(valid)[b]
        n = tg['normal'][ix]; ns = n[:, :2]@z['t']; nz = n[:, 2]; nn = np.hypot(ns, nz); ns, nz = ns/np.maximum(nn, 1e-9), nz/np.maximum(nn, 1e-9)
        r = np.sqrt(tg['area'][ix]/np.pi); w = 1.96*tg['sigma'][ix]; cs, cz = s[b], tg['target'][ix, 2]-S.ground; ts, tz = -nz, ns
        quad = np.stack([np.c_[cs-r*ts-w*ns, cz-r*tz-w*nz], np.c_[cs+r*ts-w*ns, cz+r*tz-w*nz], np.c_[cs+r*ts+w*ns, cz+r*tz+w*nz], np.c_[cs-r*ts+w*ns, cz-r*tz+w*nz]], 1)
        out[f'tq{k}'] = quad.astype('f4'); out[f'tj{k}'] = tg['judge_region'][ix].astype('i1'); out[f'tc{k}'] = np.c_[cs-r*ts, cz-r*tz, cs+r*ts, cz+r*tz].astype('f4')
        # section limits: GT in band (1-99 %), prior cut, targets
        pz = out[f'prior{k}'][:, :, 1].ravel() if len(out[f'prior{k}']) else np.zeros(0); rz = cz[cz > 5.]   # roof content: targets above 5 m (wall feet, terrain out), prior top
        y0, y1 = float(rz.min())-1., float(max(rz.max(), pz.max() if len(pz) else rz.max()))+.8
        # zoom framing: the zone box between the section height limits (roof content); outline height = median GT dense height inside the box
        gz = gs[in_zone(gs, z, S.zr)]; zh = float(np.median(gz[:, 2]))
        ring = np.asarray(z['poly'].exterior.coords)[:-1]; ZB, zc = S.zview(k); x, y, _ = S.proj(np.r_[np.c_[ring, np.full(len(ring), y0+S.ground)], np.c_[ring, np.full(len(ring), y1+S.ground)]], ZB, zc)
        zrec[k] = dict(name=ZNAME[k], source=z['source'], line_origin_xy=z['o'].tolist(), line_unit_xy=z['t'].tolist(), line_length_m=z['L'], band_half_width_m=BAND,
                       box_polygon_xy=ring.tolist(), box_z=list(S.zr), outline_z=zh, zoom_azimuth_deg=zone_az(z['t']), zoom_elevation_deg=35, zoom_basis=ZB.tolist(), zoom_centre=zc.tolist(), zoom_extent=[float(x.min()), float(x.max()), float(y.min()), float(y.max())],
                       section_height_limits_m=[y0, y1], camera_pixels=int(zp.sum()), gt_in_band=int(len(out[f'gt{k}'])), mvs_in_band=int(len(out[f'mvs{k}'])), targets_in_band=int(len(ix)),
                       prior_cut_segments=int(len(out[f'prior{k}'])), target_judgments_in_band={JN[int(j)]: int((tg['judge_region'][ix] == j).sum()) for j in (0, 2, 1, 4)},
                       target_judgments_in_box={JN[int(j)]: int((tg['judge_region'][valid & in_zone(tg['target'], z, S.zr)] == j).sum()) for j in (0, 2, 1, 4)},
                       camera_pixel_classes={str(int(cl)): int((cls[zp] == cl).sum()) for cl in np.unique(cls[zp])})
        if k == 1: zrec[k]['line_rule'] = zone1_rec
    r1 = zmask[1]; vv, uu = np.nonzero(r1); zrec[1]['share_of_camera_pixels_inside_concept_v1_zoom_520_20_760_260'] = float(((uu >= 520) & (uu < 760) & (vv >= 20) & (vv < 260)).mean()) if len(uu) else None
    zrec[1]['camera_pixel_bbox_uv'] = [int(uu.min()), int(vv.min()), int(uu.max()), int(vv.max())] if len(uu) else None
    vv, uu = np.nonzero(zmask[2]); zrec[2]['camera_pixel_bbox_uv'] = [int(uu.min()), int(vv.min()), int(uu.max()), int(vv.max())] if len(uu) else None
    # overview framing: scope footprint x [ground, z_max]
    fp = np.asarray(c['scope']['footprint']['coordinates'][0], float)[:, :2]; corners = np.array([[x, y, zz] for x, y in fp for zz in (S.ground, S.zr[1])]); x, y, _ = S.proj(corners)
    rec.update(camera=dict(name=CAM, K=S.K.tolist(), W2C=S.E.tolist(), crop_u0v0u1v1=crop), oblique=dict(basis=S.B.tolist(), centre=S.ctr.tolist(), projection='orthographic', azimuth_deg=180, elevation_deg=35,
               overview_extent=[float(x.min()), float(x.max()), float(y.min()), float(y.max())]), colour_range=dict(height_above_ground_m=[float(lo), float(hi)], bins=bins.tolist(), source='target-map 3-D points of this camera inside the building scope, 2-98 % (GT dense in scope incl. walls would give '+', '.join(f'{v:.2f}' for v in gt_lohi)+' m and leave the roofs in one or two steps)', ground_z=S.ground),
               zones=zrec, judgment_class_pixels={str(int(k)): int((cls == k).sum()) for k in np.unique(cls)}, prior_mesh=str(S1/'defs'/SITE/'prior_ALS.npz'), gt=str(GT/'reference'/SITE/'dense.npz'),
               targets=str(FT/'targets'/f'{STEM}.npz'), target_map=str(O/'concept/inputs.npz'), seconds=round(time.monotonic()-t0, 1))
    savez(STN, **out); dump(STJ, rec); print('STATIC', json.dumps(zrec, ensure_ascii=False)[:1500], crop, bins, flush=True)

# ---------------------------------------------------------------- drawing helpers
class Frame:
    def __init__(self):
        self.S = Static(); self.st = loadz(STN); self.sj = json.loads(STJ.read_text()); self.sha = {}
        self.sgt = loadz(SECD/'gt.npz'); s3 = json.loads(SECJ.read_text()); self.yr = {}
        for k in (1, 2):   # r4 height axis: linear over every drawn layer (mesh of all states, GT, prior, targets); zone 2 linear to ZTOP + one compressed band above
            zs = [r['zones'][str(k)] for r in s3['keys'].values()]
            vals = [v for z in zs if z['mesh_height_min_max'] for v in z['mesh_height_min_max']] + [float(self.sgt[f'gt{k}'][:, 1].min()), float(self.sgt[f'gt{k}'][:, 1].max())]
            vals += [float(self.st[f'prior{k}'][..., 1].min()), float(self.st[f'prior{k}'][..., 1].max()), float(self.st[f'tq{k}'][..., 1].min()), float(self.st[f'tq{k}'][..., 1].max())]
            lo, hi = np.floor(min(vals)*2)/2-.25, np.ceil(max(vals)*2)/2+.25; top = ZTOP[k] if ZTOP[k] is not None and hi > ZTOP[k] else hi
            self.yr[k] = (lo, lo, top, hi)
        b = self.st['bins']; self.bins = b; cmap = plt.get_cmap('viridis'); self.hcol = np.array([cmap((i+.5)/NBIN)[:3] for i in range(NBIN)])
        pr = loadz(S1/'defs'/SITE/'prior_ALS.npz', ['V', 'F']); self.PV, self.PF = pr['V'].astype(float), pr['F'].astype('i8')
        keep = scope_mask(self.PV[self.PF].mean(1), self.S.c); self.PFs = self.PF[keep]
        self.fig = None
    def h(self, p):
        if p not in self.sha: self.sha[p] = sha(p)
        return self.sha[p]
    def hrgb(self, ht):
        idx = np.clip(np.searchsorted(self.bins, ht, side='right')-1, 0, NBIN-1); img = self.hcol[idx]; img[~np.isfinite(ht)] = 1.; return img
    # -------- layout
    def axes(self, x, y, w, h, title=None, fs=10.5):
        ax = self.fig.add_axes([x/W_, 1-(y+h)/H_, w/W_, h/H_]); ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values(): s.set_color('#B4B2A9'); s.set_linewidth(.6)
        if title: self.fig.text((x+1)/W_, 1-(y-3)/H_, title, fontsize=fs, color=NAVY, ha='left', va='bottom')
        return ax
    def blank(self, ax): ax.set_facecolor(EMPTY)
    # -------- ① camera panels
    def cam(self, ax, img, zones=True, outline=None, dotted=False):
        u0, v0, u1, v1 = self.st['crop']; ax.imshow(img[v0:v1, u0:u1], extent=(u0, u1, v1, v0), interpolation='antialiased'); ax.set_xlim(u0, u1); ax.set_ylim(v1, v0)
        uu, vv = np.arange(u0, u1)+.5, np.arange(v0, v1)+.5
        if outline is not None and outline[v0:v1, u0:u1].any(): ax.contour(uu, vv, outline[v0:v1, u0:u1].astype(float), levels=[.5], colors=RED, linewidths=.3, alpha=.85)
        if dotted:
            for k in (1, 2):
                zm = self.st[f'zmask{k}'][v0:v1, u0:u1]
                for cl in [0, 1, 2, 4, -1]:
                    a = (self.st['cls'][v0:v1, u0:u1] == cl).astype(float)
                    if (a[zm] > 0).any() and (a[zm] < 1).any(): ax.contour(uu, vv, np.ma.masked_where(~zm, a), levels=[.5], colors='#2C2C2A', linewidths=.7, linestyles=':')
        if zones:
            for k, z in self.S.zones.items():
                ring = np.asarray(self.sj['zones'][str(k)]['box_polygon_xy']); P = np.c_[ring, np.full(len(ring), self.sj['zones'][str(k)]['outline_z'])]; u, v, _ = self.S.pix(P)
                ax.plot(np.r_[u, u[:1]], np.r_[v, v[:1]], color='white', lw=2.2); ax.plot(np.r_[u, u[:1]], np.r_[v, v[:1]], color=NAVY, lw=1.0)
                if k == 1: self.badge(ax, u[np.argmax(v)], v.max()+14, k)
                else: self.badge(ax, u.mean(), v.min()-14, k)
    def badge(self, ax, x, y, k, fs=9):
        ax.text(x, y, str(k), fontsize=fs, color='white', ha='center', va='center', fontweight='bold', bbox=dict(boxstyle='circle,pad=.18', fc=NAVY, ec='white', lw=.8), zorder=20, clip_on=True)
    # -------- ② oblique panels
    def frame_ext(self, ext, w, h, pad=.04):
        x0, x1, y0, y1 = ext; cx, cy = (x0+x1)/2, (y0+y1)/2; hx, hy = (x1-x0)/2*(1+pad), (y1-y0)/2*(1+pad)
        if hx/hy < w/h: hx = hy*w/h
        else: hy = hx*h/w
        return (cx-hx, cx+hx, cy-hy, cy+hy)
    def raster(self, V, F, C, ext, w, h, ss=2, tint=None, view=None):
        Wp, Hp = int(w*ss), int(h*ss); x0, x1, y0, y1 = ext; xs = x0+(np.arange(Wp)+.5)*(x1-x0)/Wp; ys = y1-(np.arange(Hp)+.5)*(y1-y0)/Hp; X, Y = np.meshgrid(xs, ys)
        B, ctr = view if view is not None else (self.S.B, self.S.ctr); org = ctr+X[..., None]*B[0]+Y[..., None]*B[1]-400*B[2]
        sc = o3d.t.geometry.RaycastingScene(); tm = o3d.t.geometry.TriangleMesh(); tm.vertex.positions = o3d.core.Tensor(np.ascontiguousarray(V, 'f4')); tm.triangle.indices = o3d.core.Tensor(np.ascontiguousarray(F, 'i4')); sc.add_triangles(tm)
        r = sc.cast_rays(o3d.core.Tensor(np.concatenate([org, np.broadcast_to(B[2], org.shape)], -1).reshape(-1, 6).astype('f4')))
        t = r['t_hit'].numpy(); hit = np.isfinite(t); pid = r['primitive_ids'].numpy().astype('i8'); uv = r['primitive_uvs'].numpy(); nrm = r['primitive_normals'].numpy()
        shade = .72+.28*np.abs(nrm@B[2])
        if tint is not None: col = np.broadcast_to(tint, (len(t), 3))
        else:
            tri = F[pid.clip(0, len(F)-1)]; a, b = uv[:, 0:1], uv[:, 1:2]; col = ((1-a-b)*C[tri[:, 0]]+a*C[tri[:, 1]]+b*C[tri[:, 2]])/255.
        img = np.where(hit[:, None], np.clip(col*shade[:, None], 0, 1), 1.).reshape(Hp, Wp, 3); return img, np.where(hit, t-400, np.inf).reshape(Hp, Wp)
    def show_prior(self, ax, img, dep, ext):   # input frame: prior surface at alpha PRIOR_ALPHA over the image-depth points behind it
        ax.imshow(np.dstack([img, np.where(np.isfinite(dep), PRIOR_ALPHA, 0.)]), extent=ext, interpolation='antialiased', zorder=2); ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.set_aspect('equal')
    def show(self, ax, img, ext):
        ax.imshow(img, extent=ext, interpolation='antialiased'); ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.set_aspect('equal')
    def discs(self, ax, z, sel, ext, wpx, edge=False, view=None):
        P = z['xyz'][sel].astype(float); op = z['opacity'][sel].astype(float); keep = op >= OPMIN; P, op = P[keep], op[keep]; B, ctr = view if view is not None else (self.S.B, self.S.ctr)
        x, y, d = self.S.proj(P, B, ctr); Rm = rot(z['quat'][sel][keep].astype(float)); s = z['scale'][sel][keep].astype(float)
        a0, a1 = Rm[:, :, 0]*s[:, 0:1], Rm[:, :, 1]*s[:, 1:2]; M = np.stack([np.stack([a0@B[0], a1@B[0]], 1), np.stack([a0@B[1], a1@B[1]], 1)], 1)
        Sg = M@M.transpose(0, 2, 1); w, Vv = np.linalg.eigh(Sg); ang = np.degrees(np.arctan2(Vv[:, 1, 1], Vv[:, 0, 1])); mpp = (ext[1]-ext[0])/wpx
        big, small = np.maximum(2*np.sqrt(np.maximum(w[:, 1], 0)), .6*mpp), np.maximum(2*np.sqrt(np.maximum(w[:, 0], 0)), .6*mpp)
        o = np.argsort(-d); fc = np.c_[z['rgb'][sel][keep][o].astype(float), op[o]]
        ec = np.c_[np.full((len(o), 3), .15), .45*op[o]] if edge else 'none'
        ax.add_collection(EllipseCollection(big[o], small[o], ang[o], units='xy', offsets=np.c_[x[o], y[o]], offset_transform=ax.transData, facecolors=fc, edgecolors=ec, linewidths=.3 if edge else 0))
        ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.set_aspect('equal'); return int(len(o))
    def zone_outline(self, ax, k, label=True):
        zj = self.sj['zones'][str(k)]; ring = np.asarray(zj['box_polygon_xy']); x, y, _ = self.S.proj(np.c_[ring, np.full(len(ring), zj['outline_z'])])
        ax.plot(np.r_[x, x[:1]], np.r_[y, y[:1]], color='white', lw=2.4, zorder=15); ax.plot(np.r_[x, x[:1]], np.r_[y, y[:1]], color=NAVY, lw=1.1, zorder=16)
        if label: self.badge(ax, x.mean(), y.max(), k, 10)
    # -------- ③ sections
    def ymap(self, k, h):
        lo, y0, y1, hi = self.yr[k]; h = np.asarray(h, float); b = STRIP if lo < y0 else 0.; t = STRIP if hi > y1 else 0.
        return np.where(h < y0, b*(h-lo)/max(y0-lo, 1e-9), np.where(h > y1, 1-t+t*(h-y1)/max(hi-y1, 1e-9), b+(1-b-t)*(h-y0)/(y1-y0)))
    def section(self, ax, k, sec=None, layers=('gt', 'prior', 'mvs', 'targets')):
        zj = self.sj['zones'][str(k)]; L = zj['line_length_m']; lo, y0, y1, hi = self.yr[k]; st = self.st; Y = lambda h: self.ymap(k, h)
        b = STRIP if lo < y0 else 0.; t = STRIP if hi > y1 else 0.
        for a0, a1 in ([(0, b)] if b else [])+([(1-t, 1)] if t else []): ax.axhspan(a0, a1, color=STRIPC, zorder=0, lw=0)
        for yy in ([b] if b else [])+([1-t] if t else []): ax.axhline(yy, color='#9C9A92', lw=.6, ls=(0, (4, 2)), zorder=1)
        for xl in (0, L): ax.axvline(xl, color='#B4B2A9', lw=.6, ls=':', zorder=1)
        g = self.sgt[f'gt{k}']
        if 'gt' in layers: ax.scatter(g[:, 0], Y(g[:, 1]), s=.25, c=GTC, lw=0, zorder=3, rasterized=True)
        if 'gtlight' in layers: ax.scatter(g[:, 0], Y(g[:, 1]), s=.2, c=GTL, lw=0, zorder=3, rasterized=True)
        if 'gtband' in layers: ax.scatter(g[:, 0], Y(g[:, 1]), s=9, c=GTB, lw=0, zorder=3, rasterized=True)
        if 'prior' in layers and len(st[f'prior{k}']):
            q = st[f'prior{k}'].astype(float).copy(); q[..., 1] = Y(q[..., 1]); ax.add_collection(LineCollection(q, colors=PRC, linewidths=1.4, linestyles=(0, (3, 2)), zorder=4))
        if 'mvs' in layers: mv = st[f'mvs{k}']; ax.scatter(mv[:, 0], Y(mv[:, 1]), s=4, c=MVC, lw=0, zorder=5)
        if 'targets' in layers:
            q = st[f'tq{k}'].astype(float).copy(); q[..., 1] = Y(q[..., 1])
            ax.add_collection(PolyCollection(q, facecolors=[JC[int(j)] for j in st[f'tj{k}']], edgecolors=[JC[int(j)] for j in st[f'tj{k}']], linewidths=1.2, alpha=.6, zorder=4.5))
        n_g = n_m = None
        if sec is not None and 'gaussians' in layers:   # r3 only (r4 draws no Gaussian centres)
            s, h, op = sec[f'g{k}_s'].astype(float), sec[f'g{k}_h'].astype(float), sec[f'g{k}_op'].astype(float); o = np.argsort(op)
            ax.scatter(s[o], Y(h[o]), s=4, c=plt.get_cmap('Purples')(.3+.7*np.clip(op[o], 0, 1)), lw=0, zorder=6); n_g = int(len(s))
        if sec is not None:   # unfiltered: the uncut mesh cut
            seg = sec[f'm{k}'].astype(float).copy()
            if len(seg): seg[..., 1] = Y(seg[..., 1]); ax.add_collection(LineCollection(seg, colors=MSC, linewidths=1.3, zorder=7))
            n_m = int(len(seg))
        ax.set_xlim(-EXT, L+EXT); ax.set_ylim(0, 1); ax.tick_params(labelsize=7, length=2, pad=1, colors='#5F5E5A')
        ax.set_xticks(np.arange(0, L+.01, 5 if L > 15 else 2))
        stp = 1 if y1-y0 <= 6 else (2 if y1-y0 <= 14 else 5); tk = list(np.arange(np.ceil(y0/stp)*stp, y1+1e-6, stp)); pos = [float(v) for v in Y(np.array(tk))]; lab = [f'{v:.0f}' for v in tk]
        if b: pos = [0.]+pos; lab = [f'{lo:.0f}']+lab
        if t: pos = pos+[1.]; lab = lab+[f'{hi:.0f}']
        ax.set_yticks(pos); ax.set_yticklabels(lab)
        ax.text(.995, .02, 'm', transform=ax.transAxes, ha='right', va='bottom', fontsize=7, color='#5F5E5A'); ax.text(.005, .98, '높이 m', transform=ax.transAxes, ha='left', va='top', fontsize=7, color='#5F5E5A')
        return n_g, n_m

# ---------------------------------------------------------------- one frame
def comp_state(k, it):
    if it is None: return None
    s = [x for x in COMP[k]['saved'] if x <= it]; return max(s) if s else None

def draw(F, label, cache):
    S = F.S; st = F.st; it = None if label == 'input' else int(label); t0 = time.monotonic(); rec = dict(frame=label, iteration=it, sources={}, counts={})
    F.fig = fig = plt.figure(figsize=(W_/100, H_/100), dpi=100, facecolor='white')
    # top
    fig.text(16/W_, 1-24/H_, 'B173 · 입력' if it is None else f'B173 · 반복 {it:,} / 30,000'+(' · 불투명도 초기화 직후' if it in RESETS else ''), fontsize=19, color=NAVY, va='center', fontweight='bold')
    xs = np.linspace(1040, 1890, len(FRAMES)); cur = FRAMES.index(label); ax = fig.add_axes([0, 1-44/H_, 1, 44/H_]); ax.set_xlim(0, W_); ax.set_ylim(44, 0); ax.axis('off')
    ax.plot([xs[0], xs[-1]], [16, 16], color='#D3D1C7', lw=1, zorder=1)
    for i, (x, f) in enumerate(zip(xs, FRAMES)):
        col, sz = (NAVY, 11) if i == cur else (('#9C9A92', 7) if i < cur else ('#E3E1D9', 7)); ax.plot(x, 16, 'o', ms=sz, color=col, mec='white' if i != cur else NAVY, zorder=3)
        ax.text(x, 36, '입력' if f == 'input' else f'{int(f):,}', ha='center', va='center', fontsize=8.5 if i != cur else 9.5, color=NAVY if i == cur else '#77756D', fontweight='bold' if i == cur else 'normal')
    fit = np.array([int(f) for f in FRAMES[1:]], float)   # r5 timeline facts
    for n in RESETS: ax.plot(np.interp(n, fit, xs[1:]), 5, 'v', ms=5.5, color=RESC, mec='white', mew=.4, zorder=4)
    ax.text((xs[-2]+xs[-1])/2, 16, '≈', ha='center', va='center', fontsize=12, color='#77756D', zorder=5, bbox=dict(boxstyle='square,pad=.05', fc='white', ec='none'))
    fig.text(np.interp(DENSIFY_END, fit, xs[1:])/W_, 1-52/H_, '가우시안 늘리기 끝', ha='center', va='center', fontsize=7.5, color='#77756D')
    # ① camera 2x2
    u0, v0, u1, v1 = st['crop']; ph = 250; pw = int(round(ph*(u1-u0)/(v1-v0))); X0, Y0 = 16, 66; gap = 8
    inp = loadz(O/'concept/inputs.npz', ['photo']); photo = inp['photo'].astype(float)/255.; rec['sources']['photo_and_target_map'] = F.h(O/'concept/inputs.npz')
    a = F.axes(X0, Y0, pw, ph, '① 사진'); F.cam(a, photo)
    a = F.axes(X0, Y0+ph+24, pw, ph, '① 깊이 목표'); F.cam(a, F.hrgb(st['ht']), dotted=it is None)
    a1 = F.axes(X0+pw+gap, Y0, pw, ph, '① 렌더'); a2 = F.axes(X0+pw+gap, Y0+ph+24, pw, ph, '① 렌더 깊이')
    if it is None: F.blank(a1); F.blank(a2)
    else:
        rp = O/'renders'/label/'train1_rgb.png'; F.cam(a1, np.asarray(Image.open(rp).convert('RGB'), float)/255.); rec['sources']['render_rgb'] = F.h(rp)
        gp = O/'gtj/renders'/f'{STEM}__tl_{label}'/CAM_FILE; rd = loadz(gp, ['depth'])['depth'].astype(float); rec['sources']['render_depth'] = F.h(gp)
        rok = rd > 0; Pr, _ = S.backproject(np.where(rok, rd, 0.)); hr = np.where(rok, Pr[..., 2]-S.ground, np.nan)
        td = loadz(O/'concept/inputs.npz', ['target_depth'])['target_depth'].astype(float); dist = np.abs(rd-np.where(st['tok'], td, np.nan))*st['rn']
        far = st['tok'] & rok & (dist > TAU); F.cam(a2, F.hrgb(hr)); rec['counts']['render_far_from_target_pixels_in_crop'] = int(far[v0:v1, u0:u1].sum())
        cache['dist'] = dist; cache['rok'] = rok
    ar = FancyArrowPatch(((X0+2*pw+gap+6)/W_, 1-(Y0+ph+12)/H_), ((X0+2*pw+gap+46)/W_, 1-(Y0+ph+12)/H_), transform=fig.transFigure, arrowstyle='-|>', mutation_scale=22, color=NAVY, lw=2); fig.patches.append(ar)
    # ② overview
    X2 = X0+2*pw+gap+56; w2 = (W_-16-X2-12)//2; h2 = 2*ph+24; ext = F.frame_ext(F.sj['oblique']['overview_extent'], w2, h2, .03); rec['overview_extent'] = list(ext)
    ag = F.axes(X2, Y0, w2, h2, '② 가우시안 3D' if it is not None else '② 입력 3D: 사전 정보 면 · 영상 깊이 점'); am = F.axes(X2+w2+12, Y0, w2, h2, '② 메시 3D')
    if it is None:
        img, dep = cache.setdefault('prior_overview', F.raster(F.PV, F.PFs, None, ext, w2, h2, 2, PRIOR_RGB)); F.show_prior(ag, img, dep, ext)
        F.mvs_points(ag, dep, ext, w2, h2, 2, 1.2); F.zone_outline(ag, 1); F.zone_outline(ag, 2); F.blank(am)
    else:
        dz = loadz(V2/'discs'/f'ours_{label}.npz'); rec['sources']['discs'] = F.h(V2/'discs'/f'ours_{label}.npz')
        rec['counts']['discs_drawn_overview'] = F.discs(ag, dz, np.ones(len(dz['xyz']), bool), ext, w2); ag.set_facecolor('white'); F.zone_outline(ag, 1); F.zone_outline(ag, 2)
        mz = loadz(V2/'meshcol'/f'ours_{label}.npz'); rec['sources']['mesh'] = F.h(V2/'meshcol'/f'ours_{label}.npz')
        img, _ = F.raster(mz['V'], mz['F'], mz['C'].astype(float), ext, w2, h2, 2); F.show(am, img, ext); F.zone_outline(am, 1); F.zone_outline(am, 2)
    # zone rows
    wz, ws, gz = 262, (W_-32-3*262-4*12)//2, 12; hz = 192
    for row, k in enumerate((1, 2)):
        Y = 616+row*226; zj = F.sj['zones'][str(k)]; zext = F.frame_ext(zj['zoom_extent'], wz, hz, .06); zv = (np.asarray(zj['zoom_basis']), np.asarray(zj['zoom_centre'])); cs = comp_state(k, it); cn = COMP[k]['name']
        xg = 16; xm = xg+wz+gz; xs1 = xm+wz+gz; xs2 = xs1+ws+gz; xc = xs2+ws+gz
        a_g = F.axes(xg, Y, wz, hz, f'②-{k} 가우시안 확대 · {ZNAME[k]}' if it is not None else f'②-{k} 입력 확대 · {ZNAME[k]}'); a_m = F.axes(xm, Y, wz, hz, f'②-{k} 메시 확대')
        a_s = F.axes(xs1, Y, ws, hz, f'③-{k} 본 방법 단면'); ctitle = f'비교: {cs:,}회' if cs is not None else ('비교: 입력' if it is None else '비교: 저장 상태 없음')
        a_c = F.axes(xs2, Y, ws, hz, f'③-{k} 비교 단면 · {cn} · {ctitle}'); a_cm = F.axes(xc, Y, wz, hz, f'③-{k} 비교 메시 확대 · {cn}')
        zsel = lambda P: in_zone(P, S.zones[k], S.zr)
        if it is None:
            key = f'prior_zoom{k}'
            if key not in cache:
                fsel = in_zone(F.PV[F.PF].mean(1), S.zones[k], S.zr); cache[key] = F.raster(F.PV, F.PF[fsel], None, zext, wz, hz, 3, PRIOR_RGB, view=zv)
            img, dep = cache[key]; F.show_prior(a_g, img, dep, zext); F.mvs_points(a_g, dep, zext, wz, hz, 3, 5, zone=k, view=zv); F.blank(a_m); F.blank(a_cm)
            F.section(a_s, k)
            if COMP[k]['run'] == 'nojudge': F.section(a_c, k, layers=('prior', 'mvs'))   # its inputs = both targets, no judgment
            else: F.blank(a_c)                                                          # image-only 2DGS: no section input
        else:
            sel = zsel(dz['xyz'].astype(float)); rec['counts'][f'zone{k}_discs'] = F.discs(a_g, dz, sel, zext, wz, edge=True, view=zv)
            fsel = zsel(mz['V'][mz['F']].mean(1).astype(float)); img, _ = F.raster(mz['V'], mz['F'][fsel], mz['C'].astype(float), zext, wz, hz, 3, view=zv); F.show(a_m, img, zext)
            sp = SECD/f'ours_{label}.npz'; rec['sources'][f'section{k}'] = F.h(sp)
            ng, nm = F.section(a_s, k, sec=loadz(sp), layers=('gtband',)); rec['counts'][f'zone{k}_band_gaussians'] = ng; rec['counts'][f'zone{k}_mesh_cut_segments'] = nm
            if cs is None: F.blank(a_c); F.blank(a_cm)
            else:
                ck = f"{COMP[k]['run']}_{cs}"
                if ck not in cache: cache.clear() if len(cache) > 12 else None; cache[ck] = (loadz(V2/'discs'/f'{ck}.npz'), loadz(V2/'meshcol'/f'{ck}.npz'))
                cd, cm = cache[ck]; rec['sources'][f'comparison{k}_discs'] = F.h(V2/'discs'/f'{ck}.npz'); rec['sources'][f'comparison{k}_mesh'] = F.h(V2/'meshcol'/f'{ck}.npz')
                cp = SECD/f'{ck}.npz'; rec['sources'][f'comparison{k}_section'] = F.h(cp)
                ng, nm = F.section(a_c, k, sec=loadz(cp), layers=('gtband',)); rec['counts'][f'zone{k}_comparison_band_gaussians'] = ng
                fsel = zsel(cm['V'][cm['F']].mean(1).astype(float)); img, _ = F.raster(cm['V'], cm['F'][fsel], cm['C'].astype(float), zext, wz, hz, 3, view=zv); F.show(a_cm, img, zext)
        rec[f'zone{k}'] = dict(zoom_extent=list(zext), comparison_run=COMP[k]['run'], comparison_name=cn, comparison_iteration=cs, comparison_label=ctitle)
    # legend (one line)
    lax = fig.add_axes([0, 0, 1, 34/H_]); lax.axis('off'); lax.set_xlim(0, W_); lax.set_ylim(0, 34); x = 16
    lax.text(x, 17, '지면 위 높이 m', fontsize=9, va='center', color=NAVY); x += 84
    for i in range(NBIN): lax.add_patch(plt.Rectangle((x+i*22, 9), 22, 14, color=F.hcol[i]))
    for i in range(NBIN+1): lax.text(x+i*22, 4.5, f'{F.bins[i]:.0f}', fontsize=7, ha='center', va='center', color='#5F5E5A')
    x += NBIN*22+18
    if it is None: items = [('pt', GTC, '참값'), ('dash', PRC, '사전 정보'), ('pt', MVC, '영상 깊이'), *[('box', JC[j], f'목표 {JN[j]}') for j in (0, 2, 1, 4)], ('box', STRIPC, '25 m 위(압축)'), ('dot', '#2C2C2A', '판정 경계'), ('line', NAVY, '구역 상자'), ('reset', RESC, '불투명도 초기화')]
    else: items = [('band', GTB, '참값'), ('line', MSC, '메시'), ('box', STRIPC, '25 m 위(압축)'), ('line', NAVY, '구역 상자'), ('reset', RESC, '불투명도 초기화')]
    for kind, col, txt in items:
        if kind == 'pt': lax.plot(x+5, 17, 'o', ms=4.5, color=col)
        elif kind == 'box': lax.add_patch(plt.Rectangle((x, 11), 11, 12, color=col, alpha=.75))
        elif kind == 'band': lax.plot([x, x+18], [17, 17], color=col, lw=5, solid_capstyle='butt')
        elif kind == 'reset': lax.plot(x+5, 17, 'v', ms=6, color=col, mec='white', mew=.4)
        else: lax.plot([x, x+18], [17, 17], color=col, lw=1.6, ls={'dash': (0, (3, 2)), 'dot': ':', 'line': '-'}[kind])
        x += (14 if kind in ('pt', 'box', 'reset') else 22); t = lax.text(x, 17, txt, fontsize=9, va='center', color='#2C2C2A'); x += t.get_window_extent(fig.canvas.get_renderer()).width+16
    png = FR/f'frame_{FRAMES.index(label):02d}_{label}.png'; FR.mkdir(parents=True, exist_ok=True); fig.savefig(png, dpi=100, facecolor='white'); plt.close(fig)
    rec.update(png=str(png), png_sha256=sha(png), seconds=round(time.monotonic()-t0, 1), camera=F.sj['camera'], oblique=F.sj['oblique'], zones=F.sj['zones'], colour_range=F.sj['colour_range'],
               static_sha256=F.h(STN), rule=__doc__.split('\n')[0], scientific_verdict=None)
    dump(png.with_suffix('.json'), rec); print('FRAME', label, rec['seconds'], rec['counts'], flush=True)

def mvs_points(self, ax, dep, ext, w, h, ss, size, zone=None, view=None):
    P = self.st['mvs_xyz'].astype(float)
    if zone is not None: P = P[in_zone(P, self.S.zones[zone], self.S.zr)]
    else: P = P[scope_mask(P, self.S.c)]
    x, y, d = self.S.proj(P, *(view or (None, None))); Hp, Wp = dep.shape; x0, x1, y0, y1 = ext
    ci = np.clip(((x-x0)/(x1-x0)*Wp).astype(int), 0, Wp-1); ri = np.clip(((y1-y)/(y1-y0)*Hp).astype(int), 0, Hp-1); ins = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1); vis = (d <= dep[ri, ci]+.3) & ins
    ax.scatter(x[ins & ~vis], y[ins & ~vis], s=size, c=MVC, lw=0, zorder=1)   # behind the prior surface: seen through it (the surface is drawn at alpha PRIOR_ALPHA)
    ax.scatter(x[vis], y[vis], s=size, c=MVC, lw=0, zorder=8); ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); return int(vis.sum()), int((ins & ~vis).sum())
Frame.mvs_points = mvs_points

def frames(labels):
    F = Frame(); cache = {}
    for lab in labels: draw(F, lab, cache)

# ---------------------------------------------------------------- numbers
def numbers():
    S = Static(); st = loadz(STN); inp = loadz(O/'concept/inputs.npz', ['target_depth']); td = inp['target_depth'].astype(float)
    row = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz', 'row_tau_m']); rows_out = []
    rin = {k: in_zone(row['xyz'].astype(float), S.zones[k], S.zr) for k in (1, 2)}
    import importlib.util
    spec = importlib.util.spec_from_file_location('gtj_normal_line', '/repo/scripts/phd/main_gtjudge_v1/normal_line.py'); nl = importlib.util.module_from_spec(spec); spec.loader.exec_module(nl); values = nl.values
    def mesh_scores(dist_root, fam):
        p = dist_root/f'{fam}.npz'
        if not (p.exists() and (dist_root/f'{fam}_observed.npz').exists()): return None
        z = loadz(p, ['row_s']); ob = loadz(dist_root/f'{fam}_observed.npz'); xyz = loadz(dist_root/f'{fam}_samples.npz', ['xyz'])['xyz'].astype(float); tau_s = loadz(p, ['sample_tau'])['sample_tau']; out = {}
        for k in (1, 2):
            comp = values(z['row_s'][rin[k]], row['row_tau_m'][rin[k]]); q = in_zone(xyz, S.zones[k], S.zr); acc = values(ob['sample_s'][q], tau_s[q], (ob['observed'] & ~ob['steep'])[q])
            out[k] = dict(completeness_pct=comp['within_pct'], completeness_n=comp['n'], accuracy_pct=acc['within_pct'], accuracy_n=acc['n'])
        return out, p
    discs = json.loads((V2/'discs.json').read_text())['discs']
    for lab in FRAMES:
        r = dict(frame=lab, iteration=None if lab == 'input' else int(lab))
        if lab != 'input':
            r['psnr_db'] = json.loads((O/'renders'/lab/'render.json').read_text())['train1_psnr']; rd = loadz(O/'gtj/renders'/f'{STEM}__tl_{lab}'/CAM_FILE, ['depth'])['depth'].astype(float)
            dist = np.abs(rd-td)*st['rn']
            for k in (1, 2):
                m = st[f'zmask{k}']; ok = m & (rd > 0); r[f'zone{k}_target_pixels'] = int(m.sum()); r[f'zone{k}_target_within_10cm_pct'] = float(100*(ok & (dist <= NEAR)).sum()/m.sum())
                r[f'zone{k}_no_render_depth_pct'] = float(100*(m & ~(rd > 0)).sum()/m.sum())
            sc = mesh_scores(O/'gtj/scenes'/STEM/'distances', f'tl_{lab}')
            for k in (1, 2):
                for a, b in (sc[0][k] if sc else {}).items(): r[f'zone{k}_mesh_{a}'] = b
            r['gaussians_building_scope'] = discs[f'ours_{lab}']['n_scope']; r['gaussians_all'] = discs[f'ours_{lab}']['n_all']
            for k in (1, 2):
                cs = comp_state(k, int(lab)); r[f'zone{k}_comparison_iteration'] = cs
                if cs is not None:
                    fam = f"cmp_{COMP[k]['run']}_{cs}"+('_v203' if cs == 30000 else ''); scc = mesh_scores(V2/'gtj/scenes'/STEM/'distances', fam); r[f'zone{k}_comparison_family'] = fam
                    r[f'zone{k}_comparison_mesh_completeness_pct'] = scc[0][k]['completeness_pct'] if scc else None; r[f'zone{k}_comparison_mesh_accuracy_pct'] = scc[0][k]['accuracy_pct'] if scc else None
                    if cs == 30000:   # record: RESCORE's 219-view mesh of the same state
                        s2 = mesh_scores(V2/'gtj/scenes'/STEM/'distances', f"cmp_{COMP[k]['run']}_30000")
                        r[f'zone{k}_comparison_rescore219_completeness_pct'] = s2[0][k]['completeness_pct'] if s2 else None; r[f'zone{k}_comparison_rescore219_accuracy_pct'] = s2[0][k]['accuracy_pct'] if s2 else None
        rows_out.append(r); print('ROW', r, flush=True)
    NB = 'numbers' if REV == 'r5' else f'numbers_{REV}'   # r6: its own table (the r5 numbers.* stay)
    FIGD.mkdir(parents=True, exist_ok=True); p = table(NB, rows_out, folder=FIGD)
    dump(FIGD/f'{NB}.json', dict(at=now(), rows=rows_out, rule=dict(
        psnr='renders/<n>/render.json train1_psnr (this camera, r27 renderer, full scene)',
        target_within_10cm='pixels of this camera whose target 3-D point is inside the zone box; render depth = the mesh-input render (gtj/renders, surf_depth, building box); distance = |render z - target z| x |pixel ray (x, y, 1)|; pixels without render depth count as not within',
        mesh_completeness='GTJUDGE rows (rows.npz) inside the zone box, |row_s| <= row_tau_m (0.211856 m), normal_line.values (no surface = not within)',
        mesh_accuracy='mesh samples (score_new samples) inside the zone box, eligible = observed (normal cylinder 1 m) and not steep, |s| <= sample_tau (0.211856 m) = tl_mesh.score rule',
        gaussians='building-scope Gaussians of the saved state (its own inside mask)', zone_box='static.json zones (polygon xy, z = scope z_min..z_max)'), scientific_verdict=None))
    md = ['| 시점 | 사진 일치도 dB | 구역1 목표 10 cm 안 % | 구역2 목표 10 cm 안 % | 구역1 메시 완전성 % | 구역1 정확성 % | 구역2 메시 완전성 % | 구역2 정확성 % | 건물 범위 가우시안 | 구역1 비교(완전성/정확성) | 구역2 비교(완전성/정확성) |', '|'+'---|'*11]
    f = lambda v, d=1: '—' if v is None else (f'{v:,.{d}f}' if isinstance(v, float) else f'{v:,}')
    for r in rows_out:
        if r['frame'] == 'input': md.append('| 입력 |'+' — |'*10); continue
        cc = lambda k: '—' if r.get(f'zone{k}_comparison_iteration') is None else f"{r[f'zone{k}_comparison_iteration']:,}회: {f(r.get(f'zone{k}_comparison_mesh_completeness_pct'))} / {f(r.get(f'zone{k}_comparison_mesh_accuracy_pct'))}"
        md.append(f"| {int(r['frame']):,} | {f(r['psnr_db'])} | {f(r['zone1_target_within_10cm_pct'])} | {f(r['zone2_target_within_10cm_pct'])} | {f(r.get('zone1_mesh_completeness_pct'))} | {f(r.get('zone1_mesh_accuracy_pct'))} | "
                  f"{f(r.get('zone2_mesh_completeness_pct'))} | {f(r.get('zone2_mesh_accuracy_pct'))} | {r['gaussians_building_scope']:,} | {cc(1)} | {cc(2)} |")
    (FIGD/f'{NB}.md').write_text('\n'.join(md)+'\n'); print('TABLE', p, flush=True)

def contact():
    ims = [Image.open(p).convert('RGB').resize((480, 270), Image.LANCZOS) for p in sorted(FR.glob('frame_*.png'))]; sheet = Image.new('RGB', (480*4, 270*3), 'white')
    for i, im in enumerate(ims): sheet.paste(im, ((i % 4)*480, (i//4)*270))
    FIGD.mkdir(parents=True, exist_ok=True); sheet.save(FIGD/f'contact_sheet_{REV}.png')
    (FIGD/f'frames_json_{REV}').mkdir(exist_ok=True)
    for j in sorted(FR.glob('frame_*.json')): (FIGD/f'frames_json_{REV}'/j.name).write_bytes(j.read_bytes())   # frame records in git; PNG frames stay in the payload
    print('CONTACT', len(ims), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'setup': setup()
    elif a[0] == 'frames': frames(a[1].split(',') if len(a) > 1 else FRAMES)
    elif a[0] == 'table': numbers()
    elif a[0] == 'contact': contact()
