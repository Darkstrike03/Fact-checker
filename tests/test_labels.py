import unittest

import config
import llm_client


class StrictLabelTests(unittest.TestCase):
    def test_accepts_exact_labels(self):
        self.assertEqual(llm_client.parse_dataset_label("SUPPORTED"), "SUPPORTED")
        self.assertEqual(llm_client.parse_dataset_label("refuted."), "REFUTED")

    def test_accepts_prefixed_labels(self):
        self.assertEqual(
            llm_client.parse_dataset_label("LABEL: SUPPORTED"),
            "SUPPORTED",
        )
        self.assertEqual(
            llm_client.parse_dataset_label("Verdict - REFUTED"),
            "REFUTED",
        )

    def test_rejects_non_dataset_labels(self):
        for value in ("True", "False", "Misleading", "Unverifiable", "", "maybe"):
            self.assertIsNone(llm_client.parse_dataset_label(value))

    def test_rejects_ambiguous_output(self):
        self.assertIsNone(
            llm_client.parse_dataset_label(
                "The claim could be SUPPORTED or REFUTED depending on evidence."
            )
        )

    def test_normalize_dataset_labels(self):
        self.assertEqual(llm_client.normalize_label("entailment"), "SUPPORTED")
        self.assertEqual(llm_client.normalize_label("not_entailment"), "REFUTED")
        self.assertIsNone(llm_client.normalize_label("unknown"))
        self.assertEqual(config.LABELS, ("SUPPORTED", "REFUTED"))


if __name__ == "__main__":
    unittest.main()
