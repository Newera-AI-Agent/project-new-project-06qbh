"""Unit tests for encoded onset-response measurement semantics."""
import unittest

import numpy as np

from workspace.delivery.onset_response_audit import frame_response, summarize


class OnsetResponseAuditTests(unittest.TestCase):
    def test_frame_response_measures_consecutive_not_cumulative_change(self):
        frames = {i: np.full((90, 160), i * 3, dtype=np.uint8)
                  for i in range(10)}
        result = frame_response(frames, 1, (slice(18, 72), slice(40, 120)))
        self.assertEqual(list(result), list(range(9)))
        self.assertTrue(all(value == 3.0 for value in result.values()))

    def test_summary_reports_mean_and_median(self):
        result = summarize([0.0, 1.0, 3.0])
        self.assertEqual(result["mean_abs_luma_delta_0_255"], 1.33333)
        self.assertEqual(result["median_abs_luma_delta_0_255"], 1.0)


if __name__ == "__main__":
    unittest.main()
