"""Render the neofetch-style profile header as SVG (dark + light).

Runs daily in GitHub Actions (see .github/workflows/header.yml). Needs no extra
secrets: the GITHUB_TOKEN of the workflow is enough for public profile data,
and private contributions are already counted on the public profile.
"""
import datetime as dt
import json
import os
import re
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER = "Dolcruz"
BIRTH = dt.date(2004, 11, 1)
WIDTH = 60  # characters per info line

THEMES = {
    "dark": dict(bg="#0d1117", border="#30363d", art="#8b949e", text="#c9d1d9",
                 key="#ffa657", value="#a5d6ff", dots="#484f58", accent="#7ee787"),
    "light": dict(bg="#f6f8fa", border="#d0d7de", art="#57606a", text="#24292f",
                  key="#953800", value="#0a3069", dots="#afb8c1", accent="#116329"),
}


def uptime(today: dt.date) -> str:
    years = today.year - BIRTH.year - ((today.month, today.day) < (BIRTH.month, BIRTH.day))
    months = (today.month - BIRTH.month - (today.day < BIRTH.day)) % 12
    anchor = today.replace(day=1) if today.day >= BIRTH.day else (
        today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    days = (today - anchor.replace(day=min(BIRTH.day, 28))).days
    plural = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return f"{plural(years, 'year')}, {plural(months, 'month')}, {plural(days, 'day')}"


def github_stats() -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        cached = ROOT / "assets" / "stats.json"
        return json.loads(cached.read_text()) if cached.exists() else {}
    query = """query($login:String!){user(login:$login){
      repositories(privacy:PUBLIC, ownerAffiliations:OWNER){totalCount}
      contributionsCollection{contributionCalendar{totalContributions
        weeks{contributionDays{contributionCount}}}}}}"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    user = json.load(urllib.request.urlopen(req))["data"]["user"]
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [d["contributionCount"] for w in cal["weeks"] for d in w["contributionDays"]]
    stats = {
        "repos": user["repositories"]["totalCount"],
        "contributions": cal["totalContributions"],
        "active_days": sum(1 for c in days if c),
    }
    (ROOT / "assets" / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    return stats


def info_lines(today: dt.date, s: dict) -> list:
    """Each entry: ('title', text) | ('kv', key, value) | ('pair', k1, v1, k2, v2) | ('blank',)"""
    return [
        ("title", "falk@pfisterer"),
        ("kv", "OS", "Windows 11, Android, ESP32"),
        ("kv", "Uptime", uptime(today)),
        ("kv", "Location", "Heidelberg, Germany"),
        ("kv", "Day job", "AI defect detection @ PreserviTec"),
        ("kv", "Study", "B.Sc. Geography, Heidelberg University"),
        ("blank",),
        ("kv", "Builds", "desktop apps, games, robots, websites"),
        ("kv", "Agents", "Claude Code + Codex"),
        ("kv", "Languages", "Python, TypeScript, C#, C++"),
        ("kv", "Hobbies", "building things, tinkering with tech"),
        ("blank",),
        ("section", "Contact"),
        ("kv", "Web", "pfisterer-portfolio.com"),
        ("kv", "Email", "pfistererfalk@gmail.com"),
        ("kv", "LinkedIn", "falk-pfisterer"),
        ("blank",),
        ("section", "GitHub"),
        ("pair", "Repos", f"{s.get('repos', '?')} public", "Active days", f"{s.get('active_days', '?')}"),
        ("kv", "Contributions (last year)", f"{s.get('contributions', '?'):,}" if s else "?"),
    ]


def dotted(key: str, value: str, width: int) -> tuple:
    dots = max(2, width - len(key) - len(value) - 4)
    return key, " " + "." * dots + " ", value


def render(theme: str, today: dt.date, stats: dict) -> str:
    c = THEMES[theme]
    art = (ROOT / "assets" / "ascii.txt").read_text(encoding="utf-8").splitlines()
    info = info_lines(today, stats)
    fs, lh, cw = 14, 19, 8.43  # info: font size, line height, monospace advance (~0.6em)
    afs, alh = 10, 12  # art: smaller glyphs = more detail
    pad = 28
    art_w = max(map(len, art)) * afs * 0.602
    info_x = pad + art_w + 28
    h = round(max(len(art) * alh, len(info) * lh) + 2 * pad)
    w = round(info_x + WIDTH * cw + pad)
    art_top = (h - len(art) * alh) / 2
    info_top = (h - len(info) * lh) / 2

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
           f'font-family="ui-monospace, SFMono-Regular, Consolas, \'DejaVu Sans Mono\', monospace" '
           f'font-size="{fs}px">',
           f'<style>.k{{fill:{c["key"]}}}.v{{fill:{c["value"]}}}.d{{fill:{c["dots"]}}}'
           f'.t{{fill:{c["text"]}}}.a{{fill:{c["accent"]}}}text{{white-space:pre}}</style>',
           f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" fill="{c["bg"]}" stroke="{c["border"]}"/>',
           f'<text x="{pad}" y="{art_top}" fill="{c["art"]}" font-size="{afs}px">']
    for i, line in enumerate(art):
        # dense glyphs (the dark bands of the avatar) brighter than the thin strokes
        runs = re.findall(r"[#%@*]+|[^#%@*]+", line)
        body = "".join(f'<tspan class="t">{escape(r)}</tspan>' if r[0] in "#%@*" else escape(r) for r in runs)
        out.append(f'<tspan x="{pad}" y="{art_top + (i + 0.8) * alh:.1f}">{body}</tspan>')
    out.append("</text>")

    for i, item in enumerate(info):
        y = info_top + (i + 0.8) * lh
        kind = item[0]
        spans = []
        if kind == "title":
            rule = " " + "─" * (WIDTH - len(item[1]) - 1)
            spans = [("a", item[1]), ("d", rule)]
        elif kind == "section":
            rule = " " + "─" * (WIDTH - len(item[1]) - 3)
            spans = [("t", "- "), ("t", item[1]), ("d", rule)]
        elif kind == "kv":
            k, d, v = dotted(item[1] + ":", item[2], WIDTH)
            spans = [("d", ". "), ("k", k), ("d", d), ("v", v)]
        elif kind == "pair":
            half = (WIDTH - 1) // 2  # both halves + ". " + " | " == WIDTH
            k1, d1, v1 = dotted(item[1] + ":", item[2], half)
            k2, d2, v2 = dotted(item[3] + ":", item[4], WIDTH - 1 - half)
            spans = [("d", ". "), ("k", k1), ("d", d1), ("v", v1), ("d", " | "),
                     ("k", k2), ("d", d2), ("v", v2)]
        if spans:
            body = "".join(f'<tspan class="{cl}">{escape(t)}</tspan>' for cl, t in spans)
            out.append(f'<text x="{info_x:.1f}" y="{y:.1f}">{body}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    today = dt.date.today()
    stats = github_stats()
    for theme in THEMES:
        (ROOT / f"header-{theme}.svg").write_text(render(theme, today, stats), encoding="utf-8")
    print(today, stats)


if __name__ == "__main__":
    main()
