---
name: translations
description: >-
  Update Qt .ts translation catalogs with lupdate and translate only the
  missing/unfinished strings — never re-translate existing ones. Use when the
  user asks to update, refresh, or complete the translations of a Qt project,
  or after adding/changing tr() strings.
license: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
compatibility: >-
  Designed for coding agents with shell access (Claude Code, Codex CLI, and
  similar, e.g. the llama.qtcreator chat tools). Requires lupdate (Qt bin)
  and Python 3.
disable-model-invocation: false
argument-hint: "[catalog.ts | language code]"
metadata:
  author: Cristian Adam
  version: "1.0"
  category: tool
---

# Qt Translation Catalog Updates

Sync the project's `.ts` catalogs with `lupdate` and translate **only** the
unfinished entries. Existing translations are never touched.

## Scope

In scope:

- Running `lupdate` to add new strings and mark obsolete ones.
- Translating messages with `type="unfinished"` (or an empty/missing
  `<translation>`).
- Verifying the result (counts + XML well-formedness).

Out of scope:

- Re-translating or "improving" entries that already have a translation.
- Compiling `.qm` files (the build system does that via `lrelease`).
- Catalogs for the source language (usually `*_en.ts`) and auxiliary files
  such as `*_untranslated.ts` — skip them entirely.

## Workflow

Work on **one catalog per pass**. A catalog typically holds hundreds of
messages and only a fraction is unfinished; processing several languages in
a single conversation runs out of context. If the harness supports
subagents (e.g. a `task` tool with a general/full-tool-access type), launch
one subagent per remaining catalog with a self-contained prompt (catalog
path, target language, and the rules in this skill); otherwise finish the
current catalog and tell the user which ones remain.

1. **Locate the catalogs.** Find the `.ts` files (commonly in a
   `translations/` directory). Determine the target language from the
   catalog's `language` attribute, e.g. `llamacpp_de.ts` → German.

2. **Sync with lupdate.** Run `lupdate` over the project sources with the
   catalog as target. **Do not pass a `CMakeLists.txt`** — Qt 6.7+ lupdate
   rejects it (it only accepts the `qt_add_lupdate` CMake target for CMake
   projects). Pass the source files explicitly instead — the project's own
   `.cpp`/`.h` files, e.g.
   `lupdate *.cpp *.h tools/*.cpp tools/*.h -ts translations/<catalog>.ts`
   (adjust the globs to the project layout; exclude `tests/`, `3rdparty/`,
   and build directories unless they carry translatable strings). lupdate
   adds new messages, marks removed ones `type="obsolete"`, and preserves
   existing translations for unchanged sources — check that the reported
   "already existing" count is in the right ballpark and that the translated
   count did not drop before going on. Make sure `lupdate` is on PATH (it
   lives in the Qt `bin` directory).

3. **List what is missing.**
   `python3 scripts/unfinished.py translations/<catalog>.ts`
   (relative to this skill's base directory). It prints
   `INDEX  LINE  CONTEXT  SOURCE` for every unfinished message, with the
   source text XML-escaped exactly as in the file. Do **not** read the whole
   catalog to find these — catalogs are large and mostly translated.

4. **Translate in batches of ~20–25.** For each entry, update the file with
   an exact in-place edit whose `oldText` is the full message block, e.g.

   ```xml
       <source>Next Completion</source>
       <translation type="unfinished"></translation>
   ```

   and whose `newText` is the same block with the translation filled in and
   `type="unfinished"` removed:

   ```xml
       <source>Next Completion</source>
       <translation>Nächste Vervollständigung</translation>
   ```

   - Copy the `<source>` text verbatim from the script output (it is
     escaped the way the file spells it, e.g. `&apos;`).
   - If a source text is not unique in the file, extend `oldText` with the
     preceding `<location …/>` line(s) — the `LINE` column tells you where
     to read them.
   - **Terminology, in order of authority:**
     1. The catalog's own existing translations — always search the file
        for earlier translations of recurring terms and reuse them
        verbatim.
     2. The Qt phrasebook for the target language, bundled with this skill
        (`phrasebooks/german.qph`, `french.qph`, `japanese.qph`,
        `polish.qph`, `russian.qph`, `swedish.qph`, `danish.qph`,
        `dutch.qph`, `finnish.qph`, `hungarian.qph`, `italian.qph`,
        `norwegian.qph`, `spanish.qph`; no phrasebook exists for cs, hr,
        sl, uk, zh_CN, zh_TW). An exact `<source>` match in the phrasebook
        is the official Qt rendering — use it. Phrasebooks are small XML
        files of `<source>/<target>` pairs; grep them, do not read whole.
     3. For everything else, keep the register and word choices consistent
        with both of the above.
   - **Application context.** Before the first batch, read the project's
     README (and agent instructions such as `AGENTS.md`, if present) once
     and keep a one-paragraph summary of what the application does; use it
     to pick domain-appropriate terms for ambiguous strings. (Qt's own
     machine-translation feature passes the same "Application Context" to
     its translation model.)
   - For short or ambiguous strings (acronyms, single words, UI fragments),
     read the surrounding messages, the `CONTEXT` name, and any
     `<comment>` element (a developer note) before translating.
   - Keep keyboard accelerators (`&File` — translate the text, keep the
     `&`), placeholders (`%1`, `%n`, …), markup, XML entities, and ending
     punctuation intact; never edit `<location>` tags, context names, or
     obsolete entries.
   - **Plurals.** A `<message>` with several `<source>` elements is a
     plural (the script prints the forms joined by ` | `). The
     `<TS>` root element's `forms="…"` attribute names the
     required categories (e.g. `one, few, other`); fill in exactly that
     many `<translation>` elements, one per form, each keeping `%n` and
     using the right grammatical number for its category.

5. **Verify.**
   `python3 scripts/check.py translations/<catalog>.ts`
   must report `OK` (well-formed XML, 0 unfinished). Before running it,
   self-check each batch the way Qt's translation model is prompted to:
   every string is in the target language, no translation is identical to
   its source, and plural messages have exactly the number of forms the
   catalog header requires. If the check fails, inspect the reported lines
   and fix the edit.

6. **Report.** Give the before/after unfinished counts per catalog and list
   any catalogs not yet processed.

## Notes

- The bundled `phrasebooks/` are vendored from the Qt Linguist toolchain
  (`qttools/src/linguist/phrasebooks`); they are the same glossaries the
  Linguist GUI's batch-translation feature matches against. Treat them as
  a terminology reference, not as exhaustive — the catalog's own
  translations win on any conflict.
- `lupdate` rewrites the whole file (reordering locations, refreshing
  line numbers) — that is expected; the translation edits in step 4 happen
  *after* lupdate, so the two do not conflict. Do not run lupdate again
  after editing unless new sources appeared.
- Obsolete entries are left as-is; `lrelease -no-obsolete` (run by the
  build) ignores them, and keeping them lets lupdate re-adopt the
  translation if the source string returns.
- If `lupdate` is not available or not on PATH, say so and stop — do not
  hand-edit `<location>` tags or invent new message blocks.
