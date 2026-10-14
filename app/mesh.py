# CAD MODEL MASS PROPERTIES

import struct

import numpy as np

STL_HEADER_BYTES = 80
STL_TRIANGLE_BYTES = 50  # normal (3 float32) + 3 vertices (9 float32) + attribute (uint16)


class MeshError(ValueError):
    """Raised when an uploaded model cannot be read or does not describe a closed solid."""


def parse_stl(data: bytes) -> np.ndarray:
    """
    Parse a binary or ASCII STL file into an array of triangles with shape (n, 3, 3).

    Binary STL files may also begin with the word `solid`, so a file is treated as binary when its
    size matches the triangle count in its header, and as ASCII otherwise.
    """
    if len(data) >= STL_HEADER_BYTES + 4:
        (count,) = struct.unpack_from('<I', data, STL_HEADER_BYTES)
        if len(data) == STL_HEADER_BYTES + 4 + count * STL_TRIANGLE_BYTES:
            return _parse_binary_stl(data, count)
    return _parse_ascii_stl(data)


def _parse_binary_stl(data: bytes, count: int) -> np.ndarray:
    record = np.dtype([('normal', '<f4', 3), ('vertices', '<f4', (3, 3)), ('attribute', '<u2')])
    triangles = np.frombuffer(data, dtype=record, count=count, offset=STL_HEADER_BYTES + 4)
    return triangles['vertices'].astype(np.float64)


def _parse_ascii_stl(data: bytes) -> np.ndarray:
    try:
        text = data.decode('ascii')
    except UnicodeDecodeError:
        raise MeshError('File is neither a valid binary STL nor an ASCII STL.')
    if not text.lstrip().lower().startswith('solid'):
        raise MeshError('File is neither a valid binary STL nor an ASCII STL.')
    vertices = []
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0].lower() == 'vertex':
            try:
                if len(parts) != 4:
                    raise ValueError
                vertices.append([float(v) for v in parts[1:]])
            except ValueError:
                raise MeshError(f'Invalid vertex line in ASCII STL: {line.strip()!r}')
    if len(vertices) % 3:
        raise MeshError('ASCII STL has a facet without exactly three vertices.')
    return np.array(vertices, dtype=np.float64).reshape(-1, 3, 3)


def check_closed(triangles: np.ndarray):
    """
    Require the mesh to be a closed, consistently oriented surface: every directed edge (a, b) of a
    triangle must be matched by exactly one opposite edge (b, a) in a neighbouring triangle.
    Without this, the enclosed volume (and therefore the center of mass) is not well defined.
    """
    _, index = np.unique(triangles.reshape(-1, 3), axis=0, return_inverse=True)
    faces = index.reshape(-1, 3)
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    directed, counts = np.unique(edges, axis=0, return_counts=True)
    if (counts != 1).any():
        raise MeshError('Mesh is not a closed solid: some edges are shared by more than two faces or faces are inconsistently oriented.')
    reversed_edges = {tuple(e) for e in directed[:, ::-1]}
    if len(reversed_edges.intersection(map(tuple, directed))) != len(directed):
        raise MeshError('Mesh is not a closed solid: it has holes or inconsistently oriented faces.')


def mass_properties(triangles: np.ndarray) -> dict:
    """
    Compute the volume and center of mass of the solid enclosed by a closed triangle mesh, assuming
    uniform density.

    Each triangle and a reference point form a tetrahedron whose signed volume is
    dot(a, cross(b, c)) / 6 (with a, b, c relative to the reference point). The signed volumes sum
    to the enclosed volume, and the volume-weighted tetrahedron centroids average to the center of
    mass. Using the mesh's mean vertex as the reference point limits round-off for models far from
    the origin. An inside-out mesh gives a negative volume but the same center of mass.
    """
    if len(triangles) < 4:
        raise MeshError('Mesh needs at least 4 triangles to enclose a volume.')
    if not np.isfinite(triangles).all():
        raise MeshError('Mesh contains non-finite coordinates.')
    check_closed(triangles)

    reference = triangles.reshape(-1, 3).mean(axis=0)
    a, b, c = (triangles - reference).transpose(1, 0, 2)
    signed_volumes = np.einsum('ij,ij->i', a, np.cross(b, c)) / 6
    volume = signed_volumes.sum()
    extent = np.ptp(triangles.reshape(-1, 3), axis=0).max()
    if abs(volume) <= 1e-12 * extent**3:
        raise MeshError('Mesh encloses no volume.')
    center = reference + (signed_volumes[:, None] * (a + b + c)).sum(axis=0) / (4 * volume)
    return {
        'triangleCount': int(len(triangles)),
        'volume': float(abs(volume)),
        'centerOfMass': {axis: float(v) for axis, v in zip('xyz', center)},
    }
