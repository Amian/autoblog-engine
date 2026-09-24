#!/usr/bin/env python3
"""Self-test for sourcecheck's redirect-drift heuristic. No network.

  python3 scripts/sourcecheck_selftest.py

Why this exists: urlopen follows redirects and reports the FINAL status, so a
retired page that 301s to a homepage returns 200 and passes the gate while the
claim it was cited for is nowhere on the landing page. Two such citations shipped
before a human caught them. The heuristic must stay narrow: a false positive here
blocks an auto-merge queue, which is its own kind of outage.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sourcecheck import redirect_drift as drift

CASES = [
    # (requested, final, should_flag, description)
    ("https://www.utexas.edu/some/retired/sanger-page", "https://www.utexas.edu/", True,
     "deep -> own homepage (the case that shipped)"),
    ("https://a.edu/course/module", "https://outreach.other.gov/", True,
     "deep -> a different host's homepage"),
    ("http://x.org/page/one", "https://x.org/page/one", False, "scheme bump only"),
    ("https://x.org/page/one", "https://x.org/page/one/", False, "trailing slash"),
    ("https://www.x.org/a/b", "https://x.org/a/b", False, "www toggle"),
    ("https://x.org/old/path", "https://x.org/new/path", False, "deep -> deep relocation"),
    ("https://www.python.org/dev/peps/pep-0008/", "https://peps.python.org/pep-0008/", False,
     "real cross-host deep relocation (python.org PEPs)"),
    ("https://x.org/", "https://x.org/", False, "homepage cited, stays homepage"),
    ("https://x.org/", "https://y.org/", False, "homepage cited -> other homepage"),
    ("https://x.org/a?q=1", "https://x.org/a", False, "query dropped"),
    ("https://x.org/a#frag", "https://x.org/a", False, "fragment dropped"),
    ("https://x.org/a", "", False, "no final url reported"),
]

def main() -> int:
    bad = 0
    for req, fin, want, why in CASES:
        got = drift(req, fin) is not None
        if got != want:
            bad += 1
            print(f"  FAIL flag={got} expected={want}  {why}")
        else:
            print(f"  ok   flag={got!s:<5} {why}")
    print()
    print("sourcecheck selftest: all cases passed" if not bad
          else f"sourcecheck selftest: {bad} FAILURE(S)")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
