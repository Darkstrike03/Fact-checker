import unittest

from evaluation import metrics


class MetricTests(unittest.TestCase):
    def test_perfect_predictions(self):
        gold = ["SUPPORTED", "REFUTED", "SUPPORTED"]
        result = metrics.compute_metrics(gold, gold)
        self.assertEqual(result["accuracy"], 1.0)
        self.assertEqual(result["macro_f1"], 1.0)
        self.assertEqual(result["invalid"], 0)

    def test_invalid_answers_are_excluded_and_counted(self):
        gold = ["SUPPORTED", "REFUTED", "SUPPORTED"]
        predictions = ["SUPPORTED", None, "REFUTED"]
        result = metrics.compute_metrics(gold, predictions)
        self.assertEqual(result["invalid"], 1)
        self.assertEqual(result["n_valid"], 2)
        self.assertEqual(result["accuracy"], 0.5)

    def test_confusion_matrix_order(self):
        gold = ["SUPPORTED", "SUPPORTED", "REFUTED", "REFUTED"]
        predictions = ["SUPPORTED", "REFUTED", "SUPPORTED", "REFUTED"]
        result = metrics.compute_metrics(gold, predictions)
        self.assertEqual(result["confusion_matrix"], [[1, 1], [1, 1]])

    def test_mcnemar_counts_discordant_pairs(self):
        gold = ["SUPPORTED", "REFUTED", "SUPPORTED", "REFUTED"]
        predictions_a = ["SUPPORTED", "REFUTED", "SUPPORTED", "REFUTED"]
        predictions_b = ["REFUTED", "REFUTED", "SUPPORTED", "REFUTED"]
        result = metrics.mcnemar_test(gold, predictions_a, predictions_b)
        self.assertEqual(result["only_a_correct"], 1)
        self.assertEqual(result["only_b_correct"], 0)


if __name__ == "__main__":
    unittest.main()
