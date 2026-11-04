import unittest

import evidence


class EvidenceTests(unittest.TestCase):
    def test_sentence_split_deduplicates(self):
        text = (
            "COVID-19 vaccines reduce hospitalisation. "
            "COVID-19 vaccines reduce hospitalisation. "
            "The study was observational."
        )
        sentences = evidence.split_sentences(text)
        self.assertEqual(len(sentences), 2)

    def test_build_candidates_keeps_source_metadata(self):
        pages = [
            {
                "title": "Example",
                "url": "https://example.com",
                "sentences": ["A sufficiently long evidence sentence."],
            }
        ]
        candidates = evidence.build_candidates(pages)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["url"], "https://example.com")

    def test_format_evidence_limits_output(self):
        sentences = [
            {"title": "Source", "text": "A" * 100},
            {"title": "Source", "text": "B" * 100},
        ]
        text = evidence.format_evidence(sentences, max_chars=130)
        self.assertIn("[1]", text)
        self.assertNotIn("[2]", text)

    def test_small_candidate_set_does_not_need_embeddings(self):
        candidates = [
            {"text": "First evidence sentence.", "title": "A", "url": "u1"},
            {"text": "Second evidence sentence.", "title": "B", "url": "u2"},
        ]
        ranked = evidence.rank_sentences("claim", candidates, top_k=5)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0]["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
