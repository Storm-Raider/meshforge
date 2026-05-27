"""Tests for RefinementZone and MeshParams subprocess serialization."""
from __future__ import annotations
import pytest
from dataclasses import asdict

from meshforge.models.mesh_params import MeshParams, RefinementZone


class TestRefinementZone:
    def _make_zone(self, entity_type="surface", entity_index=1):
        return RefinementZone(
            entity_type=entity_type,
            entity_index=entity_index,
            size_factor=0.3,
            influence_radius=5.0,
        )

    def test_surface_zone_fields(self):
        z = self._make_zone("surface", 2)
        assert z.entity_type == "surface"
        assert z.entity_index == 2
        assert z.size_factor == pytest.approx(0.3)
        assert z.influence_radius == pytest.approx(5.0)

    def test_curve_zone_fields(self):
        z = self._make_zone("curve", 7)
        assert z.entity_type == "curve"
        assert z.entity_index == 7

    def test_zone_index_zero_is_invalid_sentinel(self):
        z = RefinementZone(entity_type="surface", entity_index=0, size_factor=0.5, influence_radius=3.0)
        assert z.entity_index == 0  # dataclass stores it; engine skips it (index < 1)

    def test_zone_index_beyond_range_stored(self):
        z = RefinementZone(entity_type="surface", entity_index=999, size_factor=0.5, influence_radius=3.0)
        assert z.entity_index == 999  # engine skips it; no validation at construction


class TestMeshParamsSubprocessSerialization:
    """Verify the asdict → RefinementZone(**z) round-trip used by _mesh_subprocess.py."""

    def test_empty_zones_round_trip(self):
        params = MeshParams()
        params_dict = asdict(params)
        zones = [RefinementZone(**z) for z in params_dict.get("refinement_zones", [])]
        assert zones == []

    def test_single_zone_round_trip(self):
        zone = RefinementZone(entity_type="surface", entity_index=3, size_factor=0.2, influence_radius=10.0)
        params = MeshParams(refinement_zones=[zone])
        params_dict = asdict(params)

        reconstructed_zones = [RefinementZone(**z) for z in params_dict["refinement_zones"]]
        assert len(reconstructed_zones) == 1
        z = reconstructed_zones[0]
        assert z.entity_type == "surface"
        assert z.entity_index == 3
        assert z.size_factor == pytest.approx(0.2)
        assert z.influence_radius == pytest.approx(10.0)

    def test_multiple_zones_round_trip(self):
        zones = [
            RefinementZone("surface", 1, 0.1, 5.0),
            RefinementZone("curve", 4, 0.5, 2.0),
            RefinementZone("surface", 2, 0.3, 8.0),
        ]
        params = MeshParams(refinement_zones=zones)
        params_dict = asdict(params)

        reconstructed = [RefinementZone(**z) for z in params_dict["refinement_zones"]]
        assert len(reconstructed) == 3
        assert reconstructed[0].entity_type == "surface"
        assert reconstructed[1].entity_type == "curve"
        assert reconstructed[2].entity_index == 2

    def test_reconstructed_params_is_valid_meshparams(self):
        zone = RefinementZone("curve", 2, 0.4, 3.0)
        params = MeshParams(size_factor=1.5, refinement_zones=[zone])
        params_dict = asdict(params)

        params_data = dict(params_dict)
        params_data["refinement_zones"] = [
            RefinementZone(**z) for z in params_data.get("refinement_zones", [])
        ]
        rebuilt = MeshParams(**params_data)

        assert rebuilt.size_factor == pytest.approx(1.5)
        assert len(rebuilt.refinement_zones) == 1
        assert isinstance(rebuilt.refinement_zones[0], RefinementZone)
        assert rebuilt.refinement_zones[0].entity_type == "curve"
