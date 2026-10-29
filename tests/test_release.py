"""release-please owns the plugin version: its manifest, its config and plugin.json agree."""
import json
import unittest

from support import ROOT

PLUGIN = ".claude-plugin/plugin.json"


def load(name):
    return json.loads((ROOT / name).read_text())


class ReleaseConfigTest(unittest.TestCase):
    def setUp(self):
        self.config = load("release-please-config.json")
        self.manifest = load(".release-please-manifest.json")
        self.version = load(PLUGIN)["version"]

    def test_release_bumps_plugin_json_version(self):
        package = self.config["packages"]["."]
        self.assertIn({"type": "json", "path": PLUGIN, "jsonpath": "$.version"}, package["extra-files"])

    def test_manifest_matches_plugin_json(self):
        released = self.manifest["."]
        if released == "0.0.0":  # before the first release, initial-version is what it will cut
            self.assertEqual(self.config["packages"]["."]["initial-version"], self.version)
        else:
            self.assertEqual(released, self.version)


if __name__ == "__main__":
    unittest.main()
