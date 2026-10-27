from slack_sdk import WebClient

# Message subtypes that are people posting; everything else (joins, purpose
# changes, bot posts, thread broadcasts) is ignored. People posting through an
# app's user token carry a bot_id too, so a human `user` is what counts.
POSTED_SUBTYPES = {None, "file_share"}


def is_top_level(msg: dict) -> bool:
    if msg.get("subtype") not in POSTED_SUBTYPES or not msg.get("user"):
        return False
    thread_ts = msg.get("thread_ts")
    return thread_ts is None or thread_ts == msg["ts"]


def load_users(slack: WebClient) -> dict[str, str]:
    users, cursor = {}, None
    while True:
        r = slack.users_list(limit=1000, cursor=cursor)
        for u in r["members"]:
            users[u["id"]] = u.get("real_name") or u["name"]
        cursor = r.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            return users
