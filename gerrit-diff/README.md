# Gerrit Diff Fetching & Comments

Fetch and display diffs between Gerrit patch sets, including review comments.

## What it does

1. **Parses Gerrit URLs or change numbers** — extracts project, change ID, and optional patch set range.
2. **Fetches inter-patch-set diffs** — retrieves file contents from both patch sets and diffs them locally for accurate results (Gerrit's `/diff` endpoint compares against git parent, not a specific patch set).
3. **Full change diff** — shows all changes from first to latest patch set in a single view.
4. **Delta-only view** — quickly scan what changed without context lines.
5. **Review comments** — fetch and display all review comments organized by file and line, with source context.

## Usage

```bash
# Basic diff between first and latest patch set
python3 gerrit-diff.py 754263

# Specific patch sets
python3 gerrit-diff.py 754263 --ps1 1 --ps2 2

# Delta-only view (changed lines only)
python3 gerrit-diff.py 754263 --delta-only

# Full diff with default context (3 lines)
python3 gerrit-diff.py 754263 --full

# Full diff with custom context (10 lines)
python3 gerrit-diff.py 754263 --full 10

# Diff with review comments
python3 gerrit-diff.py 754263 --comments

# Different project
python3 gerrit-diff.py 12345 --project qt/tqtcreator
```

## How It Works

The Gerrit REST API does not support the `change-id/ps1..ps2` range notation directly. The script:

1. **Queries the change** to get the change key and all revision SHAs.
2. **For each file**, fetches content from both patch sets via the `/files/<path>/content` endpoint.
3. **Diffs locally** using Python's `difflib.unified_diff()` to produce accurate inter-patch-set diffs.

For full diffs (`--full`), it compares the latest revision against the first patch set, showing all changes accumulated across all patch sets.

## Arguments

| Flag | Description |
|------|-------------|
| `--project PROJECT` | Gerrit project path (default: `qt-creator/qt-creator`) |
| `--ps1 N --ps2 M` | Specific patch set numbers (defaults to first and latest) |
| `--delta-only` | Show only `+`/`-` lines, no context |
| `--full [N]` | Full diff from first to latest patch set with N lines of context (default: 3) |
| `--comments` | Fetch and display review comments |

## Output Formats

**Unified diff** (default): Shows each changed file with a header, `---`/`+++` markers, `@@` hunk headers, and 3 lines of context around each change — matching standard git diff format.

**Delta-only**: Strips all context lines, showing only the `+` and `-` lines with a `+ ` / `- ` prefix for readability.

**Comments**: Organized by file, showing author, date, line number (or "file-level"), comment text, and source context with a `>>>` marker on the commented line. Unresolved comments are flagged with `[UNRESOLVED]`.

## Requirements

- Python 3.6+
- `curl` (for Gerrit API requests)
- No external dependencies — uses only Python standard library (`difflib`, `json`, `base64`, `urllib.parse`, `argparse`)

## Installation

Copy `references/scripts/gerrit-diff.py` to a location in your PATH, or invoke it directly with:

```bash
python3 <skill-path>/references/scripts/gerrit-diff.py <change-number> [options]
```

## License

LicenseRef-Qt-Commercial OR BSD-3-Clause
