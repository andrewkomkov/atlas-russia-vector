"""The site's inverse projection (site/public/proj.js) must match pipeline/geo.py
(specs/003-cleanup, FR-010). Needs node on PATH."""
import json, os, shutil, subprocess, sys, unittest
import numpy as np
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'pipeline'))
import geo

P = json.load(open(os.path.join(ROOT, 'pipeline', 'ref.json')))['P']
HARNESS = """
const { P, pts } = JSON.parse(process.argv[2]);
console.log(JSON.stringify(pts.map(([x, y]) => invProj(P, x, y))));
"""


def js_inv(pts):
    """Run invProj from proj.js in node on [[x, y], ...] -> [[lon, lat], ...]."""
    src = open(os.path.join(ROOT, 'site', 'public', 'proj.js'), encoding='utf-8').read()
    out = subprocess.run(['node', '--input-type=module', '-', json.dumps({'P': P, 'pts': pts})],
                         input=src + HARNESS, capture_output=True, text=True, check=True)
    return np.array(json.loads(out.stdout))


class Projection(unittest.TestCase):
    def test_round_trip(self):
        lon, lat = np.array([20.5, 37.6, 104.3, 131.9, 190.2]), np.array([54.7, 55.8, 52.3, 43.1, 66.2])
        x, y = geo.fwd(P, lon, lat)
        lon2, lat2 = geo.inv(P, x, y)
        np.testing.assert_allclose(lon2, lon, atol=1e-9)
        np.testing.assert_allclose(lat2, lat, atol=1e-9)

    @unittest.skipUnless(shutil.which('node'), 'node is not installed')
    def test_js_matches_python(self):
        rng = np.random.default_rng(0)
        pts = rng.uniform(0, 2700, (200, 2))
        lon, lat = geo.inv(P, pts[:, 0], pts[:, 1])
        got = js_inv(pts.tolist())
        np.testing.assert_allclose(got[:, 0], lon, atol=1e-9)
        np.testing.assert_allclose(got[:, 1], lat, atol=1e-9)


if __name__ == '__main__':
    unittest.main()
