from __future__ import annotations
import numpy as np

from meshforge.models.mesh_data import MeshData

PASS_THRESHOLD = 0.3
WARN_THRESHOLD = 0.1

# VTK type codes
_VTK_C3D4  = 10   # 4-node linear tet (bulk element in BL meshes)
_VTK_C3D10 = 24   # 10-node quadratic tet
_VTK_C3D8  = 12   # 8-node linear hex
_VTK_C3D6  = 13   # 6-node linear wedge/prism (BL layer element)

_VTK_TET_TYPES = (_VTK_C3D4, _VTK_C3D10)

# For each of the 8 hex corners (VTK type-12 ordering), the indices of the 3
# adjacent nodes that produce a positive Jacobian on a valid (non-inverted) hex.
# Derived so that det([v_a1-v_c, v_a2-v_c, v_a3-v_c]) = +1 on a unit cube.
_HEX_CORNER_ADJ = np.array([
    [1, 3, 4],  # corner 0
    [2, 0, 5],  # corner 1
    [3, 1, 6],  # corner 2
    [0, 2, 7],  # corner 3
    [7, 5, 0],  # corner 4
    [4, 6, 1],  # corner 5
    [5, 7, 2],  # corner 6
    [6, 4, 3],  # corner 7
], dtype=np.int64)


class QualityEngine:
    """Computes scaled Jacobian quality scalars for tet (C3D10) and hex (C3D8) meshes.

    No Qt imports. Returns a float32 array of per-element scaled Jacobians.
    Range: 1.0 = perfect, 0.0 = degenerate, negative = inverted.
    Thresholds: pass > 0.3, warn 0.1–0.3, fail < 0.1.
    """

    def compute(self, mesh: MeshData) -> np.ndarray:
        """Return float32 array of shape (E,) with one Jacobian value per element.

        Prism elements (C3D6 from BL layers) are assigned quality=1.0 —
        they are structured by construction and excluded from histogram stats.
        """
        unique_types = np.unique(mesh.element_types)
        if len(unique_types) == 1 and unique_types[0] == _VTK_C3D8:
            return self._compute_hex(mesh)

        # Pure or mixed tet mesh (C3D4, C3D10, C3D6 prisms from BL)
        scalars = np.ones(len(mesh.element_types), dtype=np.float32)
        tet_mask = np.isin(mesh.element_types, list(_VTK_TET_TYPES))
        if np.any(tet_mask):
            scalars[tet_mask] = self._compute_tet_corners(
                mesh.nodes, mesh.connectivity[tet_mask, :4]
            )
        return scalars

    def _compute_tet_corners(self, nodes: np.ndarray, conn4: np.ndarray) -> np.ndarray:
        """Scaled Jacobian for tets given (E,4) corner-only connectivity."""
        v0 = nodes[conn4[:, 0]]
        v1 = nodes[conn4[:, 1]]
        v2 = nodes[conn4[:, 2]]
        v3 = nodes[conn4[:, 3]]

        e1 = v1 - v0
        e2 = v2 - v0
        e3 = v3 - v0

        # Scalar triple product — avoids BLAS/LAPACK entirely
        cross_e2_e3 = np.cross(e2, e3)
        det_J = np.einsum("ei,ei->e", e1, cross_e2_e3)

        n1 = np.sqrt(np.einsum("ei,ei->e", e1, e1))
        n2 = np.sqrt(np.einsum("ei,ei->e", e2, e2))
        n3 = np.sqrt(np.einsum("ei,ei->e", e3, e3))
        denom = n1 * n2 * n3
        denom = np.where(denom < 1e-12, 1e-12, denom)

        return (det_J / denom).astype(np.float32)

    def _compute_tet(self, mesh: MeshData) -> np.ndarray:
        """Scaled Jacobian for C3D10 tets using the first 4 corner nodes."""
        return self._compute_tet_corners(mesh.nodes, mesh.connectivity[:, :4])

    def _compute_hex(self, mesh: MeshData) -> np.ndarray:
        """Scaled Jacobian for C3D8 hexes: min over all 8 corners."""
        nodes = mesh.nodes       # (N, 3)
        conn = mesh.connectivity # (E, 8)
        verts = nodes[conn]      # (E, 8, 3) — all corner coords

        quality = np.full(len(conn), np.inf, dtype=np.float64)

        for corner in range(8):
            a1, a2, a3 = _HEX_CORNER_ADJ[corner]
            vc = verts[:, corner, :]  # (E, 3)
            e1 = verts[:, a1, :] - vc
            e2 = verts[:, a2, :] - vc
            e3 = verts[:, a3, :] - vc

            cross = np.cross(e2, e3)
            det = np.einsum("ei,ei->e", e1, cross)

            n1 = np.sqrt(np.einsum("ei,ei->e", e1, e1))
            n2 = np.sqrt(np.einsum("ei,ei->e", e2, e2))
            n3 = np.sqrt(np.einsum("ei,ei->e", e3, e3))
            denom = n1 * n2 * n3
            denom = np.where(denom < 1e-12, 1e-12, denom)

            quality = np.minimum(quality, det / denom)

        return quality.astype(np.float32)

    def summary(self, scalars: np.ndarray) -> dict:
        """Return quality summary dict for display in the quality panel."""
        n = len(scalars)
        if n == 0:
            return {"element_count": 0, "pass": 0, "warn": 0, "fail": 0,
                    "min": 0.0, "mean": 0.0, "max": 0.0, "pass_pct": 0.0,
                    "scalars": scalars}
        n_pass = int(np.sum(scalars > PASS_THRESHOLD))
        n_warn = int(np.sum((scalars >= WARN_THRESHOLD) & (scalars <= PASS_THRESHOLD)))
        n_fail = int(np.sum(scalars < WARN_THRESHOLD))
        return {
            "element_count": n,
            "pass": n_pass,
            "warn": n_warn,
            "fail": n_fail,
            "min": float(scalars.min()),
            "mean": float(scalars.mean()),
            "max": float(scalars.max()),
            "pass_pct": 100.0 * n_pass / n,
            "scalars": scalars,
        }
