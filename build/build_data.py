"""Build all data for the 2-9 player preflop range chart."""
import json
import os
import random
import zlib
from multiprocessing import Pool

import eval7

RANKS = "AKQJT98765432"
SUITS = "shdc"
ALL = [eval7.Card(r + s) for r in RANKS for s in SUITS]
TOTAL = 1326

N_HEADS = 120_000
N_POT = 50_000          # 每个「对手人数」的底池份额模拟次数
N_VS_RANGE = 50_000

HERE = os.path.dirname(os.path.abspath(__file__))
FAST = "--fast" in os.sys.argv


def all_classes():
    out = []
    for i, hi in enumerate(RANKS):
        for j, lo in enumerate(RANKS):
            if i == j:
                out.append(hi + lo)
            elif i < j:
                out.append(hi + lo + "s")
            else:
                out.append(lo + hi + "o")
    return out


def combos_of(cls):
    if len(cls) == 2:
        return [(cls[0] + SUITS[i], cls[1] + SUITS[j])
                for i in range(4) for j in range(i + 1, 4)]
    hi, lo, kind = cls[0], cls[1], cls[2]
    if kind == "s":
        return [(hi + s, lo + s) for s in SUITS]
    return [(hi + a, lo + b) for a in SUITS for b in SUITS if a != b]


# ------------------------------------------------------------- range parsing
def expand(tokens):
    """支持 '66+', 'A9s+', 'A5s-A2s', 精确牌，以及 '-A5o'（从前面的集合里剔除）。"""
    out = set()
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith("-"):
            out -= expand([tok[1:]])
            continue
        if "-" in tok:
            a, b = [x.strip() for x in tok.split("-")]
            if len(a) == 2 and len(b) == 2:
                ia, ib = RANKS.index(a[0]), RANKS.index(b[0])
                step = 1 if ia <= ib else -1
                for i in range(ia, ib + step, step):
                    out.add(RANKS[i] * 2)
            else:
                kind, hi = a[2:], a[0]
                ia, ib = RANKS.index(a[1]), RANKS.index(b[1])
                step = 1 if ia <= ib else -1
                for i in range(ia, ib + step, step):
                    out.add(hi + RANKS[i] + kind)
        elif tok.endswith("+"):
            base = tok[:-1]
            if len(base) == 2 and base[0] == base[1]:
                for i in range(0, RANKS.index(base[0]) + 1):
                    out.add(RANKS[i] * 2)
            else:
                hi, lo, kind = base[0], base[1], base[2]
                for i in range(RANKS.index(lo), RANKS.index(hi), -1):
                    out.add(hi + RANKS[i] + kind)
        else:
            out.add(tok)
    return out


def n_combos(s):
    return sum(6 if len(c) == 2 else (4 if c[2] == "s" else 12) for c in s)


def pct(s):
    return round(100.0 * n_combos(s) / TOTAL, 1)


# ------------------------------------------------------------------ equity MC
def seed_of(text):
    return zlib.crc32(text.encode()) & 0x7FFFFFFF


def eq_vs_random(hero_cards, n_opp, trials, seed):
    rng = random.Random(seed)
    deck = [c for c in ALL if c not in hero_cards]
    total = 0.0
    for _ in range(trials):
        rng.shuffle(deck)
        board = deck[:5]
        hs = eval7.evaluate(hero_cards + board)
        idx = 5
        beaten = False
        ties = 0
        for _ in range(n_opp):
            v = eval7.evaluate(deck[idx:idx + 2] + board)
            idx += 2
            if v > hs:
                beaten = True
                break
            if v == hs:
                ties += 1
        if not beaten:
            total += 1.0 / (1 + ties)
    return total / trials


def task_random(args):
    cls, n_opp = args
    hero = [eval7.Card(c) for c in COMBOS[cls][0]]
    return cls, n_opp, eq_vs_random(hero, n_opp, N_POT if n_opp > 1 else N_HEADS,
                                    seed_of(cls + str(n_opp)))


def task_vs_range(args):
    cls, key, opp_strs = args
    opp_pairs = [(eval7.Card(a), eval7.Card(b)) for a, b in opp_strs]
    hero_combos = [(eval7.Card(a), eval7.Card(b)) for a, b in COMBOS[cls]]
    all_cards = [eval7.Card(r + s) for r in RANKS for s in SUITS]
    rng = random.Random(seed_of(cls + key) + 5)
    trials = 2000 if FAST else N_VS_RANGE
    total = 0.0
    for _ in range(trials):
        h = hero_combos[rng.randrange(len(hero_combos))]
        while True:
            o = opp_pairs[rng.randrange(len(opp_pairs))]
            if o[0] != h[0] and o[0] != h[1] and o[1] != h[0] and o[1] != h[1]:
                break
        dead = {h[0], h[1], o[0], o[1]}
        deck = [c for c in all_cards if c not in dead]
        rng.shuffle(deck)
        board = deck[:5]
        a = eval7.evaluate([h[0], h[1]] + board)
        b = eval7.evaluate([o[0], o[1]] + board)
        if a > b:
            total += 1.0
        elif a == b:
            total += 0.5
    return cls, key, total / trials


# ------------------------------------------------------------------- 座位表
TABLES = {
    9: ["UTG", "UTG+1", "UTG+2", "MP", "HJ", "CO", "BTN", "SB", "BB"],
    8: ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB", "BB"],
    7: ["UTG", "MP", "HJ", "CO", "BTN", "SB", "BB"],
    6: ["UTG", "HJ", "CO", "BTN", "SB", "BB"],
    5: ["HJ", "CO", "BTN", "SB", "BB"],
    4: ["CO", "BTN", "SB", "BB"],
    3: ["BTN", "SB", "BB"],
    2: ["BTN", "BB"],
}
CN = {"UTG": "枪口", "UTG+1": "枪口+1", "UTG+2": "枪口+2", "MP": "中位", "HJ": "劫位",
      "CO": "关位", "BTN": "按钮", "SB": "小盲", "BB": "大盲"}

# 每个人数的开池者分组：EP=前位, MP=中后位(HJ/CO), LP=按钮, SB=小盲
BUCKET_SEATS = {
    9: {"EP": ["UTG", "UTG+1", "UTG+2", "MP"], "MP": ["HJ", "CO"], "LP": ["BTN"], "SB": ["SB"]},
    8: {"EP": ["UTG", "UTG+1", "MP"], "MP": ["HJ", "CO"], "LP": ["BTN"], "SB": ["SB"]},
    7: {"EP": ["UTG", "MP"], "MP": ["HJ", "CO"], "LP": ["BTN"], "SB": ["SB"]},
    6: {"EP": ["UTG"], "MP": ["HJ", "CO"], "LP": ["BTN"], "SB": ["SB"]},
    5: {"EP": ["HJ"], "MP": ["CO"], "LP": ["BTN"], "SB": ["SB"]},
    4: {"EP": [], "MP": ["CO"], "LP": ["BTN"], "SB": ["SB"]},
    3: {"EP": [], "MP": [], "LP": ["BTN"], "SB": ["SB"]},
    2: {"EP": [], "MP": [], "LP": [], "SB": ["BTN"]},
}

# ---------------------------------------------------------------- 8 人基准
RFI8 = {
    "UTG": ["66+", "A9s+", "KTs+", "QTs+", "JTs", "T9s", "98s", "87s", "AJo+", "KJo+"],
    "UTG+1": ["55+", "A8s+", "KTs+", "QTs+", "JTs", "T9s", "98s", "87s", "76s",
              "AJo+", "KJo+", "QJo"],
    "MP": ["44+", "A7s+", "K9s+", "Q9s+", "J9s+", "T9s", "T8s", "98s", "97s", "87s", "86s",
           "76s", "ATo+", "KJo+", "QJo"],
    "HJ": ["33+", "A2s+", "K8s+", "Q8s+", "J8s+", "T8s+", "97s+", "86s+", "75s+", "65s",
           "54s", "ATo+", "KJo+", "QJo"],
    "CO": ["22+", "A2s+", "K7s+", "Q7s+", "J7s+", "T7s+", "96s+", "85s+", "75s+", "64s+",
           "54s", "A9o+", "KTo+", "QTo+", "JTo"],
    "BTN": ["22+", "A2s+", "K2s+", "Q6s+", "J7s+", "T7s+", "96s+", "85s+", "74s+", "63s+",
            "52s+", "43s", "A5o+", "K8o+", "Q8o+", "J8o+", "T8o+", "98o"],
    "SB": ["22+", "A2s+", "K4s+", "Q6s+", "J7s+", "T7s+", "96s+", "85s+", "74s+", "63s+",
           "53s+", "43s", "A5o+", "K8o+", "Q9o+", "J9o+", "T9o"],
}

VS8 = {
    "UTG+1": {"EP": (["TT+", "AQs+", "AKo", "A5s-A3s", "KQs"],
                     ["77-99", "AJs", "ATs", "KJs", "QJs", "JTs", "T9s", "98s", "AQo"])},
    "MP": {"EP": (["99+", "AQs+", "AKo", "A5s-A2s", "KQs"],
                  ["55-88", "AJs", "ATs", "KJs", "QJs", "JTs", "T9s", "98s", "87s",
                   "AQo", "KQo"])},
    "HJ": {"EP": (["88+", "AJs+", "AQo+", "A5s-A2s", "KQs"],
                  ["22-77", "ATs", "A9s", "KTs", "KJs", "QTs", "QJs", "JTs", "T9s", "98s",
                   "87s", "76s", "65s", "KQo"])},
    "CO": {
        "EP": (["77+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs"],
               ["22-66", "A9s-A6s", "K9s", "QTs", "T9s", "98s", "87s", "76s", "65s",
                "54s", "AJo", "KQo", "KJo"]),
        "MP": (["66+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs",
                "T9s"],
               ["22-55", "A9s-A6s", "K9s", "QTs", "Q9s", "J9s", "T9s", "98s", "87s",
                "76s", "65s", "54s", "AJo", "KQo", "KJo"]),
        "LP": (["55+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs",
                "T9s", "98s"],
               ["22-44", "A9s-A6s", "K7s-K9s", "Q7s-Q9s", "J8s-J9s", "T7s-T9s",
                "96s-97s", "85s-87s", "76s", "65s", "54s", "AJo", "KQo", "KJo",
                "KTo", "QTo", "JTo", "QTs"]),
    },
    "BTN": {
        "EP": (["55+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs",
                "T9s", "98s"],
               ["22-44", "A9s-A6s", "K9s", "QTs", "Q9s", "J9s", "T8s", "97s", "87s",
                "86s", "76s", "75s", "65s", "54s", "AJo", "ATo", "KJo", "QJo", "KQo"]),
        "MP": (["44+", "A9s+", "ATo+", "A5s-A2s", "KTs+", "QTs+", "JTs", "T9s", "98s",
                "KQo"],
               ["22-33", "A8s-A6s", "K7s-K9s", "Q7s-Q9s", "J7s-J9s", "T7s-T8s",
                "96s-97s", "85s-87s", "75s-76s", "64s-65s", "54s", "AJo", "KJo",
                "KTo", "QJo", "QTo", "JTo", "98o"]),
        "LP": (["44+", "A9s+", "ATo+", "A5s-A2s", "KTs+", "QTs+", "JTs", "T9s", "98s",
                "KQo"],
               ["22-33", "A8s-A6s", "K8s-K9s", "Q8s-Q9s", "J8s-J9s", "T7s-T8s",
                "96s-97s", "85s-87s", "75s-76s", "64s-65s", "54s", "A9o", "KJo",
                "KTo", "QJo", "QTo", "JTo", "98o"]),
    },
    "SB": {
        "EP": (["66+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs",
                "T9s", "98s", "87s"], []),
        "MP": (["66+", "A9s+", "ATo+", "A5s-A2s", "KTs+", "QTs+", "JTs", "T9s", "98s",
                "KQo"],
               ["22-55", "A8s-A6s", "K9s", "Q9s", "J9s", "T8s", "97s", "86s-87s",
                "75s-76s", "65s", "54s"]),
        "LP": (["55+", "A9s+", "ATo+", "A5s-A2s", "KTs+", "QTs+", "JTs", "T9s", "98s",
                "KQo"],
               ["22-44", "A8s-A6s", "K9s", "Q9s", "J9s", "T8s", "97s", "86s-87s",
                "75s-76s", "65s", "54s"]),
    },
    "BB": {
        "EP": (["66+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs",
                "T9s", "98s", "87s", "76s", "65s"],
               ["22-55", "A9s-A6s", "K9s", "QTs", "Q9s", "J9s", "T8s", "97s", "86s",
                "75s", "64s", "54s", "ATo", "AJo", "KQo", "KJo", "QJo", "KTo", "QTo",
                "JTo", "T9o", "98o", "87o"]),
        "MP": (["55+", "A9s+", "ATo+", "A5s-A2s", "KQs", "KJs", "KTs", "QTs+", "JTs",
                "T9s", "98s", "KQo", "KJo"],
               ["22-44", "A8s-A6s", "K5s-K9s", "Q6s-Q9s", "J7s-J9s", "T7s-T8s",
                "96s-97s", "85s-87s", "74s-76s", "64s-65s", "53s-54s", "43s",
                "A2o-A5o", "K7o-KTo", "Q8o-QJo", "J9o-JTo", "T9o", "98o", "87o"]),
        "LP": (["55+", "A9s+", "ATo+", "A5s-A2s", "KTs+", "QTs+", "JTs", "T9s", "98s",
                "KQo", "KJo"],
               ["22-44", "A8s-A6s", "K2s-K9s", "Q6s-Q9s", "J7s-J9s", "T7s-T8s",
                "96s-97s", "85s-87s", "74s-76s", "64s-65s", "53s-54s", "43s",
                "A2o-A5o", "K5o-KTo", "Q7o-QJo", "J8o-JTo", "T8o-T9o", "97o-98o",
                "86o-87o", "76o", "65o"]),
        "SB": (["44+", "A7s+", "ATo+", "A5s-A2s", "K9s+", "QTs+", "JTs", "T9s", "98s",
                "KQo", "KJo", "QJo"],
               ["22-33", "A6s-A2s", "K2s-K8s", "Q5s-Q9s", "J7s-J9s", "T7s-T8s",
                "96s-97s", "85s-87s", "75s-76s", "64s-65s", "54s", "43s",
                "A2o-A5o", "K5o-KTo", "Q7o-QTo", "J8o-JTo", "T8o-T9o", "98o",
                "87o", "76o"]),
    },
}

# ------------------------------------------------------- 各人数 RFI 定义
# 9/7/6 人桌：由 8 人基准按「身后人数等价」平移；5/4/3/2 人桌：专门编写。
RFI_TABLES = {
    9: {
        "UTG": ["66+", "A9s+", "KTs+", "QTs+", "JTs", "T9s", "98s", "AJo+", "KQo"],
        "UTG+1": "UTG@8", "UTG+2": "UTG+1@8", "MP": "MP@8", "HJ": "HJ@8",
        "CO": "CO@8", "BTN": "BTN@8", "SB": "SB@8",
    },
    7: {"UTG": "UTG+1@8", "MP": "MP@8", "HJ": "HJ@8", "CO": "CO@8", "BTN": "BTN@8",
        "SB": "SB@8"},
    6: {"UTG": "MP@8", "HJ": "HJ@8", "CO": "CO@8", "BTN": "BTN@8", "SB": "SB@8"},
    5: {
        "HJ": ["22+", "A2s+", "K6s+", "Q7s+", "J7s+", "T7s+", "96s+", "86s+", "75s+",
               "64s+", "54s", "A9o+", "KTo+", "JTo", "T9o"],
        "CO": ["22+", "A2s+", "K2s+", "Q5s+", "J6s+", "T6s+", "95s+", "85s+", "75s+",
               "64s+", "53s+", "43s", "A7o+", "K9o+", "QTo+", "JTo", "T9o"],
        "BTN": ["22+", "A2s+", "K2s+", "Q2s+", "J4s+", "T5s+", "95s+", "85s+", "74s+",
                "63s+", "53s+", "43s", "A2o+", "K6o+", "Q8o+", "J8o+", "T8o+", "98o",
                "87o"],
        "SB": ["22+", "A2s+", "K2s+", "Q4s+", "J6s+", "T6s+", "95s+", "85s+", "74s+",
               "63s+", "53s+", "43s", "A4o+", "K7o+", "Q9o+", "J9o+", "T9o", "98o"],
    },
    4: {
        "CO": ["22+", "A2s+", "K2s+", "Q3s+", "J5s+", "T5s+", "95s+", "84s+", "74s+",
               "63s+", "52s+", "43s", "A5o+", "K7o+", "Q9o+", "J9o+", "T9o", "98o"],
        "BTN": ["22+", "A2s+", "K2s+", "Q2s+", "J3s+", "T4s+", "94s+", "84s+", "73s+",
                "63s+", "52s+", "42s+", "32s", "A2o+", "K5o+", "Q7o+", "J7o+", "T7o+",
                "97o+", "87o", "76o"],
        "SB": ["22+", "A2s+", "K2s+", "Q3s+", "J6s+", "T6s+", "95s+", "85s+", "74s+",
               "63s+", "53s+", "43s", "A3o+", "K6o+", "Q8o+", "J8o+", "T8o+", "98o",
               "87o"],
    },
    3: {
        "BTN": ["22+", "A2s+", "K2s+", "Q2s+", "J2s+", "T3s+", "93s+", "83s+", "73s+",
                "62s+", "52s+", "42s+", "32s", "A2o+", "K4o+", "Q7o+", "J7o+", "T7o+",
                "96o+", "86o+", "76o", "65o"],
        "SB": ["22+", "A2s+", "K2s+", "Q2s+", "J4s+", "T5s+", "94s+", "84s+", "74s+",
               "63s+", "52s+", "42s+", "32s", "A2o+", "K5o+", "Q7o+", "J7o+", "T7o+",
               "97o+", "87o", "76o"],
    },
    2: {
        "BTN": ["22+",
                "A2s+", "K2s+", "Q2s+", "J2s+", "T2s+", "92s+", "82s+", "72s+", "62s+",
                "52s+", "42s+", "32s",
                "A2o+", "K2o+", "Q2o+", "J2o+", "T2o+", "92o+", "82o+", "72o+", "62o+",
                "52o+",
                "-32o", "-42o", "-43o", "-52o", "-53o", "-62o", "-63o", "-64o", "-72o",
                "-73o", "-74o", "-75o", "-82o", "-83o", "-84o", "-85o", "-92o", "-93o",
                "-94o", "-95o"],
    },
}

# ------------------------------------------------------ 各人数 vs-open 定义
# 9/7/6/5/4 人桌：按座位名复用 8 人结构（5 人 CO 面前位=复用 LP）；3/2 人桌：专门编写。
VS_TABLES = {
    8: {seat: {bucket: f"{seat}.{bucket}@8" for bucket in buckets}
        for seat, buckets in VS8.items()},
    9: {"UTG+1": {"EP": "UTG+1.EP@8"},
        "UTG+2": {"EP": "UTG+1.EP@8"},
        "MP": {"EP": "MP.EP@8"}, "HJ": {"EP": "HJ.EP@8"},
        "CO": {"EP": "CO.EP@8", "MP": "CO.MP@8"},
        "BTN": {"EP": "BTN.EP@8", "MP": "BTN.MP@8", "LP": "BTN.LP@8"},
        "SB": {"EP": "SB.EP@8", "MP": "SB.MP@8", "LP": "SB.LP@8"},
        "BB": {"EP": "BB.EP@8", "MP": "BB.MP@8", "LP": "BB.LP@8", "SB": "BB.SB@8"}},
    7: {"MP": {"EP": "MP.EP@8"}, "HJ": {"EP": "HJ.EP@8"},
        "CO": {"EP": "CO.EP@8", "MP": "CO.MP@8"},
        "BTN": {"EP": "BTN.EP@8", "MP": "BTN.MP@8", "LP": "BTN.LP@8"},
        "SB": {"EP": "SB.EP@8", "MP": "SB.MP@8", "LP": "SB.LP@8"},
        "BB": {"EP": "BB.EP@8", "MP": "BB.MP@8", "LP": "BB.LP@8", "SB": "BB.SB@8"}},
    6: {"HJ": {"EP": "HJ.EP@8"},
        "CO": {"EP": "CO.EP@8", "MP": "CO.MP@8"},
        "BTN": {"EP": "BTN.EP@8", "MP": "BTN.MP@8", "LP": "BTN.LP@8"},
        "SB": {"EP": "SB.EP@8", "MP": "SB.MP@8", "LP": "SB.LP@8"},
        "BB": {"EP": "BB.EP@8", "MP": "BB.MP@8", "LP": "BB.LP@8", "SB": "BB.SB@8"}},
    5: {"CO": {"EP": "CO.MP@8"},
        "BTN": {"MP": "BTN.MP@8", "LP": "BTN.LP@8"},
        "SB": {"MP": "SB.MP@8", "LP": "SB.LP@8"},
        "BB": {"MP": "BB.MP@8", "LP": "BB.LP@8", "SB": "BB.SB@8"}},
    4: {"BTN": {"MP": "BTN.LP@8", "LP": "BTN.LP@8"},
        "SB": {"MP": "SB.LP@8", "LP": "SB.LP@8"},
        "BB": {"MP": "BB.LP@8", "LP": "BB.LP@8", "SB": "BB.SB@8"}},
    3: {
        "SB": {"LP": (["22+", "A2s+", "K7s+", "Q8s+", "J8s+", "T8s+", "97s+", "86s+",
                       "76s", "65s", "A9o+", "K9o+", "Q9o+", "J9o+", "T9o"],
                      ["K5s", "K6s", "Q6s", "Q7s", "J6s", "J7s", "T6s", "T7s", "96s",
                       "85s", "75s", "A5o-A8o", "K8o", "Q8o", "J8o", "T8o", "98o",
                       "87o"])},
        "BB": {"LP": (["22+", "A7s+", "K9s+", "Q9s+", "J9s+", "T9s", "98s", "87s",
                       "76s", "65s", "A9o+", "KTo+", "QTo+"],
                      ["A2s-A6s", "K2s-K8s", "Q6s-Q8s", "J7s-J8s", "T6s-T8s", "96s-97s",
                       "85s-86s", "75s", "64s", "54s", "A2o-A8o", "K7o+", "Q8o+", "J8o+",
                       "T8o+", "98o", "87o", "76o"]),
               "SB": (["22+", "A7s+", "K9s+", "Q9s+", "J9s+", "T9s", "98s", "87s",
                       "76s", "65s", "A9o+", "KTo+", "QTo+"],
                      ["A2s-A6s", "K2s-K8s", "Q6s-Q8s", "J7s-J8s", "T6s-T8s", "96s-97s",
                       "85s-86s", "75s", "64s", "54s", "A2o-A8o", "K7o+", "Q8o+", "J8o+",
                       "T8o+", "98o", "87o", "76o"])},
    },
    2: {"BB": {"SB": (["33+", "A6s+", "A5s-A2s", "K9s+", "Q9s+", "J9s+", "T9s", "98s",
                       "87s", "76s", "A9o+", "KTo+"],
                      ["22", "A2s-A5s", "K2s-K8s", "Q2s-Q8s", "J6s-J8s", "T6s-T8s",
                       "95s+", "85s+", "74s+", "64s+", "53s+", "43s", "A2o-A8o",
                       "K2o-K9o", "Q5o+", "J6o+", "T6o+", "96o+", "86o+", "75o+",
                       "64o+", "54o"])},
        },
}

NOTES = {
    "UTG": ("全场最紧的一档。后面的人都可能拿到强牌，任何跟注都是灾难——只打最强的手牌，纯加注或弃牌。",
            "你是第一个行动，正常情况下前面不会有人开池。若真有人入池，说明牌桌非常松，按前位 3-bet 范围收紧处理。"),
    "UTG+1": ("只比枪口略宽：加入中小对子和更多同花连张，但依然以高张强度为主。",
              "面对前位的紧范围开池：3-bet 要极化，跟注也只选能压制对方的牌。"),
    "UTG+2": ("仍是前位，策略与枪口+1 接近：强牌为主，投机牌只挑同花和连张。",
              "面对前位紧范围开池：3-bet 极化，跟注选有位置潜力的牌。"),
    "MP": ("开始纳入全部同花 A 和更多同花连张。被 3-bet 后要更谨慎。",
           "开池者来自前位，范围仍是紧的。中大对子直接 3-bet，中小对子和同花连张跟注靠隐含赔率。"),
    "HJ": ("偷盲开始有利可图。同花连张、小对子的隐含赔率明显上升，可以加入更多投机牌。",
           "面对前位紧范围，用中对以上 3-bet；小对子、同花连张跟注寻找便宜翻牌。"),
    "CO": ("按钮前最后一道关。后面只剩按钮和盲注，可以大幅放宽同花牌和中高张。",
           "前位开池时收紧 3-bet；后位开池范围更宽，可以加更多 3-bet 诈唬和跟注。"),
    "BTN": ("全场最宽。翻牌后永远最后一个行动，位置价值最大。",
            "最理想的位置：面对前位用中对以上 3-bet，面对后位可以放宽，跟注范围也最宽。"),
    "SB": ("翻牌后永远先行动，处境最差。建议纯 raise-or-fold：直接加注施压，不要平跟。",
           "翻后没位置，所以几乎不跟注：要么 3-bet 施压，要么直接弃牌。"),
    "BB": ("", "已投入 1BB，跟注所需的胜率很低，所以防守可以很宽。开池者位置越靠后范围越宽，你跟注也越宽。"),
}
NOTE_OVERRIDE = {
    2: {"BTN": ("单挑按钮位（同时是小盲）。范围极宽，弃掉的是最差的那些非同花牌；"
                "翻后永远有位置，这是全牌桌最好的一条线。", "")},
    3: {"BTN": ("3 人桌第一个行动，但身后只有两人。范围仍然很宽，翻后位置优势明显。", "")},
}


def resolve_rfi(tokens):
    if isinstance(tokens, str) and tokens.endswith("@8"):
        return RFI8[tokens[:-2]]
    return tokens


def resolve_vs(entry):
    if isinstance(entry, str) and entry.endswith("@8"):
        seat, bucket = entry[:-2].split(".")
        return VS8[seat][bucket]
    return entry


# ================================================================ 筹码档位
BANDS_META = {
    "deep":  {"label": "深码 ≥50BB",  "note": "标准深码现金局：开池 2.5BB，投机牌靠隐含赔率。"},
    "mid":   {"label": "中码 25–50BB", "note": "由深码基准派生：前位去掉小对子和最低连张（隐含赔率不足），后位收紧跟注里的投机连张；3-bet 范围与深码一致。"},
    "short": {"label": "短码 15–25BB", "note": "开池改为 min-raise（遇 3-bet 多弃）；面对开池只剩全下或弃牌——跟注列留空是刻意的：这个深度没有好的跟注空间。"},
    "jam":   {"label": "极短码 ≤15BB", "note": "纯 push/fold（Nash 均衡，来自 holdemmath-data）。多人桌采用单跟注近似求解，全下范围比部分传统表偏宽；比较请看 EV 而非逐手牌。"},
}

# 座位分类（按身后人数），中/短码派生用
def seat_class(behind):
    if behind >= 5: return "EP"
    if behind == 4: return "HJ"
    if behind == 3: return "CO"
    if behind == 2: return "BTN"
    if behind == 1: return "SB"
    return "BB"

# 中码：从深码基准剔除的牌（按类别）
MID_TRIM_RFI = {
    "EP": ["22-44", "54s", "65s"],
    "HJ": ["22-33", "54s", "64s"],
    "CO": ["22", "52s", "53s", "54s", "63s", "64s"],
    "BTN": ["32s", "42s", "43s", "52s", "53s"],
    "SB": ["32s", "42s", "43s", "52s", "53s"],
    "BB": [],
}
MID_TRIM_CALL = ["54s", "64s", "53s", "43s", "32s", "63s", "74s"]

# 短码 15–25BB：开池（min-raise）范围，按类别
SHORT_RFI = {
    "EP":  ["77+", "ATs+", "KTs+", "QTs+", "JTs", "T9s", "AJo+", "KQo"],
    "HJ":  ["55+", "A9s+", "KTs+", "Q9s+", "J9s+", "T9s", "98s", "87s", "ATo+", "KJo+"],
    "CO":  ["44+", "A5s+", "K9s+", "Q9s+", "J9s+", "T8s+", "98s", "87s",
            "A9o+", "KTo+", "QTo+", "JTo"],
    "BTN": ["22+", "A2s+", "K7s+", "Q8s+", "J8s+", "T8s+", "97s+", "87s", "76s",
            "A5o+", "K8o+", "Q9o+", "JTo", "T9o"],
    "SB":  ["22+", "A2s+", "K5s+", "Q7s+", "J7s+", "T7s+", "96s+", "86s+", "76s",
            "65s", "A6o+", "K8o+", "Q9o+", "J9o+", "T9o"],
}

# 短码：面对开池的全下（reshove）范围，[防守类别][开池者档]
SHORT_RESHOVE = {
    ("EP", "EP"):  ["99+", "AQs+", "AKo", "A5s-A3s", "KQs"],
    ("EP", "LP"):  ["88+", "AJs+", "AQo+", "A5s-A2s", "KQs", "KJs", "QJs", "JTs", "T9s"],
    ("HJ", "EP"):  ["88+", "AQs+", "AKo", "A5s-A3s", "KQs", "KJs"],
    ("HJ", "LP"):  ["77+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs",
                    "JTs", "T9s", "98s"],
    ("CO", "EP"):  ["77+", "ATs+", "AQo+", "A5s-A3s", "KQs", "KJs"],
    ("CO", "LP"):  ["55+", "ATs+", "ATo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs",
                    "QTs", "JTs", "T9s", "98s"],
    ("BTN", "EP"): ["77+", "ATs+", "AQo+", "A5s-A3s", "KQs", "KJs", "QJs"],
    ("BTN", "LP"): ["66+", "A9s+", "ATo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs",
                    "QTs", "JTs", "T9s", "98s"],
    ("SB", "EP"):  ["77+", "ATs+", "AQo+", "A5s-A2s", "KQs"],
    ("SB", "LP"):  ["55+", "A9s+", "ATo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs",
                    "JTs", "T9s", "98s", "87s"],
    ("BB", "EP"):  ["66+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs"],
    ("BB", "LP"):  ["44+", "A5s+", "ATo+", "A4s-A2s", "K9s+", "Q9s+", "JTs", "T9s",
                    "98s", "KQo", "KJo"],
    ("BB", "SB"):  ["33+", "A5s+", "A4s-A2s", "K8s+", "Q8s+", "J9s+", "T9s", "98s",
                    "87s", "A9o+", "KTo+", "QTo+", "JTo", "T9o"],
    # MP 桶（面对 HJ/CO 的 min-raise）：比 LP 略紧
    ("CO", "MP"):  ["66+", "ATs+", "AQo+", "A5s-A3s", "KQs", "KJs"],
    ("BTN", "MP"): ["55+", "ATs+", "AQo+", "A5s-A3s", "KQs", "KJs", "KTs", "QJs",
                    "JTs", "T9s"],
    ("SB", "MP"):  ["66+", "A9s+", "ATo+", "A5s-A3s", "KQs", "KJs", "QTs"],
    ("BB", "MP"):  ["55+", "A9s+", "ATo+", "A5s-A3s", "KQs", "KJs", "KJo"],
}

# ------------------------------------------- 被 3bet（你开池后被人加回来）
# 变体 later = 后位 3bet（翻后你没位置：4bet 多诈唬、跟注紧）
#       blind = 盲注 3bet（翻后你有位置：跟注更宽）
# 动作 = 4bet / 跟注 / 弃牌。深码、中码共用；短码另有 jam 表。
V3B = {
    "EP":  {"later": (["QQ+", "AKs", "AKo", "A5s-A3s"],
                      ["JJ-99", "AQs", "AJs", "ATs", "KQs"]),
            "blind": (["QQ+", "AKs", "AKo"],
                      ["JJ-88", "AQs", "AJs", "ATs", "KQs", "QJs", "JTs"])},
    "HJ":  {"later": (["QQ+", "AKs", "AKo", "A5s-A3s"],
                      ["JJ-99", "AQs", "AJs", "ATs", "KQs", "QJs"]),
            "blind": (["QQ+", "AKs", "AKo"],
                      ["JJ-77", "AQs", "AJs", "ATs", "KQs", "KJs-KTs", "QJs", "QTs",
                       "JTs", "T9s", "98s"])},
    "CO":  {"later": (["QQ+", "AKs", "AKo", "A5s-A3s"],
                      ["JJ-88", "AQs", "AJs", "ATs", "KQs", "QJs", "JTs", "T9s"]),
            "blind": (["QQ+", "AKs", "AKo", "A5s"],
                      ["JJ-77", "AQs", "AJs", "ATs", "A9s", "KQs", "KJs-KTs", "QJs",
                       "QTs", "JTs", "T9s", "98s", "87s", "AQo", "AJo"])},
    "BTN": {"blind": (["QQ+", "AKs", "AKo", "A5s-A2s"],
                      ["JJ-77", "AQs", "AJs", "ATs", "A9s", "KQs", "KJs-KTs", "QJs",
                       "QTs", "JTs", "T9s", "98s", "87s", "AQo", "AJo", "KQo"])},
    "SB":  {"later": (["QQ+", "AKs", "AKo", "A5s-A2s"],
                      ["JJ-88", "AQs", "AJs", "ATs", "KQs", "QJs", "JTs", "T9s",
                       "98s"])},
}
# 3bet 方的参考范围（用于「对 3bet 范围胜率」的蒙特卡洛）
V3_RANGE = {
    "later": ["99+", "AJs+", "A5s-A2s", "KQs", "AQo+"],
    "blind": ["88+", "ATs+", "A5s-A2s", "KQs", "KJs", "QJs", "AQo+", "KQo"],
}
# 短码：被 3bet 后基本 jam-or-fold，只列全下（4bet-jam）范围
SHORT_V3B = {
    ("EP", "later"):  ["TT+", "AKs", "AKo"],
    ("EP", "blind"):  ["TT+", "AKs", "AKo", "A5s"],
    ("HJ", "later"):  ["TT+", "AKs", "AKo"],
    ("HJ", "blind"):  ["99+", "AKs", "AKo", "A5s"],
    ("CO", "later"):  ["99+", "AKs", "AKo", "A5s"],
    ("CO", "blind"):  ["99+", "AKs", "AKo", "A5s-A4s"],
    ("BTN", "blind"): ["99+", "AKs", "AKo", "A5s-A2s"],
    ("SB", "later"):  ["99+", "AKs", "AKo", "A5s-A2s"],
}

# ------------------------------------------------- 混合频率（深码面对开池）
# hand: [3bet%, 跟注%]，剩余为弃牌。混合牌从 raise/call 纯集合里移出。
MIX8 = {
    "BB": {
        "EP": {"QTs": [40, 60], "KJo": [0, 55], "ATo": [30, 70], "76s": [50, 0]},
        "MP": {"KQo": [50, 50], "QTs": [40, 60], "J8s": [35, 65], "AJo": [35, 65]},
        "LP": {"KQo": [60, 40], "QTs": [50, 50], "A5o": [50, 0], "QJo": [0, 45],
               "J8o": [0, 50]},
        "SB": {"KQo": [55, 45], "QTs": [45, 55], "A5o": [40, 0], "AJo": [50, 50]},
    },
    "CO": {
        "EP": {"KQo": [50, 50], "AJo": [0, 60], "JTs": [50, 50]},
        "MP": {"KQo": [50, 50], "QTs": [50, 50], "A9s": [0, 60]},
        "LP": {"QTs": [50, 50], "AJo": [0, 60], "KQo": [55, 45]},
    },
    "BTN": {
        "EP": {"A5o": [50, 0], "KJs": [50, 50], "J8s": [0, 55]},
        "MP": {"KJo": [0, 55], "QJo": [0, 50], "A5o": [40, 0], "QTs": [45, 55]},
        "LP": {"KJo": [0, 50], "QJo": [0, 45], "A5o": [40, 0], "K5s": [35, 65]},
    },
    "SB": {
        "EP": {"QJo": [45, 0], "KJo": [50, 0]},
        "MP": {"KJo": [0, 50], "QTs": [45, 55], "A5o": [40, 0]},
        "LP": {"KJo": [0, 55], "QJo": [0, 45], "A5o": [35, 0], "QTs": [45, 55]},
    },
}

# 极短码多人表：PokerCoaching 公开无前注 push/fold 基准（Jonathan Little），
# 座位类别按身后人数（8=UTG … 1=SB）。10BB 参考：UTG 9.8% / BTN 33.0% / SB 58.4%（2026-10-26 修正对子跳档后）。
JAM_PC = {
    "4": {
        "UTG":  ["33+", "A3s+", "A9o+", "K9s+", "KJo+", "Q9s+", "J9s+", "T9s"],
        "UTG1": ["33+", "A2s+", "A8o+", "K9s+", "KJo+", "Q9s+", "QJo", "J9s+", "T9s"],
        "UTG2": ["33+", "A2s+", "A7o+", "A5o", "K7s+", "KTo+", "Q9s+", "QJo", "J9s+", "T9s"],
        "LJ":   ["22+", "A2s+", "A4o+", "K6s+", "KTo+", "Q9s+", "QTo+", "J9s+", "T9s"],
        "HJ":   ["22+", "A2s+", "A2o+", "K5s+", "K9o+", "Q8s+", "QTo+", "J8s+", "JTo", "T9s"],
        "CO":   ["22+", "A2s+", "A2o+", "K2s+", "K7o+", "Q6s+", "Q9o+", "J8s+", "JTo", "T8s+", "98s"],
        "BTN":  ["22+", "A2s+", "A2o+", "K2s+", "K4o+", "Q4s+", "Q8o+", "J7s+", "J9o+", "T7s+", "T9o", "98s"],
        "SB":   ["22+", "A2s+", "A2o+", "K2s+", "K2o+", "Q2s+", "Q3o+", "J2s+", "J4o+",
                 "T2s+", "T4o+", "92s+", "95o+", "83s+", "85o+", "73s+", "75o+",
                 "63s+", "53s+", "43s"],
    },
    "6": {
        "UTG":  ["44+", "A8s+", "A5s", "ATo+", "K9s+", "KQo", "Q9s+", "JTs", "T9s"],
        "UTG1": ["33+", "A4s+", "ATo+", "K9s+", "KQo", "Q9s+", "J9s+", "T9s"],
        "UTG2": ["22+", "A3s+", "A9o+", "K9s+", "KJo+", "Q9s+", "J9s+", "T9s", "98s"],
        "LJ":   ["22+", "A2s+", "A7o+", "K9s+", "KJo+", "Q9s+", "QJo", "J9s+", "T8s+", "98s"],
        "HJ":   ["22+", "A2s+", "A4o+", "K7s+", "KTo+", "Q9s+", "QJo", "J8s+", "T8s+", "98s", "87s"],
        "CO":   ["22+", "A2s+", "A2o+", "K5s+", "K9o+", "Q8s+", "QTo+", "J8s+", "JTo",
                 "T8s+", "98s", "87s", "76s"],
        "BTN":  ["22+", "A2s+", "A2o+", "K2s+", "K7o+", "Q6s+", "Q9o+", "J7s+", "JTo",
                 "T7s+", "97s+", "86s+", "76s", "65s"],
        "SB":   ["22+", "A2s+", "A2o+", "K2s+", "K2o+", "Q2s+", "Q5o+", "J2s+", "J5o+",
                 "T2s+", "T7o+", "95s+", "97o+", "84s+", "86o+", "74s+", "76o",
                 "63s+", "53s+", "43s"],
    },
    "8": {
        "UTG":  ["55+", "A9s+", "AJo+", "KTs+", "KQo", "QTs+", "JTs"],
        "UTG1": ["44+", "A8s+", "A5s", "AJo+", "K9s+", "KQo", "QTs+", "J9s+", "T9s"],
        "UTG2": ["33+", "A7s+", "A5s", "ATo+", "K9s+", "KQo", "Q9s+", "J9s+", "T9s"],
        "LJ":   ["22+", "A3s+", "A9o+", "K9s+", "KJo+", "Q9s+", "J9s+", "T9s", "98s"],
        "HJ":   ["22+", "A2s+", "A8o+", "K8s+", "KJo+", "Q9s+", "QJo", "J8s+", "T8s+", "98s", "87s"],
        "CO":   ["22+", "A2s+", "A3o+", "K7s+", "KTo+", "Q8s+", "QJo", "J8s+", "JTo",
                 "T8s+", "98s", "87s"],
        "BTN":  ["22+", "A2s+", "A2o+", "K4s+", "K9o+", "Q8s+", "QTo+", "J7s+", "JTo",
                 "T7s+", "97s+", "86s+", "76s", "65s"],
        "SB":   ["22+", "A2s+", "A2o+", "K2s+", "K2o+", "Q2s+", "Q5o+", "J2s+", "J7o+",
                 "T4s+", "T7o+", "95s+", "97o+", "85s+", "87o", "74s+", "76o",
                 "64s+", "53s+"],
    },
    "10": {
        "UTG":  ["66+", "A9s+", "A5s-A4s", "AQo+", "KTs+", "QTs+", "JTs"],
        "UTG1": ["55+", "A9s+", "A5s", "AJo+", "KTs+", "QTs+", "JTs"],
        "UTG2": ["44+", "A8s+", "A5s", "AJo+", "K9s+", "KQo", "QTs+", "J9s+", "T9s"],
        "LJ":   ["33+", "A7s+", "A5s", "ATo+", "K9s+", "KJo+", "Q9s+", "J9s+", "T9s"],
        "HJ":   ["22+", "A3s+", "A9o+", "K9s+", "KJo+", "Q9s+", "QJo", "J9s+", "T8s+", "98s"],
        "CO":   ["22+", "A2s+", "A7o+", "A5o", "K8s+", "KTo+", "Q9s+", "QJo",
                 "J8s+", "JTo", "T8s+", "98s", "87s"],
        "BTN":  ["22+", "A2s+", "A2o+", "K5s+", "KTo+", "Q8s+", "QTo+", "J8s+", "JTo",
                 "T7s+", "97s+", "86s+", "76s", "65s"],
        "SB":   ["22+", "A2s+", "A2o+", "K2s+", "K2o+", "Q2s+", "Q7o+", "J3s+", "J8o+",
                 "T4s+", "T8o+", "95s+", "97o+", "84s+", "87o", "74s+", "76o",
                 "64s+", "53s+", "43s"],
    },
    "12": {
        "UTG":  ["99+", "ATs+", "A5s-A3s", "AQo+", "KJs+", "QJs"],
        "UTG1": ["66+", "A9s+", "A5s-A4s", "AQo+", "KTs+", "QTs+", "JTs"],
        "UTG2": ["55+", "A9s+", "A5s", "AJo+", "KTs+", "QTs+", "JTs"],
        "LJ":   ["44+", "A8s+", "A5s", "AJo+", "K9s+", "KQo", "Q9s+", "J9s+", "T9s"],
        "HJ":   ["33+", "A7s+", "A5s-A4s", "ATo+", "K9s+", "KJo+", "Q9s+", "J9s+", "T9s"],
        "CO":   ["22+", "A2s+", "A8o+", "K8s+", "KJo+", "Q8s+", "QJo", "J8s+", "JTo",
                 "T8s+", "98s"],
        "BTN":  ["22+", "A2s+", "A2o+", "K6s+", "KTo+", "Q8s+", "QTo+", "J8s+", "JTo",
                 "T7s+", "97s+", "87s", "76s"],
        "SB":   ["22+", "A2s+", "A2o+", "K2s+", "K3o+", "Q2s+", "Q8o+", "J4s+", "J8o+",
                 "T6s+", "T8o+", "95s+", "98o", "85s+", "87o", "74s+", "64s+", "53s+"],
    },
    "15": {
        "UTG":  ["TT+", "ATs+", "A7s", "A5s-A3s", "AQo+", "KQs"],
        "UTG1": ["TT+", "ATs+", "A5s-A3s", "AQo+", "KJs+", "QJs"],
        "UTG2": ["66+", "ATs+", "A5s-A3s", "AQo+", "KTs+", "QTs+"],
        "LJ":   ["55+", "A9s+", "A5s", "AJo+", "KTs+", "QTs+", "JTs"],
        "HJ":   ["44+", "A8s+", "A5s", "AJo+", "K9s+", "KQo", "Q9s+", "J9s+", "T9s"],
        "CO":   ["22+", "A3s+", "ATo+", "K9s+", "KJo+", "Q9s+", "QJo", "J9s+", "T9s", "98s"],
        "BTN":  ["22+", "A2s+", "A5o+", "K7s+", "KTo+", "Q8s+", "QTo+", "J8s+", "JTo",
                 "T8s+", "98s", "87s"],
        "SB":   ["22+", "A2s+", "A2o+", "K2s+", "K6o+", "Q4s+", "Q9o+", "J6s+", "J9o+",
                 "T6s+", "T8o+", "96s+", "98o", "85s+", "75s+", "64s+", "54s"],
    },
}
# 人数 → 每个座位对应的 JAM_PC 类别（按身后人数）
JAM_CLASS = {
    9: {"UTG": "UTG", "UTG+1": "UTG1", "UTG+2": "UTG2", "MP": "LJ", "HJ": "HJ",
        "CO": "CO", "BTN": "BTN", "SB": "SB", "BB": "BB"},
    8: {"UTG": "UTG1", "UTG+1": "UTG2", "MP": "LJ", "HJ": "HJ", "CO": "CO",
        "BTN": "BTN", "SB": "SB", "BB": "BB"},
    7: {"UTG": "UTG2", "MP": "LJ", "HJ": "HJ", "CO": "CO", "BTN": "BTN",
        "SB": "SB", "BB": "BB"},
    6: {"UTG": "LJ", "HJ": "HJ", "CO": "CO", "BTN": "BTN", "SB": "SB", "BB": "BB"},
    5: {"HJ": "HJ", "CO": "CO", "BTN": "BTN", "SB": "SB", "BB": "BB"},
    4: {"CO": "CO", "BTN": "BTN", "SB": "SB", "BB": "BB"},
    3: {"BTN": "BTN", "SB": "SB", "BB": "BB"},
    2: {"BTN": "HUSB", "BB": "HUBB"},
}

COMBOS = {c: combos_of(c) for c in all_classes()}


def band_positions(size, seats, rfi_map, vs_map, v3_map=None):
    """按人数组装 positions；rfi_map/vs_map/v3_map 给出每座位的内容。"""
    positions = []
    for i, seat in enumerate(seats):
        behind = len(seats) - 1 - i
        notes = NOTE_OVERRIDE.get(size, {}).get(seat) or NOTES[seat]
        entry = {"id": seat, "cn": CN[seat], "behind": behind,
                 "notes": {"rfi": notes[0], "vs": notes[1]}, "vs": {}, "v3": {}}
        spec = rfi_map[seat]
        s = spec["set"]
        entry["rfi"] = {
            "na": seat == "BB", "raise": sorted(s), "call": [],
            "playPct": pct(s), "raisePct": pct(s), "callPct": 0.0,
            "label": spec.get("label", "加注"), "callLabel": "—",
            "tokens": spec.get("tokens", []),
        }
        for bucket in ("EP", "MP", "LP", "SB"):
            info = vs_map.get(seat, {}).get(bucket)
            if not info:
                continue
            t3, cl = info["three"], info["call"]
            e = entry["vs"][bucket] = {
                "raise": sorted(t3), "call": sorted(cl),
                "raisePct": pct(t3), "callPct": pct(cl),
                "playPct": pct(t3 | cl),
                "label": info.get("label", "3-Bet"),
                "callLabel": info.get("callLabel", "跟注"),
                "raiseTokens": info["threeTokens"], "callTokens": info["callTokens"],
                "eqKey": info["eqKey"],
                "openers": info["openers"],
                "openerPct": info.get("openerPct", info["pct"]),
            }
            if info.get("mix"):
                e["mix"] = info["mix"]
        if v3_map:
            for bucket, info in v3_map.get(seat, {}).items():
                entry["v3"][bucket] = {
                    "raise": sorted(info["four"]), "call": sorted(info["call"]),
                    "raisePct": pct(info["four"]), "callPct": pct(info["call"]),
                    "playPct": pct(info["four"] | info["call"]),
                    "label": info.get("label", "4-Bet"),
                    "callLabel": info.get("callLabel", "跟注"),
                    "raiseTokens": info["fourTokens"], "callTokens": info["callTokens"],
                    "eqKey": info["eqKey"], "variant": info["variant"],
                    "rangePct": info.get("rangePct"),
                    "threebettors": info["threebettors"],
                }
        positions.append(entry)
    return positions


def build():
    classes = all_classes()

    # ---- eq1..eq8（对手 1..8 人 = 桌型 2..9 人），缓存
    cache_path = os.path.join(HERE, "eq_cache2.json")
    eq = {}
    if os.path.exists(cache_path):
        eq = {k: dict(v) for k, v in json.load(open(cache_path, encoding="utf-8")).items()}
    tasks = [(c, n) for c in classes for n in range(1, 9) if n not in eq.get(c, {})]
    if tasks:
        with Pool(min(20, os.cpu_count() or 4)) as p:
            for c, n, v in p.map(task_random, tasks, chunksize=4):
                eq.setdefault(c, {})[str(n)] = v
        json.dump(eq, open(cache_path, "w", encoding="utf-8"))

    eq_by_n = {c: [round(100 * eq[c][str(n)], 1) for n in range(1, 9)] for c in classes}
    rank_by_n = {c: [0] * 8 for c in classes}
    for n in range(8):
        order = sorted(classes, key=lambda c: -eq[c][str(n + 1)])
        for i, c in enumerate(order):
            rank_by_n[c][n] = i + 1

    # ---- 深码：现有逻辑
    deep_rfi_sets, deep_vs_ranges, deep_v3_ranges = {}, {}, {}
    for size, seats in TABLES.items():
        deep_rfi_sets[size] = {}
        for seat in seats:
            src = RFI_TABLES.get(size, {}).get(seat)
            if src is None:
                src = RFI8[seat] if seat in RFI8 else []
            deep_rfi_sets[size][seat] = set() if seat == "BB" else expand(resolve_rfi(src))
        table_vs = VS_TABLES.get(size, {})
        for i, seat in enumerate(seats):
            for bucket in ("EP", "MP", "LP", "SB"):
                eligible = [s for s in seats[:i]
                            if s in BUCKET_SEATS[size].get(bucket, [])]
                entry = table_vs.get(seat, {}).get(bucket)
                if not eligible or entry is None:
                    continue
                three, call_t = resolve_vs(entry)
                t3 = expand(three)
                cl = expand(call_t) - t3
                mix = {}
                for h, (r, c) in MIX8.get(seat, {}).get(bucket, {}).items():
                    t3.discard(h)
                    cl.discard(h)
                    mix[h] = {"r": r, "c": c, "f": 100 - r - c}
                u = set()
                for s in eligible:
                    u |= deep_rfi_sets[size][s]
                info = {
                    "openers": eligible, "pct": pct(u),
                    "combos": [(a, b) for h in u for a, b in COMBOS[h]],
                    "three": t3, "call": cl, "threeTokens": three, "callTokens": call_t,
                    "eqKey": f"{size}|{seat}|{bucket}",
                }
                if mix:
                    info["mix"] = mix
                deep_vs_ranges[(size, seat, bucket)] = info

        # 被 3bet：LP3=后位 3bet（你没位置），SB3=盲注 3bet（你有位置；SB 开池时除外）
        for i, seat in enumerate(seats):
            if seat == "BB":
                continue
            after = seats[i + 1:]
            nonblind_after = [s for s in after if s not in ("SB", "BB")]
            cls = seat_class(len(seats) - 1 - i)
            v3buckets = {}
            if nonblind_after and "later" in V3B.get(cls, {}):
                v3buckets["LP3"] = "later"
            if seat == "SB" and "later" in V3B.get(cls, {}):
                v3buckets["SB3"] = "later"          # BB 3bet：翻后小盲先行动
            elif any(s in ("SB", "BB") for s in after) and "blind" in V3B.get(cls, {}):
                v3buckets["SB3"] = "blind"
            for bucket, variant in v3buckets.items():
                four_t, call_t = V3B[cls][variant]
                four = expand(four_t)
                call = expand(call_t) - four
                deep_v3_ranges[(size, seat, bucket)] = {
                    "four": four, "call": call,
                    "fourTokens": four_t, "callTokens": call_t,
                    "variant": variant,
                    "rangePct": pct(expand(V3_RANGE["later" if bucket == "LP3" else "blind"])),
                    "eqKey": f"3b|{'later' if bucket == 'LP3' else 'blind'}",
                    "threebettors": nonblind_after if bucket == "LP3"
                    else [s for s in after if s in ("SB", "BB")],
                }

    vs_tasks = []

    # ---- 深码 positions
    deep_tables = {}
    for size, seats in TABLES.items():
        rfi_map, vs_map, v3_map = {}, {}, {}
        for seat in seats:
            tokens = resolve_rfi(RFI_TABLES.get(size, {}).get(seat) or RFI8.get(seat, []))
            rfi_map[seat] = {"set": deep_rfi_sets[size][seat], "tokens": tokens}
        for (sz, seat, bucket), info in deep_vs_ranges.items():
            if sz != size:
                continue
            vs_map.setdefault(seat, {})[bucket] = info
        for (sz, seat, bucket), info in deep_v3_ranges.items():
            if sz != size:
                continue
            v3_map.setdefault(seat, {})[bucket] = info
        deep_tables[str(size)] = {"positions": band_positions(size, seats, rfi_map, vs_map, v3_map)}

    # ---- 中码：深码剔除投机牌；对范围胜率沿用深码键（开池范围只微调，差值 <1 个点）
    mid_tables = {}
    for size, seats in TABLES.items():
        rfi_map, vs_map, v3_map = {}, {}, {}
        for i, seat in enumerate(seats):
            cls = seat_class(len(seats) - 1 - i)
            base = deep_rfi_sets[size][seat]
            s = (set(base) - expand(MID_TRIM_RFI.get(cls, []))) if seat != "BB" else set()
            rfi_map[seat] = {"set": s,
                             "tokens": resolve_rfi(RFI_TABLES.get(size, {}).get(seat)
                                                   or RFI8.get(seat, []))}
        for seat in seats:
            for bucket in ("EP", "MP", "LP", "SB"):
                info = deep_vs_ranges.get((size, seat, bucket))
                if not info:
                    continue
                call = info["call"] - expand(MID_TRIM_CALL)
                vs_map.setdefault(seat, {})[bucket] = dict(info, call=call)
            for bucket in ("LP3", "SB3"):
                info = deep_v3_ranges.get((size, seat, bucket))
                if info:
                    v3_map.setdefault(seat, {})[bucket] = info
        mid_tables[str(size)] = {"positions": band_positions(size, seats, rfi_map, vs_map, v3_map)}

    # ---- 短码：min-raise 开池 + reshove 全下；跟注刻意留空
    short_tables = {}
    for size, seats in TABLES.items():
        rfi_map, vs_map, v3_map = {}, {}, {}
        for i, seat in enumerate(seats):
            cls = seat_class(len(seats) - 1 - i)
            s = set() if seat == "BB" else expand(SHORT_RFI.get(cls, []))
            rfi_map[seat] = {"set": s, "tokens": SHORT_RFI.get(cls, []),
                             "label": "min-raise"}
        for i, seat in enumerate(seats):
            mycls = seat_class(len(seats) - 1 - i)
            for bucket in ("EP", "MP", "LP", "SB"):
                eligible = [s for s in seats[:i]
                            if s in BUCKET_SEATS[size].get(bucket, [])]
                tokens = SHORT_RESHOVE.get((mycls, bucket))
                if not eligible or tokens is None:
                    continue
                t3 = expand(tokens)
                u = set()
                for s in eligible:
                    u |= rfi_map[s]["set"]
                key = f"short|{size}|{seat}|{bucket}"
                info = {
                    "openers": eligible, "pct": pct(u),
                    "combos": [(a, b) for h in u for a, b in COMBOS[h]],
                    "three": t3, "call": set(),
                    "threeTokens": tokens, "callTokens": [],
                    "eqKey": key, "label": "全下 (reshove)", "callLabel": "—",
                }
                vs_map.setdefault(seat, {})[bucket] = info
                vs_tasks += [(c, key, info["combos"]) for c in classes]
            # 短码被 3bet：jam-or-fold
            if seat != "BB":
                after = seats[i + 1:]
                nonblind_after = [s for s in after if s not in ("SB", "BB")]
                v3buckets = {}
                if nonblind_after and (mycls, "later") in SHORT_V3B:
                    v3buckets["LP3"] = "later"
                if seat == "SB" and (mycls, "later") in SHORT_V3B:
                    v3buckets["SB3"] = "later"
                elif any(s in ("SB", "BB") for s in after) and (mycls, "blind") in SHORT_V3B:
                    v3buckets["SB3"] = "blind"
                for bucket, variant in v3buckets.items():
                    four_t = SHORT_V3B[(mycls, variant)]
                    v3_map.setdefault(seat, {})[bucket] = {
                        "four": expand(four_t), "call": set(),
                        "fourTokens": four_t, "callTokens": [],
                        "variant": variant,
                        "rangePct": pct(expand(V3_RANGE["later" if bucket == "LP3" else "blind"])),
                        "eqKey": f"3b|{'later' if bucket == 'LP3' else 'blind'}",
                        "threebettors": nonblind_after if bucket == "LP3"
                        else [s for s in after if s in ("SB", "BB")],
                        "label": "全下 (4-Bet)", "callLabel": "—",
                    }
        short_tables[str(size)] = {"positions": band_positions(size, seats, rfi_map, vs_map, v3_map)}

    # ---- 极短码：多人 = PokerCoaching 无前注基准；单挑 = holdemmath 近精确均衡
    pf = json.load(open(os.path.join(HERE, "pushfold.json"), encoding="utf-8"))
    jam_out = {
        "depths": pf["depths"],
        "pc": {d: {cls: sorted(expand(toks)) for cls, toks in seats.items()}
               for d, seats in JAM_PC.items()},
        "pcPct": {d: {cls: pct(expand(toks)) for cls, toks in seats.items()}
                  for d, seats in JAM_PC.items()},
        "hu": pf["hu"],
        "classMap": {str(k): v for k, v in JAM_CLASS.items()},
    }
    for d in JAM_PC:
        for cls, toks in JAM_PC[d].items():
            if cls == "SB" or cls[0] == "U" or cls in ("LJ", "HJ", "CO", "BTN"):
                combos = [(a, b) for h in expand(toks) for a, b in COMBOS[h]]
                vs_tasks += [(c, f"jam|pc|{cls}|{d}", combos) for c in classes]
    for d in pf["depths"]:
        combos = [(a, b) for h in pf["hu"][str(d)]["SB"]["h"] for a, b in COMBOS[h]]
        vs_tasks += [(c, f"jam|huSB|{d}", combos) for c in classes]

    # ---- 深码场景的蒙特卡洛
    for info in deep_vs_ranges.values():
        vs_tasks += [(c, info["eqKey"], info["combos"]) for c in classes]
    # 被 3bet：对「3bet 方参考范围」的胜率（两个变体共用，与人数无关）
    for variant, toks in V3_RANGE.items():
        combos = [(a, b) for h in expand(toks) for a, b in COMBOS[h]]
        vs_tasks += [(c, f"3b|{variant}", combos) for c in classes]

    eq_vs = {c: {} for c in classes}
    vs_cache_path = os.path.join(HERE, "vs_cache.json")
    vs_cache = {}
    if os.path.exists(vs_cache_path):
        vs_cache = json.load(open(vs_cache_path, encoding="utf-8"))
    need_tasks = [t for t in vs_tasks
                  if not (t[1] in vs_cache and t[0] in vs_cache[t[1]])]
    if not FAST:
        if need_tasks:
            with Pool(min(20, os.cpu_count() or 4)) as p:
                for c, key, v in p.map(task_vs_range, need_tasks, chunksize=2):
                    vs_cache.setdefault(key, {})[c] = round(100 * v, 1)
            json.dump(vs_cache, open(vs_cache_path, "w", encoding="utf-8"))
        for c in classes:
            eq_vs[c] = {k: vals[c] for k, vals in vs_cache.items() if c in vals}

    hands = {}
    for c in classes:
        hands[c] = {"eqByN": eq_by_n[c], "rankByN": rank_by_n[c],
                    "combos": len(COMBOS[c]), "eqVs": eq_vs[c]}

    out = {
        "hands": hands, "defaultSize": 8,
        "bands": {
            "deep": dict(BANDS_META["deep"], tables=deep_tables),
            "mid": dict(BANDS_META["mid"], tables=mid_tables),
            "short": dict(BANDS_META["short"], tables=short_tables),
            "jam": dict(BANDS_META["jam"], **jam_out),
        },
    }
    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("data.json", os.path.getsize(os.path.join(HERE, "data.json")), "bytes",
          "(FAST)" if FAST else "", "| vs 场景:", len(vs_tasks) // len(classes))

    for band in ("deep", "mid", "short"):
        print(f"--- {band} ---")
        for size in sorted(TABLES):
            ps = out["bands"][band]["tables"][str(size)]["positions"]
            line = "  ".join(f"{p['id']}:{p['rfi']['playPct'] if not p['rfi']['na'] else 'na'}"
                             for p in ps)
            print(f"  {size}ren  {line}")
    print("--- jam 全下% ---")
    for d in ("4", "10", "15"):
        print(f"  {d}bb  " + "  ".join(f"{k}:{v}" for k, v in jam_out["pcPct"][d].items()))
    print("  hu  " + "  ".join(
        f"{d}bb:SB {pf['hu'][str(d)]['SB']['p']}/BBcall {pf['hu'][str(d)]['BB|SB']['p']}"
        for d in pf["depths"]))


if __name__ == "__main__":
    build()
