from __future__ import annotations
import numpy as np

from meshforge.models.mesh_data import MeshData

PASS_THRESHOLD = 0.3
WARN_THRESHOLD = 0.1


class QualityEngine:
    """Computes scaled Jacobian quality scalars for a MeshData C3D10 mesh.

    No Qt imports. Returns a float32 array of per-element scaled Jacobians.

    Formula: det(J) / (||col0|| * ||col1|| * ||col2||)
    where J columns are the three edge vectors from corner node 0.
    A perfect equilateral tet ≈ 0.707. Thresholds: pass > 0.3, warn 0.1–0.3, fail < 0.1.
    """

    def compute(self, mesh: MeshData) -> np.ndarray:
        """Return float32 array of shape (E,) with one Jacobian value per element."""
        nodes = mesh.nodes                  # (N, 3)
        conn = mesh.connectivity[:, :4]    # (E, 4) — first 4 corner nodes of C3D10

        v0 = nodes[conn[:, 0]]  # (E, 3)
        v1 = nodes[conn[:, 1]]
        v2 = nodes[conn[:, 2]]
        v3 = nodes[conn[:, 3]]

        # J columns: three edge vectors from v0
        e1 = v1 - v0
        e2 = v2 - v0
        e3 = v3 - v0
        # Scalar triple product: det = e1 · (e2 × e3) — avoids LAPACK entirely
        cross_e2_e3 = np.cross(e2, e3)                          # (E, 3)
        det_J = np.einsum("ei,ei->e", e1, cross_e2_e3)          # (E,)

        # Column norms via einsum — no BLAS/LAPACK dependency
        n1 = np.sqrt(np.einsum("ei,ei->e", e1, e1))
        n2 = np.sqrt(np.einsum("ei,ei->e", e2, e2))
        n3 = np.sqrt(np.einsum("ei,ei->e", e3, e3))
        denom = n1 * n2 * n3
        denom = np.where(denom < 1e-12, 1e-12, denom)

        return (det_J / denom).astype(np.float32)

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
