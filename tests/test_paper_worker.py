import unittest
import pandas as pd

from paper_worker import entry_signal


class SignalTests(unittest.TestCase):
    def test_buy_requires_completed_crossover_and_trend(self):
        five = pd.DataFrame({
            "ema9": [99.0, 100.0, 102.0],
            "ema21": [100.0, 100.0, 101.0],
            "rsi": [50.0, 55.0, 60.0],
        })
        fifteen = pd.DataFrame({
            "ema9": [101.0, 102.0],
            "ema21": [100.0, 101.0],
        })
        self.assertEqual(entry_signal(five, fifteen), "BUY")

    def test_no_buy_without_trend_alignment(self):
        five = pd.DataFrame({
            "ema9": [99.0, 100.0, 102.0],
            "ema21": [100.0, 100.0, 101.0],
            "rsi": [50.0, 55.0, 60.0],
        })
        fifteen = pd.DataFrame({
            "ema9": [99.0, 98.0],
            "ema21": [100.0, 99.0],
        })
        self.assertEqual(entry_signal(five, fifteen), "WAIT")


if __name__ == "__main__":
    unittest.main()
