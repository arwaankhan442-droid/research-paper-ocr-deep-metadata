import json
import unittest
from pathlib import Path

import extract_paper_meta as pipeline


class PipelineUnitTests(unittest.TestCase):
    def test_clean_text_repairs_hyphenation_and_whitespace(self):
        self.assertEqual(pipeline.clean_text("multi-\nmodal   model"), "multimodal model")

    def test_github_url_is_normalized(self):
        self.assertEqual(
            pipeline.normalize_github_url("https://github.com/org/repo.git/tree/main"),
            "https://github.com/org/repo",
        )

    def test_non_github_url_is_rejected(self):
        with self.assertRaises(ValueError):
            pipeline.normalize_github_url("https://example.com/project")

    def test_all_five_reviewed_configs_have_required_fields(self):
        config = json.loads(pipeline.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(config), set(pipeline.IDS))
        for paper_id, item in config.items():
            self.assertTrue(pipeline.normalize_github_url(item["github_url"]))
            for key in ("tasks", "methods", "models", "datasets", "sota_claims"):
                self.assertIsInstance(item[key], list, f"{paper_id}: {key}")
            for claim in item["sota_claims"]:
                self.assertTrue({"benchmark", "metric", "value", "comparison_target"}.issubset(claim))


if __name__ == "__main__":
    unittest.main(verbosity=2)
