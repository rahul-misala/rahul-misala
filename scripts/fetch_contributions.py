#!/usr/bin/env python3
"""Fetch the last year of contributions (and public repo stats) into data/contributions.json.

Run by .github/workflows/readme-cards.yml every morning. Locally:
    GITHUB_TOKEN=$(gh auth token) python scripts/fetch_contributions.py
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOGIN = os.environ.get("GH_LOGIN", "rahul-misala")
OUT = Path(__file__).resolve().parent.parent / "data" / "contributions.json"

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes { name description url stargazerCount pushedAt primaryLanguage { name } }
    }
  }
}
"""


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        sys.exit(f"GraphQL error: {payload['errors']}")

    user = payload["data"]["user"]
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [
        {"date": d["date"], "count": d["contributionCount"]}
        for w in cal["weeks"]
        for d in w["contributionDays"]
    ]
    repos = {
        n["name"]: {
            "description": n["description"],
            "url": n["url"],
            "stars": n["stargazerCount"],
            "pushed_at": n["pushedAt"],
            "language": (n["primaryLanguage"] or {}).get("name"),
        }
        for n in user["repositories"]["nodes"]
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "login": LOGIN,
                "name": user["name"],
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "total": cal["totalContributions"],
                "days": days,
                "repos": repos,
            },
            indent=1,
        )
        + "\n"
    )
    print(f"wrote {OUT} — {cal['totalContributions']} contributions, {len(days)} days")


if __name__ == "__main__":
    main()
