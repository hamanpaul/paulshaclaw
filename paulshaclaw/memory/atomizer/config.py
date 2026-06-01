"""Atomizer configuration loader with deterministic hashing."""
import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

# Default config directory is package location
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent

# Supported schema version
_SUPPORTED_SCHEMA = "1"

# Sentinel for default override path resolution
_DEFAULT_SENTINEL = object()


class AtomizerConfigError(Exception):
    """Raised when atomizer configuration is invalid or unsupported."""
    pass


@dataclass(frozen=True)
class AtomizerConfig:
    """Atomizer configuration."""
    schema_version: str
    boundary_patterns: tuple[str, ...]
    max_fragment_chars: int
    artifact_kind_map: Mapping[str, str]
    phase_map: Mapping[str, str]
    default_artifact_kind: str = "report"
    default_phase: str = "review"


def _read_mapping(path: Path) -> Mapping[str, Any]:
    """Read YAML or JSON config file and return root mapping.
    
    Args:
        path: Path to config file
        
    Returns:
        Mapping from config file root
        
    Raises:
        AtomizerConfigError: If file cannot be read or root is not a mapping
    """
    try:
        text = path.read_text(encoding='utf-8')
    except Exception as e:
        raise AtomizerConfigError(f"Cannot read config file {path}: {e}") from e
    
    # Try YAML first if available, fall back to JSON
    try:
        import yaml
        try:
            data = yaml.safe_load(text)
        except Exception as e:
            raise AtomizerConfigError(f"Cannot parse YAML from {path}: {e}") from e
    except ImportError:
        try:
            data = json.loads(text)
        except Exception as e:
            raise AtomizerConfigError(f"Cannot parse JSON from {path}: {e}") from e
    
    if not isinstance(data, Mapping):
        raise AtomizerConfigError(f"Config file {path} root must be a mapping, got {type(data).__name__}")
    
    return data


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Deep merge override into base, preserving base defaults.
    
    Args:
        base: Base dictionary (will be copied, not modified)
        override: Override mapping to merge in
        
    Returns:
        New merged dictionary
    """
    result = copy.deepcopy(base)
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, Mapping):
            # Recursively merge nested dicts
            result[key] = _deep_merge(result[key], value)
        else:
            # Override scalar or new key
            result[key] = value
    
    return result


def _resolve_override(override_path):
    """Resolve override path from parameter.
    
    Args:
        override_path: None (disabled), _DEFAULT_SENTINEL (use default), or explicit path
        
    Returns:
        Resolved Path or None if disabled
    """
    if override_path is None:
        return None
    elif override_path is _DEFAULT_SENTINEL:
        return Path.home() / ".config" / "paulshaclaw" / "atomizer.override.yaml"
    else:
        return Path(override_path)


def load_config(
    default_dir: str | Path | None = None,
    override_path: str | Path | None | object = _DEFAULT_SENTINEL
) -> tuple[AtomizerConfig, str]:
    """Load atomizer configuration with optional override and compute hash.
    
    Args:
        default_dir: Directory containing atomizer.yaml (default: package dir)
        override_path: Override config path or None to disable or _DEFAULT_SENTINEL for default
        
    Returns:
        Tuple of (AtomizerConfig, hex hash string)
        
    Raises:
        AtomizerConfigError: If config is invalid or schema unsupported
    """
    # Resolve default config directory
    if default_dir is None:
        config_dir = DEFAULT_CONFIG_DIR
    else:
        config_dir = Path(default_dir)
    
    # Load default config
    default_config_path = config_dir / "atomizer.yaml"
    if not default_config_path.exists():
        raise AtomizerConfigError(f"Default config not found: {default_config_path}")
    
    config_data = dict(_read_mapping(default_config_path))
    
    # Merge override if path resolves and exists
    resolved_override = _resolve_override(override_path)
    if resolved_override is not None and resolved_override.exists():
        override_data = _read_mapping(resolved_override)
        config_data = _deep_merge(config_data, override_data)
    
    # Validate schema version
    schema_version = str(config_data.get("schema_version", ""))
    if schema_version != _SUPPORTED_SCHEMA:
        raise AtomizerConfigError(
            f"Unsupported schema version: {schema_version}. "
            f"Expected: {_SUPPORTED_SCHEMA}"
        )
    
    # Extract split configuration
    split_config = config_data.get("split", {})
    if not isinstance(split_config, Mapping):
        raise AtomizerConfigError(
            f"split must be a mapping, got {type(split_config).__name__}"
        )

    raw_patterns = split_config.get("boundary_patterns", [])
    if isinstance(raw_patterns, str) or not isinstance(raw_patterns, list):
        raise AtomizerConfigError(
            f"boundary_patterns must be list, got {type(raw_patterns).__name__}"
        )
    if not all(isinstance(pattern, str) for pattern in raw_patterns):
        raise AtomizerConfigError("boundary_patterns entries must be strings")
    boundary_patterns = tuple(raw_patterns)

    raw_max_fragment_chars = split_config.get("max_fragment_chars", 8000)
    if isinstance(raw_max_fragment_chars, bool):
        raise AtomizerConfigError("max_fragment_chars must be int, got bool")
    max_fragment_chars = int(raw_max_fragment_chars)
    if max_fragment_chars <= 0:
        raise AtomizerConfigError(
            f"max_fragment_chars must be positive, got {max_fragment_chars}"
        )
    
    # Extract maps
    artifact_kind_map = MappingProxyType(dict(config_data.get("artifact_kind_map", {})))
    phase_map = MappingProxyType(dict(config_data.get("phase_map", {})))
    
    # Extract defaults
    default_artifact_kind = config_data.get("default_artifact_kind", "report")
    default_phase = config_data.get("default_phase", "review")
    
    # Build config object
    cfg = AtomizerConfig(
        schema_version=schema_version,
        boundary_patterns=boundary_patterns,
        max_fragment_chars=max_fragment_chars,
        artifact_kind_map=artifact_kind_map,
        phase_map=phase_map,
        default_artifact_kind=default_artifact_kind,
        default_phase=default_phase,
    )
    
    # Compute deterministic hash of effective config
    # Use canonical JSON representation
    canonical_json = json.dumps(config_data, sort_keys=True, separators=(",", ":"))
    config_hash = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
    
    return cfg, config_hash
