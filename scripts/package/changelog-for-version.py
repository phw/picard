#!/usr/bin/env python

import re
import sys


if len(sys.argv) == 1:
    sys.exit(1)

version = sys.argv[1]
re_changes = re.compile(r'^# Version ' + re.escape(version) + '.*?\n(.*?)# Version',
    re.DOTALL | re.MULTILINE)

with open('NEWS.md', 'r') as newsfile:
    news = newsfile.read()
    result = re_changes.search(news)
    if not result:
        sys.exit(1)
    print(result[1].strip())
