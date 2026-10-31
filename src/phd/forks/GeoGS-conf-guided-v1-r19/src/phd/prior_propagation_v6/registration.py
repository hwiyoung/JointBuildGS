"""Registration of the prior to the current MVS (prior_propagation_v5, PHD-MAIN-PREP-DISCARD-RULE-v1).

Moved unchanged from the PHD-MAIN-PREP-MEASURE-v1 stage-1 script (step03_stage1.py, config v2 rules):
  Nuth-Kaab horizontal steps proposed from fit pixels (roof-like confidence-1 building-face pixels, plane update), each step
  accepted only when the NMAD of the re-rendered height differences on the gate views decreases (gate callback);
  vertical shift = the median of the re-rendered height differences after the horizontal shift when |median| > NMAD;
  final check (fix 4): the horizontal shift is kept only when the all-view building-face NMAD decreases.
Pure numpy; rendering stays with the caller (gate callbacks). The order of calls (hence of the caller's random draws) is the
original one. scientific_verdict: null."""
import numpy as np

NMAD_C = 1.4826


def nmad(x):
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return np.nan, np.nan
    m = float(np.median(x))
    return m, float(NMAD_C * np.median(np.abs(x - m)))


def nk_fit(dh, n, w=None):
    """dh / tan(slope) = A cos(aspect) + B sin(aspect) + C; correction applied to the prior: (dx, dy) = (B, A)."""
    nz = np.abs(n[:, 2]); nxy = np.hypot(n[:, 0], n[:, 1])
    tan = nxy / np.maximum(nz, 1e-9)
    asp = np.arctan2(n[:, 0] * np.sign(n[:, 2]), n[:, 1] * np.sign(n[:, 2]))      # azimuth of the downslope direction
    y = dh / tan
    X = np.stack([np.cos(asp), np.sin(asp), np.ones_like(asp)], 1)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return np.array([coef[1], coef[0]]), asp


def apply_shift_dh(dh, n, d):
    gx = n[:, 0] / n[:, 2]; gy = n[:, 1] / n[:, 2]
    return dh - gx * d[0] - gy * d[1]


def estimable(asp, cfg):
    q = np.floor(((asp + np.pi) % (2 * np.pi)) / (np.pi / 2)).astype(int)
    share = np.bincount(np.clip(q, 0, 3), minlength=4) / max(len(asp), 1)
    return bool((share >= 0.05).sum() >= 3 and len(asp) >= 2000), share.tolist()


def nuth_kaab(dh, n, cfg):
    """ungated estimator (tile observation): dict(dx, dy, iterations, accepted, nmad trace); dh, n of the fit pixels."""
    rec = dict(iterations=[], horizontal_estimable=None)
    asp = np.arctan2(n[:, 0], n[:, 1])
    est, share = estimable(asp, cfg)
    rec["horizontal_estimable"] = est; rec["aspect_quadrant_share"] = share; rec["n_fit"] = int(len(dh))
    total = np.zeros(2)
    cur = dh.copy()
    m0, s0 = nmad(cur); rec["nmad_start"] = s0; rec["median_start"] = m0
    if not est:
        rec["shift_xy"] = [0.0, 0.0]; return rec
    s_prev = s0
    for it in range(cfg["iterations_max"]):
        m, s = nmad(cur)
        inl = np.abs(cur - m) <= 3 * s
        d, _ = nk_fit(cur[inl], n[inl])
        trial = apply_shift_dh(cur, n, d)
        mt, st = nmad(trial)
        accept = st < s_prev
        rec["iterations"].append(dict(it=it, step=d.tolist(), nmad_before=s_prev, nmad_after=st, accepted=bool(accept)))
        if not accept:
            break
        cur = trial; total += d; s_prev = st
        if np.linalg.norm(d) < cfg["stop_increment_m"]:
            break
    rec["shift_xy"] = total.tolist(); rec["nmad_end"] = s_prev
    return rec


def gated_horizontal(S, gate, cfg, reg):
    """Nuth-Kaab steps on the fit samples S (dh, n) accepted by the gate. gate(shift_xyz) -> (median, nmad) of the
    re-rendered height differences. Fills reg (iterations, horizontal_estimable, aspect_quadrant_share, gate_start) and
    returns the horizontal shift [2]."""
    asp = np.arctan2(S["n"][:, 0], S["n"][:, 1]) if len(S["dh"]) else np.zeros(0)
    est, share = estimable(asp, cfg)
    reg["horizontal_estimable"] = est; reg["aspect_quadrant_share"] = share
    cur = np.zeros(2)
    m_cur, s_cur = gate([0.0, 0.0, 0.0])
    reg["gate_start"] = dict(median=m_cur, nmad=s_cur)
    if est:
        for it in range(cfg["iterations_max"]):
            dhc = apply_shift_dh(S["dh"], S["n"], cur)
            m_, s_ = nmad(dhc)
            inl = np.abs(dhc - m_) <= 3 * s_
            d, _ = nk_fit(dhc[inl], S["n"][inl])
            mt, st_ = gate([cur[0] + d[0], cur[1] + d[1], 0.0])
            acc_ = bool(st_ < s_cur)
            reg["iterations"].append(dict(it=it, step=d.tolist(), gate_nmad_before=s_cur, gate_nmad_after=st_, accepted=acc_))
            if not acc_:
                break
            cur = cur + d; m_cur, s_cur = mt, st_
            if np.linalg.norm(d) < cfg["stop_increment_m"]:
                break
    return cur


def vertical_shift(gate, dxy):
    """(dz, median, nmad): the median of the re-rendered height differences after the horizontal shift, applied when
    |median| > NMAD."""
    m_h, s_h = gate([dxy[0], dxy[1], 0.0])
    dz = float(m_h) if (np.isfinite(m_h) and abs(m_h) > s_h) else 0.0
    return dz, m_h, s_h


VERTICAL_RULE = ("median of the re-rendered height differences (gate views, roof-like confidence-1 building-face pixels) after the "
                 "horizontal shift, applied when |median| > NMAD")
ACCEPTANCE_RULE = ("config v2: horizontal Nuth-Kaab steps (proposed on the fit pixels) accepted only when the NMAD of the re-rendered "
                   "height differences on the gate views decreases; the final horizontal shift kept only when the all-view building-face "
                   "NMAD decreases (fix 4); vertical by the median rule on the re-rendered gate views")


def final_check_fails(dxy, nmad_unregistered, nmad_registered):
    """fix 4: True when a non-zero horizontal shift does not decrease the all-view building-face NMAD (reject it)."""
    return bool(np.linalg.norm(dxy) > 0 and not (nmad_registered < nmad_unregistered))


def fixed_from_summary(fs, prior_name, reg_own, tol_roof, tol_wall, source):
    """fixed run (prep user decision 23:02, this task 5.2): the shift and the tolerances of another run's summary.json.
    Returns (shift [3], roof tolerance dict, wall tolerance dict, reg dict, fixed_info dict)."""
    fixed_info = dict(fixed_from=f"{source}/{prior_name}", tolerance_box=dict(roof=tol_roof, wall=tol_wall), registration_box=dict(reg_own),
                      note="judgments use the fixed values; the box's own values on its MVS are recorded here for comparison")
    shift = np.asarray(fs["registration"]["shift_applied"], np.float64)
    roof_t = dict(fs["tolerance"]["roof"]); wall_t = dict(fs["tolerance"]["wall"])
    reg = dict(fixed_from=f"{source}/{prior_name}", shift_applied=shift.tolist(), horizontal_estimable=fs["registration"].get("horizontal_estimable"),
               building_face_nmad_unregistered=reg_own.get("building_face_nmad_unregistered"), building_face_nmad_registered=reg_own.get("building_face_nmad_registered"),
               final_check=fs["registration"].get("final_check"), accepted_horizontal=fs["registration"].get("accepted_horizontal"),
               accepted_vertical=fs["registration"].get("accepted_vertical"))
    return shift, roof_t, wall_t, reg, fixed_info
