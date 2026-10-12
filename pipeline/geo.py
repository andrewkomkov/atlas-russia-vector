"""Shared georeferencing helpers: equidistant conic model + Russia outline."""
import json, numpy as np

def load_russia(path):
    """Russia rings in lon/lat, lon unwrapped to (0..360) on the far east."""
    fc = json.load(open(path))
    rings = []
    for f in fc['features']:
        if f['properties'].get('ADM0_A3') == 'RUS':
            g = f['geometry']
            polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
            for p in polys:
                r = np.array(p[0], float)
                r[:, 0] = np.where(r[:, 0] < 0, r[:, 0] + 360, r[:, 0])
                rings.append(r)
    return rings

def fwd(P, lon, lat):
    """P = [n, G, lon0, k, tx, ty, rot] -> pixel x,y (y down)."""
    n, G, lon0, k, tx, ty, rot = P
    rho = G - np.radians(lat)
    th = n * np.radians(lon - lon0)
    x, y = rho * np.sin(th), -rho * np.cos(th)
    c, s = np.cos(rot), np.sin(rot)
    return tx + k * (c * x - s * y), ty - k * (s * x + c * y)

def inv(P, X, Y):
    n, G, lon0, k, tx, ty, rot = P
    u, v = (X - tx) / k, -(Y - ty) / k
    c, s = np.cos(rot), np.sin(rot)
    x, y = c * u + s * v, -s * u + c * v
    rho = np.hypot(x, y)
    th = np.arctan2(x, -y)
    return lon0 + np.degrees(th / n), np.degrees(G - rho)

def conic(phi1, phi2):
    p1, p2 = np.radians(phi1), np.radians(phi2)
    n = (np.cos(p1) - np.cos(p2)) / (p2 - p1)
    return n, np.cos(p1) / n + p1
