"""Decide whether a top-level Slack message fails the channel's moderation bar.

A message fails when it is a template message (written once and posted to many
places) and either is off the channel's core topic or was not written for this
channel.
"""

import re

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"

SYSTEM = """You moderate a Slack channel. You read one top-level message and decide whether it fails the channel's bar.

The bar has two rules. Both only apply to template messages.

A template message is text written once and posted, unchanged or nearly so, to many channels, mailing lists or groups: event and program announcements, job ads, recruitment calls, product launches, newsletter promotions, surveys and calls for participants. Signs include a headline or bolded title, marketing or press-release tone, generic calls to action ("apply here", "sign up by", "learn more"), eligibility rules, deadlines, and nothing that refers to this channel, its members or an ongoing conversation. A message is not a template just because it shares a link, promotes the author's own work, or is long and well formatted. Personal posts that share something the author built, read or thinks, written in their own voice for this audience, are not templates.

Rule 1 - off-topic template: a template message whose subject is not the channel's core topic. Being about AI is not enough; the message must be about the core topic itself.

Rule 2 - template not addressed to this channel: a template message that was not adapted for this channel. A template counts as addressed to the channel when the author added their own framing for this audience, such as why they think members here would care, a personal note, or a question to the channel. Merely posting it here does not count.

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
    template_evidence: str = Field(description="One or two sentences on whether the text reads as a template and why.")
    is_template: bool
    on_core_topic: bool = Field(description="Whether the message's subject is the channel's core topic.")
    addressed_to_channel: bool = Field(description="Whether the author wrote or adapted the message for this channel.")
    reason: str = Field(description="One sentence, addressed to the author, explaining the decision. Plain and polite.")


def violations(v: Verdict) -> list[str]:
    if not v.is_template:
        return []
    out = []
    if not v.on_core_topic:
        out.append("off_topic_template")
    if not v.addressed_to_channel:
        out.append("not_addressed_template")
    return out


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
