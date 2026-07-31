from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "docs" / "research"


class ResearchCanonCommonBaseTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_current_contract_set_uses_v2(self) -> None:
        canonical_files = (
            "00_RESEARCH_CHARTER.md",
            "01_MASTER_ROADMAP.md",
            "02_NOVELTY_MAP.md",
            "03_DATA_AND_BASELINE_SCOPE.md",
            "04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md",
            "05_HANDOFF_PROTOCOL.md",
            "06_DECISION_LOG.md",
        )
        for name in canonical_files:
            with self.subTest(name=name):
                self.assertIn("`C1C5_CANON_v2`", (RESEARCH / name).read_text(encoding="utf-8"))

    def test_c3_c5_common_base_contract_is_explicit(self) -> None:
        charter = self.read("docs/research/00_RESEARCH_CHARTER.md")
        data_scope = self.read("docs/research/03_DATA_AND_BASELINE_SCOPE.md")
        result_contract = self.read("docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md")
        decision_log = self.read("docs/research/06_DECISION_LOG.md")

        for document in (charter, data_scope, result_contract, decision_log):
            self.assertIn("no-external-prior", document)
            self.assertIn("B_current", document)
            self.assertIn("SfM sparse", document)
            self.assertIn("dense MVS", document)
            self.assertIn("depth", document)
            self.assertIn("normal", document)
            self.assertIn("confidence", document)
            self.assertIn("1,104", document)

        self.assertIn("C3 common base + Existing ALS prior", charter)
        self.assertIn("C3 common base + independent existing LoD1 prior", charter)
        self.assertIn("mvs_direct_roofer", result_contract)
        self.assertIn("gs_reoptimized_then_roofer", result_contract)
        self.assertIn("DEC-P1-010", decision_log)

    def test_gate_freeze_packet_is_non_executable_draft(self) -> None:
        packet = self.read(
            "docs/research/preregistration/gate_s0/GATE_S0_FREEZE_PACKET_v1.md"
        )
        self.assertIn("status: `DRAFT_NOT_APPROVED`", packet)
        self.assertIn("execution_authority: `NONE`", packet)
        self.assertIn("gate_decision: null", packet)
        self.assertIn("scientific_verdict: null", packet)
        self.assertIn("performance_execution: PROHIBITED", packet)
        self.assertIn("SENSOR_PROCESSING_BUNDLE_CONTEXT_ONLY", packet)
        self.assertIn("final surface adapter 선택은 P2", packet)
        self.assertIn("common parameter/config IDs와 hashes", packet)
        self.assertIn("이 DRAFT 자체를 Experiment Host에 보내 실행하지 않는다", packet)

    def test_historical_gate_packets_are_named_as_protected_inputs(self) -> None:
        packet = self.read(
            "docs/research/preregistration/gate_s0/GATE_S0_FREEZE_PACKET_v1.md"
        )
        protected_paths = (
            "docs/handoffs/P2_W2C_GATE_S0_PREPARATION_v1.md",
            "docs/handoffs/P2_W2C_GATE_S0_REMEDIATION_R1_v1.md",
            "docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md",
            "docs/handoffs/returns/P2_C2W_GATE_S0_REMEDIATION_R1_RETURN_v1.md",
            "docs/evidence/archive/pre_c1c5_research/",
        )
        for relative_path in protected_paths:
            with self.subTest(relative_path=relative_path):
                self.assertIn(relative_path, packet)
                self.assertTrue((ROOT / relative_path).exists())


if __name__ == "__main__":
    unittest.main()
