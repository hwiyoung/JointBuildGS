import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "repository"
    / "validate_agent_instructions.py"
)
SPEC = importlib.util.spec_from_file_location("validate_agent_instructions", MODULE_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def write_valid_fixture(root: Path) -> None:
    instruction = "\n".join(validator.REQUIRED_MARKERS)
    (root / "AGENTS.md").write_text(instruction, encoding="utf-8")
    (root / "CLAUDE.md").write_text(instruction, encoding="utf-8")
    for relative in validator.PHASE_READMES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        markers = validator.PHASE_README_REQUIRED_MARKERS.get(relative, ())
        path.write_text(
            "\n".join(("status; governed by root `AGENTS.md`", *markers)) + "\n",
            encoding="utf-8",
        )
    for relative, contract in validator.SUPPORT_FILE_CONTRACTS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(contract["required"]) + "\n", encoding="utf-8")


class AgentInstructionContractTests(unittest.TestCase):
    def test_current_repository_contract(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(validator.validate(root), [])

    def test_detects_root_mirror_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_fixture(root)
            (root / "CLAUDE.md").write_text("drift\n", encoding="utf-8")
            self.assertIn(
                "root CLAUDE.md is not byte-identical to root AGENTS.md",
                validator.validate(root),
            )

    def test_accepts_identical_crlf_root_mirrors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_fixture(root)
            relatives = (
                "AGENTS.md",
                "CLAUDE.md",
                *validator.PHASE_READMES,
                *validator.SUPPORT_FILE_CONTRACTS,
            )
            for relative in relatives:
                path = root / relative
                crlf_bytes = path.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
                path.write_bytes(crlf_bytes)
            self.assertEqual(validator.validate(root), [])

    def test_rejects_mixed_eol_root_mirrors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_fixture(root)
            instruction = (root / "AGENTS.md").read_text(encoding="utf-8")
            (root / "AGENTS.md").write_bytes(instruction.replace("\n", "\r\n").encode("utf-8"))
            self.assertIn(
                "root CLAUDE.md is not byte-identical to root AGENTS.md",
                validator.validate(root),
            )

    def test_detects_missing_root_contract_files(self):
        for relative in (
            "AGENTS.md",
            "CLAUDE.md",
            *validator.PHASE_READMES,
            *validator.SUPPORT_FILE_CONTRACTS,
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_valid_fixture(root)
                (root / relative).unlink()
                self.assertTrue(validator.validate(root))

    def test_rejects_symlinked_root_contract_files(self):
        for name in ("AGENTS.md", "CLAUDE.md"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_valid_fixture(root)
                external = root.parent / f"{root.name}-{name}"
                external.write_text((root / name).read_text(encoding="utf-8"), encoding="utf-8")
                (root / name).unlink()
                (root / name).symlink_to(external)
                expected = (
                    f"canonical instruction must not be a symlink: {name}"
                    if name == "AGENTS.md"
                    else f"compatibility mirror must not be a symlink: {name}"
                )
                self.assertIn(expected, validator.validate(root))
                external.unlink()

    def test_detects_nested_agent_instruction(self):
        for name in ("AGENTS.md", "CLAUDE.md"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_valid_fixture(root)
                nested = root / "phases" / "demo" / name
                nested.parent.mkdir(parents=True, exist_ok=True)
                nested.write_text("stale rule\n", encoding="utf-8")
                self.assertIn(
                    f"nested agent instruction is forbidden: phases/demo/{name}",
                    validator.validate(root),
                )

    def test_detects_phase_readme_without_root_deference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_fixture(root)
            path = root / validator.PHASE_READMES[0]
            path.write_text("historical notes only\n", encoding="utf-8")
            self.assertIn(
                f"phase README does not defer to root AGENTS.md: {validator.PHASE_READMES[0]}",
                validator.validate(root),
            )

    def test_detects_each_missing_repository_invariant(self):
        for marker in validator.REQUIRED_MARKERS:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_valid_fixture(root)
                instruction = (root / "AGENTS.md").read_text(encoding="utf-8")
                instruction = instruction.replace(marker, "")
                (root / "AGENTS.md").write_text(instruction, encoding="utf-8")
                (root / "CLAUDE.md").write_text(instruction, encoding="utf-8")
                self.assertIn(
                    f"canonical instruction missing marker: {marker}",
                    validator.validate(root),
                )

    def test_detects_forbidden_legacy_mount_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_fixture(root)
            marker = validator.FORBIDDEN_MARKERS[0]
            for name in ("AGENTS.md", "CLAUDE.md"):
                path = root / name
                path.write_text(path.read_text(encoding="utf-8") + marker, encoding="utf-8")
            self.assertIn(
                f"canonical instruction contains forbidden marker: {marker}",
                validator.validate(root),
            )

    def test_detects_p0_readme_mount_contract_drift(self):
        relative = "phases/p0-audit/README.md"
        for marker in validator.PHASE_README_REQUIRED_MARKERS[relative]:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_valid_fixture(root)
                path = root / relative
                text = path.read_text(encoding="utf-8").replace(marker, "")
                path.write_text(text, encoding="utf-8")
                self.assertIn(
                    f"phase README missing marker ({relative}): {marker}",
                    validator.validate(root),
                )

    def test_detects_p0_readme_forbidden_legacy_path(self):
        relative = "phases/p0-audit/README.md"
        marker = validator.PHASE_README_FORBIDDEN_MARKERS[relative][0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_fixture(root)
            path = root / relative
            path.write_text(path.read_text(encoding="utf-8") + marker, encoding="utf-8")
            self.assertIn(
                f"phase README contains forbidden marker ({relative}): {marker}",
                validator.validate(root),
            )

    def test_detects_support_file_contract_drift(self):
        for relative, contract in validator.SUPPORT_FILE_CONTRACTS.items():
            for marker in contract["required"]:
                with self.subTest(relative=relative, marker=marker), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    write_valid_fixture(root)
                    path = root / relative
                    path.write_text(
                        path.read_text(encoding="utf-8").replace(marker, ""),
                        encoding="utf-8",
                    )
                    self.assertIn(
                        f"instruction support file missing marker ({relative}): {marker}",
                        validator.validate(root),
                    )
            for marker in contract["forbidden"]:
                with self.subTest(relative=relative, marker=marker), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    write_valid_fixture(root)
                    path = root / relative
                    path.write_text(path.read_text(encoding="utf-8") + marker, encoding="utf-8")
                    self.assertIn(
                        f"instruction support file contains forbidden marker ({relative}): {marker}",
                        validator.validate(root),
                    )


if __name__ == "__main__":
    unittest.main()
