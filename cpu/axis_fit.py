"""Axis estimators that use the WHOLE sherd surface, not just the rim arc.

normals      Surface-normal line fit. On a surface of revolution every surface
             normal line intersects the axis, so the axis is the line that is
             closest to being coplanar with all normal lines (Pottmann-style
             line geometry, solved as a 6x6 eigenproblem, IRLS for outliers).
             Needs no rim, so it is the candidate for body sherds.
refine       Profile-consistency refinement. For the right axis, radius is a
             function of height alone, so within a thin height band every vertex
             has nearly the same radius. Nudge (tilt, offset) of a seed axis to
             minimise that within-band spread. Derivative-free pattern search,
             numpy only.

Both return (point_on_axis, unit_dir, info) like fit_axis_rim_arc.
"""
import numpy as np


def vertex_normals(V, T):
    f = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])  # area-weighted
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, T[:, k], f)
    L = np.linalg.norm(N, axis=1)
    ok = L > 1e-12
    N[ok] /= L[ok, None]
    return N, ok


def _basis(d):
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(d, a); e1 /= np.linalg.norm(e1)
    return e1, np.cross(d, e1)


def fit_axis_normals(V, T, n_iter=12, ridge=1e-6):
    """Return (p0, d, info). info carries conditioning/residual signals for gating."""
    N, ok = vertex_normals(V, T)
    V, N = V[ok], N[ok]
    c = V.mean(0)
    s = float(np.mean(np.linalg.norm(V - c, axis=1))) + 1e-9
    P = (V - c) / s
    Q = np.cross(P, N)                      # moment of each normal line
    A_rows = np.hstack([Q, N])              # residual = A_rows @ [d, m]
    w = np.ones(len(P))
    for it in range(n_iter):
        A = (A_rows * w[:, None]).T @ A_rows
        Add, Adm, Amm = A[:3, :3], A[:3, 3:], A[3:, 3:]
        Amm_r = Amm + ridge * np.trace(Amm) / 3 * np.eye(3)
        S = Add - Adm @ np.linalg.solve(Amm_r, Adm.T)        # Schur complement
        S = 0.5 * (S + S.T)
        ev, evec = np.linalg.eigh(S)
        d = evec[:, 0]
        m = -np.linalg.solve(Amm_r, Adm.T @ d)
        m = m - (d @ m) * d                                   # enforce d.m = 0
        res = A_rows @ np.concatenate([d, m])
        sig = 1.4826 * np.median(np.abs(res)) + 1e-9
        w = 1.0 / (1.0 + (res / (2.5 * sig)) ** 2)            # Cauchy IRLS
    p0 = c + s * np.cross(d, m)
    cond = float(ev[0] / (ev[1] + 1e-15))                     # ->0: axis well pinned; ->1: ambiguous
    info = dict(method="normals", n_used=int(len(P)),
                resid_mm=round(float(sig * s), 4), cond=round(cond, 4),
                inlier_frac=round(float((np.abs(res) < 3 * sig).mean()), 3))
    return p0, d / np.linalg.norm(d), info


def consistency_cost(V, p0, d, band_pts=60):
    """RMS within-band spread of radius (mm), equal-count height bands."""
    W = V - p0
    h = W @ d
    r = np.linalg.norm(W - np.outer(h, d), axis=1)
    order = np.argsort(h)
    r = r[order]
    nb = len(r) // band_pts
    if nb < 4:
        return np.inf
    B = r[:nb * band_pts].reshape(nb, band_pts)
    dev = B - np.median(B, axis=1, keepdims=True)
    return float(np.sqrt(np.mean(dev ** 2)))


def refine_consistency(V, p0, d, band_pts=60, tilt0=0.03, off0=1.5, n_round=60):
    """Pattern search over (2 tilt angles, 2 lateral offsets). Returns (p0, d, info)."""
    d = d / np.linalg.norm(d)
    e1, e2 = _basis(d)
    x = np.zeros(4)
    steps = np.array([tilt0, tilt0, off0, off0])

    def build(x):
        dd = d + x[0] * e1 + x[1] * e2
        dd /= np.linalg.norm(dd)
        return p0 + x[2] * e1 + x[3] * e2, dd

    best = consistency_cost(V, *build(x))
    start = best
    for _ in range(n_round):
        improved = False
        for i in range(4):
            for sgn in (+1, -1):
                y = x.copy(); y[i] += sgn * steps[i]
                cst = consistency_cost(V, *build(y))
                if cst < best - 1e-9:
                    x, best, improved = y, cst, True
        if not improved:
            steps *= 0.5
            if steps[0] < 1e-5:
                break
    p1, d1 = build(x)
    return p1, d1, dict(refined=True, spread_before_mm=round(start, 4),
                        spread_after_mm=round(best, 4),
                        shift_tilt_deg=round(float(np.degrees(np.hypot(x[0], x[1]))), 3),
                        shift_offset_mm=round(float(np.hypot(x[2], x[3])), 3))


def axis_uncertainty(V, p0, d, band_pts=60, n_mc=40, seed=0):
    """Indicative 1-sigma radial uncertainty (mm) of the drawn profile caused by axis
    error. Takes the curvature (Hessian) of the consistency cost around the fitted
    axis: a flat direction (e.g. a sphere cap, or a thin horizontal strip) means the
    axis is not identifiable and the uncertainty blows up. Covariance = 2*c0^2/N_eff
    * H^-1 with N_eff = number of height bands (neighbouring vertices are correlated,
    so this is deliberately conservative). Parameters match refine_consistency."""
    d = d / np.linalg.norm(d)
    e1, e2 = _basis(d)
    steps = np.array([0.01, 0.01, 0.5, 0.5])

    def f(x):
        dd = d + x[0] * e1 + x[1] * e2; dd /= np.linalg.norm(dd)
        return consistency_cost(V, p0 + x[2] * e1 + x[3] * e2, dd, band_pts) ** 2

    f0 = f(np.zeros(4))
    H = np.zeros((4, 4))
    for i in range(4):
        ei = np.zeros(4); ei[i] = steps[i]
        H[i, i] = (f(ei) - 2 * f0 + f(-ei)) / steps[i] ** 2
        for j in range(i + 1, 4):
            ej = np.zeros(4); ej[j] = steps[j]
            H[i, j] = H[j, i] = (f(ei + ej) - f(ei - ej) - f(-ei + ej) + f(-ei - ej)) / (4 * steps[i] * steps[j])
    n_eff = max(len(V) // band_pts, 4)
    ev, U = np.linalg.eigh(0.5 * (H + H.T))
    if ev.min() <= 1e-12 * max(ev.max(), 1e-30):
        return 99.0                                  # not identifiable
    cov = 2 * f0 / n_eff * (U @ np.diag(1 / ev) @ U.T)
    cov = 0.5 * (cov + cov.T)
    rng = np.random.default_rng(seed)
    L = np.linalg.cholesky(cov + 1e-18 * np.eye(4))
    r0 = np.linalg.norm((V - p0) - np.outer((V - p0) @ d, d), axis=1)
    acc = []
    for _ in range(n_mc):
        x = L @ rng.standard_normal(4)
        dd = d + x[0] * e1 + x[1] * e2; dd /= np.linalg.norm(dd)
        pp = p0 + x[2] * e1 + x[3] * e2
        W = V - pp
        r = np.linalg.norm(W - np.outer(W @ dd, dd), axis=1)
        acc.append(np.mean((r - r0) ** 2))
    return float(np.sqrt(np.mean(acc)))


def fit_axis_multistart(V, T, extra_seeds=(), n_jitter=4, jitter_deg=8.0, tol=1.15, seed=0):
    """Option 1 + 2 combined, with an ambiguity check.

    Seeds: surface-normal fit, PCA, any caller seeds, plus random tilts of the normals
    seed. Each is refined by profile consistency. The best-cost axis wins. Every
    refined axis whose cost is within `tol` x best is 'near-optimal'; if those
    disagree (a sphere cap, a cone, a too-small fragment: a continuum of equally good
    axes) the axis is ambiguous and the caller should flag the sherd for review.
    Returns (p0, d, info)."""
    rng = np.random.default_rng(seed)
    pn, dn, inf_n = fit_axis_normals(V, T)
    c = V.mean(0)
    cov = np.cov((V - c).T)
    ev, evec = np.linalg.eigh(cov)
    seeds = [(pn, dn), (c, evec[:, -1])] + list(extra_seeds)
    e1, e2 = _basis(dn)
    for _ in range(n_jitter):
        a = np.radians(jitter_deg) * rng.uniform(0.4, 1.0)
        ph = rng.uniform(0, 2 * np.pi)
        dj = dn + np.tan(a) * (np.cos(ph) * e1 + np.sin(ph) * e2)
        seeds.append((pn, dj / np.linalg.norm(dj)))
    sols = []
    for p, d in seeds:
        p1, d1, j = refine_consistency(V, p, d)
        sols.append((j["spread_after_mm"], p1, d1))
    sols.sort(key=lambda s: s[0])
    best_cost, pb, db = sols[0]
    near = [s for s in sols if s[0] <= best_cost * tol]
    r_best = _radii(V, pb, db)
    amb_deg = max(float(np.degrees(np.arccos(np.clip(abs(db @ s[2]), 0, 1)))) for s in near)
    amb_mm = max(float(np.sqrt(np.mean((_radii(V, s[1], s[2]) - r_best) ** 2))) for s in near)
    info = dict(method="normals_multistart", cond=inf_n["cond"], spread_mm=round(best_cost, 4),
                n_seeds=len(sols), n_near_optimal=len(near),
                ambiguity_deg=round(amb_deg, 2), ambiguity_mm=round(amb_mm, 3))
    return pb, db, info


def _radii(V, p, d):
    W = V - p
    return np.linalg.norm(W - np.outer(W @ d, d), axis=1)
