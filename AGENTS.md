# slackbots

Scope: Slack bots for the AI Uplift for EA workspace (`T094GSSSF3M`). First bot:
Moderation Bot, which asks authors to delete template messages, since the policy
is no template messages without asking Alejo first.

- Visibility: public repo; Slack history and bot decisions stay in ignored `data/`
- Google account: none
- Still running or billing: `modbot.service` on the agent server, live in #too-much-ai (`C0B9PH0TA7J`) and the private #modbot-test (`C0CC9UY80MR`); Anthropic API usage per message

## Moderation Bot

A shareable copy with a setup guide lives in
[slack-moderation-bot](/Users/alejo/best/projects/2026-10-31-slack-moderation-bot/AGENTS.md);
port behaviour changes between the two.

Slack app `A0CCFRH2CPL` ("Moderation Bot"), Socket Mode, bot scopes
`channels:history groups:history channels:read groups:read chat:write users:read`.

- `channels.toml` lists watched channels, each `off`, `dry_run` (log only) or
  `live` (replies in thread). Only flip a main channel to `live` with Alejo's
  approval.
- `modbot/classifier.py` holds the moderation prompt. A message fails when it is
  a template: not written specifically for this channel, whatever its topic. A
  short personal note on top of pasted announcement text still counts.
- `uv run python -m modbot.backfill CHANNEL_ID` classifies a channel's history
  with Alejo's user token and writes `data/backfill-<name>.json`; it never posts.
- `uv run python -m modbot.bot` runs the bot and appends every decision to
  `data/decisions.jsonl`.

The bot only receives messages from channels it's a member of; invite it before
setting a channel to `dry_run` or `live`.

Run either locally with credentials injected:
`~/best/dotfiles/bin/op-agent run --env-file=.env.tpl -- uv run python -m modbot.bot`.
Stop any local bot while the server runs: Slack splits events between connections.

## Agent server

The bot runs as `alejo`'s user service `modbot.service`
([server/modbot.service](server/modbot.service)) from `~/work/slackbots`, with
secrets from [server/env.tpl](server/env.tpl). It runs as `alejo` rather than
`agent` because it makes single tool-free Claude calls, not agent sessions.
Decisions append to `~/work/slackbots/data/decisions.jsonl` there.

Deploy: push, then
`ssh agent-server 'cd ~/work/slackbots && git pull && ~/.local/bin/uv sync --frozen && systemctl --user restart modbot'`.
Logs: `ssh agent-server journalctl --user -u modbot -f`.

## Credentials (personal 1Password, vault `mac-agents`; server copies in `server-agents`)

| Variable | Item | Field |
|---|---|---|
| `MODBOT_BOT_TOKEN` | Moderation Bot Slack | `bot_token` |
| `MODBOT_APP_TOKEN` | Moderation Bot Slack | `app_token` |
| `SLACK_USER_TOKEN` | AI Uplift Slack API (`ifyve5el5crjmu3kbvaq2od6ui`) | `user_token` |
| `ANTHROPIC_API_KEY` | ANTHROPIC_API_KEY — personal-apps-2026-10 (`mj6dyf42xml2ughfxqzpxey3zi`) | `credential` |
