#!/usr/bin/env python3
"""Fetch and display diff between two patch sets of a Gerrit change.

Usage:
    gerrit-diff.py <change-number> [--project PROJECT] [--ps1 N] [--ps2 M] [--delta-only] [--comments] [--full [N]]

Examples:
    gerrit-diff.py 754263
    gerrit-diff.py 754263 --project qt-creator/qt-creator
    gerrit-diff.py 754263 --ps1 1 --ps2 2
    gerrit-diff.py 754263 --delta-only
    gerrit-diff.py 754263 --unified
    gerrit-diff.py 754263 --comments
    gerrit-diff.py 754263 --full
    gerrit-diff.py 754263 --full 3

Defaults:
    - Project: qt-creator/qt-creator
    - PS1: first patch set, PS2: latest patch set
    - Output: unified diff (3 lines of context)
"""

import argparse
import base64
import difflib
import json
import subprocess
import sys
import urllib.parse

BASE = "https://codereview.qt-project.org"


def gerrit_json(raw):
    """Parse Gerrit JSON response, stripping the )]}' prefix."""
    if raw.startswith(")]}'"):
        raw = raw[4:]
    return json.loads(raw.lstrip("\n"))


def get_change_info(change_id):
    """Get change details including all revision SHAs."""
    url = f"{BASE}/changes/?q=project:qt-creator/qt-creator+change:{change_id}"
    result = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
    data = gerrit_json(result.stdout)
    if not data:
        print(f"Error: Change {change_id} not found", file=sys.stderr)
        sys.exit(1)
    return data[0]


def get_revision_shas(change_id):
    """Get mapping of patch set number -> commit SHA."""
    change = get_change_info(change_id)
    change_key = change["id"]  # e.g., "qt-creator%2Fqt-creator~754263"

    url = f"{BASE}/changes/{change_key}/detail?o=ALL_REVISIONS"
    result = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
    data = gerrit_json(result.stdout)

    shas = {}
    for sha, info in data.get("revisions", {}).items():
        ps_num = info.get("_number")
        shas[ps_num] = sha
    return shas, change_key


def get_file_list(change_key, rev_sha):
    """Get list of files in a revision."""
    url = f"{BASE}/changes/{change_key}/revisions/{rev_sha}/files"
    result = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
    data = gerrit_json(result.stdout)
    return set(data.keys())


def get_file_lines(change_key, rev_sha, filepath):
    """Get file content as list of lines (base64 decoded)."""
    encoded = urllib.parse.quote(filepath, safe="")
    url = f"{BASE}/changes/{change_key}/revisions/{rev_sha}/files/{encoded}/content"
    result = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
    raw = result.stdout
    if raw.startswith(")]}'"):
        raw = raw[4:]
    raw = raw.lstrip("\n")
    decoded = base64.b64decode(raw).decode("utf-8", errors="replace")
    return decoded.split("\n")


def fetch_diff(change_id, ps1_num, ps2_num, change_key, context=3):
    """Fetch diff between two patch sets."""
    shas, change_key = get_revision_shas(change_id)

    if ps1_num not in shas:
        print(f"Error: Patch set {ps1_num} not found (available: {sorted(shas.keys())})", file=sys.stderr)
        sys.exit(1)
    if ps2_num not in shas:
        print(f"Error: Patch set {ps2_num} not found (available: {sorted(shas.keys())})", file=sys.stderr)
        sys.exit(1)

    rev1 = shas[ps1_num]
    rev2 = shas[ps2_num]

    files1 = get_file_list(change_key, rev1)
    files2 = get_file_list(change_key, rev2)
    all_files = sorted(files1 | files2)

    diffs = []
    for filepath in all_files:
        lines1 = get_file_lines(change_key, rev1, filepath) if filepath in files1 else []
        lines2 = get_file_lines(change_key, rev2, filepath) if filepath in files2 else []

        diff = list(difflib.unified_diff(
            lines1, lines2,
            fromfile=f"a/{filepath}",
            tofile=f"b/{filepath}",
            lineterm="",
            n=context
        ))

        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

        if added == 0 and removed == 0:
            continue

        diffs.append((filepath, added, removed, diff))

    return diffs, shas.get(ps2_num), change_id


def print_unified(diffs, context=3):
    """Print unified diff with specified context lines."""
    total_added = sum(d[1] for d in diffs)
    total_removed = sum(d[2] for d in diffs)

    print("=" * 70)
    print(f"Change: {diffs[0][0].split('/')[-1] if diffs else ''}")
    print(f"Diff between patch sets (unified, {context} lines context)")
    print("=" * 70)
    print()

    for filepath, added, removed, diff_lines in diffs:
        print(f"## {filepath} (+{added} -{removed})")
        print()
        for line in diff_lines:
            print(line)
        print()

    print("=" * 70)
    print(f"TOTAL: +{total_added} -{total_removed}")
    print("=" * 70)


def print_delta(diffs):
    """Print delta-only view (changes only, no context)."""
    total_added = sum(d[1] for d in diffs)
    total_removed = sum(d[2] for d in diffs)

    print("=" * 70)
    print("DELTA-ONLY VIEW (changes only, no context)")
    print("=" * 70)
    print()
    print("Legend: + added, - removed")
    print()

    for filepath, added, removed, diff_lines in diffs:
        print(f"## {filepath} (+{added} -{removed})")
        print()
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                print(f"+ {line[1:]}")
            elif line.startswith("-") and not line.startswith("---"):
                print(f"- {line[1:]}")
        print()

    print("=" * 70)
    print(f"TOTAL: +{total_added} -{total_removed}")
    print("=" * 70)


def parse_git_patch(patch_text):
    """Parse a git format patch into per-file diffs.

    Returns a list of (filepath, added, removed, diff_lines) tuples.
    """
    lines = patch_text.split("\n")
    diffs = []
    current_file = None
    current_diff = []
    in_diff = False

    for line in lines:
        # Detect start of a new file diff
        if line.startswith("diff --git "):
            # Save previous file's diff if any
            if current_file and current_diff:
                added = sum(1 for l in current_diff if l.startswith("+") and not l.startswith("+++"))
                removed = sum(1 for l in current_diff if l.startswith("-") and not l.startswith("---"))
                if added > 0 or removed > 0:
                    diffs.append((current_file, added, removed, current_diff))
            # Extract filepath from "diff --git a/path b/path"
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3][2:]  # Strip "b/" prefix
            current_diff = []
            in_diff = True
        elif in_diff:
            current_diff.append(line)

    # Save last file's diff
    if current_file and current_diff:
        added = sum(1 for l in current_diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in current_diff if l.startswith("-") and not l.startswith("---"))
        if added > 0 or removed > 0:
            diffs.append((current_file, added, removed, current_diff))

    return diffs


def fetch_full_diff(change_key, shas, context=3):
    """Fetch full diff from first to latest patch set.

    For single patch set: uses Gerrit's /patch endpoint (vs parent commit).
    For multiple patch sets: diffs file contents between first and latest.
    """
    ps_numbers = sorted(shas.keys())

    if len(ps_numbers) == 1:
        # Single patch set: use Gerrit's /patch endpoint for efficient diff
        rev_sha = shas[ps_numbers[0]]
        url = f"{BASE}/changes/{change_key}/revisions/{rev_sha}/patch"
        result = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
        raw = result.stdout
        if raw.startswith(")]}'"):
            raw = raw[4:]
        raw = raw.lstrip("\n")
        patch_text = base64.b64decode(raw).decode("utf-8", errors="replace")
        return parse_git_patch(patch_text)

    rev1_sha = shas[ps_numbers[0]]
    rev2_sha = shas[ps_numbers[-1]]

    files1 = get_file_list(change_key, rev1_sha)
    files2 = get_file_list(change_key, rev2_sha)
    all_files = sorted(files1 | files2)

    diffs = []
    for filepath in all_files:
        lines1 = get_file_lines(change_key, rev1_sha, filepath) if filepath in files1 else []
        lines2 = get_file_lines(change_key, rev2_sha, filepath) if filepath in files2 else []

        diff = list(difflib.unified_diff(
            lines1, lines2,
            fromfile=f"a/{filepath}",
            tofile=f"b/{filepath}",
            lineterm="",
            n=context
        ))

        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

        if added == 0 and removed == 0:
            continue

        diffs.append((filepath, added, removed, diff))

    return diffs


def fetch_comments(change_key):
    """Fetch review comments for a change."""
    url = f"{BASE}/changes/{change_key}/comments"
    result = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
    return gerrit_json(result.stdout)


def get_file_lines_from_sha(change_key, sha, filepath):
    """Get file content as list of lines from a specific commit SHA."""
    encoded = urllib.parse.quote(filepath, safe="")
    url = f"{BASE}/changes/{change_key}/revisions/{sha}/files/{encoded}/content"
    result = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
    raw = result.stdout
    if raw.startswith(")]}'"):
        raw = raw[4:]
    raw = raw.lstrip("\n")
    decoded = base64.b64decode(raw).decode("utf-8", errors="replace")
    return decoded.split("\n")


def print_comments(comments, change_key, shas):
    """Print review comments organized by file and line."""
    if not comments:
        print("No comments found.")
        return

    # Gerrit returns comments as arrays keyed by filepath
    sorted_files = sorted(comments.keys())

    print("=" * 70)
    print("REVIEW COMMENTS")
    print("=" * 70)
    print()

    for filepath in sorted_files:
        file_comments = comments[filepath]
        if not isinstance(file_comments, list):
            continue
        
        # Determine which patch set to fetch source from
        # Use the highest patch set number among comments for this file
        ps_for_file = 1
        for c in file_comments:
            ps = c.get("patch_set", 1)
            if ps > ps_for_file:
                ps_for_file = ps
        
        rev_sha = shas.get(ps_for_file)
        if not rev_sha:
            continue
        
        # Fetch file content once per file (for this patch set)
        lines = []
        try:
            lines = get_file_lines_from_sha(change_key, rev_sha, filepath)
        except Exception:
            pass

        print(f"## {filepath} ({len(file_comments)} comment(s))")
        print()

        # Sort by line number (comments without line number first)
        file_comments.sort(key=lambda c: c.get("line", -1))

        for comment in file_comments:
            line = comment.get("line")
            author = comment.get("author", {}).get("name", "Unknown")
            date = comment.get("updated", "")[:19] if comment.get("updated") else ""
            message = comment.get("message", "(no text)")
            unresolved = comment.get("unresolved", False)
            reply_to = comment.get("in_reply_to")

            location = f"line {line}" if line else "file-level"
            status = " [UNRESOLVED]" if unresolved else ""
            
            prefix = f"  [{author}] ({location}){status} {date}"
            if reply_to:
                prefix += " (reply)"
            print(prefix)
            print()
            
            # Show comment text first
            for msg_line in message.split("\n"):
                print(f"    {msg_line}")
            print()
            
            # Then show source context around the comment
            if line and lines:
                context_start = max(0, line - 3)
                context_end = min(len(lines), line + 2)
                
                for i in range(context_start, context_end):
                    marker = ">>>" if (i + 1) == line else "   "
                    content = lines[i] if i < len(lines) else ""
                    print(f"{marker} {i+1}: {content}")
            print()

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Fetch Gerrit diff between patch sets")
    parser.add_argument("change_id", help="Gerrit change number (e.g., 754263)")
    parser.add_argument("--project", default="qt-creator/qt-creator", help="Project path")
    parser.add_argument("--ps1", type=int, default=None, help="First patch set number")
    parser.add_argument("--ps2", type=int, default=None, help="Second patch set number")
    parser.add_argument("--delta-only", action="store_true", help="Show only changed lines (no context)")
    parser.add_argument("--unified", action="store_true", help="Show full unified diff (default)")
    parser.add_argument("--comments", action="store_true", help="Fetch and display review comments")
    parser.add_argument("--full", nargs="?", const=3, type=int, default=None,
                        metavar="CONTEXT",
                        help="Show full diff (first to latest patch set) with N lines of context (default: 3)")
    args = parser.parse_args()

    # Determine patch sets
    shas, change_key = get_revision_shas(args.change_id)
    ps_numbers = sorted(shas.keys())

    if args.ps1 is None:
        args.ps1 = ps_numbers[0]
    if args.ps2 is None:
        args.ps2 = ps_numbers[-1]

    if args.full is not None or len(ps_numbers) == 1:
        # Full diff: first patch set vs latest (all changes in the change)
        # Also used when there's only one patch set
        diffs = fetch_full_diff(change_key, shas, context=args.full if args.full is not None else 3)
        display_title = f"Full diff (patch set {ps_numbers[-1]} vs {ps_numbers[0]})"
    else:
        diffs, ps2_sha, change_id = fetch_diff(args.change_id, args.ps1, args.ps2, change_key, context=3)
        display_title = f"Diff between patch set {args.ps1} and {args.ps2}"

    if not diffs:
        print("No changes found.")
        return

    print("=" * 70)
    print(display_title)
    print("=" * 70)
    print()

    if args.delta_only:
        print_delta(diffs)
    else:
        context = args.full if args.full is not None else 3
        print_unified(diffs, context=context)

    if args.comments:
        comments = fetch_comments(change_key)
        print_comments(comments, change_key, shas)


if __name__ == "__main__":
    main()
