import unittest

from portfolio_model.sentiment import score_texts


class SentimentTest(unittest.TestCase):
    def test_consistent_positive_score(self):
        sentiment, confidence = score_texts(["Company beats expectations and raises guidance with strong growth"])

        self.assertGreater(sentiment, 0)
        self.assertGreater(confidence, 0)

    def test_consistent_negative_score(self):
        sentiment, confidence = score_texts(["Company misses estimates after weak demand and downgrade"])

        self.assertLess(sentiment, 0)
        self.assertGreater(confidence, 0)


if __name__ == "__main__":
    unittest.main()
