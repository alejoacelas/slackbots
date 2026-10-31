"""Moderation Bot: classify each new top-level message in watched channels and,
in live channels, ask the author in a thread to delete template messages.

Usage: uv run python -m modbot.bot
Needs MODBOT_BOT_TOKEN (xoxb), MODBOT_APP_TOKEN (xapp, Socket Mode) and ANTHROPIC_API_KEY.
Optional MODBOT_USER_TOKEN (xoxp, Alejo's, scopes im:read and im:history): before replying, the bot
reads Alejo's DMs with the author from the past week and stays quiet if Alejo approved the post.
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

from modbot.classifier import check_approval, classify, violations
from modbot.config import load_channels
from modbot.slack_util import is_top_level

log = logging.getLogger("modbot")
DECISIONS = Path("data/decisions.jsonl")

def reply_text(user: str) -> str:
    return (
        f"Hi <@{user}>, I'm Alejo's bot. This channel doesn't take template messages (posts written for many "
        "places rather than for this channel) unless you've checked with Alejo first. Could you please delete "
        "this one?\n\n"
        "If Alejo already said yes, or you wrote this specifically for this channel, feel free to leave it up."
    )


class Bot:
    def __init__(self) -> None:
        self.web = WebClient(token=os.environ["MODBOT_BOT_TOKEN"])
        self.claude = anthropic.Anthropic()
        self.channels = load_channels()
        self.users: dict[str, str] = {}
        self.seen: set[str] = set()
        self.pool = ThreadPoolExecutor(4)
        self.own_user = self.web.auth_test()["user_id"]
        token = os.environ.get("MODBOT_USER_TOKEN")
        self.owner = WebClient(token=token) if token else None
        self.owner_id = self.owner.auth_test()["user_id"] if self.owner else None

    def user_name(self, user_id: str) -> str:
        if user_id not in self.users:
            try:
                u = self.web.users_info(user=user_id)["user"]
                self.users[user_id] = u.get("real_name") or u["name"]
            except Exception:
                self.users[user_id] = user_id
        return self.users[user_id]

    def dm_with(self, user_id: str, days: int = 7) -> list[dict]:
        """The owner's 1:1 DM messages with this user from the past `days` days."""
        cursor = None
        while True:
            r = self.owner.conversations_list(types="im", limit=1000, cursor=cursor)
            for c in r["channels"]:
                if c.get("user") == user_id:
                    return self.owner.conversations_history(
                        channel=c["id"], oldest=str(time.time() - days * 86400), limit=200
                    )["messages"]
            cursor = r.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                return []

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
        if event.get("user") in channel.get("exempt_users", []) + [self.own_user]:
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
            approval = None
            if found and self.owner:
                dm = self.dm_with(event["user"])
                if dm:
                    approval = check_approval(self.claude, event, dm, self.owner_id, self.users)
            approved = bool(approval and approval.approved)
            posted = False
            if found and not approved and channel["mode"] == "live":
                self.web.chat_postMessage(
                    channel=channel["id"],
                    thread_ts=event["ts"],
                    text=reply_text(event["user"]),
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
                "approval": approval.model_dump() if approval else None,
            }
            DECISIONS.parent.mkdir(exist_ok=True)
            with DECISIONS.open("a") as f:
                f.write(json.dumps(record) + "\n")
            log.info("%s %s %s approved=%s posted=%s", channel["name"], event["ts"], found or "pass", approved, posted)
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
