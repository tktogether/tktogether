#!/usr/bin/env python3
"""Regenerate profile statistics SVGs from GitHub data.

Run from the repository root with GITHUB_TOKEN set:
    GITHUB_TOKEN=... PROFILE_LOGIN=tktogether python scripts/generate_stats.py

Writes assets/activity.svg, assets/stack.svg and assets/telemetry.svg.
No third-party dependencies.
"""

import json
import os
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
TELEMETRY_TEMPLATE = ROOT / "scripts" / "telemetry.template.svg"

MONO = "Consolas, 'SFMono-Regular', Menlo, 'Courier New', monospace"
SANS = "'Segoe UI', 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
CYAN = "#35E0F0"
TEXT = "#E8F6F8"
MUTED = "#5E7478"
MID = "#9FB4B8"
PANEL = "#070C12"
LEVEL_COLORS = ["#0C161C", "#103A42", "#176E7A", "#22B6C4", "#35E0F0"]
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
LANG_COLORS = {
    "Python": "#FFB454",
    "TypeScript": "#7C9CFF",
    "Vue": "#35E0F0",
    "JavaScript": "#FFD166",
    "Shell": "#7CF0B0",
    "Go": "#2DD4BF",
    "Other": "#5E7478",
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
    allRepos: repositories(privacy: PUBLIC, ownerAffiliations: OWNER, first: 1) {
      totalCount
    }
    ownRepos: repositories(privacy: PUBLIC, ownerAffiliations: OWNER, isFork: false, first: 100) {
      totalCount
      nodes {
        name
        primaryLanguage { name }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def fetch_payload(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "tktogether-profile-stats",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload


def normalize(payload):
    user = payload["data"]["user"]
    calendar = user["contributionsCollection"]["contributionCalendar"]
    weeks = []
    for week in calendar["weeks"]:
        days = week["contributionDays"]
        weeks.append(
            {
                "start": days[0]["date"] if days else "",
                "days": [day["contributionCount"] for day in days],
            }
        )
    counts = [count for week in weeks for count in week["days"]]
    sizes = Counter()
    for node in user["ownRepos"]["nodes"]:
        for edge in (node.get("languages") or {}).get("edges", []):
            name = (edge.get("node") or {}).get("name") or "Other"
            sizes[name] += edge.get("size", 0)
    top = sizes.most_common(5)
    rest = sum(size for name, size in sizes.items() if name not in dict(top))
    if rest:
        top.append(("Other", rest))
    if not top:
        top = [("Other", 0)]
    return {
        "total_contributions": calendar["totalContributions"],
        "active_days": sum(1 for count in counts if count > 0),
        "peak_day": max(counts) if counts else 0,
        "public_repos": user["allRepos"]["totalCount"],
        "original_repos": user["ownRepos"]["totalCount"],
        "weeks": weeks,
        "languages": top,
    }


def _level(count, peak):
    if count <= 0 or peak <= 0:
        return 0
    ratio = count / peak
    if ratio <= 0.25:
        return 1
    if ratio <= 0.5:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


def _month_of(date_text):
    return int(date_text[5:7])


def build_activity_svg(data):
    x0, y0, pitch, size = 48, 80, 12, 9
    cells = []
    for week_index, week in enumerate(data["weeks"]):
        for day_index, count in enumerate(week["days"]):
            level = _level(count, data["peak_day"])
            cells.append(
                f'<rect class="cell" x="{x0 + week_index * pitch}" y="{y0 + day_index * pitch}" '
                f'width="{size}" height="{size}" rx="1" fill="{LEVEL_COLORS[level]}"/>'
            )

    month_labels = []
    previous = None
    for week_index, week in enumerate(data["weeks"]):
        if not week["start"]:
            continue
        month = _month_of(week["start"])
        if month != previous:
            month_labels.append(
                f'<text x="{x0 + week_index * pitch}" y="68" font-family="{MONO}" '
                f'font-size="9" letter-spacing="1.4" fill="{MUTED}">{MONTHS[month - 1]}</text>'
            )
        previous = month

    weekdays = []
    for row, name in [(1, "MON"), (3, "WED"), (5, "FRI")]:
        weekdays.append(
            f'<text x="22" y="{y0 + row * pitch + 8}" font-family="{MONO}" font-size="8" '
            f'letter-spacing="1" fill="{MUTED}">{name}</text>'
        )

    legend_x = 90
    legend = [
        f'<text x="48" y="197" font-family="{MONO}" font-size="8" letter-spacing="1.4" fill="{MUTED}">LESS</text>'
    ]
    for index, color in enumerate(LEVEL_COLORS[1:]):
        legend.append(
            f'<rect x="{legend_x + index * 12}" y="189" width="9" height="9" rx="1" fill="{color}"/>'
        )
    legend.append(
        f'<text x="{legend_x + 5 * 12}" y="197" font-family="{MONO}" font-size="8" '
        f'letter-spacing="1.4" fill="{MUTED}">MORE</text>'
    )

    metrics = [
        ("CONTRIBUTIONS", data["total_contributions"]),
        ("ACTIVE DAYS", data["active_days"]),
        ("PEAK DAY", data["peak_day"]),
        ("PUBLIC REPOS", data["public_repos"]),
    ]
    metric_parts = []
    for index, (label, value) in enumerate(metrics):
        top = 82 + index * 48
        metric_parts.append(
            f'<text x="720" y="{top}" font-family="{MONO}" font-size="9" letter-spacing="2" '
            f'fill="{CYAN}" fill-opacity="0.75">{label}</text>'
            f'<text x="720" y="{top + 26}" font-family="{MONO}" font-size="22" fill="{TEXT}">{value}</text>'
        )
        if index < len(metrics) - 1:
            metric_parts.append(
                f'<line x1="720" y1="{top + 36}" x2="988" y2="{top + 36}" '
                f'stroke="{CYAN}" stroke-opacity="0.12"/>'
            )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1012" height="300" viewBox="0 0 1012 300" role="img" aria-labelledby="title desc">
  <title id="title">System Load — Activity</title>
  <desc id="desc">Contribution heatmap for the last 12 months: {data["total_contributions"]} contributions, {data["active_days"]} active days, peak {data["peak_day"]} in one day.</desc>
  <rect x="0.5" y="0.5" width="1011" height="299" fill="{PANEL}" stroke="{CYAN}" stroke-opacity="0.25"/>
  <text x="24" y="32" font-family="{MONO}" font-size="11" letter-spacing="2.5" fill="{CYAN}">SYSTEM LOAD // ACTIVITY</text>
  <text x="988" y="32" text-anchor="end" font-family="{MONO}" font-size="9" letter-spacing="1.6" fill="{MUTED}">LAST 12 MONTHS · LIVE</text>
  {"".join(month_labels)}
  {"".join(weekdays)}
  {"".join(cells)}
  {"".join(legend)}
  {"".join(metric_parts)}
  <text x="48" y="290" font-family="{MONO}" font-size="8" letter-spacing="1.2" fill="{MUTED}">AUTO-SYNCED VIA GITHUB ACTIONS</text>
  <g stroke="{CYAN}" stroke-opacity="0.3" fill="none">
    <path d="M10 16 V10 H16"/>
    <path d="M996 10 H1002 V16"/>
    <path d="M10 284 V290 H16"/>
    <path d="M996 290 H1002 V284"/>
  </g>
</svg>
'''


def _allocate_widths(segments, total_width, gap):
    available = total_width - gap * (len(segments) - 1)
    exact = [available * c / sum(c for _, c in segments) for _, c in segments]
    widths = [int(value) for value in exact]
    remainder = available - sum(widths)
    order = sorted(range(len(exact)), key=lambda i: exact[i] - widths[i], reverse=True)
    for index in order[:remainder]:
        widths[index] += 1
    return widths


def _segment_widths(svg):
    return re.findall(r'<rect class="seg"[^>]*width="([0-9.]+)"', svg)


def _human_bytes(value):
    size = float(value)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def build_stack_svg(data):
    segments = data["languages"]
    total = sum(size for _, size in segments) or 1
    widths = _allocate_widths(segments, 964, 2)
    parts = []
    x = 24
    for (name, size), width in zip(segments, widths):
        color = LANG_COLORS.get(name, LANG_COLORS["Other"])
        text_color = "#E8F6F8" if name == "Other" else "#05070B"
        percent = size / total * 100
        label = f"{percent:.0f}%" if percent >= 10 else f"{percent:.1f}%"
        parts.append(f'<rect class="seg" x="{x}" y="72" width="{width}" height="24" fill="{color}"/>')
        if width >= 46:
            parts.append(
                f'<text x="{x + width / 2}" y="88" text-anchor="middle" font-family="{MONO}" '
                f'font-size="10" fill="{text_color}">{label}</text>'
            )
        x += width + 2

    legend = []
    lx = 24
    for name, size in segments:
        color = LANG_COLORS.get(name, LANG_COLORS["Other"])
        percent = size / total * 100
        legend.append(
            f'<rect x="{lx}" y="121" width="7" height="7" fill="{color}"/>'
            f'<text x="{lx + 12}" y="128" font-family="{MONO}" font-size="9" letter-spacing="1" '
            f'fill="{MID}">{name.upper()} {percent:.1f}% · {_human_bytes(size)}</text>'
        )
        lx += 12 + (len(name) + 8 + len(_human_bytes(size)) + 4) * 5.8 + 16

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1012" height="190" viewBox="0 0 1012 190" role="img" aria-labelledby="title desc">
  <title id="title">Module Distribution — language volume</title>
  <desc id="desc">Code volume by language across {data["original_repos"]} public original repositories: {", ".join(f"{name} {size / total * 100:.1f}%" for name, size in segments)}.</desc>
  <rect x="0.5" y="0.5" width="1011" height="189" fill="{PANEL}" stroke="{CYAN}" stroke-opacity="0.25"/>
  <text x="24" y="32" font-family="{MONO}" font-size="11" letter-spacing="2.5" fill="{CYAN}">MODULE DISTRIBUTION // LANGUAGE VOLUME</text>
  <text x="988" y="32" text-anchor="end" font-family="{MONO}" font-size="9" letter-spacing="1.6" fill="{MUTED}">{data["original_repos"]} PUBLIC ORIGINALS · LIVE</text>
  {"".join(parts)}
  {"".join(legend)}
  <text x="24" y="160" font-family="{MONO}" font-size="8" letter-spacing="1.2" fill="{MUTED}">CODE BYTES BY LANGUAGE · FORKS EXCLUDED</text>
  <text x="988" y="160" text-anchor="end" font-family="{MONO}" font-size="8" letter-spacing="1.2" fill="{MUTED}">TOTAL {_human_bytes(total)}</text>
  <g stroke="{CYAN}" stroke-opacity="0.3" fill="none">
    <path d="M10 16 V10 H16"/>
    <path d="M996 10 H1002 V16"/>
    <path d="M10 174 V180 H16"/>
    <path d="M996 180 H1002 V174"/>
  </g>
</svg>
'''


def render_telemetry(template, data):
    return template.replace("{{NODES}}", str(data["public_repos"]))


def write_if_changed(path, content):
    path = Path(path)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 1
    login = os.environ.get("PROFILE_LOGIN", "tktogether")
    data = normalize(fetch_payload(login, token))

    changed = []
    if write_if_changed(ASSETS / "activity.svg", build_activity_svg(data)):
        changed.append("activity.svg")
    if write_if_changed(ASSETS / "stack.svg", build_stack_svg(data)):
        changed.append("stack.svg")
    if TELEMETRY_TEMPLATE.exists():
        template = TELEMETRY_TEMPLATE.read_text(encoding="utf-8")
        if write_if_changed(ASSETS / "telemetry.svg", render_telemetry(template, data)):
            changed.append("telemetry.svg")

    print(
        f"contributions={data['total_contributions']} active={data['active_days']} "
        f"peak={data['peak_day']} public={data['public_repos']} original={data['original_repos']}"
    )
    print("updated:", ", ".join(changed) if changed else "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
