#!/usr/bin/env python3
"""List the unfinished (missing) translations in Qt .ts catalog(s).

Usage: unfinished.py CATALOG.ts [CATALOG.ts ...]

Prints, per catalog, a summary line followed by one line per unfinished
message:

    INDEX<TAB>LINE<TAB>CONTEXT<TAB>SOURCE

INDEX is a 1-based counter within the catalog, LINE the 1-based line
number of the <message> element in the file (useful for targeted reads),
CONTEXT the <context> name, and SOURCE the source text exactly as it
appears in the file (XML-escaped, newlines written as a literal \\n).
Plural messages (several <source> forms) are printed with the forms
joined by " | " in the catalog's forms order.

Messages with type="obsolete" are skipped. A message counts as
unfinished when any of its <translation> forms carries
type="unfinished" or is empty (including a missing <translation>
element).

Exits 1 if any catalog has unfinished messages, 0 otherwise.
"""

import sys
import xml.parsers.expat
from xml.sax.saxutils import escape


def esc(text: str) -> str:
    return escape(text, {'"': "&quot;", "'": "&apos;"})


class CatalogScanner:
    """expat handler collecting per-message data (with line numbers)."""

    def __init__(self):
        self.entries = []
        self.total = self.translated = self.obsolete = 0
        self._parser = xml.parsers.expat.ParserCreate()
        self._parser.StartElementHandler = self._start
        self._parser.EndElementHandler = self._end
        self._parser.CharacterDataHandler = self._data
        self._stack = []
        self._current_context = ""
        self._reset_message()

    def _reset_message(self):
        self._msg_line = 0
        self._sources = []       # one entry per <source> (plurals)
        self._tr_types = []      # one entry per <translation>
        self._tr_texts = []
        self._capture = None     # which field character data goes to

    def _start(self, name, attrs):
        self._stack.append(name)
        if name == "context":
            self._current_context = ""
        elif name == "message":
            self._reset_message()
            self._msg_line = self._parser.CurrentLineNumber
        elif name == "name" and self._stack[-2:] == ["context", "name"]:
            self._capture = "ctx"
        elif name == "source":
            self._sources.append("")
            self._capture = "source"
        elif name == "translation":
            self._tr_types.append(attrs.get("type"))
            self._tr_texts.append("")
            self._capture = "tr"

    def _end(self, name):
        self._stack.pop()
        if name in ("name", "source", "translation"):
            self._capture = None
        elif name == "message":
            self.total += 1
            if "obsolete" in self._tr_types:
                self.obsolete += 1
                return
            unfinished = (not self._tr_texts
                          or any(t == "unfinished" for t in self._tr_types)
                          or any(not (text or "").strip()
                                 for text, tr_type
                                 in zip(self._tr_texts, self._tr_types)
                                 if tr_type != "obsolete"))
            if unfinished:
                src = " | ".join(self._sources)
                self.entries.append((len(self.entries) + 1,
                                     self._msg_line,
                                     self._current_context,
                                     esc(src.replace("\n", "\\n"))))
            else:
                self.translated += 1

    def _data(self, data):
        if self._capture == "ctx":
            self._current_context += data
        elif self._capture == "source" and self._sources:
            self._sources[-1] += data
        elif self._capture == "tr" and self._tr_texts:
            self._tr_texts[-1] += data


def scan(path: str):
    scanner = CatalogScanner()
    with open(path, "rb") as f:
        scanner._parser.ParseFile(f)
    return (scanner.total, scanner.translated, scanner.obsolete,
            scanner.entries)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2
    any_unfinished = False
    for path in sys.argv[1:]:
        try:
            total, translated, obsolete, entries = scan(path)
        except xml.parsers.expat.ExpatError as err:
            print(f"== {path}: NOT WELL-FORMED XML: {err}")
            any_unfinished = True
            continue
        any_unfinished = any_unfinished or bool(entries)
        print(f"== {path}: {len(entries)} unfinished "
              f"({total} messages, {translated} translated, {obsolete} obsolete)")
        for index, line, context, source in entries:
            print(f"{index}\t{line}\t{context}\t{source}")
    return 1 if any_unfinished else 0


if __name__ == "__main__":
    sys.exit(main())
