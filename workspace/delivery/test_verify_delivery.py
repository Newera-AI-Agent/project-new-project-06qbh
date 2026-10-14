"""Regression tests for the standalone package-integrity gate.

Run from the repository root with:
    python3 -m unittest workspace.delivery.test_verify_delivery -v
The tamper case changes only the transcript temporarily and restores its exact
original bytes in a finally block, including when the subprocess assertion fails.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "workspace/delivery/verify_delivery.py"
TRANSCRIPT = ROOT / "workspace/delivery/newera_intro_transcript.md"


class DeliveryIntegrityTests(unittest.TestCase):
    def run_gate(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFY)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_unchanged_delivery_matches_baseline(self) -> None:
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("PASS: delivery manifest matches", result.stdout)
        self.assertIn("full MP4 decode", result.stdout)

    def test_transcript_tamper_is_rejected_and_original_restored(self) -> None:
        original = TRANSCRIPT.read_bytes()
        sentinel = b"\nDELIVERY-INTEGRITY-REGRESSION-SENTINEL\n"
        try:
            TRANSCRIPT.write_bytes(original + sentinel)
            result = self.run_gate()
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("Delivery manifest mismatch", result.stderr)
        finally:
            TRANSCRIPT.write_bytes(original)

        self.assertEqual(TRANSCRIPT.read_bytes(), original)
        restored = self.run_gate()
        self.assertEqual(restored.returncode, 0, restored.stderr or restored.stdout)
        self.assertIn("PASS: delivery manifest matches", restored.stdout)


if __name__ == "__main__":
    unittest.main()
