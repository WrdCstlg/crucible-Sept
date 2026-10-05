"""
Crucible: Adversarial Verification Engine for Autonomous Agent Code.
"""
from crucible.contract import audit_contract, BLOCKED_MODULES
from crucible.mutation import (
    MutationSlaughterGate,
    MutationSlaughterResult,
    generate_mutants,
    MutantRecord,
    RelationalMutator,
    BoundaryConstantMutator,
    ArithmeticMutator,
    BooleanFlipMutator,
    ReturnNullifierMutator,
)
from crucible.invariants import MetamorphicInvariantChecker, InvariantCheckResult
from crucible.sandbox import (
    deterministic_env,
    run_python,
    sanitize_paths,
    create_locked_down_agent_config,
)

__version__ = "2.0.0"
__all__ = [
    "audit_contract",
    "BLOCKED_MODULES",
    "MutationSlaughterGate",
    "MutationSlaughterResult",
    "generate_mutants",
    "MutantRecord",
    "RelationalMutator",
    "BoundaryConstantMutator",
    "ArithmeticMutator",
    "BooleanFlipMutator",
    "ReturnNullifierMutator",
    "MetamorphicInvariantChecker",
    "InvariantCheckResult",
    "deterministic_env",
    "run_python",
    "sanitize_paths",
    "create_locked_down_agent_config",
]
