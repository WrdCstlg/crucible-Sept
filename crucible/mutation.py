"""
Crucible mutation gate: measures whether an AI-written test suite can tell correct code from broken code.

The failure it refuses: a suite that passes the trusted reference but would also pass plausible bugs
(tautological checks such as `assert isinstance(result, list)`). Such a suite gives false confidence, so it is
quarantined and never allowed to block or promote a candidate.

Algorithm (deterministic for a given reference, suite, corpus and settings):
  1. BASELINE. The suite must pass the unmutated reference. If it doesn't, its kill count is meaningless
     (a suite that crashes "kills" every mutant), so the gate fails closed.
  2. MUTANTS. Single-point AST mutants of the reference, drawn round-robin across 10 operators so no single
     operator dominates: relational, boundary +1, boundary -1, arithmetic, augmented assignment, logical
     and/or, condition negation, boolean flip, statement deletion, return nullification.
  3. EQUIVALENCE FILTER. Each mutant and the reference run on a differential corpus (inputs only, no expected
     values). A mutant whose outputs are identical on every input is excluded as (likely) equivalent: no suite
     could be blamed for missing it. A mutant that cannot even be imported is excluded as stillborn: killing it
     proves nothing. Without a corpus this step is skipped and the report says so.
  4. SLAUGHTER. The suite runs against every viable mutant. Exit 0 = SURVIVED. Otherwise KILLED, classified as
     timeout, assertion or error (crash) so a reader can see how the suite detects bugs.
  5. OUTPUT-CONTRACT PROBES (second, independent axis; needs an entrypoint and a corpus). Code mutants of a small
     function mostly crash or change how MANY results come back, so a suite that only checks `len(result) >= 1`
     can still kill most of them (measured: 67.6% on the mock reference). Output probes leave the logic intact
     and corrupt the RETURN VALUE in plausible ways: drop the first/last row, duplicate a row, return an empty
     result, rename or drop a field, shift a number by one, alter a string, flip a bool. Probes that are
     equivalent on the corpus (e.g. flipping bools in output that has none) or that behave identically to an
     earlier probe are excluded. A suite that never inspects values cannot kill these.
  6. INPUT-DOMAIN PROBES (third axis; same requirements). Mutating the reference cannot produce an implementation
     that ACCEPTS input the reference rejects, because the reference handles such input by rejecting it. Measured: a
     6-case exact suite was admitted on the first two axes yet missed case-insensitive event names, decimal
     timestamps and arrival-order bugs. Input probes keep the reference's logic but feed it a transformed input
     (upper/lower-cased strings, whitespace removed, decimals truncated, first/last item dropped, items reversed,
     sorted or de-duplicated, numbers shifted by one), which simulates a lenient or careless reader. Probes that are
     equivalent on the corpus are excluded, so only probes that change behaviour are counted.
  7. VERDICT. Admit only if code score >= threshold AND viable code mutants >= min_viable AND (when probes ran)
     output score >= output_threshold AND input score >= input_threshold. Zero viable code mutants fails closed:
     nothing was demonstrated.

Limits (stated, not hidden): the gate measures a suite's power to detect *these* fault classes in *this*
reference. It cannot detect a suite and reference that share the same misreading of the spec (correlated error);
only an independent oracle (human acceptance cases, a brute-force reference, spec-derived properties) can.
"""
from __future__ import annotations

import ast
import copy
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence


@dataclass
class MutantRecord:
    mutant_id: str
    operator: str
    description: str
    diff_summary: str
    code: str
    lineno: Optional[int] = None


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
    baseline_passed: Optional[bool] = None
    generated_mutants: int = 0
    equivalent_mutants: int = 0
    stillborn_mutants: int = 0
    equivalence_checked: bool = False
    kills_by_kind: dict = field(default_factory=dict)
    by_operator: dict = field(default_factory=dict)
    code_axis_passed: Optional[bool] = None
    output_probes_checked: bool = False
    output_threshold: Optional[float] = None
    output_total: int = 0
    output_killed: int = 0
    output_rate: Optional[float] = None
    output_axis_passed: Optional[bool] = None
    output_details: List[dict] = field(default_factory=list)
    input_threshold: Optional[float] = None
    input_total: int = 0
    input_killed: int = 0
    input_rate: Optional[float] = None
    input_axis_passed: Optional[bool] = None
    input_details: List[dict] = field(default_factory=list)

    def summary(self) -> dict:
        d = asdict(self)
        d.pop("details")
        d.pop("output_details")
        d.pop("input_details")
        d["survivors"] = [x["description"] for x in self.details if x["status"] == "SURVIVED"]
        d["output_survivors"] = [x["description"] for x in self.output_details if x["status"] == "SURVIVED"]
        d["input_survivors"] = [x["description"] for x in self.input_details if x["status"] == "SURVIVED"]
        return d


# ── Operators ────────────────────────────────────────────────────────────
class ASTMutator(ast.NodeTransformer):
    """Mutates exactly the `target_index`-th eligible node, counting eligible nodes in AST visit order."""
    operator = "base"

    def __init__(self, mutation_type: str = "", target_index: int = 0):
        super().__init__()
        self.mutation_type = mutation_type or self.operator
        self.target_index = target_index
        self.current_index = 0
        self.applied_mutation: Optional[str] = None
        self.lineno: Optional[int] = None

    def _should_mutate(self, node=None) -> bool:
        hit = self.current_index == self.target_index and self.applied_mutation is None
        self.current_index += 1
        if hit and node is not None:
            self.lineno = getattr(node, "lineno", None)
        return hit


class RelationalMutator(ASTMutator):
    operator = "relational"
    OP_MAP = {ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Eq: ast.NotEq,
              ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}

    def visit_Compare(self, node):
        self.generic_visit(node)
        new_ops = []
        for op in node.ops:
            if type(op) in self.OP_MAP and self._should_mutate(node):
                new = self.OP_MAP[type(op)]
                self.applied_mutation = f"Relational swap: {type(op).__name__} -> {new.__name__}"
                new_ops.append(new())
            else:
                new_ops.append(op)
        node.ops = new_ops
        return node


class _ConstantShift(ASTMutator):
    delta = 1

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool) and self._should_mutate(node):
            old = node.value
            node.value = old + self.delta if isinstance(old, int) else round(old + self.delta, 6)
            self.applied_mutation = f"Boundary shift: {old} -> {node.value}"
        return node


class BoundaryConstantMutator(_ConstantShift):
    operator = "boundary_plus"
    delta = 1


class BoundaryMinusMutator(_ConstantShift):
    operator = "boundary_minus"
    delta = -1


class ArithmeticMutator(ASTMutator):
    operator = "arithmetic"
    OP_MAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult,
              ast.Div: ast.Mult, ast.Mod: ast.FloorDiv}

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if type(node.op) in self.OP_MAP and self._should_mutate(node):
            new = self.OP_MAP[type(node.op)]
            self.applied_mutation = f"Arithmetic swap: {type(node.op).__name__} -> {new.__name__}"
            node.op = new()
        return node


class AugAssignMutator(ASTMutator):
    operator = "augassign"
    OP_MAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv}

    def visit_AugAssign(self, node):
        self.generic_visit(node)
        if type(node.op) in self.OP_MAP and self._should_mutate(node):
            new = self.OP_MAP[type(node.op)]
            self.applied_mutation = f"Augmented assignment: {type(node.op).__name__}= -> {new.__name__}="
            node.op = new()
        return node


class LogicalMutator(ASTMutator):
    operator = "logical"

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self._should_mutate(node):
            new = ast.Or if isinstance(node.op, ast.And) else ast.And
            self.applied_mutation = f"Logical swap: {type(node.op).__name__} -> {new.__name__}"
            node.op = new()
        return node


class ConditionNegationMutator(ASTMutator):
    operator = "negate_condition"

    def _negate(self, node):
        if self._should_mutate(node):
            node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
            self.applied_mutation = f"Condition negated: {type(node).__name__.lower()} not (...)"

    def visit_If(self, node):
        self.generic_visit(node)
        self._negate(node)
        return node

    def visit_While(self, node):
        self.generic_visit(node)
        self._negate(node)
        return node

    def visit_IfExp(self, node):
        self.generic_visit(node)
        self._negate(node)
        return node


class BooleanFlipMutator(ASTMutator):
    operator = "boolean"

    def visit_Constant(self, node):
        if isinstance(node.value, bool) and self._should_mutate(node):
            self.applied_mutation = f"Boolean flip: {node.value} -> {not node.value}"
            node.value = not node.value
        return node


class StatementDeletionMutator(ASTMutator):
    """Replaces one executable statement inside a function body with `pass`."""
    operator = "statement_deletion"
    ELIGIBLE = (ast.Assign, ast.AugAssign, ast.Expr, ast.If, ast.For, ast.While, ast.AnnAssign)

    def _visit_body(self, body):
        for i, stmt in enumerate(body):
            if isinstance(stmt, ast.Expr) and isinstance(getattr(stmt, "value", None), ast.Constant):
                continue  # docstrings
            if isinstance(stmt, self.ELIGIBLE) and self._should_mutate(stmt):
                self.applied_mutation = f"Statement deleted (line {stmt.lineno}): {ast.unparse(stmt).splitlines()[0][:60]}"
                body[i] = ast.copy_location(ast.Pass(), stmt)
                return
        return

    def generic_visit(self, node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.If, ast.For, ast.While, ast.With, ast.Try)):
            for attr in ("body", "orelse", "finalbody"):
                if hasattr(node, attr) and self.applied_mutation is None:
                    self._visit_body(getattr(node, attr))
        return super().generic_visit(node)


class ReturnNullifierMutator(ASTMutator):
    operator = "return_null"

    def visit_Return(self, node):
        if node.value is not None and self._should_mutate(node):
            node.value = ast.Constant(value=None)
            self.applied_mutation = "Return nullification: return None"
        return node


OPERATORS: Sequence[type] = (
    RelationalMutator, BoundaryConstantMutator, BoundaryMinusMutator, ArithmeticMutator, AugAssignMutator,
    LogicalMutator, ConditionNegationMutator, BooleanFlipMutator, StatementDeletionMutator, ReturnNullifierMutator,
)


def _mutants_for(base_tree, source_key: str, op_cls, seen: set, cap: int) -> List[MutantRecord]:
    out = []
    for target in range(cap * 3):
        tree = copy.deepcopy(base_tree)
        m = op_cls(target_index=target)
        tree = ast.fix_missing_locations(m.visit(tree))
        if m.applied_mutation is None:
            break  # no more eligible nodes for this operator
        try:
            code = ast.unparse(tree)
            compile(code, "<mutant>", "exec")
        except Exception:
            continue
        if code in seen:
            continue
        seen.add(code)
        out.append(MutantRecord(mutant_id=f"mutant_{op_cls.operator}_{target + 1:02d}", operator=op_cls.operator,
                                description=m.applied_mutation, diff_summary=f"[{op_cls.operator}] {m.applied_mutation}",
                                code=code, lineno=m.lineno))
        if len(out) >= cap:
            break
    return out


def generate_mutants(source_code: str, max_mutants: int = 40, per_operator_cap: int = 25) -> List[MutantRecord]:
    """Deterministic, de-duplicated single-point mutants, interleaved round-robin across operators."""
    try:
        base_tree = ast.parse(source_code)
    except SyntaxError:
        return []
    seen = {ast.unparse(base_tree)}
    pools = [_mutants_for(base_tree, source_code, op, seen, per_operator_cap) for op in OPERATORS]
    mutants: List[MutantRecord] = []
    i = 0
    while len(mutants) < max_mutants and any(i < len(p) for p in pools):
        for p in pools:
            if i < len(p) and len(mutants) < max_mutants:
                mutants.append(p[i])
        i += 1
    return mutants


# ── Differential runner (equivalence + stillborn detection) ──────────────
DIFF_RUNNER = r'''
import importlib.util, json, sys
mod_file, entry, corpus_file = sys.argv[1:4]
try:
    spec = importlib.util.spec_from_file_location("candidate_module", mod_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, entry)
except BaseException as e:
    print(json.dumps({"stillborn": f"{type(e).__name__}: {e}"[:200]}))
    sys.exit(0)
outs = []
for item in json.load(open(corpus_file, encoding="utf-8")):
    arg = list(item) if isinstance(item, list) else item
    try:
        r = fn(arg)
        kind = type(r).__name__
        if not isinstance(r, (list, dict, str, int, float, bool, type(None), tuple)):
            r = list(r)
        outs.append([kind, json.loads(json.dumps(r, sort_keys=True, default=repr))])
    except BaseException as e:
        outs.append(["raised", type(e).__name__])
print(json.dumps({"outs": outs}, sort_keys=True))
'''


# ── Output-contract probes ───────────────────────────────────────────────
_PROBE_LIB = r'''
import copy as _crucible_copy
def _crucible_is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)
def _crucible_seq(orig, items):
    if isinstance(orig, tuple) and hasattr(orig, "_fields"):
        return type(orig)(*items)
    return type(orig)(items) if type(orig) in (list, tuple) else list(items)
def _crucible_norm(r):
    if isinstance(r, (list, dict, str, int, float, bool, tuple, type(None))):
        return _crucible_copy.deepcopy(r)
    try:
        return list(r)
    except TypeError:
        return r
def _crucible_map_dicts(x, f):
    if isinstance(x, dict):
        return f({k: _crucible_map_dicts(v, f) for k, v in x.items()})
    if isinstance(x, (list, tuple)):
        return _crucible_seq(x, [_crucible_map_dicts(v, f) for v in x])
    return x
def _crucible_map_leaves(x, f):
    if isinstance(x, dict):
        return {k: _crucible_map_leaves(v, f) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return _crucible_seq(x, [_crucible_map_leaves(v, f) for v in x])
    return f(x)
def _crucible_shift_num(x, pick):
    if isinstance(x, dict):
        x = {k: (v if _crucible_is_num(v) else _crucible_shift_num(v, pick)) for k, v in x.items()}
        keys = [k for k, v in x.items() if _crucible_is_num(v)]
        if keys:
            k = keys[pick]
            x[k] = x[k] + 1
        return x
    if isinstance(x, (list, tuple)):
        return _crucible_seq(x, [_crucible_shift_num(v, pick) for v in x])
    return x + 1 if _crucible_is_num(x) else x
def _crucible_rename_first(d):
    if not d:
        return d
    k0 = next(iter(d))
    return {(f"{k}_" if k == k0 and isinstance(k, str) else k): v for k, v in d.items()}
'''

# name -> (description, body of `def _crucible_probe(r):`)
OUTPUT_PROBES = {
    "drop_last": ("Output probe: drop the last element/field",
                  "if isinstance(r, (list, tuple, str)) and len(r): return r[:-1]\n"
                  "if isinstance(r, dict) and r: return dict(list(r.items())[:-1])\n"
                  "if isinstance(r, bool): return not r\n"
                  "return r + 1 if _crucible_is_num(r) else r"),
    "drop_first": ("Output probe: drop the first element/field",
                   "if isinstance(r, (list, tuple, str)) and len(r): return r[1:]\n"
                   "if isinstance(r, dict) and r: return dict(list(r.items())[1:])\n"
                   "if isinstance(r, bool): return not r\n"
                   "return r - 1 if _crucible_is_num(r) else r"),
    "duplicate_first": ("Output probe: duplicate the first element",
                        "return r[:1] + r if isinstance(r, (list, tuple)) and len(r) else r"),
    "empty": ("Output probe: return an empty result",
              "if isinstance(r, (list, tuple, dict, str)): return type(r)()\n"
              "return 0 if _crucible_is_num(r) else r"),
    "shift_last_number": ("Output probe: last numeric field of every record +1", "return _crucible_shift_num(r, -1)"),
    "shift_first_number": ("Output probe: first numeric field of every record +1", "return _crucible_shift_num(r, 0)"),
    "rename_field": ("Output probe: rename the first field of every record",
                     "return _crucible_map_dicts(r, _crucible_rename_first)"),
    "drop_field": ("Output probe: drop the last field of every record",
                   "return _crucible_map_dicts(r, lambda d: dict(list(d.items())[:-1]))"),
    "flip_bools": ("Output probe: flip every boolean value",
                   "return _crucible_map_leaves(r, lambda v: (not v) if isinstance(v, bool) else v)"),
    "alter_strings": ("Output probe: alter every string value",
                      "return _crucible_map_leaves(r, lambda v: v + '~' if isinstance(v, str) else v)"),
}


def generate_output_probes(source_code: str, entrypoint: str) -> List[MutantRecord]:
    """Wraps `entrypoint` so its return value is corrupted by each probe; the reference's logic is untouched."""
    if not entrypoint.isidentifier():
        return []
    out = []
    for name, (desc, body) in OUTPUT_PROBES.items():
        probe = "def _crucible_probe(r):\n" + "\n".join("    " + line for line in body.splitlines())
        code = (f"{source_code}\n\n{_PROBE_LIB}\n{probe}\n\n_crucible_original_entry = {entrypoint}\n\n"
                f"def {entrypoint}(*args, **kwargs):\n"
                f"    return _crucible_probe(_crucible_norm(_crucible_original_entry(*args, **kwargs)))\n")
        try:
            compile(code, "<probe>", "exec")
        except SyntaxError:
            continue
        out.append(MutantRecord(mutant_id=f"probe_{name}", operator=f"output:{name}", description=desc,
                                diff_summary=f"[output:{name}] {desc}", code=code))
    return out


_INPUT_LIB = r'''
import re as _crucible_re
def _crucible_map_str(x, f):
    if isinstance(x, str):
        return f(x)
    if isinstance(x, dict):
        return {k: _crucible_map_str(v, f) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return type(x)(_crucible_map_str(v, f) for v in x)
    return x
def _crucible_map_num(x, f):
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return f(x)
    if isinstance(x, dict):
        return {k: _crucible_map_num(v, f) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return type(x)(_crucible_map_num(v, f) for v in x)
    return x
def _crucible_seq_in(x):
    return list(x) if not isinstance(x, (str, bytes, dict, int, float, bool, type(None))) else None
'''

# name -> (description, body of `def _crucible_in(x):`)
INPUT_PROBES = {
    "upper_strings": ("Input probe: upper-case every string (case-insensitive reader)",
                      "return _crucible_map_str(x, str.upper)"),
    "lower_strings": ("Input probe: lower-case every string (case-insensitive reader)",
                      "return _crucible_map_str(x, str.lower)"),
    "squash_whitespace": ("Input probe: remove all whitespace inside strings",
                          "return _crucible_map_str(x, lambda s: ''.join(s.split()))"),
    "truncate_decimals": ("Input probe: truncate decimal numbers inside strings (lenient number parser)",
                          "return _crucible_map_str(x, lambda s: _crucible_re.sub(r'(\\d)\\.\\d+', r'\\1', s))"),
    "drop_first_item": ("Input probe: skip the first item",
                        "s = _crucible_seq_in(x)\nreturn x if s is None else s[1:]"),
    "drop_last_item": ("Input probe: skip the last item",
                       "s = _crucible_seq_in(x)\nreturn x if s is None else s[:-1]"),
    "reverse_items": ("Input probe: process items in reverse arrival order",
                      "s = _crucible_seq_in(x)\nreturn x if s is None else s[::-1]"),
    "sort_items": ("Input probe: process items sorted by their text (lexicographic, not by value)",
                   "s = _crucible_seq_in(x)\nreturn x if s is None else sorted(s, key=repr)"),
    "dedupe_items": ("Input probe: drop repeated identical items",
                     "s = _crucible_seq_in(x)\nif s is None:\n    return x\nseen, out = set(), []\n"
                     "for i in s:\n    if repr(i) not in seen:\n        seen.add(repr(i))\n        out.append(i)\nreturn out"),
    "shift_numbers": ("Input probe: every number in the input +1 (off-by-one reader)",
                      "return _crucible_map_num(x, lambda v: v + 1)"),
}


def generate_input_probes(source_code: str, entrypoint: str) -> List[MutantRecord]:
    """Wraps `entrypoint` so its first argument is transformed before the untouched reference logic sees it."""
    if not entrypoint.isidentifier():
        return []
    out = []
    for name, (desc, body) in INPUT_PROBES.items():
        probe = "def _crucible_in(x):\n" + "\n".join("    " + line for line in body.splitlines())
        code = (f"{source_code}\n\n{_INPUT_LIB}\n{probe}\n\n_crucible_original_entry = {entrypoint}\n\n"
                f"def {entrypoint}(*args, **kwargs):\n"
                f"    if args:\n"
                f"        args = (_crucible_in(args[0]),) + tuple(args[1:])\n"
                f"    return _crucible_original_entry(*args, **kwargs)\n")
        try:
            compile(code, "<probe>", "exec")
        except SyntaxError:
            continue
        out.append(MutantRecord(mutant_id=f"inprobe_{name}", operator=f"input:{name}", description=desc,
                                diff_summary=f"[input:{name}] {desc}", code=code))
    return out


class MutationSlaughterGate:
    """Admits a suite only if it passes the reference and kills >= threshold of viable mutants."""

    def __init__(self, run_python_fn: Callable, threshold: float = 0.60, max_mutants: int = 40,
                 min_viable: int = 5, timeout: int = 120, workers: int = 4, output_threshold: Optional[float] = None,
                 output_probes: bool = True, input_threshold: Optional[float] = None, input_probes: bool = True):
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        output_threshold = threshold if output_threshold is None else output_threshold
        if not 0.0 < output_threshold <= 1.0:
            raise ValueError("output_threshold must be in (0, 1]")
        input_threshold = threshold if input_threshold is None else input_threshold
        if not 0.0 < input_threshold <= 1.0:
            raise ValueError("input_threshold must be in (0, 1]")
        self.output_threshold = output_threshold
        self.output_probes = output_probes
        self.input_threshold = input_threshold
        self.input_probes = input_probes
        self.run_python_fn = run_python_fn
        self.threshold = threshold
        self.max_mutants = max_mutants
        self.min_viable = min_viable
        self.timeout = timeout
        self.workers = max(1, workers)

    @staticmethod
    def _read(ref) -> str:
        if isinstance(ref, Path) or (isinstance(ref, str) and len(ref) < 1024 and "\n" not in ref and Path(ref).exists()):
            return Path(ref).read_text(encoding="utf-8")
        return str(ref)

    def _run_suite(self, suite_code: str, solution_code: str, timeout: Optional[int] = None) -> tuple:
        with tempfile.TemporaryDirectory(prefix="crucible_mutant_") as d:
            (Path(d) / "solution.py").write_text(solution_code, encoding="utf-8")
            (Path(d) / "arena_test.py").write_text(suite_code, encoding="utf-8")
            return self.run_python_fn("arena_test.py", Path(d), timeout=timeout or self.timeout)

    def _behaviour(self, code: str, entrypoint: str, corpus: list, timeout: Optional[int] = None) -> dict:
        with tempfile.TemporaryDirectory(prefix="crucible_diff_") as d:
            (Path(d) / "candidate.py").write_text(code, encoding="utf-8")
            (Path(d) / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
            (Path(d) / "diff_runner.py").write_text(DIFF_RUNNER, encoding="utf-8")
            rc, out, err, _ = self.run_python_fn("diff_runner.py", Path(d), timeout=timeout or self.timeout,
                                                 args=["candidate.py", entrypoint, "corpus.json"])
            if rc != 0:
                return {"divergent": f"exit {rc}"}  # e.g. a mutant that loops forever: behaviour differs
            try:
                return json.loads(out.strip().splitlines()[-1])
            except (ValueError, IndexError):
                return {"divergent": "unparseable output"}

    @staticmethod
    def _kill_kind(code: int, out: str, err: str) -> str:
        if code == 124:
            return "timeout"
        text = f"{out}\n{err}"
        if "AssertionError" in text or "FAIL" in text.upper():
            return "assertion"
        return "error"

    def evaluate_suite(self, suite_path, reference_source_or_path, equivalence_corpus: Optional[list] = None,
                       entrypoint: Optional[str] = None) -> MutationSlaughterResult:
        ref_code = self._read(reference_source_or_path)
        suite_code = Path(suite_path).read_text(encoding="utf-8")

        def fail(reason, **kw):
            base = dict(total_mutants=0, killed_mutants=0, survived_mutants=0, slaughter_rate=0.0,
                        passed_gate=False, threshold=self.threshold, reason=reason)
            base.update(kw)
            return MutationSlaughterResult(**base)

        # 1. Baseline
        code, out, err, base_secs = self._run_suite(suite_code, ref_code)
        # Mutant runs get ~10x the baseline time (min 15 s): a mutant that loops forever is killed by timeout
        # without stalling the gate for the full limit.
        mtimeout = int(min(self.timeout, max(15, 10 * base_secs)))
        if code != 0:
            tail = ((err or out).strip().splitlines() or [""])[-1][:200]
            return fail(f"Mutation gate: the suite fails the unmutated reference (exit {code}: {tail}); "
                        f"its kill count would be meaningless. Fail closed.", baseline_passed=False)

        # 2. Mutants
        mutants = generate_mutants(ref_code, max_mutants=self.max_mutants)
        if not mutants:
            return fail("Mutation gate: no mutants could be generated from the reference, so the suite's strength "
                        "cannot be demonstrated. Fail closed.", baseline_passed=True)

        # 3. Equivalence / stillborn filter
        checked = bool(equivalence_corpus) and bool(entrypoint)
        status = {m.mutant_id: "viable" for m in mutants}
        if checked:
            ref_behaviour = self._behaviour(ref_code, entrypoint, equivalence_corpus)
            ref_secs_limit = mtimeout
            if "outs" not in ref_behaviour:
                return fail(f"Mutation gate: the reference itself could not run the equivalence corpus "
                            f"({ref_behaviour}). Fail closed.", baseline_passed=True)
            with ThreadPoolExecutor(self.workers) as pool:
                behaviours = list(pool.map(
                    lambda m: self._behaviour(m.code, entrypoint, equivalence_corpus, ref_secs_limit), mutants))
            for m, b in zip(mutants, behaviours):
                if "stillborn" in b:
                    status[m.mutant_id] = "stillborn"
                elif b.get("outs") == ref_behaviour["outs"]:
                    status[m.mutant_id] = "equivalent"
        viable = [m for m in mutants if status[m.mutant_id] == "viable"]
        n_equiv = sum(1 for s in status.values() if s == "equivalent")
        n_still = sum(1 for s in status.values() if s == "stillborn")
        common = dict(baseline_passed=True, generated_mutants=len(mutants), equivalent_mutants=n_equiv,
                      stillborn_mutants=n_still, equivalence_checked=checked)
        if not viable:
            return fail("Mutation gate: every generated mutant was equivalent or stillborn on the corpus; nothing "
                        "can be demonstrated. Fail closed.", **common)

        # 4. Slaughter
        kinds = {"assertion": 0, "error": 0, "timeout": 0}
        by_op: dict = {}
        details = self._slaughter(suite_code, viable, mtimeout, kinds, by_op)
        for m in mutants:
            if status[m.mutant_id] != "viable":
                details.append({"mutant_id": m.mutant_id, "operator": m.operator, "description": m.description,
                                "lineno": m.lineno, "status": status[m.mutant_id].upper(), "killed_by": None,
                                "exit_code": None})

        # 5. Output-contract probes and 6. input-domain probes (only meaningful with a corpus to filter
        # equivalent probes)
        out_checked = bool(self.output_probes and checked)
        in_checked = bool(self.input_probes and checked)
        out_details, out_total, out_killed, out_rate, out_pass = [], 0, 0, None, None
        in_details, in_total, in_killed, in_rate, in_pass = [], 0, 0, None, None
        if out_checked:
            out_details, out_total, out_killed, out_rate, out_pass = self._probe_axis(
                generate_output_probes(ref_code, entrypoint), suite_code, entrypoint, equivalence_corpus,
                ref_behaviour["outs"], mtimeout, kinds, by_op, self.output_threshold)
        if in_checked:
            in_details, in_total, in_killed, in_rate, in_pass = self._probe_axis(
                generate_input_probes(ref_code, entrypoint), suite_code, entrypoint, equivalence_corpus,
                ref_behaviour["outs"], mtimeout, kinds, by_op, self.input_threshold)

        # 7. Verdict
        killed = sum(1 for d in details if d["status"] == "KILLED")
        total = len(viable)
        rate = round(killed / total, 3)
        enough = total >= self.min_viable
        code_pass = rate >= self.threshold and enough
        passed = code_pass and out_pass is not False and in_pass is not False
        scope = (f"{n_equiv} equivalent and {n_still} stillborn excluded" if checked
                 else "equivalence NOT checked (no corpus): score is a lower bound")
        if not enough:
            verdict = f"Only {total} viable mutants (< {self.min_viable}): too few to demonstrate strength. Fail closed."
        elif not code_pass:
            verdict = f"FAILED threshold of {self.threshold * 100:.1f}%. Suite is rejected as weak/tautological."
        else:
            verdict = f"Meets threshold of {self.threshold * 100:.1f}%."
        reason = (f"Adversarial Mutation Gate: Slaughtered {killed}/{total} viable mutants ({rate * 100:.1f}%; "
                  f"{scope}). {verdict}")
        reason += self._axis_text("Output-contract", self.output_probes, out_checked, out_total, out_killed, out_rate,
                                  out_pass, self.output_threshold, "the suite does not check output values")
        reason += self._axis_text("Input-domain", self.input_probes, in_checked, in_total, in_killed, in_rate, in_pass,
                                  self.input_threshold, "the suite does not exercise the input classes a careless "
                                  "reader gets wrong (case, whitespace, order, malformed values)")
        return MutationSlaughterResult(total_mutants=total, killed_mutants=killed, survived_mutants=total - killed,
                                       slaughter_rate=rate, passed_gate=passed, threshold=self.threshold,
                                       details=details, reason=reason, kills_by_kind=kinds, by_operator=by_op,
                                       code_axis_passed=code_pass, output_probes_checked=out_checked,
                                       output_threshold=self.output_threshold, output_total=out_total,
                                       output_killed=out_killed, output_rate=out_rate, output_axis_passed=out_pass,
                                       output_details=out_details, input_threshold=self.input_threshold,
                                       input_total=in_total, input_killed=in_killed, input_rate=in_rate,
                                       input_axis_passed=in_pass, input_details=in_details, **common)

    def _probe_axis(self, probes: list, suite_code: str, entrypoint: str, corpus: list, ref_outs, timeout: int,
                    kinds: dict, by_op: dict, threshold: float) -> tuple:
        """Filters probes that are equivalent to the reference (or to an earlier probe) on the corpus, then runs the
        suite against the rest. Returns (details, total, killed, rate, passed); rate/passed are None if none viable."""
        with ThreadPoolExecutor(self.workers) as pool:
            pbehav = list(pool.map(lambda p: self._behaviour(p.code, entrypoint, corpus, timeout), probes))
        seen_outs: list = [ref_outs]
        filtered: List[dict] = []
        viable_probes = []
        for p, b in zip(probes, pbehav):
            outs = b.get("outs")
            if outs is not None and outs in seen_outs:
                st = "EQUIVALENT" if outs == ref_outs else "DUPLICATE"
                filtered.append({"mutant_id": p.mutant_id, "operator": p.operator, "description": p.description,
                                 "lineno": None, "status": st, "killed_by": None, "exit_code": None})
                continue
            if outs is not None:
                seen_outs.append(outs)
            viable_probes.append(p)
        details = self._slaughter(suite_code, viable_probes, timeout, kinds, by_op) + filtered
        total = len(viable_probes)
        killed = sum(1 for d in details if d["status"] == "KILLED")
        if not total:
            return details, 0, 0, None, None
        rate = round(killed / total, 3)
        return details, total, killed, rate, rate >= threshold

    @staticmethod
    def _axis_text(label: str, enabled: bool, checked: bool, total: int, killed: int, rate, passed,
                   threshold: float, weakness: str) -> str:
        if not enabled:
            return f" {label} probes DISABLED by configuration."
        if not checked:
            return f" {label} probes NOT run (need an entrypoint and an equivalence corpus)."
        if not total:
            return f" {label} probes: none viable on the corpus (not applicable)."
        return (f" {label} probes: killed {killed}/{total} ({rate * 100:.1f}%) "
                + (f"meets {threshold * 100:.1f}%." if passed else
                   f"FAILED {threshold * 100:.1f}%: {weakness} (rejected as weak/tautological)."))

    def _slaughter(self, suite_code: str, mutants: list, timeout: int, kinds: dict, by_op: dict) -> List[dict]:
        with ThreadPoolExecutor(self.workers) as pool:
            runs = list(pool.map(lambda m: self._run_suite(suite_code, m.code, timeout), mutants))
        details = []
        for m, (c, o, e, _secs) in zip(mutants, runs):
            killed = c != 0
            kind = self._kill_kind(c, o, e) if killed else None
            if kind:
                kinds[kind] += 1
            op = by_op.setdefault(m.operator, {"viable": 0, "killed": 0})
            op["viable"] += 1
            op["killed"] += killed
            details.append({"mutant_id": m.mutant_id, "operator": m.operator, "description": m.description,
                            "lineno": m.lineno, "status": "KILLED" if killed else "SURVIVED", "killed_by": kind,
                            "exit_code": c})
        return details
