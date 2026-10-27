"""Run the classifier over a channel's whole history and write the results.

Usage: uv run python -m modbot.backfill CHANNEL_ID
Reads history with SLACK_USER_TOKEN, so it never posts anything.
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
from slack_sdk import WebClient

from modbot.classifier import classify, violations
from modbot.config import load_channels
from modbot.slack_util import is_top_level, load_users

OUT = Path("data")


def fetch_history(slack: WebClient, channel_id: str) -> list[dict]:
    msgs, cursor = [], None
    while True:
        r = slack.conversations_history(channel=channel_id, limit=200, cursor=cursor)
        msgs += r["messages"]
        cursor = r.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            return msgs


def main(channel_id: str) -> None:
    slack = WebClient(token=os.environ["SLACK_USER_TOKEN"])
    channel = load_channels()[channel_id]
    channel["purpose"] = slack.conversations_info(channel=channel_id)["channel"]["purpose"]["value"]
    users = load_users(slack)
    msgs = [m for m in fetch_history(slack, channel_id) if is_top_level(m)]
    print(f"{len(msgs)} top-level messages", file=sys.stderr)

    client = anthropic.Anthropic()

    def run(m):
        v = classify(client, m, channel, users)
        author = users.get(m.get("user", "")) or m.get("user_profile", {}).get("real_name") or m.get("user")
        link = slack.chat_getPermalink(channel=channel_id, message_ts=m["ts"])["permalink"]
        return {
            "ts": m["ts"],
            "author": author,
            "permalink": link,
            "text": m.get("text", ""),
            "verdict": v.model_dump() if v else None,
            "violations": violations(v) if v else ["refused"],
        }

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(run, msgs))

    OUT.mkdir(exist_ok=True)
    path = OUT / f"backfill-{channel['name']}.json"
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    flagged = [r for r in results if r["violations"]]
    print(f"{len(flagged)} flagged of {len(results)}; wrote {path}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])
