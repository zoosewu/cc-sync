# cc-sync

Two-way sync of [Claude Code](https://code.claude.com) user config (`~/.claude`) across
Windows, macOS and Linux machines through a private git repo. Additions **and removals**
propagate; machine-specific settings stay put.

## Getting started

You need [uv](https://docs.astral.sh/uv/) and git on `PATH`, and an **empty private git repo**
you can push to (GitHub, GitLab, a self-hosted server — any URL `git push` accepts). That repo
is where your config is synced; it is yours, and your config goes nowhere else.

1. Install the plugin on every machine:
   ```sh
   claude plugin marketplace add zoosewu/cc-sync
   claude plugin install cc-sync@cc-sync
   ```
2. Restart Claude Code, then on the first machine run `/sync init <your-repo-url>`.
   This seeds the repo with that machine's config.
3. On each other machine run the same `/sync init <your-repo-url>`. Joining is a union:
   it adds what the repo has and uploads what only this machine has; nothing is removed.

From then on every session start and every turn syncs in the background.
`/sync remote` shows where you sync to; `/sync remote <new-url>` moves to another repo
(an empty one receives your data; one with unrelated history is refused).

## What syncs

| Synced | Stays local |
|---|---|
| `enabledPlugins`, `extraKnownMarketplaces` (minus local-only patterns such as `*-lsp@*`) | `hooks`, `statusLine`, `autoMode`, permission-related keys, anything not whitelisted |
| preference keys listed in `sync-config.json` | sessions, history, credentials, plugin caches, account-synced skills (`skills/synced/`) |
| `CLAUDE.md`, `skills/`, `agents/`, `commands/`, `os/` | files listed in the machine's `.git/info/exclude` |

Settings are stored one entry per file under `shared/` so git merges them per entry.

## OS-specific content

- `os/<windows|macos|linux>.md` is copied to `~/.claude/rules/cc-sync-os.md` on the matching OS.
- A skill whose frontmatter has `metadata: { os: [linux, macos] }` is turned off through
  `skillOverrides` on other systems.

## Commands

Inside Claude Code:

| Command | What it does |
|---|---|
| `/sync` or `/sync now` | sync now |
| `/sync status` | last sync result |
| `/sync confirm` | push removals held by the brake |
| `/sync init <git-url>` | seed or join a sync repo |
| `/sync remote [git-url]` | show, or move, the sync location |
| `/sync update` | update cc-sync now (it also updates itself after each session-start sync) |

The same CLI without the plugin:

```sh
uvx --from git+https://github.com/zoosewu/cc-sync cc-sync bootstrap <git-url>
uvx --from git+https://github.com/zoosewu/cc-sync cc-sync sync [--force]
uvx --from git+https://github.com/zoosewu/cc-sync cc-sync status | remote [git-url] | update
```

The config directory defaults to `~/.claude`; set `CLAUDE_CONFIG_DIR` or pass `--root` to use another.

## Safety

- Joining is a union: nothing local is removed; conflicting files are backed up to `.cc-sync-backup/`.
- A sync that would remove more than 3 entries (or ≥50% of tracked files) is held until `/sync confirm`.
- Pull conflicts abort the rebase and keep local commits; nothing is resolved automatically.

## Development

```sh
uv run pytest
```

From any machine with the plugin installed, `/cc-sync:enhance <change>` clones this repo to
`~/.cache/cc-sync-dev` (or uses the current checkout), makes the change, runs the tests,
bumps the plugin version, pushes after confirmation, and updates the local plugin.
