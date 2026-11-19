#!/usr/bin/env python3
"""Render the profile README cards into cards/ as animated SVGs.

    python scripts/render_readme_cards.py            # animated
    STATIC=1 python scripts/render_readme_cards.py   # final frame only, for screenshots

Reads data/contributions.json (refreshed daily by .github/workflows/readme-cards.yml).
Everything the cards use works inside <img>: an inline <style> with CSS keyframes,
SMIL <animate>/<set>, and fonts subset with pyftsubset and embedded as base64 WOFF.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import subprocess
import sys
import tempfile
from collections import OrderedDict
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "contributions.json"
OUT = ROOT / "cards"
FONTS = ROOT / "fonts"
STATIC = os.environ.get("STATIC") == "1"

# ── Palette and type, matched to avivashishta.com ────────────────────────────
PAPER = "#F3F3F1"
CARD = "#FBFBF9"
INK = "#111111"
MUTED = "#6E6E6A"
RULE = "#DEDED9"
BLUE = "#2F55FF"
RED = "#EF3B2D"
YELLOW = "#FFC81A"
BRAND = BLUE  # contribution graph + best month

SERIF = "Instrument Serif"
SERIF_IT = "Instrument Serif Italic"
SANS = "Geist"
SANS_MED = "Geist Medium"
MONO = "Geist Mono"
FONT_FILES = {
    SERIF: "InstrumentSerif-Regular.woff",
    SERIF_IT: "InstrumentSerif-Italic.woff",
    SANS: "Geist-Regular.ttf",
    SANS_MED: "Geist-Medium.ttf",
    MONO: "GeistMono-Regular.ttf",
}

# ── Content ──────────────────────────────────────────────────────────────────
SKILLS = [  # group label, skills; rendered as chips in cards/skills.svg
    ("Languages", ["TypeScript", "JavaScript", "Python", "Java", "C++", "SQL", "Solidity", "Bash"]),
    ("Frontend", ["React", "Next.js", "Tailwind CSS", "HTML", "CSS", "WebSockets", "WebRTC"]),
    ("Backend", ["Node.js", "Express", "Bun", "REST APIs", "JWT auth", "Cloudflare Workers", "Serverless",
                 "Turborepo", "Queues & pub/sub"]),
    ("Databases & ORM", ["PostgreSQL", "MongoDB", "MySQL", "Prisma", "Drizzle", "Zod"]),
    ("Cloud & DevOps", ["AWS (EC2, S3, Lambda, RDS, IAM, CloudWatch)", "Docker", "Kubernetes", "CI/CD",
                        "GitHub Actions", "Vercel", "Infrastructure as code", "Monitoring & observability",
                        "Reverse proxies", "CDNs & object stores", "Firecracker", "Linux", "Git", "GitHub", "Postman"]),
    ("AI & LLMs", ["Neural networks", "CNNs", "RNNs/LSTMs", "Attention (KV cache, GQA, MLA)", "Hugging Face", "RAG",
                   "Vector DBs", "Context engineering", "AI agents", "Agent memory", "Multimodal agents",
                   "Fine-tuning", "RL fine-tuning", "Evals", "LLM observability", "Manim", "FFmpeg"]),
    ("CS fundamentals", ["Data structures & algorithms", "OOP", "Design patterns", "System design",
                         "Distributed systems", "Async processing", "Data pipelines", "Operating systems", "DBMS"]),
    ("Web3", ["Solidity", "Smart contracts", "NFTs"]),
]

HERO = {
    "kicker": "HYDERABAD · FULL-STACK ENGINEER",
    "first": "Rahul",
    "last": "Misala",
    "line": "I turn ideas into products people use. Now building ELOFY.",
    "status": "Open to full-stack and SDE-1 roles · Hyderabad or remote",
    # Optional: drop a square photo at assets/portrait.png or .jpg and it replaces the board.
    "portrait": next((p for p in [ROOT / "assets/portrait.png", ROOT / "assets/portrait.jpg"] if p.exists()), None),
}

REPOS = [  # "repo" pulls stars/language/updated from the JSON when it is public
    {"file": "repo-elofy", "name": "ELOFY", "repo": None,
     "desc": "A structured chess curriculum from beginner to advanced: reading modules, board exercises and mastery tracking. Invite-only beta.",
     "tags": ["Next.js", "TypeScript", "PostgreSQL", "Vercel"], "colour": BLUE, "kicker": "NOW BUILDING"},
    {"file": "repo-algovision", "name": "AlgoVision", "repo": None,
     "desc": "Turns DSA concepts into animated explainer videos, with async job queues driving a Manim and FFmpeg render pipeline.",
     "tags": ["React", "Node.js", "Python", "Manim"], "colour": YELLOW, "kicker": "AI · VIDEO"},
    {"file": "repo-fdxchainge", "name": "FDXChainge", "repo": "FDXChainge",
     "desc": "NFT marketplace for tokenising and fractionally owning fixed deposits. Finalist, HackFiniti 2025.",
     "tags": ["React", "Express", "MongoDB", "Solidity"], "colour": RED, "kicker": "WEB3"},
    {"file": "repo-blog", "name": "Serverless Blog", "repo": "Blogging-website",
     "desc": "Full-stack blog on the edge, with type-safe validation shared between client and server.",
     "tags": ["TypeScript", "Workers", "Prisma", "Postgres"], "colour": BLUE, "kicker": "EDGE"},
]

# Start time of each card, so the page plays top to bottom.
T_HERO, T_GRAPH, T_ACTIVITY, T_SKILLS, T_REPOS = 0.0, 1.1, 2.0, 3.0, 5.1

EXTRA_GLYPHS = "→↗·—•↑★"

# ── Fonts ────────────────────────────────────────────────────────────────────
_font_cache: dict[str, str] = {}
_metrics: dict[str, TTFont] = {}


def font_face(family: str) -> str:
    """Subset to printable ASCII + a few symbols with pyftsubset, return an @font-face rule."""
    if family not in _font_cache:
        src = FONTS / FONT_FILES[family]
        chars = "".join(chr(c) for c in range(0x20, 0x7F)) + EXTRA_GLYPHS
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "f.woff"
            subprocess.run(
                [sys.executable, "-m", "fontTools.subset", str(src), f"--text={chars}",
                 "--flavor=woff", "--layout-features=kern,liga", "--no-hinting",
                 "--desubroutinize", f"--output-file={out}"],
                check=True,
            )
            b64 = base64.b64encode(out.read_bytes()).decode()
        _font_cache[family] = f"@font-face{{font-family:'{family}';src:url(data:font/woff;base64,{b64}) format('woff')}}"
    return _font_cache[family]


def text_width(s: str, family: str, size: float, tracking: float = 0) -> float:
    if family not in _metrics:
        _metrics[family] = TTFont(FONTS / FONT_FILES[family])
    f = _metrics[family]
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    w = sum(hmtx[cmap.get(ord(c), cmap[ord("?")])][0] for c in s)
    return w * size / upm + tracking * size * max(len(s) - 1, 0)


def wrap(s: str, family: str, size: float, width: float) -> list[str]:
    lines, cur = [], ""
    for word in s.split():
        nxt = f"{cur} {word}".strip()
        if cur and text_width(nxt, family, size) > width:
            lines.append(cur)
            cur = word
        else:
            cur = nxt
    return lines + [cur] if cur else lines


# ── SVG scaffolding ──────────────────────────────────────────────────────────
BASE_CSS = f"""
text{{font-kerning:normal}}
.serif{{font-family:'{SERIF}',Georgia,serif}}
.serif-it{{font-family:'{SERIF_IT}',Georgia,serif;font-style:normal}}
.sans{{font-family:'{SANS}',system-ui,sans-serif}}
.sans-med{{font-family:'{SANS_MED}','{SANS}',system-ui,sans-serif}}
.mono{{font-family:'{MONO}',ui-monospace,monospace;letter-spacing:.08em}}
.a{{animation-fill-mode:both;animation-timing-function:cubic-bezier(.2,.75,.25,1)}}
.fb{{transform-box:fill-box}}
.rise{{animation-name:rise;animation-duration:.8s}}
.fade{{animation-name:fade;animation-duration:.6s}}
.pop{{animation-name:pop;animation-duration:.35s;transform-origin:center}}
.grow{{animation-name:grow;animation-duration:.7s;transform-origin:50% 100%}}
.swing{{animation-name:swing;animation-duration:1.1s;transform-origin:50% 100%;animation-timing-function:cubic-bezier(.3,1.35,.45,1)}}
.nudge{{animation:nudge 2.4s ease-in-out infinite}}
.pulse{{animation:pulse 2s ease-in-out infinite;transform-origin:center}}
.ring{{opacity:0;animation:ring 3.2s ease-out infinite;transform-origin:center}}
.sweep{{opacity:0;animation:sweep 5s ease-in-out infinite}}
.rmo{{display:none}}
@keyframes rise{{from{{opacity:0;transform:translateY(22px)}}to{{opacity:1;transform:none}}}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes pop{{0%{{opacity:0;transform:scale(.2)}}70%{{opacity:1;transform:scale(1.15)}}100%{{opacity:1;transform:none}}}}
@keyframes grow{{from{{transform:scaleY(0)}}to{{transform:none}}}}
@keyframes swing{{0%{{opacity:0;transform:translateY(70px) rotate(-7deg)}}60%{{opacity:1;transform:translateY(-6px) rotate(1.5deg)}}100%{{opacity:1;transform:none}}}}
@keyframes nudge{{0%,70%,100%{{transform:none}}80%{{transform:translate(3px,-3px)}}90%{{transform:translate(0,0)}}}}
@keyframes pulse{{0%,100%{{opacity:1;transform:none}}50%{{opacity:.45;transform:scale(.8)}}}}
@keyframes ring{{0%{{opacity:.55;transform:scale(.4)}}45%,100%{{opacity:0;transform:scale(1.8)}}}}
@keyframes sweep{{0%{{opacity:0;transform:translateX(-120%)}}4%{{opacity:1}}26%{{opacity:1;transform:translateX(120%)}}27%,100%{{opacity:0;transform:translateX(120%)}}}}
"""

OFF_CSS = "*{animation:none!important}.smil{display:none!important}.rmo{display:inline!important}"


def svg(w: int, h: int, body: str, fonts: list[str], title: str) -> str:
    css = "".join(font_face(f) for f in fonts) + BASE_CSS
    css += OFF_CSS if STATIC else f"@media (prefers-reduced-motion:reduce){{{OFF_CSS}}}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="{escape(title)}"><title>{escape(title)}</title>'
        f"<style>{css}</style>{body}</svg>\n"
    )


def d(t: float) -> str:
    """Inline animation-delay."""
    return f'style="animation-delay:{t:.3f}s"'


def frame(w: int, h: int, fill: str = CARD, r: int = 14) -> str:
    return f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="{r}" fill="{fill}" stroke="{RULE}"/>'


def count_up(value: str, x: float, y: float, cls: str, size: int, fill: str, begin: float, anchor: str = "start") -> str:
    """Number that counts up from zero. CSS can't change text, so: one <text> per frame, each shown briefly by a SMIL <animate>."""
    final = f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}" fill="{fill}" text-anchor="{anchor}"'
    num = "".join(ch for ch in value if ch.isdigit())
    if STATIC or not num:
        return f"{final}>{escape(value)}</text>"
    target, suffix, n, dur = int(num), value[len(num):] if value.startswith(num) else "", 18, 0.05
    out = [f'<g class="smil">']
    for i in range(1, n + 1):
        v = round(target * (1 - (1 - i / n) ** 3))
        t = begin + (i - 1) * dur
        last = i == n
        setter = (f'<animate attributeName="opacity" values="1" begin="{t:.3f}s" dur="{dur}s"{" fill=\"freeze\"" if last else ""}/>')
        out.append(f'{final} opacity="0">{v}{escape(suffix) if last else ""}{setter}</text>')
    out.append("</g>")
    out.append(f'<g class="rmo">{final}>{escape(value)}</text></g>')
    return "".join(out)


# ── Data ─────────────────────────────────────────────────────────────────────
def load() -> dict:
    if not DATA.exists():
        sys.exit(f"{DATA} not found. Run: GITHUB_TOKEN=$(gh auth token) python scripts/fetch_contributions.py")
    data = json.loads(DATA.read_text())
    data["days"] = [{"date": date.fromisoformat(x["date"]), "count": x["count"]} for x in data["days"]]
    return data


def stats(days: list[dict]) -> dict:
    counts = [x["count"] for x in days]
    today_has = counts[-1] > 0
    cur, i = 0, len(counts) - 1 if today_has else len(counts) - 2
    while i >= 0 and counts[i] > 0:
        cur, i = cur + 1, i - 1
    best = run = 0
    for c in counts:
        run = run + 1 if c else 0
        best = max(best, run)
    busiest = max(days, key=lambda x: x["count"])
    months: OrderedDict[tuple[int, int], int] = OrderedDict()
    last = days[-1]["date"]
    for k in range(11, -1, -1):
        y, m = last.year, last.month - k
        while m <= 0:
            y, m = y - 1, m + 12
        months[(y, m)] = 0
    for x in days:
        key = (x["date"].year, x["date"].month)
        if key in months:
            months[key] += x["count"]
    return {"current": cur, "longest": best, "active": sum(1 for c in counts if c),
            "busiest": busiest, "months": months, "total": sum(counts), "span": len(counts)}


def mix(hex_a: str, hex_b: str, t: float) -> str:
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


# ── Cards ────────────────────────────────────────────────────────────────────
def hero() -> str:
    W, H = 840, 350
    t0 = T_HERO
    b = [frame(W, H)]
    b.append(f'<text x="48" y="64" class="mono a fade" font-size="12" fill="{MUTED}" {d(t0)}>{escape(HERO["kicker"])}</text>')
    b.append(f'<text x="44" y="150" class="serif a rise" font-size="96" fill="{INK}" {d(t0 + .15)}>{escape(HERO["first"])}</text>')
    last = escape(HERO["last"])
    b.append(f'<g class="a rise" {d(t0 + .35)}><text x="44" y="230" class="serif-it" font-size="96" fill="{INK}">{last}</text>')
    if not STATIC:  # shine: a gradient fill whose gradientTransform is animated with SMIL
        lw = text_width(HERO["last"], SERIF_IT, 96)
        b.append(
            f'<defs><linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="160" y2="0">'
            f'<stop offset="0" stop-color="{BLUE}" stop-opacity="0"/><stop offset=".5" stop-color="{BLUE}"/>'
            f'<stop offset="1" stop-color="{BLUE}" stop-opacity="0"/>'
            f'<animateTransform attributeName="gradientTransform" type="translate" values="-200 0;{44 + lw + 40:.0f} 0;{44 + lw + 40:.0f} 0" '
            f'keyTimes="0;.32;1" dur="4.5s" begin="{t0 + 1.4:.2f}s" repeatCount="indefinite"/></linearGradient></defs>'
            f'<text x="44" y="230" class="serif-it smil" font-size="96" fill="url(#shine)">{last}</text>')
    b.append("</g>")
    lines = wrap(HERO["line"], SANS, 18, 490)
    for i, ln in enumerate(lines):
        b.append(f'<text x="48" y="{272 + i * 26}" class="sans a rise" font-size="18" fill="{INK}" {d(t0 + .6 + i * .1)}>{escape(ln)}</text>')
    sy = 272 + (len(lines) - 1) * 26 + 34
    b.append(f'<g class="a fade" {d(t0 + .9)}><circle cx="53" cy="{sy - 4}" r="4.5" fill="{BLUE}" class="pulse fb"/>'
             f'<text x="66" y="{sy}" class="mono" font-size="11.5" fill="{MUTED}">{escape(HERO["status"])}</text></g>')

    # right side: portrait if present, else a chessboard that a knight hops across
    X, Y, S = 580, 52, 216
    if HERO["portrait"]:
        p = HERO["portrait"]
        mime = "image/png" if p.suffix == ".png" else "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode()
        b.append(f'<defs><clipPath id="pc"><rect x="{X}" y="{Y}" width="{S}" height="{S}" rx="10"/></clipPath></defs>'
                 f'<image href="data:{mime};base64,{b64}" x="{X}" y="{Y}" width="{S}" height="{S}" '
                 f'preserveAspectRatio="xMidYMid slice" clip-path="url(#pc)" style="filter:grayscale(1) contrast(1.05)"/>')
        rows = 24  # prints in row by row: paper strips that fade away top to bottom
        for r in range(rows):
            y = Y + r * S / rows
            b.append(f'<rect x="{X - 1}" y="{y:.2f}" width="{S + 2}" height="{S / rows + .6:.2f}" fill="{CARD}" '
                     f'class="a" style="animation:fade .25s reverse both;animation-delay:{t0 + .5 + r * .045:.3f}s;opacity:0"/>')
    else:
        sq = S / 8
        for r in range(8):
            for c in range(8):
                fill = mix(CARD, INK, .09) if (r + c) % 2 else mix(CARD, INK, .025)
                b.append(f'<rect x="{X + c * sq:.1f}" y="{Y + r * sq:.1f}" width="{sq:.1f}" height="{sq:.1f}" fill="{fill}" '
                         f'class="a pop fb" {d(t0 + .3 + (r + c) * .035)}/>')
        path = [(7, 1), (5, 2), (3, 3), (2, 5), (4, 6)]  # knight's route, rank/file in board coords
        cols = [BLUE, RED, YELLOW, BLUE, RED]
        for k, ((r, c), col) in enumerate(zip(path, cols)):
            cx, cy = X + c * sq + sq / 2, Y + r * sq + sq / 2
            b.append(f'<rect x="{X + c * sq + 3:.1f}" y="{Y + r * sq + 3:.1f}" width="{sq - 6:.1f}" height="{sq - 6:.1f}" rx="3" '
                     f'fill="{col}" class="a pop fb" {d(t0 + 1.0 + k * .22)}/>')
            if k:
                pr, pc_ = path[k - 1]
                px, py = X + pc_ * sq + sq / 2, Y + pr * sq + sq / 2
                b.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{cx:.1f}" y2="{cy:.1f}" stroke="{INK}" stroke-width="1.4" '
                         f'stroke-dasharray="3 4" class="a fade" {d(t0 + .95 + k * .22)}/>')
        b.append(f'<text x="{X + S}" y="{Y + S + 22}" text-anchor="end" class="mono a fade" font-size="10.5" fill="{MUTED}" '
                 f'{d(t0 + 2)}>ELOFY · STOP GUESSING WHAT TO STUDY</text>')
    return svg(W, H, "".join(b), [SERIF, SERIF_IT, SANS, MONO], f'{HERO["first"]} {HERO["last"]}')


def graph(data: dict, st: dict) -> str:
    days = data["days"]
    lead = (days[0]["date"].weekday() + 1) % 7  # GitHub weeks start on Sunday
    cells = [None] * lead + days
    weeks = math.ceil(len(cells) / 7)
    X0, Y0 = 62, 84
    step = (840 - X0 - 30) / weeks
    cell = step - 3
    W, H = 840, Y0 + 7 * step + 40
    maxc = max(x["count"] for x in days) or 1
    levels = [mix(PAPER, INK, .07)] + [mix(CARD, BRAND, t) for t in (.3, .55, .8, 1)]

    def level(c: int) -> int:
        if c == 0:
            return 0
        return min(4, 1 + int(3.999 * c / maxc)) if maxc > 4 else min(4, c)

    t0 = T_GRAPH
    b = [frame(W, H)]
    b.append(f'<text x="32" y="44" class="mono a fade" font-size="12" fill="{MUTED}" {d(t0)}>CONTRIBUTIONS · LAST 12 MONTHS</text>')
    b.append(f'<text x="{W - 32}" y="48" text-anchor="end" class="serif a rise" font-size="34" fill="{INK}" {d(t0 + .1)}>'
             f'{st["total"]:,} <tspan class="serif-it" fill="{BRAND}">contributions</tspan></text>')
    for i, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        b.append(f'<text x="30" y="{Y0 + i * step + cell - 2:.1f}" class="mono a fade" font-size="9.5" fill="{MUTED}" {d(t0 + .2)}>{name}</text>')
    seen = None
    for w in range(weeks):
        col = [x for x in cells[w * 7:(w + 1) * 7]]
        first = next((x for x in col if x), None)
        if first and first["date"].month != seen and first["date"].day <= 7 and w < weeks - 1:
            seen = first["date"].month
            b.append(f'<text x="{X0 + w * step:.1f}" y="{Y0 - 10}" class="mono a fade" font-size="9.5" fill="{MUTED}" '
                     f'{d(t0 + .2 + w * .016)}>{first["date"].strftime("%b")}</text>')
        for r, x in enumerate(col):
            if not x:
                continue
            b.append(f'<rect x="{X0 + w * step:.1f}" y="{Y0 + r * step:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2.5" '
                     f'fill="{levels[level(x["count"])]}" class="a pop fb" {d(t0 + .25 + w * .018 + r * .006)}/>')
    lx = W - 32 - 5 * step - 70
    ly = H - 20
    b.append(f'<g class="a fade" {d(t0 + 1.3)}><text x="{lx}" y="{ly + 9}" class="mono" font-size="9.5" fill="{MUTED}">LESS</text>')
    for i, c in enumerate(levels):
        b.append(f'<rect x="{lx + 38 + i * step:.1f}" y="{ly}" width="{cell:.1f}" height="{cell:.1f}" rx="2.5" fill="{c}"/>')
    b.append(f'<text x="{lx + 42 + 5 * step:.0f}" y="{ly + 9}" class="mono" font-size="9.5" fill="{MUTED}">MORE</text></g>')
    return svg(W, H, "".join(b), [SERIF, SERIF_IT, MONO], f"{st['total']} contributions in the last year")


def activity(st: dict) -> str:
    W, H = 840, 330
    t0 = T_ACTIVITY
    b = [frame(W, H)]
    b.append(f'<text x="32" y="44" class="mono a fade" font-size="12" fill="{MUTED}" {d(t0)}>CONTRIBUTIONS PER MONTH</text>')
    months = list(st["months"].items())
    peak_key, peak = max(months, key=lambda kv: kv[1])
    X0, base, bw, slot, maxh = 32, 268, 26, 40, 170
    b.append(f'<line x1="{X0}" y1="{base + .5}" x2="{X0 + 12 * slot - 14}" y2="{base + .5}" stroke="{RULE}" class="a fade" {d(t0)}/>')
    for i, ((y, m), v) in enumerate(months):
        h = max(2, maxh * v / peak) if peak else 2
        x = X0 + i * slot
        is_peak = (y, m) == peak_key and peak > 0
        fill = BRAND if is_peak else mix(CARD, INK, .82)
        b.append(f'<rect x="{x}" y="{base - h:.1f}" width="{bw}" height="{h:.1f}" rx="3" fill="{fill}" class="a grow fb" '
                 f'{d(t0 + .15 + i * .06)}/>')
        b.append(f'<text x="{x + bw / 2}" y="{base + 20}" text-anchor="middle" class="mono a fade" font-size="9.5" '
                 f'fill="{INK if is_peak else MUTED}" {d(t0 + .15 + i * .06)}>{date(y, m, 1).strftime("%b").upper()}</text>')
        if is_peak:
            b.append(f'<text x="{x + bw / 2}" y="{base - h - 10:.1f}" text-anchor="middle" class="serif a pop fb" font-size="26" '
                     f'fill="{BRAND}" {d(t0 + 1.1)}>{v}</text>')
    # stat column
    SX = 540
    b.append(f'<line x1="{SX - 24}" y1="40" x2="{SX - 24}" y2="{H - 40}" stroke="{RULE}" class="a fade" {d(t0 + .3)}/>')
    busiest = st["busiest"]
    rows = [
        ("CURRENT STREAK", f'{st["current"]}', "days" if st["current"] != 1 else "day"),
        ("LONGEST STREAK", f'{st["longest"]}', "days"),
        ("ACTIVE DAYS", f'{st["active"]}', f'of {st["span"]}'),
        ("BUSIEST DAY", f'{busiest["count"]}', busiest["date"].strftime("on %-d %b %Y")),
    ]
    for i, (label, val, unit) in enumerate(rows):
        y = 70 + i * 66
        tb = t0 + .5 + i * .15
        b.append(f'<text x="{SX}" y="{y}" class="mono a fade" font-size="10.5" fill="{MUTED}" {d(tb)}>{label}</text>')
        b.append(f'<g class="a rise" {d(tb)}>{count_up(val, SX, y + 38, "serif", 40, INK, tb + .1)}</g>')
        vw = text_width(val, SERIF, 40)
        b.append(f'<text x="{SX + vw + 10:.0f}" y="{y + 37}" class="sans a fade" font-size="14" fill="{MUTED}" {d(tb + .4)}>{escape(unit)}</text>')
    return svg(W, H, "".join(b), [SERIF, SANS, MONO], "Monthly contributions, streak and busiest day")


def skills() -> str:
    W = 840
    CX, RIGHT = 184, W - 32             # chips wrap between CX and RIGHT; labels sit left of CX
    CH, GAP, ROW = 22, 6, 28            # chip height, gap between chips, row pitch
    STEP, GROUP_GAP = .02, .05          # stagger per chip, extra pause between groups
    t = T_SKILLS + .1
    cols = [BLUE, RED, YELLOW]
    missing = {c for _, items in SKILLS for s in items for c in s if not (" " <= c <= "~" or c in EXTRA_GLYPHS)}
    assert not missing, f"SKILLS uses glyphs outside the font subset: {missing}"
    body, y = [], 68
    for g, (label, items) in enumerate(SKILLS):
        if g:
            body.append(f'<line x1="32" y1="{y - 11.5}" x2="{RIGHT}" y2="{y - 11.5}" stroke="{RULE}" class="a fade" {d(t)}/>')
        body.append(f'<g class="a fade" {d(t)}><rect x="32" y="{y + 9}" width="14" height="4" rx="2" fill="{cols[g % 3]}"/>'
                    f'<text x="54" y="{y + 15}" class="mono" font-size="10.5" fill="{MUTED}">{escape(label.upper())}</text></g>')
        x, row_y = CX, y
        for s in items:
            w = text_width(s, MONO, 10, .08) + 18
            if x > CX and x + w > RIGHT:
                x, row_y = CX, row_y + ROW
            body.append(f'<g class="a pop fb" {d(t)}><rect x="{x:.1f}" y="{row_y}" width="{w:.1f}" height="{CH}" rx="11" '
                        f'fill="none" stroke="{RULE}"/><text x="{x + 9:.1f}" y="{row_y + 15}" class="mono" font-size="10" '
                        f'fill="{INK}">{escape(s)}</text></g>')
            x += w + GAP
            t += STEP
        t += GROUP_GAP
        y = row_y + CH + 24
    H = y - 24 + 32
    b = [frame(W, H), f'<text x="32" y="44" class="mono a fade" font-size="12" fill="{MUTED}" {d(T_SKILLS)}>SKILLS · TOOLS I SHIP WITH</text>']
    names = ", ".join(s for _, items in SKILLS for s in items)
    return svg(W, H, "".join(b + body), [MONO], f"Skills: {names}")


def repo(r: dict, idx: int, data: dict) -> str:
    W, H = 410, 250
    t0 = T_REPOS + idx * .15
    meta = data.get("repos", {}).get(r["repo"] or "", {})
    b = [frame(W, H), f'<g class="a rise" {d(t0)}>',
         f'<rect x="24" y="28" width="28" height="4" rx="2" fill="{r["colour"]}"/>',
         f'<text x="62" y="34" class="mono" font-size="10.5" fill="{MUTED}">{escape(r["kicker"])}</text>',
         f'<g class="nudge" style="animation-delay:{t0 + 1.3:.2f}s"><text x="{W - 24}" y="38" text-anchor="end" class="sans" font-size="18" fill="{INK}">↗</text></g>',
         f'<text x="22" y="80" class="serif" font-size="38" fill="{INK}">{escape(r["name"])}</text></g>']
    for i, ln in enumerate(wrap(r["desc"], SANS, 13.5, W - 48)[:3]):
        b.append(f'<text x="24" y="{110 + i * 20}" class="sans a fade" font-size="13.5" fill="{INK}" {d(t0 + .25 + i * .06)}>{escape(ln)}</text>')
    x = 24
    for i, tag in enumerate(r["tags"]):
        w = text_width(tag.upper(), MONO, 10, .08) + 18
        b.append(f'<g class="a pop fb" {d(t0 + .5 + i * .07)}><rect x="{x}" y="{H - 74}" width="{w:.0f}" height="22" rx="11" '
                 f'fill="none" stroke="{RULE}"/><text x="{x + 9}" y="{H - 59}" class="mono" font-size="10" fill="{INK}">{escape(tag.upper())}</text></g>')
        x += w + 6
    foot = []
    if meta.get("language"):
        foot.append(meta["language"])
    if meta:
        foot.append(f'★ {meta.get("stars", 0)}')
        if meta.get("pushed_at"):
            foot.append("updated " + datetime.fromisoformat(meta["pushed_at"].replace("Z", "+00:00")).strftime("%b %Y"))
    if foot:
        b.append(f'<text x="24" y="{H - 24}" class="mono a fade" font-size="9.5" fill="{MUTED}" '
                 f'{d(t0 + .8)}>{escape(" · ".join(foot)).upper()}</text>')
    return svg(W, H, "".join(b), [SERIF, SANS, MONO], f'{r["name"]}: {r["desc"]}')


def main() -> None:
    data = load()
    st = stats(data["days"])
    OUT.mkdir(exist_ok=True)
    files = {"hero.svg": hero(), "graph.svg": graph(data, st), "activity.svg": activity(st)}
    files["skills.svg"] = skills()
    for i, r in enumerate(REPOS):
        files[f'{r["file"]}.svg'] = repo(r, i, data)
    for name, content in files.items():
        (OUT / name).write_text(content)
        print(f"cards/{name:22} {len(content) / 1024:6.1f} KB")
    print("mode:", "STATIC (final frame)" if STATIC else "animated")


if __name__ == "__main__":
    main()
