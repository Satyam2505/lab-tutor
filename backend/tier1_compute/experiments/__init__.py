"""Per-experiment plugins. Importing this package registers all of them.

Every module named `expNN.py` is imported at package load so its
`register(...)` call runs. Files beginning with `_` are helpers
(`_template.py`) and are skipped.
"""

from __future__ import annotations

import importlib
import pkgutil

from backend.tier1_compute.experiments.registry import (  # noqa: F401
    DeterministicPlugin,
    ExperimentPlugin,
    ManualNotTranscribedError,
    PendingManualPlugin,
    QualitativeOrderingPlugin,
    UnknownExperimentError,
    all_plugins,
    get_plugin,
    ready_plugins,
    register,
)


def _load_plugins() -> None:
    for module in pkgutil.iter_modules(__path__):
        if module.name.startswith("_") or module.name == "registry":
            continue
        importlib.import_module(f"{__name__}.{module.name}")


_load_plugins()

__all__ = [
    "DeterministicPlugin",
    "ExperimentPlugin",
    "ManualNotTranscribedError",
    "PendingManualPlugin",
    "QualitativeOrderingPlugin",
    "UnknownExperimentError",
    "all_plugins",
    "get_plugin",
    "ready_plugins",
    "register",
]
