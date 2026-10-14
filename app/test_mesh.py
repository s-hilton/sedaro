#!/usr/bin/env python3

"""
NOTE: Tests for CAD model mass properties. Run from `app/` with `python3 -m unittest test_mesh`.
"""

import struct
import unittest

import numpy as np

from mesh import MeshError, mass_properties, parse_stl


def box(lo, hi):
    """Closed, outward-facing triangle mesh of an axis-aligned box."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], dtype=float)
    faces = [(0, 3, 2), (0, 2, 1), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (2, 3, 7), (2, 7, 6), (1, 2, 6), (1, 6, 5), (3, 0, 4), (3, 4, 7)]
    return v[np.array(faces)]


def l_shape():
    """Closed mesh of an L-shaped prism: a 2x1x1 bar with a 1x1x1 cube on top of its x<1 end."""
    # Profile in the xz-plane, counter-clockwise when viewed from +y.
    profile = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
    front = [(x, 0, z) for x, z in profile]
    back = [(x, 1, z) for x, z in profile]
    v = np.array(front + back, dtype=float)
    n = len(profile)
    faces = []
    # Caps: fan triangulation of the (non-convex but star-shaped from vertex 0) profile.
    for i in range(1, n - 1):
        faces.append((0, i, i + 1))              # y=0 cap, normal -y
        faces.append((n, n + i + 1, n + i))      # y=1 cap, normal +y
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, n + i, n + j))
        faces.append((i, n + j, j))
    return v[np.array(faces)]


def to_binary_stl(triangles, header=b'binary'):
    out = header.ljust(80, b' ') + struct.pack('<I', len(triangles))
    for tri in triangles:
        out += struct.pack('<3f', 0, 0, 0) + struct.pack('<9f', *tri.ravel()) + struct.pack('<H', 0)
    return out


def to_ascii_stl(triangles):
    lines = ['solid test']
    for tri in triangles:
        lines += ['  facet normal 0 0 0', '    outer loop']
        lines += [f'      vertex {float(x)!r} {float(y)!r} {float(z)!r}' for x, y, z in tri]
        lines += ['    endloop', '  endfacet']
    lines.append('endsolid test')
    return '\n'.join(lines).encode('ascii')


class MassPropertiesTest(unittest.TestCase):
    def assertVector(self, actual, expected):
        np.testing.assert_allclose([actual[k] for k in 'xyz'], expected, rtol=1e-9, atol=1e-9)

    def test_unit_cube(self):
        props = mass_properties(box((0, 0, 0), (1, 1, 1)))
        self.assertAlmostEqual(props['volume'], 1.0)
        self.assertVector(props['centerOfMass'], [0.5, 0.5, 0.5])
        self.assertEqual(props['triangleCount'], 12)

    def test_offset_box(self):
        props = mass_properties(box((10, -4, 2), (14, -1, 3)))
        self.assertAlmostEqual(props['volume'], 12.0)
        self.assertVector(props['centerOfMass'], [12, -2.5, 2.5])

    def test_solid_center_not_surface_center(self):
        # The L's two unit cubes along the bottom and one on top: the solid's center of mass is the
        # average of the three cube centers. A surface-area or vertex average would differ.
        props = mass_properties(l_shape())
        self.assertAlmostEqual(props['volume'], 3.0)
        self.assertVector(props['centerOfMass'], [(0.5 + 1.5 + 0.5) / 3, 0.5, (0.5 + 0.5 + 1.5) / 3])

    def test_inside_out_mesh_has_same_center(self):
        flipped = box((0, 0, 0), (2, 1, 1))[:, ::-1]
        props = mass_properties(flipped)
        self.assertAlmostEqual(props['volume'], 2.0)
        self.assertVector(props['centerOfMass'], [1, 0.5, 0.5])

    def test_far_from_origin(self):
        props = mass_properties(box((1e6, 1e6, 1e6), (1e6 + 1, 1e6 + 1, 1e6 + 1)))
        self.assertAlmostEqual(props['volume'], 1.0, places=6)
        self.assertVector(props['centerOfMass'], [1e6 + 0.5] * 3)

    def test_open_mesh_rejected(self):
        with self.assertRaisesRegex(MeshError, 'not a closed solid'):
            mass_properties(box((0, 0, 0), (1, 1, 1))[:-1])

    def test_inconsistent_orientation_rejected(self):
        tris = box((0, 0, 0), (1, 1, 1))
        tris[0] = tris[0][::-1]
        with self.assertRaisesRegex(MeshError, 'not a closed solid'):
            mass_properties(tris)

    def test_too_few_triangles_rejected(self):
        with self.assertRaisesRegex(MeshError, 'at least 4'):
            mass_properties(box((0, 0, 0), (1, 1, 1))[:3])


class ParseStlTest(unittest.TestCase):
    def test_binary_and_ascii_agree(self):
        tris = l_shape()
        np.testing.assert_allclose(parse_stl(to_binary_stl(tris)), tris)
        np.testing.assert_allclose(parse_stl(to_ascii_stl(tris)), tris)

    def test_binary_with_solid_header(self):
        # Many exporters write binary STLs whose header starts with "solid".
        tris = box((0, 0, 0), (1, 1, 1))
        np.testing.assert_allclose(parse_stl(to_binary_stl(tris, header=b'solid exported')), tris)

    def test_garbage_rejected(self):
        with self.assertRaises(MeshError):
            parse_stl(b'\x00\xff' * 100)

    def test_bad_vertex_rejected(self):
        with self.assertRaisesRegex(MeshError, 'Invalid vertex'):
            parse_stl(b'solid x\nfacet normal 0 0 0\nouter loop\nvertex 1 2\nendloop\nendfacet\nendsolid x')


if __name__ == '__main__':
    unittest.main()
