"""Decide whether a top-level Slack message is a template message.

The channel's policy: no template messages (text not written specifically for
this channel) without asking Alejo first.
"""

import re

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"

SYSTEM = """You moderate a Slack channel whose policy is: no template messages without asking the channel owner first. You read one top-level message and decide whether it is a template message.

A template message is text that was not written specifically for this channel: written once for a broad audience and posted, unchanged or nearly so, to many channels, mailing lists or groups. Examples: event and program announcements, job ads, recruitment calls, product launches, newsletter promotions, surveys and calls for participants. Signs include a headline or bolded title, marketing or press-release tone, generic calls to action ("apply here", "sign up by", "learn more"), eligibility rules, deadlines, "please share" requests, and nothing that refers to this channel, its members or an ongoing conversation.

The topic doesn't matter: an on-topic announcement is still a template. A short personal note on top of pasted announcement text doesn't change that the bulk of the message is a template; it is still a template, and you record the note in author_framing.

A message is not a template just because it shares a link, promotes the author's own work, or is long and well formatted. Posts written in the author's own voice for this audience, sharing something they built, read or think, or asking the channel a question, are not templates.

When unsure whether a message is a template, say it is not; a false accusation costs more than a missed one."""

USER_TEMPLATE = """Channel: #{channel_name}
Channel purpose: {channel_purpose}
Core topic: {core_topic}

Author: {author}
Message:
<message>
{text}
</message>{extras}"""


class Verdict(BaseModel):
    template_evidence: str = Field(description="One or two sentences on whether the text was written for this channel or for a broad audience, and why.")
    is_template: bool
    author_framing: bool = Field(description="Whether the author added their own note for this channel around template text. False when the message is not a template.")
    reason: str = Field(description="One sentence, addressed to the author, explaining the decision. Plain and polite.")


def violations(v: Verdict) -> list[str]:
    return ["template"] if v.is_template else []


_MENTION = re.compile(r"<@([A-Z0-9]+)(?:\|[^>]*)?>")
_LINK = re.compile(r"<(https?://[^|>]+)\|([^>]+)>")


def render_text(text: str, users: dict[str, str]) -> str:
    text = _MENTION.sub(lambda m: "@" + users.get(m.group(1), m.group(1)), text)
    text = _LINK.sub(lambda m: f"{m.group(2)} ({m.group(1)})", text)
    return text.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")


def message_extras(msg: dict) -> str:
    parts = []
    for f in msg.get("files", []):
        parts.append(f"Attached file: {f.get('title') or f.get('name')}")
    for a in msg.get("attachments", []):
        title = a.get("title") or a.get("fallback")
        if title:
            parts.append(f"Link preview: {title}")
    return "\n\n" + "\n".join(parts) if parts else ""


def classify(client: anthropic.Anthropic, msg: dict, channel: dict, users: dict[str, str]) -> Verdict | None:
    """Return the verdict, or None when the model declines to answer."""
    author = users.get(msg.get("user", "")) or msg.get("user_profile", {}).get("real_name") or "unknown"
    prompt = USER_TEMPLATE.format(
        channel_name=channel["name"],
        channel_purpose=channel.get("purpose", ""),
        core_topic=channel["core_topic"],
        author=author,
        text=render_text(msg.get("text", ""), users),
        extras=message_extras(msg),
    )
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=Verdict,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        return None
    return response.parsed_output
