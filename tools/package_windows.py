"""
QuMail Windows x64 Production Packaging Tool.

Builds and packages the complete QuMail desktop application into a standalone
distribution directory under dist/QuMail ready for Inno Setup installer compilation.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.packaging import (
    APPLICATION_VERSION,
    assemble_production_bundle,
    verify_bundle_layout,
)


def get_git_commit() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser(description="Package QuMail for Windows production deployment.")
    parser.add_argument("--output", "-o", default=str(ROOT / "dist" / "QuMail"), help="Output directory")
    parser.add_argument("--version", "-v", default=APPLICATION_VERSION, help="Release version string")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing bundle without rebuilding")
    args = parser.parse_args()

    out_dir = Path(args.output).resolve()

    if args.verify_only:
        print(f"Verifying existing bundle at {out_dir}...")
        res = verify_bundle_layout(out_dir)
        print("Bundle verification successful:")
        print(res)
        return 0

    commit = get_git_commit()
    print(f"Assembling QuMail production bundle (v{args.version}, commit: {commit[:8]})...")
    meta = assemble_production_bundle(
        source_root=ROOT,
        output_dir=out_dir,
        version=args.version,
        commit_sha=commit,
    )
    print(f"Bundle assembled successfully at {out_dir}")

    print("Verifying bundle integrity and PE mitigations...")
    ver = verify_bundle_layout(out_dir)
    print("Verification passed:")
    for k, v in ver["providers"].items():
        print(f"  - {k}: SHA256={v['digest'][:16]}... PE_CFG={v['pe_mitigations']['guard_cf']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
