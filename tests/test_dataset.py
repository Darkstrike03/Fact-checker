import unittest

from evaluation.evaluate_covidfact import load_split


class DatasetTests(unittest.TestCase):
    def test_test_split_integrity(self):
        rows = load_split("test")
        self.assertEqual(len(rows), 401)
        self.assertEqual(sum(1 for row in rows if row["gold"] == "SUPPORTED"), 130)
        self.assertEqual(sum(1 for row in rows if row["gold"] == "REFUTED"), 271)
        self.assertTrue(all(row["claim"] for row in rows))
        self.assertTrue(all(row["evidence"] for row in rows))

    def test_dev_split_integrity(self):
        rows = load_split("dev")
        self.assertEqual(len(rows), 419)
        self.assertEqual(sum(1 for row in rows if row["gold"] == "SUPPORTED"), 130)
        self.assertEqual(sum(1 for row in rows if row["gold"] == "REFUTED"), 289)


if __name__ == "__main__":
    unittest.main()
