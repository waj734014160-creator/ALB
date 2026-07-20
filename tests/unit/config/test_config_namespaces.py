"""Tests for domainized configuration imports and migration."""

from ALB.config import ALBConfig, HydConfig, PIDConfig, ThermalConfig
from ALB.config.control import PIDConfig as DomainPIDConfig
from ALB.config.film import HydConfig as DomainHydConfig
from ALB.config.migration import migrate_legacy_config
from ALB.config.system import ALBConfig as DomainALBConfig
from ALB.config.thermal import ThermalConfig as DomainThermalConfig


def test_domain_modules_own_the_public_import_paths():
    assert PIDConfig is DomainPIDConfig
    assert HydConfig is DomainHydConfig
    assert ALBConfig is DomainALBConfig
    assert ThermalConfig is DomainThermalConfig


def test_flat_legacy_payload_is_grouped_without_mutation():
    source = {"r": 0.04, "kp": 0.3, "node_link": 2, "custom": "keep"}
    migrated, report = migrate_legacy_config(source)

    assert source == {"r": 0.04, "kp": 0.3, "node_link": 2, "custom": "keep"}
    assert migrated == {
        "schema_version": "0.2.0",
        "film": {"r": 0.04},
        "control": {"kp": 0.3},
        "system": {"node_link": 2},
        "legacy_unmapped": {"custom": "keep"},
    }
    assert report.unmapped_keys == ("custom",)
