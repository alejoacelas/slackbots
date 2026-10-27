# slackbots

Scope: Slack bots for the AI Uplift for EA workspace (`T094GSSSF3M`). First bot:
Moderation Bot, which asks authors to delete template posts that fail a
channel's bar.

- Visibility: public repo; Slack history and bot decisions stay in ignored `data/`
- Google account: none
- Still running or billing: none

## Moderation Bot

Slack app `A0CCFRH2CPL` ("Moderation Bot"), Socket Mode, bot scopes
`channels:history groups:history channels:read groups:read chat:write users:read`.

- `channels.toml` lists watched channels, each `off`, `dry_run` (log only) or
  `live` (replies in thread). Only flip a main channel to `live` with Alejo's
  approval.
- `modbot/classifier.py` holds the moderation prompt. A message fails when it is
  a template and is off the core topic or not written for the channel.
- `uv run python -m modbot.backfill CHANNEL_ID` classifies a channel's history
  with Alejo's user token and writes `data/backfill-<name>.json`; it never posts.
- `uv run python -m modbot.bot` runs the bot and appends every decision to
  `data/decisions.jsonl`.

Run either with credentials injected:
`~/best/dotfiles/bin/op-agent run --env-file=.env.tpl -- uv run python -m modbot.bot`

## Credentials (personal 1Password, vault `mac-agents`)

| Variable | Item | Field |
|---|---|---|
| `MODBOT_BOT_TOKEN` | Moderation Bot Slack | `bot_token` |
| `MODBOT_APP_TOKEN` | Moderation Bot Slack | `app_token` |
| `SLACK_USER_TOKEN` | AI Uplift Slack API (`ifyve5el5crjmu3kbvaq2od6ui`) | `user_token` |
| `ANTHROPIC_API_KEY` | ANTHROPIC_API_KEY — personal-apps-2026-10 (`mj6dyf42xml2ughfxqzpxey3zi`) | `credential` |
