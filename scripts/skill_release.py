"""Content-bound skill audit, validation receipts and selective atomic install.

Stdlib only. Digests cover relative names and raw bytes; only interpreter caches
are excluded. A report binds command inputs, not just a Git commit. No execution
of report contents, automatic drift choice, Git repair or full-library install.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

VERSION = 1
KINDS = ("structure", "unit", "model_behavior", "platform_native")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def linked(path):
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def digest(path):
    path = Path(path)
    if linked(path):
        raise ValueError(f"links/junctions are not supported: {path}")
    if not path.exists():
        return None
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    records = []
    for folder, dirs, names in os.walk(path, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "__pycache__"})
        for d in dirs:
            if linked(Path(folder) / d):
                raise ValueError(f"linked directory: {Path(folder) / d}")
        for name in sorted(names):
            p = Path(folder) / name
            if p.suffix in {".pyc", ".pyo"}:
                continue
            if linked(p):
                raise ValueError(f"linked file: {p}")
            records.append((p.relative_to(path).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(sorted(records), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def git(source, *args):
    p = subprocess.run(["git", "-C", str(source), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"ok": p.returncode == 0, "value": p.stdout.strip() if p.returncode == 0 else p.stderr.strip()}


def checkout(source):
    info = {k: git(source, *v) for k, v in {
        "root": ("rev-parse", "--show-toplevel"), "head": ("rev-parse", "HEAD"),
        "branch": ("branch", "--show-current"), "remote": ("remote", "-v"),
        "status": ("status", "--porcelain=v1", "--untracked-files=all"),
    }.items()}
    info["dirty"] = bool(info["status"]["value"]) if info["status"]["ok"] else None
    return info


def skills(root):
    root = Path(root)
    if not root.is_dir():
        return set()
    return {p.name for p in root.iterdir() if not p.name.startswith(".") and (p / "SKILL.md").is_file()}


def subject(source, name):
    if not NAME.fullmatch(name) or not (source / name / "SKILL.md").is_file():
        raise ValueError(f"invalid or missing skill: {name}")
    return {"skill": name, "sha256": digest(source / name)}


def inputs(source, extra):
    result = []
    for relative in extra:
        p = (source / relative).resolve()
        if not p.is_relative_to(source.resolve()) or not p.exists():
            raise ValueError(f"missing/outside validation input: {relative}")
        result.append({"path": p.relative_to(source.resolve()).as_posix(), "sha256": digest(p)})
    return result


def report_applicable(report, source, name, platform):
    expected = subject(source, name)["sha256"]
    if report.get("platform") != platform or report.get("schema_version") != VERSION:
        return False
    if not any(s.get("skill") == name and s.get("sha256") == expected for s in report.get("subjects", [])):
        return False
    try:
        subjects = report.get("subjects", [])
        return bool(subjects) and all(subject(source, s["skill"]) == s for s in subjects) and inputs(source, [i["path"] for i in report.get("inputs", [])]) == report.get("inputs", [])
    except (OSError, ValueError, KeyError):
        return False


def audit(source, runtime, platform, reports=()):
    source, runtime = Path(source).resolve(), Path(runtime).resolve()
    loaded = [(str(Path(p).resolve()), read(p)) for p in reports]
    rows = []
    for name in sorted(skills(source) | skills(runtime)):
        problems = []
        def checked(path):
            try:
                return digest(path)
            except (OSError, ValueError) as exc:
                problems.append(str(exc))
                return None
        a, b = checked(source / name), checked(runtime / name)
        status = "unverifiable" if problems else "runtime_only" if a is None else "not_installed" if b is None else "same_version" if a == b else "drift"
        verifications = []
        for kind in KINDS:
            matches = [{"path": path, "sha256": digest(path), "status": r.get("status"),
                        "applicable": report_applicable(r, source, name, platform) if a else False}
                       for path, r in loaded if r.get("kind") == kind and any(s.get("skill") == name for s in r.get("subjects", []))]
            verifications.append({"kind": kind, "reports": matches, "status": "not_run" if not matches else "see_reports"})
        state = git(source, "status", "--porcelain=v1", "--untracked-files=all", "--", name)
        rows.append({"skill": name, "source_sha256": a, "runtime_sha256": b, "installation": status,
                     "source_dirty": bool(state["value"]) if state["ok"] and a else None,
                     "source_status": state, "validation": verifications,
                     "limits": problems + (["drift requires explicit review; no preferred version inferred"] if status == "drift" else [])})
    return {"schema_version": VERSION, "platform": platform, "observed_at": now(),
            "source": str(source), "runtime": str(runtime), "checkout": checkout(source),
            "fingerprint_algorithm": "sha256(sorted JSON [relative POSIX path, raw-byte sha256]); excludes .git, __pycache__, .pyc, .pyo",
            "rows": rows, "limits": ["not_installed is not an error", "no platform reload or behavior implied by same_version",
                                    "reports are local evidence, not signed certificates", "runtime roots are explicit, not autodetected"]}


def verify(source, platform, names, extra, kind, command, output, timeout=300):
    if Path(output).exists():
        raise ValueError("validation report already exists; use a new filename")
    before = [subject(source, n) for n in names]
    before_inputs = inputs(source, extra)
    started = time.monotonic()
    try:
        run = subprocess.run(command, cwd=source, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        rc, stdout, stderr = run.returncode, run.stdout, run.stderr
    except subprocess.TimeoutExpired as exc:
        rc, stdout, stderr = None, str(exc.stdout or ""), "TIMEOUT: " + str(exc.stderr or "")
    after = [subject(source, n) for n in names]
    unchanged = before == after and before_inputs == inputs(source, extra)
    payload = {"schema_version": VERSION, "platform": platform, "kind": kind, "status": "pass" if rc == 0 and unchanged else "fail",
               "recorded_at": now(), "source": str(source.resolve()), "checkout": checkout(source), "subjects": before,
               "inputs": before_inputs, "command": command, "returncode": rc, "content_unchanged": unchanged,
               "elapsed_seconds": round(time.monotonic() - started, 3), "stdout": stdout, "stderr": stderr,
               "limits": ["command result only; structure/unit results do not prove model or native behavior"]}
    write_new(output, payload)
    return payload


def safe_root(path):
    p = Path(path).absolute()
    for ancestor in [p, *p.parents]:
        if linked(ancestor):
            raise ValueError(f"linked ancestor: {ancestor}")
    return p.resolve()


def install(source, runtime, backup_root, platform, name, expected, reports):
    source, runtime, backup_root = map(safe_root, (source, runtime, backup_root))
    if source == runtime or source.is_relative_to(runtime) or runtime.is_relative_to(source):
        raise ValueError("source and runtime must be disjoint")
    if any(backup_root == r or backup_root.is_relative_to(r) or r.is_relative_to(backup_root) for r in (source, runtime)):
        raise ValueError("backup root must be disjoint from source/runtime")
    selected = subject(source, name)
    target, src = runtime / name, source / name
    observed = digest(target)
    if expected != (observed or "absent"):
        raise ValueError("runtime changed or drift not reviewed: expected digest mismatch")
    applicable = [read(p) for p in reports if report_applicable(read(p), source, name, platform)]
    if not any(r.get("kind") == "structure" and r.get("status") == "pass" for r in applicable):
        raise ValueError("current content needs a passing structure report")
    if any(r.get("status") == "fail" for r in applicable):
        raise ValueError("current content has a failing supplied report")
    if observed == selected["sha256"]:
        return {"status": "already_same", "skill": name, "sha256": observed}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    bundle = backup_root / run_id
    bundle.mkdir(parents=True, exist_ok=False)
    runtime.mkdir(parents=True, exist_ok=True)
    recovery = safe_root(runtime.parent / ".skill-release-recovery") / run_id
    recovery.mkdir(parents=True, exist_ok=False)
    stage = recovery / ("new-" + name)
    shutil.copytree(src, stage, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".git"))
    if digest(stage) != selected["sha256"] or digest(src) != selected["sha256"]:
        raise ValueError(f"source/stage changed; preserved stage at {stage}")
    if digest(target) != observed:
        raise ValueError("target changed while staging")
    provenance = bundle / "provenance"
    provenance.mkdir()
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        if (source / filename).is_file():
            shutil.copy2(source / filename, provenance / filename)
    backup = bundle / name
    intent = {"schema_version": VERSION, "platform": platform, "skill": name, "source": str(src),
              "source_sha256": selected["sha256"], "checkout": checkout(source), "previous_sha256": observed,
              "backup": str(backup) if observed else None, "target": str(target), "created_at": now(),
              "reports": [{"path": str(Path(p).resolve()), "sha256": digest(p)} for p in reports]}
    write_new(bundle / "intent.json", intent)
    # Persistent backup may be on another volume: copy and hash it before
    # any runtime mutation. Renames used for swapping stay on runtime volume.
    if observed is not None:
        shutil.copytree(target, backup)
        if digest(backup) != observed or digest(target) != observed:
            raise ValueError("backup/source changed before swap")
    retired = recovery / ("old-" + name)
    moved_old = False
    installed_new = False
    try:
        if target.exists():
            target.rename(retired)
            moved_old = True
        stage.rename(target)
        installed_new = True
        actual = digest(target)
        if actual != selected["sha256"] or digest(src) != selected["sha256"]:
            raise ValueError("post-install digest mismatch")
    except Exception:
        if installed_new and target.exists():
            target.rename(recovery / ("failed-new-" + name))
        if moved_old and not target.exists():
            retired.rename(target)
        raise
    # Keep the retired copy as an additional recovery point. No recursive
    # cleanup occurs here, even after a successful durable backup.
    receipt = dict(intent, status="installed_verified", runtime_sha256=actual,
                   retired=str(retired) if moved_old else None, completed_at=now())
    write_new(bundle / "receipt.json", receipt)
    return dict(receipt, receipt=str(bundle / "receipt.json"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--platform", choices=("codex", "workbuddy"), required=True)
    sub = p.add_subparsers(dest="action", required=True)
    a = sub.add_parser("audit")
    a.add_argument("--runtime", type=Path, required=True)
    a.add_argument("--report", type=Path, action="append", default=[])
    a.add_argument("--output", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("--skill", action="append", required=True)
    v.add_argument("--input", action="append", default=[])
    v.add_argument("--kind", choices=KINDS, required=True)
    v.add_argument("--output", type=Path, required=True)
    v.add_argument("--timeout", type=int, default=300)
    v.add_argument("command", nargs=argparse.REMAINDER)
    i = sub.add_parser("install")
    i.add_argument("--runtime", type=Path, required=True)
    i.add_argument("--backup-root", type=Path, required=True)
    i.add_argument("--skill", required=True)
    i.add_argument("--expected-runtime-sha256", required=True)
    i.add_argument("--report", type=Path, action="append", required=True)
    args = p.parse_args()
    try:
        if args.action == "audit":
            result = audit(args.source, args.runtime, args.platform, args.report)
            write_new(args.output, result)
            print(json.dumps({"output": str(args.output), "counts": {s: sum(r["installation"] == s for r in result["rows"]) for s in ("same_version", "drift", "not_installed", "runtime_only", "unverifiable")}}))
        elif args.action == "verify":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command:
                raise ValueError("verification command required after --")
            result = verify(args.source, args.platform, args.skill, args.input, args.kind, command, args.output, args.timeout)
            print(json.dumps({"output": str(args.output), "status": result["status"], "stdout": result["stdout"], "stderr": result["stderr"]}, ensure_ascii=False))
            return 0 if result["status"] == "pass" else 1
        else:
            print(json.dumps(install(args.source, args.runtime, args.backup_root, args.platform, args.skill, args.expected_runtime_sha256, args.report), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
