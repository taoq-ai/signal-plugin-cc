"""Draws docs/diagram-light.svg and docs/diagram-dark.svg (WUWEI's palette). Run: python3 docs/diagram.py"""
from pathlib import Path

THEMES = {
    "light": dict(bg="#F4FAF8", text="#183B37", muted="#42615C", accent="#00C9A7", accent_text="#00735F",
                  warm="#935600", node="#FFFFFF", bubble="#E3F2EE", out_text="#0B2E29"),
    "dark": dict(bg="#102622", text="#ECF8F5", muted="#B1CBC4", accent="#00C9A7", accent_text="#00C9A7",
                 warm="#F2B65E", node="#193B35", bubble="#21463F", out_text="#0B2E29"),
}

TITLE = "signal-plugin-cc: answer Claude Code from Signal"
DESC = ("Claude Code sessions on your Mac ask for permission, ask questions or finish a turn. While you are away, "
        "the plugin's hooks send each one through a local signal-cli daemon to your Note to Self, where you tap a "
        "reaction or a poll, or reply. Your answer goes back to the session that asked, and a reply to a finished "
        "turn wakes that session with your message.")


def svg(c):
    def text(x, y, s, size=12, fill=c["muted"], weight=None, anchor=None):
        w = f' font-weight="{weight}"' if weight else ""
        a = f' text-anchor="{anchor}"' if anchor else ""
        return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}"{w}{a}>{s}</text>'

    def arrow(x1, y1, x2, y2, color):
        return (f'<path d="M{x1} {y1}L{x2} {y2}" stroke="{color}" stroke-width="2" fill="none" '
                f'marker-end="url(#m-{color[1:]})"/>')

    def session(y, name, what):
        return (f'<rect x="64" y="{y}" width="272" height="56" rx="14" fill="{c["bg"]}" stroke="{c["accent"]}" '
                f'stroke-width="1.5"/>' + text(84, y + 23, name, 14, c["text"], 700) + text(84, y + 43, what))

    def bubble(y, h, lines):
        out = f'<rect x="878" y="{y}" width="232" height="{h}" rx="14" fill="{c["bubble"]}"/>'
        for i, (s, bold) in enumerate(lines):
            out += text(892, y + 20 + 18 * i, s, 12, c["text"], 700 if bold else None)
        return out

    marker = ('<marker id="m-{0}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" '
              'orient="auto"><path d="M0 0L10 5L0 10z" fill="#{0}"/></marker>')
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 640" role="img" aria-labelledby="title desc" '
        'font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="13">',
        f'<title id="title">{TITLE}</title>', f'<desc id="desc">{DESC}</desc>',
        "<defs>" + "".join(marker.format(k[1:]) for k in {c["accent"], c["warm"]}) + "</defs>",
        f'<rect width="1200" height="640" rx="28" fill="{c["bg"]}"/>',
        f'<text x="40" y="54" fill="{c["text"]}" font-size="38" font-weight="700">signal<tspan '
        f'fill="{c["accent_text"]}">-plugin-cc</tspan></text>',
        text(40, 84, "Answer Claude Code from Signal while you're away from the Mac.", 16),
        # legend
        arrow(960, 66, 1010, 66, c["accent"]), text(1020, 70, "to you"),
        arrow(960, 90, 1010, 90, c["warm"]), text(1020, 94, "from you"),
        # column labels
        text(200, 140, "YOUR MAC", 12, c["muted"], 700, "middle"),
        text(600, 140, "IN THE BACKGROUND, ON THE MAC", 12, c["muted"], 700, "middle"),
        text(1010, 140, "YOUR PHONE", 12, c["muted"], 700, "middle"),
        # sessions
        f'<rect x="40" y="160" width="320" height="330" rx="20" fill="{c["node"]}" stroke="{c["muted"]}" '
        f'stroke-opacity="0.35"/>',
        text(200, 192, "Claude Code sessions", 15, c["text"], 700, "middle"),
        session(212, "ziran-paper", "wants to run: rm -rf build"),
        session(282, "wuwei", "asks: which plan?"),
        session(352, "signal-plugin-cc", "finished: 18 tests pass"),
        text(200, 448, "desktop app, terminal or IDE", 12, c["muted"], None, "middle"),
        text(200, 468, "no CLI flag, nothing to start by hand", 12, c["muted"], None, "middle"),
        # hooks and daemon
        f'<rect x="440" y="200" width="320" height="118" rx="18" fill="{c["node"]}" stroke="{c["accent"]}" '
        f'stroke-width="2"/>',
        text(600, 228, "signal-plugin-cc hooks", 15, c["text"], 700, "middle"),
        text(600, 252, "PermissionRequest → allow or deny", 12, c["muted"], None, "middle"),
        text(600, 272, "AskUserQuestion → the answers", 12, c["muted"], None, "middle"),
        text(600, 292, "Stop (asyncRewake) → wake with your reply", 12, c["muted"], None, "middle"),
        arrow(585, 322, 585, 366, c["accent"]), arrow(615, 368, 615, 324, c["warm"]),
        f'<rect x="480" y="372" width="240" height="60" rx="18" fill="{c["node"]}" stroke="{c["accent"]}" '
        f'stroke-width="2"/>',
        text(600, 398, "signal-cli daemon", 15, c["text"], 700, "middle"),
        text(600, 418, "linked device · localhost only", 12, c["muted"], None, "middle"),
        # between the Mac and the hooks
        arrow(362, 246, 436, 246, c["accent"]), text(399, 238, "asks", 11, c["muted"], None, "middle"),
        arrow(438, 288, 364, 288, c["warm"]), text(401, 306, "answer", 11, c["muted"], None, "middle"),
        # between the daemon and the phone
        arrow(722, 390, 854, 390, c["accent"]), text(788, 380, "Note to Self, notifies", 11, c["muted"], None,
                                                     "middle"),
        arrow(854, 414, 722, 414, c["warm"]), text(788, 432, "tap, react, quote, reply", 11, c["muted"], None,
                                                   "middle"),
        # phone
        f'<rect x="860" y="150" width="300" height="380" rx="34" fill="{c["node"]}" stroke="{c["text"]}" '
        f'stroke-width="2"/>',
        f'<rect x="975" y="160" width="70" height="6" rx="3" fill="{c["muted"]}" opacity="0.4"/>',
        text(1010, 190, "Note to Self", 13, c["text"], 700, "middle"),
        f'<path d="M876 202H1144" stroke="{c["muted"]}" stroke-opacity="0.3"/>',
        bubble(214, 48, [("[a3f1] Bash in ziran-paper", True), ("rm -rf build", False)]),
        f'<circle cx="1098" cy="262" r="13" fill="{c["node"]}" stroke="{c["muted"]}" stroke-opacity="0.4"/>',
        text(1098, 267, "\U0001F44D", 13, c["text"], None, "middle"),
        bubble(282, 82, [("[7c2e] wuwei: which plan?", True)]),
        f'<rect x="892" y="310" width="204" height="20" rx="10" fill="{c["accent"]}" fill-opacity="0.35"/>',
        text(904, 324, "✓ Plan A (Recommended)", 11, c["text"]),
        f'<rect x="892" y="336" width="204" height="20" rx="10" fill="none" stroke="{c["muted"]}" '
        f'stroke-opacity="0.5"/>',
        text(904, 350, "Plan B", 11, c["text"]),
        bubble(380, 48, [("[b91d] signal-plugin-cc", True), ("Done; 18 tests pass.", False)]),
        f'<rect x="964" y="444" width="180" height="62" rx="14" fill="{c["accent"]}"/>',
        f'<rect x="976" y="454" width="156" height="20" rx="6" fill="{c["out_text"]}" fill-opacity="0.12"/>',
        text(984, 468, "[b91d] Done; 18 tests…", 10, c["out_text"]),
        text(976, 494, "run the tests too", 12, c["out_text"], 700),
        # rules
    ]
    notes = [("Only while you're away", "touch the Mac and the prompt comes back to it"),
             ("Replies never cross sessions", "quote, react, tag, or the only one waiting"),
             ("No reply in time?", "the Mac asks as usual")]
    for i, (head, rest) in enumerate(notes):
        x = 40 + 400 * i
        parts += [f'<circle cx="{x + 6}" cy="576" r="5" fill="{c["accent"]}"/>',
                  text(x + 20, 581, head, 14, c["text"], 700), text(x + 20, 601, rest, 13)]
    return "\n".join(parts + ["</svg>"]) + "\n"


for name, colors in THEMES.items():
    (Path(__file__).parent / f"diagram-{name}.svg").write_text(svg(colors))
