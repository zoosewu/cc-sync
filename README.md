# cc-sync

Two-way sync of [Claude Code](https://code.claude.com) user config (`~/.claude`) across
Windows, macOS and Linux machines through a private git repo. Additions **and removals**
propagate; machine-specific settings stay put.

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

## Usage

```sh
# first machine seeds the data repo, later machines join (union, nothing is removed)
uvx --from git+https://github.com/zoosewu/cc-sync cc-sync bootstrap <your-private-data-repo-url>

cc-sync sync            # export → commit → pull --rebase → apply → push
cc-sync sync --force    # confirm removals held by the brake
cc-sync status
```

The `cc-sync` Claude Code plugin in this repo runs the sync automatically.

## Safety

- Joining is a union: nothing local is removed; conflicting files are backed up to `.cc-sync-backup/`.
- A sync that would remove more than 3 entries (or ≥50% of tracked files) is held until `--force`.
- Pull conflicts abort the rebase and keep local commits; nothing is resolved automatically.

## Development

```sh
uv run pytest
```
