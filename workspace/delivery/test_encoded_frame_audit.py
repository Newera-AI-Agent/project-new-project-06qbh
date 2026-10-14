"""Unit tests for the read-only encoded-frame QA utility."""
import unittest

from PIL import Image

from workspace.delivery.encoded_frame_audit import describe, sample_frames


class EncodedFrameAuditTests(unittest.TestCase):
    def test_samples_exact_cut_neighbors_and_ending(self):
        storyboard = {
            "fps": 60,
            "actual_scene_boundaries": [
                {"frame": 0}, {"frame": 924}, {"frame": 1802},
                {"frame": 3602}, {"frame": 5388}, {"frame": 6475},
            ],
        }
        samples = sample_frames(storyboard, 6475)
        frames = {s["frame"] for s in samples}
        self.assertTrue({923, 924, 925, 1801, 1802, 1803}.issubset(frames))
        self.assertIn(6474, frames)
        self.assertEqual([s["frame"] for s in samples], sorted(frames))
        self.assertTrue(all(0 <= s["frame"] < 6475 for s in samples))

    def test_luma_metrics_are_bounded_and_report_exact_sample(self):
        img = Image.new("RGB", (4, 2), (0, 0, 0))
        img.putpixel((0, 0), (255, 255, 255))
        result = describe(img, 924, 15.4)
        self.assertEqual(result["frame"], 924)
        self.assertEqual(result["time_sec"], 15.4)
        self.assertEqual(result["thumbnail_dimensions"], [4, 2])
        self.assertEqual(result["mean_luma_0_255"], 31.875)
        for key in ("pixels_above_luma_30_pct", "pixels_above_luma_80_pct"):
            self.assertGreaterEqual(result[key], 0)
            self.assertLessEqual(result[key], 100)


if __name__ == "__main__":
    unittest.main()
