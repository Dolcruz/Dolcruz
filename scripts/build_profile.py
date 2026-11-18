"""Build the whole profile: SVG cards (dark + light) and README.md from profile.json.

Cards: hero (contribution waveform + stats), one tile per project, an "also built" list
and link chips. The neofetch block comes from build_header.py. Every card is its own
linked image (GitHub strips CSS), fonts and media are embedded as data URIs (an SVG used
as <img> cannot load anything external), and every README reference carries a content
hash so GitHub's image cache never shows stale numbers.

Deterministic: same data -> byte-identical files, so the daily Action only commits when
something actually changed.

Run locally:  GH_TOKEN=$(gh auth token) python scripts/build_profile.py
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import urllib.request
from datetime import date
from html import escape
from pathlib import Path

import build_header  # neofetch block

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "profile" / "generated"
CFG = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
USER = CFG["handle"]

THEMES = {
    "dark": dict(bg="#0d1117", panel="#0d1117", bar="#161b22", line="#30363d", text="#e6edf3", muted="#8b949e",
                 faint="#6e7681", warm="#ffa657", cool="#58a6ff", green="#7ee787", cta_text="#0d1117",
                 media_bg="#161b22"),
    "light": dict(bg="#ffffff", panel="#ffffff", bar="#f6f8fa", line="#d0d7de", text="#1f2328", muted="#59636e",
                  faint="#818b98", warm="#bc4c00", cool="#0969da", green="#1a7f37", cta_text="#ffffff",
                  media_bg="#161b22"),
}
MONO = "JBM, ui-monospace, Consolas, monospace"
SANS = "IN, 'Segoe UI', Helvetica, Arial, sans-serif"


# ----------------------------------------------------------------------------- helpers
def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


FONT_FILES = {  # only the faces a card actually uses get embedded
    ("JBM", 400): "jetbrains-mono-400.woff2",
    ("JBM", 500): "jetbrains-mono-500.woff2",
    ("IN", 600): "inter-600.woff2",
}


def font_css(body: str) -> str:
    css = ""
    for (fam, weight), name in FONT_FILES.items():
        used = ('class="s"' in body) if fam == "IN" else (
            'class="m"' in body and (('font-weight="500"' in body) if weight == 500 else True))
        if used:
            css += ("@font-face{font-family:%s;font-weight:%d;src:url(data:font/woff2;base64,%s) format('woff2')}"
                    % (fam, weight, b64(ROOT / "assets" / "fonts" / name)))
    return css


def svg(w: int, h: int, title: str, body: str, c: dict) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">'
        f"<title>{escape(title)}</title><style>{font_css(body)}"
        f".m{{font-family:{MONO}}}.s{{font-family:{SANS};font-weight:600}}</style>"
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" fill="{c["panel"]}" stroke="{c["line"]}"/>'
        f"{body}</svg>\n"
    )


def text(x, y, s, c, size=13, color="text", cls="m", anchor="start", weight=None, ls=None) -> str:
    extra = f' font-weight="{weight}"' if weight else ""
    extra += f' letter-spacing="{ls}"' if ls else ""
    return (f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}" fill="{c[color]}" '
            f'text-anchor="{anchor}"{extra}>{escape(s)}</text>')


def wrap(s: str, max_chars: int) -> list:
    words, lines, cur = s.split(), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    return lines + ([cur] if cur else [])


def hline(x1, x2, y, c) -> str:
    return f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{c["line"]}"/>'


def vline(x, y1, y2, c) -> str:
    return f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="{c["line"]}"/>'


def mix(a: str, b: str, t: float) -> str:
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


# ----------------------------------------------------------------------------- data
def gql(query: str, variables: dict) -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    out = json.load(urllib.request.urlopen(req))
    if "errors" in out:
        raise RuntimeError(out["errors"])
    return out["data"]


def fetch() -> dict:
    cache = ROOT / "profile" / "data.json"
    if not (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")):
        return json.loads(cache.read_text(encoding="utf-8"))
    repos = [p["repo"] for p in CFG["projects"]] + [a["repo"] for a in CFG["also_built"]]
    fields = "\n".join(
        f'r{i}: repository(owner:$login, name:"{r}") {{ name primaryLanguage {{ name }} '
        f"latestRelease {{ tagName }} pushedAt }}"
        for i, r in enumerate(repos)
    )
    q = ("query($login:String!){ user(login:$login){ repositories(privacy:PUBLIC, ownerAffiliations:OWNER){totalCount} "
         "contributionsCollection{ contributionCalendar{ totalContributions "
         "weeks{ contributionDays{ date contributionCount } } } } } " + fields + " }")
    d = gql(q, {"login": USER})
    cal = d["user"]["contributionsCollection"]["contributionCalendar"]
    days = [(x["date"], x["contributionCount"]) for w in cal["weeks"] for x in w["contributionDays"]]
    data = {
        "repos_public": d["user"]["repositories"]["totalCount"],
        "contributions": cal["totalContributions"],
        "active_days": sum(1 for _, n in days if n),
        "days": days,
        "repo": {
            v["name"]: {
                "language": (v.get("primaryLanguage") or {}).get("name"),
                "release": (v.get("latestRelease") or {}).get("tagName"),
                "pushed": (v.get("pushedAt") or "")[:10],
            }
            for k, v in d.items() if k.startswith("r") and v
        },
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return data


def month(iso: str) -> str:
    y, m, _ = iso.split("-")
    return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m) - 1] + f" {y}"


# ----------------------------------------------------------------------------- hero
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def waveform(days: list, x0: int, y0: int, w: int, h: int, c: dict, cell: int = 5) -> str:
    """Dithered waveform of the last year's contributions (old -> new, left -> right)."""
    vals = [n for _, n in days]
    cols, rows = w // cell, h // cell
    # resample to one value per column, then smooth
    raw = [vals[min(len(vals) - 1, int(i * len(vals) / cols))] for i in range(cols)]
    sig = 2.2
    k = [math.exp(-(j * j) / (2 * sig * sig)) for j in range(-6, 7)]
    sm = [sum(raw[min(cols - 1, max(0, i + j - 6))] * k[j] for j in range(13)) / sum(k) for i in range(cols)]
    top = max(sm) or 1.0
    groups: dict = {}
    for ci in range(cols):
        a = 0.10 + 0.82 * math.sqrt(sm[ci] / top)
        a *= 0.9 + 0.1 * math.sin(ci * 0.55) * math.sin(ci * 0.13)   # a little texture on the edge
        tint = ci / max(1, cols - 1)
        for ri in range(rows):
            y = abs((ri + 0.5) / rows * 2 - 1)                            # 0 at the centre line
            glow = math.exp(-((y / max(a, 0.06)) ** 2) * 1.6)
            if y > a:
                glow *= 0.35
            t = (BAYER[ri % 4][ci % 4] + 0.5) / 16
            if glow < t * 0.85 + 0.06:
                continue
            lvl = 2 if glow > 0.72 else 1 if glow > 0.42 else 0
            step = min(7, int(tint * 8))
            groups.setdefault((step, lvl), []).append((ci, ri))
    out = []
    for (step, lvl), cells in sorted(groups.items()):
        base = mix(c["cool"], c["warm"], (step + 0.5) / 8)
        col = mix(c["bg"], base, (0.35, 0.65, 1.0)[lvl])
        d = "".join(f"M{x0 + ci * cell} {y0 + ri * cell}h{cell - 1}v{cell - 1}h-{cell - 1}z" for ci, ri in cells)
        out.append(f'<path d="{d}" fill="{col}"/>')
    return "".join(out)


def hero(data: dict, c: dict) -> str:
    W, H = 1000, 410
    b = []
    # top bar
    b.append(f'<rect x="1" y="1" width="{W - 2}" height="36" fill="{c["bar"]}"/>' + hline(0, W, 37, c))
    b.append(text(18, 24, "falk@pfisterer", c, 13, "text", weight=500))
    b.append(f'<rect x="150" y="14" width="7" height="7" fill="{c["warm"]}"/>')
    b.append(text(164, 24, CFG["status"], c, 12, "warm", weight=500, ls="1.5"))
    b.append(text(W - 18, 24, f"github.com/{USER}", c, 12, "muted", anchor="end"))
    # banner
    b.append(waveform(data["days"], 10, 47, W - 20, 120, c))
    first, last = data["days"][0][0], data["days"][-1][0]
    b.append(text(18, 186, month(first), c, 11, "faint"))
    b.append(text(W / 2, 186, f"{data['contributions']:,} contributions in the last 12 months", c, 11, "faint", anchor="middle"))
    b.append(text(W - 18, 186, month(last), c, 11, "faint", anchor="end"))
    b.append(hline(0, W, 198, c))
    # identity
    b.append(text(26, 268, CFG["name"], c, 54, "text", cls="s", ls="-1"))
    b.append(text(28, 298, CFG["tagline"], c, 15, "muted"))
    # optional rows (e.g. "now" only makes sense while someone keeps it current)
    rows = [(k.upper(), CFG[k]) for k in ("now", "based") if CFG.get(k)]
    for j, (k, v) in enumerate(rows):
        y = 372 - (len(rows) - 1 - j) * 28
        b.append(text(28, y, k, c, 11, "faint", ls="1.5"))
        b.append(text(110, y, v, c, 13, "text"))
    # stat cells (2 x 2)
    gx, gw, gy, gh = 600, 400, 198, (H - 198) / 2
    b.append(vline(gx, gy, H, c) + vline(gx + gw / 2, gy, H, c) + hline(gx, W, gy + gh, c))
    cells = [
        ("CONTRIBUTIONS (1Y)", f"{data['contributions']:,}"),
        ("ACTIVE DAYS", str(data["active_days"])),
        ("PROJECTS SHIPPED", str(len(CFG["projects"]) + len(CFG["also_built"]))),
        ("AGENTS", CFG["agents"]),
    ]
    for i, (k, v) in enumerate(cells):
        cx, cy = gx + (i % 2) * gw / 2 + 20, gy + (i // 2) * gh
        b.append(text(cx, cy + 34, k, c, 10.5, "faint", ls="1.2"))
        size = 26 if len(v) < 8 else 13
        b.append(text(cx, cy + 34 + (38 if size > 20 else 30), v, c, size, "cool" if size > 20 else "text", weight=500))
    alt = f"{CFG['name']}: {CFG['tagline']} {data['contributions']} contributions in the last year."
    return svg(W, H, alt, "".join(b), c)


# ----------------------------------------------------------------------------- tiles
def tile(i: int, p: dict, info: dict, c: dict) -> tuple:
    W, H = 500, 560
    mh = 312  # 16:10 media
    b = [f'<rect x="1" y="1" width="{W - 2}" height="32" fill="{c["bar"]}"/>' + hline(0, W, 33, c)]
    b.append(text(16, 22, f"{i:02d}", c, 12, "warm", weight=500))
    b.append(text(44, 22, p["repo"], c, 12, "text", weight=500))
    b.append(text(W - 16, 22, p["kind"], c, 11, "muted", anchor="end"))
    my = 34
    if p.get("media"):
        path = ROOT / p["media"]
        mime = {"gif": "gif", "jpg": "jpeg", "jpeg": "jpeg", "png": "png"}[path.suffix[1:].lower()]
        b.append(f'<rect x="1" y="{my}" width="{W - 2}" height="{mh}" fill="{c["media_bg"]}"/>')
        b.append(f'<image x="1" y="{my}" width="{W - 2}" height="{mh}" preserveAspectRatio="xMidYMid slice" '
                 f'href="data:image/{mime};base64,{b64(path)}"/>')
    else:  # metric tile
        m = p["metric"]
        b.append(f'<rect x="1" y="{my}" width="{W - 2}" height="{mh}" fill="{c["bar"]}"/>')
        b.append(text(28, my + 92, m["value"], c, 60, "green", weight=500, ls="-1"))
        b.append(text(30, my + 122, m["label"], c, 13, "muted"))
        for j, (n, label) in enumerate(m["rows"]):
            y = my + 200 + j * 30
            b.append(text(92, y, n, c, 15, "cool", anchor="end", weight=500))
            b.append(text(108, y, label, c, 13, "muted"))
    b.append(hline(0, W, my + mh, c))
    # title + text
    ty = my + mh
    b.append(text(18, ty + 36, p["title"], c, 22, "text", cls="s"))
    for j, line in enumerate(wrap(p["text"], 60)[:2]):
        b.append(text(18, ty + 60 + j * 19, line, c, 13, "muted"))
    # meta row
    my2 = ty + 104
    b.append(hline(0, W, my2, c))
    meta = [("LANGUAGE", info.get("language") or "—"), ("RELEASE", info.get("release") or "—"),
            ("PLATFORM", {"web app": "web", "windows app": "windows", "robot": "esp32", "research": "paper"}.get(p["kind"], p["kind"]))]
    for j, (k, v) in enumerate(meta):
        cx = 18 + j * (W / 3)
        if j:
            b.append(vline(j * W / 3, my2, my2 + 56, c))
        b.append(text(cx, my2 + 22, k, c, 10, "faint", ls="1.2"))
        b.append(text(cx, my2 + 43, v, c, 13, "text", weight=500))
    b.append(hline(0, W, my2 + 56, c))
    # call to action
    if info.get("release"):
        label, href = "DOWNLOAD", f"https://github.com/{USER}/{p['repo']}/releases/latest"
    else:
        label, href = "VIEW SOURCE", f"https://github.com/{USER}/{p['repo']}"
    bw, by = 150, H - 46
    b.append(f'<rect x="{W - 16 - bw}" y="{by}" width="{bw}" height="32" fill="{c["warm"]}"/>')
    b.append(text(W - 16 - bw / 2, by + 21, label + (" ↓" if label == "DOWNLOAD" else " ↗"), c, 12, "cta_text",
                  anchor="middle", weight=500, ls="1.5"))
    if info.get("release"):
        b.append(text(18, by + 21, "+ source code on GitHub", c, 11, "faint"))
    alt = f"{p['title']}: {p['text']}"
    return svg(W, H, alt, "".join(b), c), href, alt


# ----------------------------------------------------------------------------- list + chips
def also_built(data: dict, c: dict) -> str:
    W = 1000
    rows = CFG["also_built"]
    H = 44 + len(rows) * 40 + 8
    b = [f'<rect x="1" y="1" width="{W - 2}" height="34" fill="{c["bar"]}"/>' + hline(0, W, 35, c)]
    b.append(text(18, 23, "ALSO BUILT", c, 11, "warm", weight=500, ls="1.5"))
    b.append(text(W - 18, 23, f"{data['repos_public']} public repositories", c, 11, "muted", anchor="end"))
    for j, a in enumerate(rows):
        info = data["repo"].get(a["repo"], {})
        y = 44 + j * 40
        if j:
            b.append(hline(18, W - 18, y, c))
        b.append(text(18, y + 25, a["repo"], c, 13, "text", weight=500))
        b.append(text(260, y + 25, a["text"], c, 13, "muted"))
        b.append(text(W - 250, y + 25, info.get("language") or "", c, 12, "cool"))
        if info.get("pushed"):
            b.append(text(W - 18, y + 25, month(info["pushed"]), c, 12, "faint", anchor="end"))
    return svg(W, H, "Also built: " + ", ".join(a["repo"] for a in rows), "".join(b), c)


def chip(label: str, c: dict) -> str:
    W = max(170, 56 + round(len(label) * 7.3))
    body = (f'<rect x="12" y="13" width="9" height="9" fill="none" stroke="{c["muted"]}"/>'
            + text(30, 23, label, c, 12, "text") + text(W - 12, 23, "↗", c, 12, "muted", anchor="end"))
    return svg(W, 36, label, body, c)


# ----------------------------------------------------------------------------- README
def write(name: str, theme: str, content: str) -> str:
    GEN.mkdir(parents=True, exist_ok=True)
    (GEN / f"{name}-{theme}.svg").write_text(content, encoding="utf-8")
    return hashlib.sha1(content.encode()).hexdigest()[:10]


def picture(name: str, ver: str, alt: str, width: str) -> str:
    p = f"./profile/generated/{name}"
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{p}-dark.svg?v={ver}">'
            f'<source media="(prefers-color-scheme: light)" srcset="{p}-light.svg?v={ver}">'
            f'<img src="{p}-dark.svg?v={ver}"{f' width="{width}"' if width else ""} alt="{escape(alt)}"></picture>')


def build_all(theme_map=THEMES) -> None:
    data = fetch()
    parts, vers = {}, {}
    for theme, c in theme_map.items():
        h = hashlib.sha1()
        h.update(write("hero", theme, hero(data, c)).encode())
        vers["hero"] = h.hexdigest()[:10]
        for i, p in enumerate(CFG["projects"], 1):
            content, href, alt = tile(i, p, data["repo"].get(p["repo"], {}), c)
            vers[f"project-{i:02d}"] = write(f"project-{i:02d}", theme, content)
            parts[f"project-{i:02d}"] = (href, alt)
        vers["also"] = write("also", theme, also_built(data, c))
        for j, l in enumerate(CFG["links"], 1):
            vers[f"link-{j:02d}"] = write(f"link-{j:02d}", theme, chip(l["label"], c))

    # neofetch block (existing generator), reuse its stats file
    build_header.main()
    neo_ver = hashlib.sha1((ROOT / "header-dark.svg").read_bytes() + (ROOT / "header-light.svg").read_bytes()).hexdigest()[:10]

    md = ["<!-- Generated by scripts/build_profile.py from profile.json. Edit those, not this file. -->", ""]
    md.append(f'<a href="https://pfisterer-portfolio.com">{picture("hero", vers["hero"], CFG["name"] + ": " + CFG["tagline"], "100%")}</a>')
    md.append("")
    projects = [k for k in parts]
    for a, b in zip(projects[0::2], projects[1::2]):
        row = ""
        for k in (a, b):
            href, alt = parts[k]
            row += f'<a href="{href}">{picture(k, vers[k], alt, "50%")}</a>'
        md += [row, ""]
    md.append(f'<a href="https://github.com/{USER}?tab=repositories">{picture("also", vers["also"], "Also built", "100%")}</a>')
    md.append("")
    md.append('<picture><source media="(prefers-color-scheme: dark)" srcset="header-dark.svg?v=%s">'
              '<source media="(prefers-color-scheme: light)" srcset="header-light.svg?v=%s">'
              '<img src="header-dark.svg?v=%s" width="100%%" alt="falk@pfisterer neofetch: uptime, stack and GitHub stats"></picture>'
              % (neo_ver, neo_ver, neo_ver))
    md.append("")
    chips = "".join(f'<a href="{l["href"]}">{picture(f"link-{j:02d}", vers[f"link-{j:02d}"], l["label"], "")}</a> '
                    for j, l in enumerate(CFG["links"], 1))
    md.append(f'<p align="center">{chips.strip()}</p>')
    md.append("")
    md.append('<sub>Cards regenerated daily from live GitHub data by <a href="scripts/build_profile.py">a small script</a>.</sub>')
    (ROOT / "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(date.today(), "contributions", data["contributions"], "active days", data["active_days"])


if __name__ == "__main__":
    build_all()
