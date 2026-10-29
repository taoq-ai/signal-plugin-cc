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


def imported_modules(path, source=None):
    """What a module imports from the package, relative or absolute, as name tuples below signal_cc
    (the last name may be a module or a name in one)."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text() if source is None else source)):
        if isinstance(node, ast.Import):
            dotted = [alias.name.split(".") for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level:
            base = path.relative_to(PACKAGE).parts[:-1]
            base = [PACKAGE.name, *base[:len(base) - (node.level - 1)], *(node.module or "").split(".")]
            dotted = [[*filter(None, base), alias.name] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            dotted = [[*node.module.split("."), alias.name] for alias in node.names]
        else:
            continue
        out.update(tuple(d[1:]) for d in dotted if d[0] == PACKAGE.name and len(d) > 1)
    return out


def imported_layers(path, source=None):
    """The package layers a module imports."""
    return {m[0] for m in imported_modules(path, source)}


class ArchitectureTest(unittest.TestCase):
    def test_layers_depend_inward_only(self):
        for path in PACKAGE.rglob("*.py"):
            layer = layer_of(path)
            if layer not in ALLOWED:
                continue
            with self.subTest(module=str(path.relative_to(ROOT))):
                self.assertLessEqual(imported_layers(path) - {layer}, ALLOWED[layer] | {layer})

    def test_absolute_and_relative_imports_both_count(self):
        routing = PACKAGE / "domain" / "routing.py"
        for source, layer in [("from signal_cc.adapters import files", "adapters"),
                              ("import signal_cc.entry.wiring", "entry"),
                              ("import signal_cc.app.desk as d", "app"),
                              ("from ..adapters import files", "adapters"),
                              ("from .. import ports", "ports")]:
            with self.subTest(source=source):
                self.assertIn(layer, imported_layers(routing, source))
        self.assertEqual(imported_layers(routing, "import queue\nfrom typing import List\nfrom . import model"),
                         {"domain"})

    def test_only_wiring_picks_the_port_adapters(self):
        # processes is plumbing for the relay's own processes, not a port adapter
        for path in (PACKAGE / "entry").glob("*.py"):
            if path.name == "wiring.py":
                continue
            with self.subTest(module=path.name):
                picked = {m[1] for m in imported_modules(path) if m[0] == "adapters" and len(m) > 1}
                self.assertLessEqual(picked, {"processes"})


if __name__ == "__main__":
    unittest.main()
