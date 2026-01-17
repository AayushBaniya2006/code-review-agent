import unittest

from app.services.diff_parser import DiffParser


class TestDiffParser(unittest.TestCase):
    def test_parse_basic_diff(self):
        diff = (
            "diff --git a/app.py b/app.py\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def hello():\n"
            "-    return 'hi'\n"
            "+    msg = 'hi'\n"
            "+    return msg\n"
        )
        parsed = DiffParser().parse(diff)

        self.assertEqual(parsed.file_count, 1)
        self.assertEqual(parsed.total_additions, 2)
        self.assertEqual(parsed.total_deletions, 1)
        self.assertIn("python", parsed.languages)


if __name__ == "__main__":
    unittest.main()
