"""Moderation Bot: classify each new top-level message in watched channels and,
in live channels, ask the author in a thread to delete messages that fail the bar.

Usage: uv run python -m modbot.bot
Needs MODBOT_BOT_TOKEN (xoxb), MODBOT_APP_TOKEN (xapp, Socket Mode) and ANTHROPIC_API_KEY.
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from modbot.classifier import classify, violations
from modbot.config import load_channels
from modbot.slack_util import is_top_level

log = logging.getLogger("modbot")
DECISIONS = Path("data/decisions.jsonl")

REASONS = {
    "off_topic_template": "it looks like a template message that isn't about this channel's core topic",
    "not_addressed_template": "it looks like a template message that wasn't written for this channel",
}


def reply_text(user: str, found: list[str], core_topic: str) -> str:
    why = " and ".join(REASONS[v] for v in found)
    return (
        f"Hi <@{user}>, could you please delete this message? {why[0].upper()}{why[1:]}. "
        f"This channel is for {core_topic}.\n\n"
        "If you think I got this wrong, reply in this thread and a moderator will take a look."
    )


class Bot:
    def __init__(self) -> None:
        self.web = WebClient(token=os.environ["MODBOT_BOT_TOKEN"])
        self.claude = anthropic.Anthropic()
        self.channels = load_channels()
        self.users: dict[str, str] = {}
        self.seen: set[str] = set()
        self.pool = ThreadPoolExecutor(4)

    def user_name(self, user_id: str) -> str:
        if user_id not in self.users:
            try:
                u = self.web.users_info(user=user_id)["user"]
                self.users[user_id] = u.get("real_name") or u["name"]
            except Exception:
                self.users[user_id] = user_id
        return self.users[user_id]

    def on_request(self, client: SocketModeClient, req: SocketModeRequest) -> None:
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        if req.type != "events_api":
            return
        event = req.payload.get("event", {})
        if event.get("type") != "message":
            return
        channel = self.channels.get(event.get("channel"))
        key = f"{event.get('channel')}:{event.get('ts')}"
        if not channel or channel["mode"] == "off" or key in self.seen or not is_top_level(event):
            return
        if event.get("user") in channel.get("exempt_users", []):
            return
        self.seen.add(key)
        self.pool.submit(self.handle, event, channel)

    def handle(self, event: dict, channel: dict) -> None:
        try:
            if "purpose" not in channel:
                channel["purpose"] = self.web.conversations_info(channel=channel["id"])["channel"]["purpose"]["value"]
            self.user_name(event["user"])
            verdict = classify(self.claude, event, channel, self.users)
            found = violations(verdict) if verdict else []
            posted = False
            if found and channel["mode"] == "live":
                self.web.chat_postMessage(
                    channel=channel["id"],
                    thread_ts=event["ts"],
                    text=reply_text(event["user"], found, channel["core_topic"]),
                )
                posted = True
            record = {
                "time": time.time(),
                "channel": channel["name"],
                "ts": event["ts"],
                "user": event["user"],
                "violations": found,
                "posted": posted,
                "verdict": verdict.model_dump() if verdict else None,
            }
            DECISIONS.parent.mkdir(exist_ok=True)
            with DECISIONS.open("a") as f:
                f.write(json.dumps(record) + "\n")
            log.info("%s %s %s posted=%s", channel["name"], event["ts"], found or "pass", posted)
        except Exception:
            log.exception("failed to handle %s %s", channel["name"], event.get("ts"))

    def run(self) -> None:
        socket = SocketModeClient(app_token=os.environ["MODBOT_APP_TOKEN"], web_client=self.web)
        socket.socket_mode_request_listeners.append(self.on_request)
        socket.connect()
        log.info("connected; watching %s", [c["name"] for c in self.channels.values() if c["mode"] != "off"])
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    Bot().run()
