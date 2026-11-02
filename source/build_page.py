"""Build ../index.html from data/, template.html, gloss.js and vendor/chess.min.js. Standard library only.

Usage
  python build_page.py
No PGN files are needed: data/puzzles.json already holds the games' moves and headers. To make a new puzzles.json from PGN files, run gen_puzzles.py.
"""
import argparse
import base64
import json
import re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--anonymous', action='store_true', help='write index_anonymous.html: no logo, no brand name, no co-author statement (for blind review)')
args = ap.parse_args()
HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'

moves = json.loads((DATA / 'moves.json').read_text(encoding='utf-8'))
puzzles = json.loads((DATA / 'puzzles.json').read_text(encoding='utf-8'))
takeaways = json.loads((DATA / 'takeaways.json').read_text(encoding='utf-8'))
replies = json.loads((DATA / 'replies.json').read_text(encoding='utf-8'))
for p in puzzles:
    p['takeaway'] = takeaways.get(str(p['ridx']))
comm = json.loads((DATA / 'communities.json').read_text(encoding='utf-8'))
data = dict(puzzles=puzzles, moves=moves, owner_replies=len(replies), comm=comm)

tpl = (HERE / 'template.html').read_text(encoding='utf-8')
lib = (HERE / 'vendor' / 'chess.min.js').read_text(encoding='utf-8').strip()
gloss = (HERE / 'gloss.js').read_text(encoding='utf-8').strip()
def uri(name):
    return 'data:image/png;base64,' + base64.b64encode((HERE / 'assets' / name).read_bytes()).decode('ascii')


html = tpl.replace('/*__LOGO__*/', uri('ihydro-chess-logo-760.png')).replace('/*__FAVICON__*/', uri('favicon.png'))
html = html.replace('/*__DATA__*/null', json.dumps(data, ensure_ascii=False)).replace('/*__GLOSS__*/', gloss)
html = html.replace('/*__CHESSJS__*/', '/* chess.js 0.10.3, BSD-2-Clause licence, Copyright (c) Jeff Hlywa. https://github.com/jhlywa/chess.js */\n' + lib)
i = html.index('<div class="wrap">')
head, body = html[:i], html[i:]
title = re.search(r'<title>.*?</title>', head).group(0)
head = head.replace(title, '')
doc = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
       + title + '\n<meta name="description" content="iHydro Chess: chess puzzles built from real grandmaster games. Each puzzle has as many moves as a real expert reply in the SWAT-MODFLOW Google group; solve the chess, then learn the hydrology.">\n'
       + '<style>html{color-scheme:dark}</style>\n' + head.strip() + '\n</head>\n<body>\n<noscript>This page needs JavaScript to show the chess puzzles.</noscript>\n' + body.strip() + '\n</body>\n</html>\n')
if args.anonymous:
    doc = doc.replace('iHydro Chess', 'Chess puzzles').replace('iHydro Check', 'the tool')
    doc = re.sub(r'<h1 class="brand-lockup">.*?</h1>', '<h1 class="brand-lockup" style="line-height:1.1;font-size:30px">Expert replies as chess puzzles</h1>', doc, flags=re.S)
    doc = re.sub(r'<link rel="icon"[^>]*>', '', doc)
    doc = doc.replace('the group owner is a co-author of this project', 'the group owner is an author of the study (details withheld for review)')
    out = HERE.parent / 'index_anonymous.html'
else:
    out = HERE.parent / 'index.html'
out.write_text(doc, encoding='utf-8')
print(len(doc), 'bytes ->', out)
