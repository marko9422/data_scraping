"""Offline unit tests for the generic HTML diff engine."""
import unittest

from html_diff import create_html_diff


class HtmlDiffTests(unittest.TestCase):
    def test_identical_html_has_no_changes(self):
        html = "<main>\n<p>Chef</p>\n</main>"
        result = create_html_diff(html, html)
        self.assertFalse(result["changed"])
        self.assertEqual(result["added_content"], "")
        self.assertEqual(result["removed_content"], "")

    def test_addition_and_removal_are_returned_together(self):
        old = "<main>\n<p>Chef</p>\n<p>Receptionist</p>\n</main>"
        new = "<main>\n<p>Chef</p>\n<p>Sous Chef</p>\n</main>"
        result = create_html_diff(old, new)
        self.assertTrue(result["changed"])
        self.assertIn("Sous Chef", result["added_content"])
        self.assertIn("Receptionist", result["removed_content"])

    def test_changed_line_is_addition_and_removal(self):
        old = "<p>Waiter - part time</p>"
        new = "<p>Waiter - full time</p>"
        result = create_html_diff(old, new)
        self.assertIn("full time", result["added_content"])
        self.assertIn("part time", result["removed_content"])


if __name__ == "__main__":
    unittest.main()
