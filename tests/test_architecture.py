"""The layers only depend inward: domain <- ports <- app <- adapters <- entry."""
import ast
import unittest

from support import ROOT

PACKAGE = ROOT / "signal_cc"
# what each layer may import from the package (config is plain data, open to the outer layers)
ALLOWED = {
    "domain": {"domain"},
    "ports.py": {"domain"},
    "app": {"domain", "ports"},
    "adapters": {"domain", "ports"},
    "entry": {"domain", "ports", "app", "adapters", "entry", "config"},
}


def layer_of(path):
    return path.relative_to(PACKAGE).parts[0]


def imported_layers(path):
    """The package layers a module imports, from its relative imports."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.level:
            base = path.relative_to(PACKAGE).parts[:-1]
            parts = list(base[:len(base) - (node.level - 1)]) + (node.module.split(".") if node.module else [])
            if parts:
                out.add(parts[0])
            else:  # from . import x, at the package root
                out.update(alias.name for alias in node.names)
    return out


class ArchitectureTest(unittest.TestCase):
    def test_layers_depend_inward_only(self):
        for path in PACKAGE.rglob("*.py"):
            layer = layer_of(path)
            if layer not in ALLOWED:
                continue
            with self.subTest(module=str(path.relative_to(ROOT))):
                self.assertLessEqual(imported_layers(path) - {layer}, ALLOWED[layer] | {layer})


if __name__ == "__main__":
    unittest.main()
