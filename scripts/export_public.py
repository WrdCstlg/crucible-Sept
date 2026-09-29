"""Prepares a clean public copy of the repository. It never creates a repository or pushes anything.

  python scripts/export_public.py <target folder>

1. Copies exactly the files git would publish: tracked files plus untracked files that .gitignore does not exclude
   (so .env, workspaces, caches and deployments are never copied). Git history is NOT copied.
2. Redacts local machine paths (project folder and home folder) from ordinary text files, and lists every redaction.
3. Never edits fingerprinted evidence (audit records, observer reports, ledgers, the frozen test set): if one of those
   contains a local path, it is reported as a blocking issue instead, because editing it would break its fingerprint.
4. Scans the copy for secrets: common key formats, plus the actual values in .env (compared, never printed).
5. Writes EXPORT_REPORT.md into the target folder. Exit code 1 if anything blocks publication.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTECTED_NAMES = {"audit.json", "audit_summary.json", "observer_report.json", "observer_report.md", "ledger.jsonl",
                   "FROZEN.json", "SPEC.md", "hand_cases.json", "generated_cases.json", "reference.py",
                   "reference_intervals.py", "generate_cases.py"}
SECRET_PATTERNS = {
    "Google API key": r"AIza[0-9A-Za-z_\-]{30,}",
    "Anthropic key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "OpenAI/Moonshot-style key": r"\bsk-[A-Za-z0-9]{32,}",
    "GitHub token": r"\bgh[pousr]_[A-Za-z0-9]{30,}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}


def publishable_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return sorted(Path(p) for p in out.split("\0") if p and (ROOT / p).is_file())


def local_path_pattern() -> re.Pattern:
    """The folder that holds this repository (so sibling projects too) and the home folder, however a path to them is
    written: / or \\ separators, doubled or JSON-escaped backslashes, and spaces written as %20."""
    alternatives = []
    for base in (ROOT.parent, Path.home()):
        pieces = [base.drive] + list(base.parts[1:])
        escaped = ["".join("(?: |%20)" if ch == " " else re.escape(ch) for ch in piece) for piece in pieces]
        alternatives.append(r"(?:\\+|/)+".join(escaped))
    return re.compile("|".join(sorted(alternatives, key=len, reverse=True)), re.IGNORECASE)


def env_values() -> list[str]:
    env = ROOT / ".env"
    if not env.exists():
        return []
    values = []
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if len(v) >= 16 and not v.startswith("http"):
                values.append(v)
    return values


def main(target: Path):
    if target.exists() and any(target.iterdir()):
        sys.exit(f"{target} exists and is not empty; choose a new folder")
    paths = local_path_pattern()
    secrets = env_values()
    redacted, blocking, found_secrets, binary = [], [], [], 0
    files = publishable_files()
    for rel in files:
        src, dst = ROOT / rel, target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            shutil.copy2(src, dst)
            binary += 1
            continue
        for label, pat in SECRET_PATTERNS.items():
            if re.search(pat, text):
                found_secrets.append(f"{rel}: looks like a {label}")
        if any(v in text for v in secrets):
            found_secrets.append(f"{rel}: contains a value from .env")
        hits = len(paths.findall(text))
        if hits and rel.name in PROTECTED_NAMES:
            blocking.append(f"{rel}: {hits} local path(s) inside fingerprinted evidence (not edited)")
            dst.write_bytes(data)
        elif hits:
            dst.write_text(paths.sub("<local path>", text), encoding="utf-8", newline="")
            redacted.append((rel, hits))
        else:
            dst.write_bytes(data)

    ok = not found_secrets and not blocking
    report = ["# Public export report\n",
              f"Source: this repository's publishable files ({len(files)} files, {binary} binary). Git history not copied.\n",
              f"**Result: {'READY: no secrets found, no blocking issues' if ok else 'BLOCKED: fix the issues below first'}**\n",
              "## Secrets", *(f"- {s}" for s in found_secrets or ["none found (key formats and .env values checked)"]),
              "\n## Blocking issues", *(f"- {b}" for b in blocking or ["none"]),
              "\n## Local paths redacted (replaced with `<local path>`)", *(f"- `{r}`: {n}" for r, n in redacted or [("none", 0)]),
              "\n## Before publishing",
              "- Create a NEW repository from this folder (do not make the old private repository public: its orphaned "
              "commits remain reachable by SHA).",
              "- Decide which email address the new commits should show (a GitHub noreply address keeps yours private).",
              "- Review the case study and README one last time."]
    (target / "EXPORT_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
