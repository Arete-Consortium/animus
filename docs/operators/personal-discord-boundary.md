# Personal Discord access boundary

The personal `tools/animus_discord_bot.py` process exposes memory, harvest, tasks
and model responses only to one configured owner in a direct message with the bot.
The separate Hunter application is responsible for shared MHW chat. A legacy
`ANIMUS_CHAT_CHANNEL` value or a bot mention cannot grant personal access in a guild.

Install the optional SDK with `pip install -e 'packages/core[discord]'` alongside
the normal Core dependencies. Supply settings through the existing host secret
configuration; do not put tokens in commands or checked-in files.

| Setting | Behavior |
| --- | --- |
| `ANIMUS_PERSONAL_OWNER_ID` | Positive ASCII Discord user ID. Missing disables personal chat and commands; malformed values stop startup. |
| `ANIMUS_DISCORD_SYNC_COMMANDS` | Only literal `true` synchronizes the command tree on startup. Default leaves the registered commands untouched. |
| `ANIMUS_ENABLE_INTEL_PUSH` | Only literal `true` enables the configured public harvest destination. Default disables public auto-push. |
| `ANIMUS_CHAT_CHANNEL` | Retained for compatibility; never authorizes personal memory in a guild or thread. |

The message callback checks the owner, DM channel type, absence of a guild,
bot flag and webhook flag before logging, rate limiting, replying or loading
memory/model capabilities. The command tree applies the same owner-DM policy to
all registered slash commands. Rejections are ephemeral. Group DMs are denied.
Allowed mentions are disabled for the client. Personal chat and uncaught slash
command exceptions log only their class name; their error handlers do not log
prompt, memory or provider exception text. Slash-command failures return a neutral
ephemeral response, including failures after an earlier deferred response.

Public harvest push remains a separate, explicit operator choice. It can disclose
the harvest report to its destination; review that destination and report content
before enabling it. It does not authorize public conversational memory access.

## Command ownership and rollout

Before deploying this code, identify which process owns this Discord application's
global commands. Enable synchronization only for that process when an intentional
command registration change is needed. This patch does not remove existing remote
commands; the runtime guard denies unauthorized invocation even if Discord still
displays them. The personal application must not share the Hunter application's
token or command registration responsibility.

This is a source-control reconciliation of an existing local privacy patch, with
an additional opt-in synchronization guard. No service configuration, Discord
permissions, commands or messages are changed by applying this Git diff. Existing
deployments need an explicit rollout; a passing local test is not deployment proof.

## Regression and human acceptance

Run `python -m pytest tests/test_personal_discord_boundary.py -q` from the repository
root after installing the Core dependencies and Discord extra. CI runs this suite
explicitly because root `tests/` is outside the default Core test discovery path.

The suite uses the actual Discord SDK dispatcher with mocked network responses.
It verifies every registered command is denied for guilds, foreign DMs, group DMs
and missing owner configuration; guild mentions and legacy chat/thread destinations
never load memory/model capabilities; bot/webhook messages are ignored; an owner
DM successfully reaches both `/ask` and conversational chat. It also checks error
redaction, suppressed mentions, public-push defaults and synchronization ownership.

After a separately authorized rollout, the owner should check:

1. An ordinary owner DM receives a response and `/ask` works in that DM.
2. An owner guild `/ask` is denied; mentioning the personal bot in shared MHW chat
   receives no personal answer.
3. A second account's DM and a group DM cannot retrieve personal information.
4. Hunter still answers through its separate application in the configured channel.

These human Discord checks are not performed by the mocked regression suite.
