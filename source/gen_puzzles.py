"""Fit the coded expert replies to real elite games and write data/puzzles.json.

The code
  * one solver move per move of the reply;
  * a costed move fixes the piece that moves: pawn 0, knight 1, bishop 2, rook 3, queen 4, king or castling 5;
    a move with no cost of its own (manner moves and the promise to look) is a free move: any piece;
  * the solver is White if the reply needed at most L2, Black if it needed L3;
  * a direct reply (class D) is the end of a decisive game (the loser resigns): the solver's last moves;
    a reply that asks (class A or P) is a stretch of the middle of a game, left open;
  * a direct reply for which no game ending in the right resignation is left (none fits, or its games are taken by other replies) is shown as a
    stretch of the middle of a game (kind 'midres': the case is resolved, the game goes on).

Usage
  pip install chess
  python gen_puzzles.py --pgn-dir PATH_TO_PGN_FOLDER [--out data/puzzles.json]
The PGN folder holds the elite games (any depth, *.pgn); it is not part of this repository. The folder names under it set the order in which events are
preferred (EVENT_PRIORITY). The coded replies are in data/replies.json and the cost of each move in data/moves.json.
"""
import argparse
import glob
import json
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

import chess
import chess.pgn

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'
PIECE_OF_RUNG = {0: 'P', 1: 'N', 2: 'B', 3: 'R', 4: 'Q', 5: 'K'}
EVENT_PRIORITY = ['wc_2023_astana', 'wc_2021_dubai', 'candidates_2024', 'norway_chess_2024', 'norway_chess_2025', 'tata_steel_2024', 'tata_steel_2025', 'real_pgn']
# the replies chosen for what they teach, in order of preference (index in data/replies.json)
CURATED = [18, 37, 17, 52, 47, 53, 11, 45, 13, 35, 42, 19, 8, 22, 39, 20, 24, 40, 27, 44, 4, 30, 55, 48, 10, 6, 23, 43, 21, 50, 26, 15, 9, 0, 12, 5, 32]
SEED = 20261029
MID_MIN_K = 2   # direct replies this long or longer may fall back to a stretch of the middle game

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--pgn-dir', default=os.environ.get('CHESS_PGN_DIR'), help='folder with the elite games (*.pgn); or set CHESS_PGN_DIR')
ap.add_argument('--out', default=str(DATA / 'puzzles.json'))
args = ap.parse_args()
if not args.pgn_dir:
    sys.exit('Give --pgn-dir (or set CHESS_PGN_DIR).')
random.seed(SEED)

# ---- the expert replies
RUNG = {m['id']: m['rung'] for m in json.loads((DATA / 'moves.json').read_text(encoding='utf-8'))}
replies = json.loads((DATA / 'replies.json').read_text(encoding='utf-8'))
for r in replies:
    r['rungs'] = [RUNG[m] for m in r['moves'] if RUNG[m] is not None]

# ---- real games (sorted, so that the choice is reproducible)
games = []
for f in sorted(glob.glob(os.path.join(args.pgn_dir, '**', '*.pgn'), recursive=True)):
    folder = os.path.basename(os.path.dirname(f))
    with open(f, encoding='utf-8', errors='replace') as fh:
        while True:
            g = chess.pgn.read_game(fh)
            if g is None:
                break
            games.append((folder, g))
print(len(games), 'games')


def ptype(board, mv):
    return 'K' if (board.is_castling(mv) or board.piece_at(mv.from_square).piece_type == chess.KING) else board.piece_at(mv.from_square).symbol().upper()


def segment(g, start_ply, k):
    """The 2k-1 plies from start_ply: (fen, uci list, solver piece types), or None."""
    moves = list(g.mainline_moves())
    if start_ply + 2 * k - 1 > len(moves):
        return None
    b = g.board()
    for mv in moves[:start_ply]:
        b.push(mv)
    fen = b.fen()
    types, ucis = [], []
    for i in range(2 * k - 1):
        mv = moves[start_ply + i]
        if i % 2 == 0:
            types.append(ptype(b, mv))
        ucis.append(mv.uci())
        b.push(mv)
    return fen, ucis, types


def game_info(g):
    h = g.headers
    url = h.get('GameURL', '')
    return dict(white=h.get('White'), black=h.get('Black'), event=h.get('Event'), date=h.get('Date'), round=h.get('Round'), result=h.get('Result'),
                site=h.get('Site'), whiteElo=h.get('WhiteElo'), blackElo=h.get('BlackElo'), whiteTitle=h.get('WhiteTitle'), blackTitle=h.get('BlackTitle'),
                eco=h.get('ECO'), opening=h.get('Opening'), url=url if url.startswith('https://lichess.org/') else None)


# ---- match: a costed move fixes the piece, a free move leaves it open
cands = defaultdict(list)
mid = defaultdict(list)   # mid-game stretches for direct replies (the fallback)
for ri in CURATED:
    rp = replies[ri]
    k = len(rp['moves'])
    if k < 2 or k > 6 or rp['cls'] not in ('D', 'A', 'P') or not rp['text']:
        continue
    pat = [PIECE_OF_RUNG[RUNG[m]] if RUNG[m] is not None else None for m in rp['moves']]
    side = chess.BLACK if rp['lvl'] >= 3 else chess.WHITE
    kind = 'resign' if rp['cls'] == 'D' else 'analysis'

    def ok(types):
        return all(p is None or p == t for p, t in zip(pat, types))

    def middle(kind, folder, g, moves, into):
        first_ply = 6 if side == chess.WHITE else 7
        for start in range(first_ply, min(len(moves) - 2 * k - 6, 100), 2):
            seg = segment(g, start, k)
            if seg and ok(seg[2]):
                into[ri].append(dict(kind=kind, folder=folder, g=g, start=start, seg=seg, pat=pat))

    for folder, g in games:
        res = g.headers.get('Result')
        moves = list(g.mainline_moves())
        if kind == 'resign':
            if res not in ('1-0', '0-1') or (res == '1-0') != (side == chess.WHITE):
                continue
            if (len(moves) % 2 == 1) != (side == chess.WHITE):
                continue
            start = len(moves) - (2 * k - 1)
            if start < 10:
                continue
            seg = segment(g, start, k)
            if seg and ok(seg[2]):
                cands[ri].append(dict(kind=kind, folder=folder, g=g, start=start, seg=seg, pat=pat))
        else:
            middle(kind, folder, g, moves, cands)
    if kind == 'resign' and k >= MID_MIN_K:
        for folder, g in games:
            middle('midres', folder, g, list(g.mainline_moves()), mid)
print({ri: (replies[ri]['cls'], len(replies[ri]['moves']), len(c)) for ri, c in cands.items()})

# ---- one game per reply, famous events first, never the same game twice
used = set()
puzzles = []


def take(ri, source):
    rp = replies[ri]
    pool = [c for c in source.get(ri, []) if id(c['g']) not in used]
    if not pool:
        return
    pool.sort(key=lambda c: (EVENT_PRIORITY.index(c['folder']) if c['folder'] in EVENT_PRIORITY else 99, random.random()))
    c = pool[0]
    used.add(id(c['g']))
    fen, ucis, types = c['seg']
    b = chess.Board(fen)
    side = 'w' if b.turn == chess.WHITE else 'b'
    sans = []
    for u in ucis:
        mv = chess.Move.from_uci(u)
        assert mv in b.legal_moves
        sans.append(b.san(mv))
        b.push(mv)
    puzzles.append(dict(id=len(puzzles) + 1, ridx=ri, kind=c['kind'], side=side, fen=fen, line=ucis, sans=sans, num=chess.Board(fen).fullmove_number,
                        types=[t if p is not None else None for t, p in zip(types, c['pat'])], k=len(types),
                        game=game_info(c['g']), start_ply=c['start'],
                        reply=dict(cls=rp['cls'], lvl=rp['lvl'], moves=rp['moves'], rungs=rp['rungs'], text=rp['text'], prob=rp['prob'], cat=rp['cat'])))


# first the replies with a game of their own kind (end of a game, or a stretch left open), in the order above; then the direct replies left without one
# take a stretch of the middle game, so the fallback never takes a game another reply needs
for ri in CURATED:
    take(ri, cands)
for ri in CURATED:
    if ri not in {p['ridx'] for p in puzzles}:
        take(ri, mid)
# how many real stretches fit each reply considered (the figure of the paper that describes the page uses this)
chosen = {p['ridx'] for p in puzzles}
matches = []
for ri in CURATED:
    rp = replies[ri]
    k = len(rp['moves'])
    if k < 2 or k > 6 or rp['cls'] not in ('D', 'A', 'P') or not rp['text']:
        continue
    pz = next((p for p in puzzles if p['ridx'] == ri), None)
    kd = pz['kind'] if pz else ('resign' if cands.get(ri) and rp['cls'] == 'D' else None)
    n = len(mid.get(ri, [])) if kd == 'midres' else len(cands.get(ri, []))
    matches.append(dict(ridx=ri, cls=rp['cls'], k=k, kind=kd, side='b' if rp['lvl'] >= 3 else 'w', n_matches=n, n_end_of_game=len(cands.get(ri, [])) if rp['cls'] == 'D' else None, selected=ri in chosen))
json.dump(matches, open(Path(args.out).with_name('matches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump(puzzles, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(puzzles), 'puzzles written to', args.out)
