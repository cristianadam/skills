#!/usr/bin/env python3
"""Validate a Qt .ts catalog: well-formed XML and translation counts.

Usage: check.py CATALOG.ts [CATALOG.ts ...]

Prints a per-catalog summary. Exits 0 only when every catalog is
well-formed and has no unfinished messages.
"""

import sys
import xml.etree.ElementTree as ET


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2
    ok = True
    for path in sys.argv[1:]:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as err:
            print(f"{path}: FAIL - not well-formed XML: {err}")
            ok = False
            continue
        total = translated = obsolete = unfinished = 0
        for ctx in root.iter("context"):
            for msg in ctx.findall("message"):
                total += 1
                trs = msg.findall("translation")
                if any(tr.get("type") == "obsolete" for tr in trs):
                    obsolete += 1
                    continue
                # A plural message (several <translation> forms) is only
                # done when every form is filled in.
                if not trs or any(tr.get("type") == "unfinished"
                                  or not (tr.text or "").strip()
                                  for tr in trs):
                    unfinished += 1
                else:
                    translated += 1
        status = "OK" if unfinished == 0 else "INCOMPLETE"
        print(f"{path}: {status} - {total} messages, {translated} translated, "
              f"{unfinished} unfinished, {obsolete} obsolete")
        ok = ok and unfinished == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
