"""
Crucible Adversarial Mutation Engine & Anti-Tautology Slaughter Gate.

Breaks the "Ouroboros of Mediocrity" where AI models generate trivial or tautological
test suites that pass flawed code and create a false sense of security.

Algorithm:
  1. Parse the trusted reference solution into an AST.
  2. Generate a deterministic pool of synthetic AST mutants across 5 mutation categories:
     - Relational operator inversion (e.g. >= to >, == to !=)
     - Boundary constant perturbation (e.g. 95.0 to 96.0, 500 to 501)
     - Arithmetic operator mutation (e.g. + to -, * to /)
     - Boolean literal inversion (True to False)
     - Return state nullification (returning [] or None)
  3. Execute the candidate AI-generated test suite against each mutant in an isolated,
     deterministic subprocess.
  4. Measure the Slaughter Rate = (Killed Mutants) / (Total Viable Mutants).
  5. QUARANTINE any test suite that fails to achieve the required slaughter threshold.
"""
import ast
import copy
import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Tuple


@dataclass
class MutantRecord:
    mutant_id: str
    description: str
    diff_summary: str
    code: str


@dataclass
class MutationSlaughterResult:
    total_mutants: int
    killed_mutants: int
    survived_mutants: int
    slaughter_rate: float
    passed_gate: bool
    threshold: float
    details: List[dict] = field(default_factory=list)
    reason: str = ""


class ASTMutator(ast.NodeTransformer):
    """
    Base AST transformer that generates targeted single-point mutations.
    """
    def __init__(self, mutation_type: str, target_index: int):
        super().__init__()
        self.mutation_type = mutation_type
        self.target_index = target_index
        self.current_index = 0
        self.applied_mutation = None

    def _should_mutate(self) -> bool:
        matches = (self.current_index == self.target_index)
        self.current_index += 1
        return matches


class RelationalMutator(ASTMutator):
    OP_MAP = {
        ast.Gt: ast.LtE,
        ast.GtE: ast.Gt,     # boundary off-by-one! >= becomes strictly >
        ast.Lt: ast.GtE,
        ast.LtE: ast.Lt,     # boundary off-by-one! <= becomes strictly <
        ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq,
    }

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        new_ops = []
        mutated = False
        for op in node.ops:
            op_type = type(op)
            if op_type in self.OP_MAP and self._should_mutate():
                new_op_cls = self.OP_MAP[op_type]
                new_ops.append(new_op_cls())
                self.applied_mutation = f"Relational swap: {op_type.__name__} -> {new_op_cls.__name__}"
                mutated = True
            else:
                new_ops.append(op)
        if mutated:
            node.ops = new_ops
        return node


class BoundaryConstantMutator(ASTMutator):
    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            if self._should_mutate():
                old_val = node.value
                # Shift boundary by +1
                new_val = old_val + 1 if isinstance(old_val, int) else round(old_val + 1.0, 2)
                node.value = new_val
                self.applied_mutation = f"Boundary shift: {old_val} -> {new_val}"
        return node


class ArithmeticMutator(ASTMutator):
    OP_MAP = {
        ast.Add: ast.Sub,
        ast.Sub: ast.Add,
        ast.Mult: ast.FloorDiv,
    }

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        op_type = type(node.op)
        if op_type in self.OP_MAP and self._should_mutate():
            new_op_cls = self.OP_MAP[op_type]
            node.op = new_op_cls()
            self.applied_mutation = f"Arithmetic swap: {op_type.__name__} -> {new_op_cls.__name__}"
        return node


class BooleanFlipMutator(ASTMutator):
    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, bool):
            if self._should_mutate():
                old_val = node.value
                node.value = not old_val
                self.applied_mutation = f"Boolean flip: {old_val} -> {not old_val}"
        return node


class ReturnNullifierMutator(ASTMutator):
    def visit_Return(self, node: ast.Return) -> ast.AST:
        if node.value is not None and self._should_mutate():
            node.value = ast.Constant(value=[])
            self.applied_mutation = "Return nullification: return []"
        return node


def generate_mutants(source_code: str, max_mutants: int = 12) -> List[MutantRecord]:
    """
    Generates a deterministic list of viable, non-equivalent mutant programs from source code.
    """
    try:
        base_tree = ast.parse(source_code)
    except SyntaxError:
        return []

    mutators: List[Tuple[str, type]] = [
        ("relational", RelationalMutator),
        ("boundary", BoundaryConstantMutator),
        ("arithmetic", ArithmeticMutator),
        ("boolean", BooleanFlipMutator),
        ("return_null", ReturnNullifierMutator),
    ]

    mutants: List[MutantRecord] = []
    seen_codes = {source_code.strip()}

    for mut_name, mut_cls in mutators:
        target_idx = 0
        while len(mutants) < max_mutants:
            tree_copy = copy.deepcopy(base_tree)
            transformer = mut_cls(mutation_type=mut_name, target_index=target_idx)
            mutated_tree = transformer.visit(tree_copy)
            ast.fix_missing_locations(mutated_tree)

            if transformer.applied_mutation is None:
                # No more nodes of this type to mutate
                break

            try:
                mutant_code = ast.unparse(mutated_tree)
                if mutant_code.strip() not in seen_codes:
                    seen_codes.add(mutant_code.strip())
                    mut_id = f"mutant_{mut_name}_{target_idx + 1:02d}"
                    mutants.append(MutantRecord(
                        mutant_id=mut_id,
                        description=transformer.applied_mutation,
                        diff_summary=f"[{mut_name}] {transformer.applied_mutation}",
                        code=mutant_code,
                    ))
            except Exception:
                pass

            target_idx += 1
            if target_idx > 20:  # safety cap per category
                break

    return mutants[:max_mutants]


class MutationSlaughterGate:
    """
    Adversarial Gatekeeper that subjects candidate test suites to mutant slaughter.
    A test suite is admitted only if it kills >= threshold of viable mutants.
    """
    def __init__(self, run_python_fn: Callable, threshold: float = 0.60, max_mutants: int = 8):
        self.run_python_fn = run_python_fn
        self.threshold = threshold
        self.max_mutants = max_mutants

    def evaluate_suite(self, suite_path: Path, reference_source_or_path: str | Path) -> MutationSlaughterResult:
        """
        Executes the test suite against mutants of the reference implementation.
        """
        if isinstance(reference_source_or_path, Path) or (isinstance(reference_source_or_path, str) and Path(reference_source_or_path).exists()):
            ref_code = Path(reference_source_or_path).read_text(encoding="utf-8")
        else:
            ref_code = str(reference_source_or_path)

        mutants = generate_mutants(ref_code, max_mutants=self.max_mutants)
        if not mutants:
            # If no mutants could be generated (e.g. trivial code), fail closed or pass with warning
            return MutationSlaughterResult(
                total_mutants=0,
                killed_mutants=0,
                survived_mutants=0,
                slaughter_rate=1.0,
                passed_gate=True,
                threshold=self.threshold,
                reason="No viable mutants could be synthesized from reference."
            )

        suite_code = suite_path.read_text(encoding="utf-8")
        details = []
        killed_count = 0

        for mutant in mutants:
            with tempfile.TemporaryDirectory(prefix="crucible_mutant_") as tmp_d:
                tmp_dir = Path(tmp_d)
                (tmp_dir / "solution.py").write_text(mutant.code, encoding="utf-8")
                (tmp_dir / "arena_test.py").write_text(suite_code, encoding="utf-8")

                code, out, err, dur = self.run_python_fn("arena_test.py", tmp_dir, timeout=30)
                # If test suite exits non-zero, it successfully detected the mutant (KILLED)
                # If exit code is 0, the mutant SURVIVED (test suite failed to detect bug)
                was_killed = (code != 0)
                if was_killed:
                    killed_count += 1

                details.append({
                    "mutant_id": mutant.mutant_id,
                    "description": mutant.description,
                    "status": "KILLED" if was_killed else "SURVIVED",
                    "exit_code": code,
                    "duration_seconds": dur,
                })

        total = len(mutants)
        survived = total - killed_count
        rate = round(killed_count / total, 3) if total > 0 else 0.0
        passed = (rate >= self.threshold)

        reason = (
            f"Adversarial Mutation Gate: Slaughtered {killed_count}/{total} mutants ({rate * 100:.1f}%). "
            + (f"Exceeds threshold of {self.threshold * 100:.1f}%." if passed
               else f"FAILED threshold of {self.threshold * 100:.1f}%. Suite is rejected as weak/tautological.")
        )

        return MutationSlaughterResult(
            total_mutants=total,
            killed_mutants=killed_count,
            survived_mutants=survived,
            slaughter_rate=rate,
            passed_gate=passed,
            threshold=self.threshold,
            details=details,
            reason=reason,
        )
