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
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

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
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode())
            break
        except Exception as error:
            last_error = error
            time.sleep(2)
    else:
        raise last_error
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
    x0, y0, pitch, size = 48, 250, 18, 14
    cells = []
    peak_index = None
    peak_count = -1
    for week_index, week in enumerate(data["weeks"]):
        for day_index, count in enumerate(week["days"]):
            level = _level(count, data["peak_day"])
            cells.append(
                f'<rect class="cell" x="{x0 + week_index * pitch}" y="{y0 + day_index * pitch}" '
                f'width="{size}" height="{size}" rx="1" fill="{LEVEL_COLORS[level]}"/>'
            )
            if count > peak_count:
                peak_count = count
                peak_index = (week_index, day_index)

    highlight = ""
    if peak_index and peak_count > 0:
        px = x0 + peak_index[0] * pitch - 2
        py = y0 + peak_index[1] * pitch - 2
        highlight = (
            f'<rect x="{px}" y="{py}" width="{size + 4}" height="{size + 4}" rx="1" '
            f'fill="none" stroke="#FFB454" stroke-opacity="0.85"/>'
        )

    month_labels = []
    previous = None
    for week_index, week in enumerate(data["weeks"]):
        if not week["start"]:
            continue
        month = _month_of(week["start"])
        if month != previous:
            month_labels.append(
                f'<text x="{x0 + week_index * pitch}" y="232" font-family="{MONO}" '
                f'font-size="9" letter-spacing="1.6" fill="{MUTED}">{MONTHS[month - 1]}</text>'
            )
        previous = month

    weekdays = []
    for row, name in [(1, "MON"), (3, "WED"), (5, "FRI")]:
        weekdays.append(
            f'<text x="20" y="{y0 + row * pitch + 11}" font-family="{MONO}" font-size="8" '
            f'letter-spacing="1" fill="{MUTED}">{name}</text>'
        )

    legend = [
        f'<text x="48" y="408" font-family="{MONO}" font-size="8" letter-spacing="1.4" fill="{MUTED}">LESS</text>'
    ]
    for index, color in enumerate(LEVEL_COLORS[1:]):
        legend.append(
            f'<rect x="{90 + index * 14}" y="399" width="10" height="10" rx="1" fill="{color}"/>'
        )
    legend.append(
        f'<text x="{90 + 5 * 14}" y="408" font-family="{MONO}" font-size="8" '
        f'letter-spacing="1.4" fill="{MUTED}">MORE</text>'
    )

    metrics = [
        ("ACTIVE DAYS", data["active_days"]),
        ("PEAK DAY", data["peak_day"]),
        ("PUBLIC REPOS", data["public_repos"]),
    ]
    metric_parts = []
    for index, (label, value) in enumerate(metrics):
        left = 360 + index * 210
        metric_parts.append(
            f'<text x="{left}" y="112" font-family="{MONO}" font-size="9" letter-spacing="2" '
            f'fill="{CYAN}" fill-opacity="0.7">{label}</text>'
            f'<text x="{left}" y="154" font-family="{MONO}" font-size="40" fill="{TEXT}">{value}</text>'
        )
        if index:
            metric_parts.append(
                f'<line x1="{left - 28}" y1="90" x2="{left - 28}" y2="164" '
                f'stroke="{CYAN}" stroke-opacity="0.16"/>'
            )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1012" height="430" viewBox="0 0 1012 430" role="img" aria-labelledby="title desc">
  <title id="title">System Load — Activity</title>
  <desc id="desc">Contribution heatmap for the last 12 months: {data["total_contributions"]} contributions, {data["active_days"]} active days, peak {data["peak_day"]} in one day.</desc>
  <defs>
    <style>
      .scan {{ animation: scan 9s linear infinite; transform-box: fill-box; transform-origin: left center; }}
      @keyframes scan {{ from {{ transform: translateX(0); }} to {{ transform: translateX(942px); }} }}
      @media (prefers-reduced-motion: reduce) {{ .scan {{ animation: none; opacity: 0; }} }}
    </style>
  </defs>
  <rect x="0.5" y="0.5" width="1011" height="429" fill="{PANEL}" stroke="{CYAN}" stroke-opacity="0.25"/>
  <text x="24" y="34" font-family="{MONO}" font-size="9" letter-spacing="3" fill="{CYAN}" fill-opacity="0.8">SYSTEM LOAD // ACTIVITY</text>
  <text x="24" y="62" font-family="{SANS}" font-size="20" font-weight="600" fill="{TEXT}">CONTRIBUTION MATRIX — LAST 12 MONTHS</text>
  <text x="988" y="34" text-anchor="end" font-family="{MONO}" font-size="9" letter-spacing="1.6" fill="{MUTED}">LIVE // AUTO-SYNCED</text>
  <text x="24" y="150" font-family="{MONO}" font-size="92" fill="{TEXT}">{data["total_contributions"]}</text>
  <text x="24" y="176" font-family="{MONO}" font-size="9" letter-spacing="2.2" fill="{CYAN}" fill-opacity="0.7">CONTRIBUTIONS</text>
  {"".join(metric_parts)}
  <line x1="24" y1="196" x2="988" y2="196" stroke="{CYAN}" stroke-opacity="0.18"/>
  {"".join(month_labels)}
  {"".join(weekdays)}
  {"".join(cells)}
  {highlight}
  <rect class="scan" x="48" y="250" width="2" height="126" fill="{CYAN}" fill-opacity="0.25"/>
  {"".join(legend)}
  <text x="988" y="408" text-anchor="end" font-family="{MONO}" font-size="8" letter-spacing="1.2" fill="{MUTED}">AUTO-SYNCED VIA GITHUB ACTIONS</text>
  <g stroke="{CYAN}" stroke-opacity="0.3" fill="none">
    <path d="M10 16 V10 H16"/>
    <path d="M996 10 H1002 V16"/>
    <path d="M10 414 V420 H16"/>
    <path d="M996 420 H1002 V414"/>
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

    columns = []
    for index, (name, size) in enumerate(segments):
        left = 24 + index * 160
        color = LANG_COLORS.get(name, LANG_COLORS["Other"])
        percent = size / total * 100
        label = f"{percent:.0f}%" if percent >= 10 else f"{percent:.1f}%"
        columns.append(
            f'<text x="{left}" y="128" font-family="{MONO}" font-size="52" fill="{color}">{label}</text>'
            f'<text x="{left}" y="156" font-family="{MONO}" font-size="10" letter-spacing="2" '
            f'fill="{TEXT}">{name.upper()}</text>'
            f'<text x="{left}" y="176" font-family="{MONO}" font-size="9" letter-spacing="1" '
            f'fill="{MUTED}">{_human_bytes(size)}</text>'
        )
        if index:
            columns.append(
                f'<line x1="{left - 12}" y1="100" x2="{left - 12}" y2="182" '
                f'stroke="{CYAN}" stroke-opacity="0.14"/>'
            )

    parts = []
    x = 24
    for (name, size), width in zip(segments, widths):
        color = LANG_COLORS.get(name, LANG_COLORS["Other"])
        parts.append(f'<rect class="seg" x="{x}" y="200" width="{width}" height="14" fill="{color}"/>')
        x += width + 2

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1012" height="260" viewBox="0 0 1012 260" role="img" aria-labelledby="title desc">
  <title id="title">Module Distribution — language volume</title>
  <desc id="desc">Code volume by language across {data["original_repos"]} public original repositories: {", ".join(f"{name} {size / total * 100:.1f}%" for name, size in segments)}.</desc>
  <rect x="0.5" y="0.5" width="1011" height="259" fill="{PANEL}" stroke="{CYAN}" stroke-opacity="0.25"/>
  <text x="24" y="34" font-family="{MONO}" font-size="9" letter-spacing="3" fill="{CYAN}" fill-opacity="0.8">MODULE DISTRIBUTION</text>
  <text x="24" y="64" font-family="{SANS}" font-size="20" font-weight="600" fill="{TEXT}">LANGUAGE VOLUME</text>
  <text x="988" y="34" text-anchor="end" font-family="{MONO}" font-size="9" letter-spacing="1.6" fill="{MUTED}">{data["original_repos"]} PUBLIC ORIGINALS · LIVE</text>
  <text x="988" y="58" text-anchor="end" font-family="{MONO}" font-size="9" letter-spacing="1.6" fill="{MUTED}">{len(segments)} LANGUAGES</text>
  {"".join(columns)}
  {"".join(parts)}
  <text x="24" y="240" font-family="{MONO}" font-size="8" letter-spacing="1.2" fill="{MUTED}">CODE BYTES BY LANGUAGE · FORKS EXCLUDED</text>
  <text x="988" y="240" text-anchor="end" font-family="{MONO}" font-size="8" letter-spacing="1.2" fill="{MUTED}">TOTAL {_human_bytes(total)}</text>
  <g stroke="{CYAN}" stroke-opacity="0.3" fill="none">
    <path d="M10 16 V10 H16"/>
    <path d="M996 10 H1002 V16"/>
    <path d="M10 244 V250 H16"/>
    <path d="M996 250 H1002 V244"/>
  </g>
</svg>
'''


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

    print(
        f"contributions={data['total_contributions']} active={data['active_days']} "
        f"peak={data['peak_day']} public={data['public_repos']} original={data['original_repos']}"
    )
    print("updated:", ", ".join(changed) if changed else "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
