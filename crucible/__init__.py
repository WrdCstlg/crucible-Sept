"""
Crucible: adversarial verification for AI-generated code.

Untrusted code runs in `crucible.sandbox` (Docker by default; a bare subprocess only by explicit, labelled opt-in).
AI-written test suites decide nothing until `crucible.mutation.MutationSlaughterGate` admits them on three axes:
code mutants of a trusted reference, output-contract probes, and input-domain probes.
`crucible.contract` is a code-quality lint (entrypoint and blocked imports), NOT a security boundary.
"""
from crucible.contract import audit_contract, audit_source, BLOCKED_MODULES
from crucible.mutation import (
    MutationSlaughterGate,
    MutationSlaughterResult,
    generate_mutants,
    generate_output_probes,
    generate_input_probes,
    MutantRecord,
    RelationalMutator,
    BoundaryConstantMutator,
    BoundaryMinusMutator,
    ArithmeticMutator,
    AugAssignMutator,
    LogicalMutator,
    ConditionNegationMutator,
    BooleanFlipMutator,
    StatementDeletionMutator,
    ReturnNullifierMutator,
)
from crucible.invariants import MetamorphicInvariantChecker, InvariantCheckResult
from crucible.sandbox import (
    Sandbox,
    SandboxUnavailable,
    default_sandbox,
    docker_available,
    scrubbed_env,
    deterministic_env,
    run_python,
    sanitize_paths,
    create_locked_down_agent_config,
)

__version__ = "3.0.0"
__all__ = [
    "audit_contract",
    "audit_source",
    "BLOCKED_MODULES",
    "MutationSlaughterGate",
    "MutationSlaughterResult",
    "generate_mutants",
    "generate_output_probes",
    "generate_input_probes",
    "MutantRecord",
    "RelationalMutator",
    "BoundaryConstantMutator",
    "BoundaryMinusMutator",
    "ArithmeticMutator",
    "AugAssignMutator",
    "LogicalMutator",
    "ConditionNegationMutator",
    "BooleanFlipMutator",
    "StatementDeletionMutator",
    "ReturnNullifierMutator",
    "MetamorphicInvariantChecker",
    "InvariantCheckResult",
    "Sandbox",
    "SandboxUnavailable",
    "default_sandbox",
    "docker_available",
    "scrubbed_env",
    "deterministic_env",
    "run_python",
    "sanitize_paths",
    "create_locked_down_agent_config",
]
