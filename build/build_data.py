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

# 每个人数的开池者分组：EP=前位, LP=后位, SB=小盲
BUCKET_SEATS = {
    9: {"EP": ["UTG", "UTG+1", "UTG+2", "MP"], "LP": ["HJ", "CO", "BTN"], "SB": ["SB"]},
    8: {"EP": ["UTG", "UTG+1", "MP"], "LP": ["HJ", "CO", "BTN"], "SB": ["SB"]},
    7: {"EP": ["UTG", "MP"], "LP": ["HJ", "CO", "BTN"], "SB": ["SB"]},
    6: {"EP": ["UTG"], "LP": ["HJ", "CO", "BTN"], "SB": ["SB"]},
    5: {"EP": ["HJ"], "LP": ["CO", "BTN"], "SB": ["SB"]},
    4: {"EP": [], "LP": ["CO", "BTN"], "SB": ["SB"]},
    3: {"EP": [], "LP": ["BTN"], "SB": ["SB"]},
    2: {"EP": [], "LP": [], "SB": ["BTN"]},
}

# ---------------------------------------------------------------- 8 人基准
RFI8 = {
    "UTG": ["66+", "A9s+", "KTs+", "QTs+", "JTs", "T9s", "98s", "87s", "AJo+", "KJo+"],
    "UTG+1": ["55+", "A8s+", "KTs+", "QTs+", "JTs", "T9s", "98s", "87s", "76s",
              "AJo+", "KJo+", "QJo"],
    "MP": ["44+", "A7s+", "K9s+", "Q9s+", "J9s+", "T9s", "T8s", "98s", "97s", "87s", "86s",
           "ATo+", "KJo+"],
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
        "EP": (["77+", "ATs+", "AQo+", "A4s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs"],
               ["22-66", "A9s-A6s", "K9s", "QTs", "T9s", "98s", "87s", "76s", "65s",
                "54s", "AJo", "KQo", "KJo"]),
        "LP": (["66+", "AJs+", "AQo+", "A4s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs"],
               ["22-55", "A9s-A6s", "K9s", "K8s", "QTs", "Q9s", "J9s", "T9s", "98s",
                "87s", "76s", "65s", "54s", "AJo", "KQo", "KJo"]),
    },
    "BTN": {
        "EP": (["55+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs",
                "T9s", "98s"],
               ["22-44", "A9s-A6s", "K9s", "Q9s", "J9s", "T8s", "97s", "86s", "75s",
                "65s", "54s", "AJo", "ATo", "KJo", "QJo", "KQo"]),
        "LP": (["44+", "A9s+", "ATo+", "A5s-A2s", "KTs+", "QTs+", "JTs", "T9s", "98s",
                "KQo"],
               ["22-33", "A8s-A6s", "K8s", "K9s", "Q8s", "Q9s", "J8s", "J9s", "T7s",
                "T8s", "96s", "85s", "75s", "64s", "54s", "A9o", "KTo", "QTo", "JTo",
                "98o"]),
    },
    "SB": {
        "EP": (["66+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs",
                "T9s", "98s", "87s"], []),
        "LP": (["55+", "A9s+", "ATo+", "A5s-A2s", "KTs+", "QTs+", "JTs", "T9s", "98s",
                "KQo"],
               ["22-44", "A8s-A6s", "K9s", "Q9s", "J9s", "T8s", "97s", "86s", "75s",
                "65s", "54s"]),
    },
    "BB": {
        "EP": (["66+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs",
                "T9s", "98s", "87s", "76s", "65s"],
               ["22-55", "A9s-A6s", "K9s", "Q9s", "J9s", "T8s", "97s", "86s", "75s",
                "64s", "54s", "ATo", "AJo", "KJo", "QJo", "KTo", "QTo", "JTo", "T9o",
                "98o", "87o"]),
        "LP": (["55+", "A9s+", "ATo+", "A5s-A2s", "KTs+", "QTs+", "JTs", "T9s", "98s",
                "KQo", "KJo"],
               ["22-44", "A8s-A6s", "K2s-K7s", "Q6s-Q7s", "J7s", "T7s", "96s", "85s",
                "74s", "64s", "53s", "43s", "A2o-A5o", "K5o-K9o", "Q7o-Q9o", "J8o-J9o",
                "T8o-T9o", "97o", "86o", "76o", "65o"]),
        "SB": (["44+", "A7s+", "ATo+", "A5s-A2s", "K9s+", "QTs+", "JTs", "T9s", "98s",
                "KQo", "KJo", "QJo"],
               ["22-33", "A6s-A2s", "K4s-K8s", "Q5s-Q8s", "J7s-J8s", "T7s-T8s", "96s",
                "85s", "75s", "64s", "54s", "43s", "A2o-A5o", "K5o-K8o", "Q7o-Q9o",
                "J8o-J9o", "T8o-T9o", "98o", "87o", "76o"]),
    },
}

# ------------------------------------------------------- 各人数 RFI 定义
# 9/7/6 人桌：由 8 人基准按「身后人数等价」平移；5/4/3/2 人桌：专门编写。
RFI_TABLES = {
    9: {
        "UTG": ["66+", "A9s+", "A5s", "KTs+", "QTs+", "JTs", "T9s", "98s", "AJo+", "KQo"],
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
               "64s+", "53s+", "43s", "A7o+", "K9o+", "QTo+", "JTo"],
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
        "MP": {"EP": "MP.EP@8"}, "HJ": {"EP": "HJ.EP@8", "LP": "HJ.LP@8"},
        "CO": {"EP": "CO.EP@8", "LP": "CO.LP@8"},
        "BTN": {"EP": "BTN.EP@8", "LP": "BTN.LP@8"},
        "SB": {"EP": "SB.EP@8", "LP": "SB.LP@8"},
        "BB": {"EP": "BB.EP@8", "LP": "BB.LP@8", "SB": "BB.SB@8"}},
    7: {"MP": {"EP": "MP.EP@8"}, "HJ": {"EP": "HJ.EP@8", "LP": "HJ.LP@8"},
        "CO": {"EP": "CO.EP@8", "LP": "CO.LP@8"},
        "BTN": {"EP": "BTN.EP@8", "LP": "BTN.LP@8"},
        "SB": {"EP": "SB.EP@8", "LP": "SB.LP@8"},
        "BB": {"EP": "BB.EP@8", "LP": "BB.LP@8", "SB": "BB.SB@8"}},
    6: {"HJ": {"EP": "HJ.EP@8", "LP": "HJ.LP@8"},
        "CO": {"EP": "CO.EP@8", "LP": "CO.LP@8"},
        "BTN": {"EP": "BTN.EP@8", "LP": "BTN.LP@8"},
        "SB": {"EP": "SB.EP@8", "LP": "SB.LP@8"},
        "BB": {"EP": "BB.EP@8", "LP": "BB.LP@8", "SB": "BB.SB@8"}},
    5: {"CO": {"EP": "CO.LP@8", "LP": "CO.LP@8"},
        "BTN": {"EP": "BTN.EP@8", "LP": "BTN.LP@8"},
        "SB": {"EP": "SB.EP@8", "LP": "SB.LP@8"},
        "BB": {"EP": "BB.EP@8", "LP": "BB.LP@8", "SB": "BB.SB@8"}},
    4: {"BTN": {"LP": "BTN.LP@8"},
        "SB": {"LP": "SB.LP@8"},
        "BB": {"LP": "BB.LP@8", "SB": "BB.SB@8"}},
    3: {
        "SB": {"LP": (["22+", "A2s+", "K7s+", "Q8s+", "J8s+", "T8s+", "97s+", "86s+",
                       "76s", "65s", "A9o+", "K9o+", "Q9o+", "J9o+", "T9o"],
                      ["K5s", "K6s", "Q6s", "Q7s", "J6s", "J7s", "T6s", "T7s", "96s",
                       "85s", "75s", "A5o", "A6o", "K8o", "Q8o", "J8o", "T8o", "98o",
                       "87o"])},
        "BB": {"LP": (["22+", "A7s+", "K9s+", "Q9s+", "J9s+", "T9s", "98s", "87s",
                       "76s", "65s", "A9o+", "KTo+", "QTo+"],
                      ["A2s-A6s", "K2s-K8s", "Q6s-Q8s", "J7s-J8s", "T6s-T8s", "96s",
                       "85s", "75s", "64s", "54s", "A2o-A8o", "K7o+", "Q8o+", "J8o+",
                       "T8o+", "98o", "87o", "76o"]),
               "SB": (["22+", "A7s+", "K9s+", "Q9s+", "J9s+", "T9s", "98s", "87s",
                       "76s", "65s", "A9o+", "KTo+", "QTo+"],
                      ["A2s-A6s", "K2s-K8s", "Q6s-Q8s", "J7s-J8s", "T6s-T8s", "96s",
                       "85s", "75s", "64s", "54s", "A2o-A8o", "K7o+", "Q8o+", "J8o+",
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


COMBOS = {c: combos_of(c) for c in all_classes()}


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

    # ---- 每个人数的 RFI 集合
    rfi_sets = {}
    for size, seats in TABLES.items():
        rfi_sets[size] = {}
        for seat in seats:
            if seat == "BB":
                rfi_sets[size][seat] = set()
                continue
            src = RFI_TABLES.get(size, {}).get(seat)
            if src is None:
                src = RFI8[seat]  # 8 人基准表自身
            rfi_sets[size][seat] = expand(resolve_rfi(src))

    # ---- 每个人数每座位面对的开池者分组与 vs 范围
    vs_ranges = {}   # (size, seat, bucket) -> info
    vs_tasks = []
    for size, seats in TABLES.items():
        table_vs = VS_TABLES.get(size, {})
        for i, seat in enumerate(seats):
            for bucket in ("EP", "LP", "SB"):
                eligible = [s for s in seats[:i]
                            if s in BUCKET_SEATS[size].get(bucket, [])]
                if not eligible:
                    continue
                entry = table_vs.get(seat, {}).get(bucket)
                if entry is None:
                    continue
                three, call_t = resolve_vs(entry)
                t3 = expand(three)
                cl = expand(call_t) - t3
                u = set()
                for s in eligible:
                    u |= rfi_sets[size][s]
                key = f"{size}|{seat}|{bucket}"
                combos_strs = [(a, b) for h in u for a, b in COMBOS[h]]
                vs_ranges[(size, seat, bucket)] = {
                    "openers": eligible, "hands": u, "pct": pct(u),
                    "combos": combos_strs, "three": t3, "call": cl,
                    "threeTokens": three, "callTokens": call_t,
                }
                vs_tasks += [(c, key, combos_strs) for c in classes]

    eq_vs = {c: {} for c in classes}
    if not FAST:
        with Pool(min(20, os.cpu_count() or 4)) as p:
            for c, key, v in p.map(task_vs_range, vs_tasks, chunksize=2):
                eq_vs[c][key] = round(100 * v, 1)

    hands = {}
    for c in classes:
        hands[c] = {
            "eqByN": eq_by_n[c],
            "rankByN": rank_by_n[c],
            "combos": len(COMBOS[c]),
            "eqVs": eq_vs[c],
        }

    # ---- 组装每个人数的 positions
    tables_out = {}
    for size, seats in TABLES.items():
        positions = []
        for i, seat in enumerate(seats):
            notes = NOTE_OVERRIDE.get(size, {}).get(seat) or NOTES[seat]
            entry = {"id": seat, "cn": CN[seat], "behind": len(seats) - 1 - i,
                     "notes": {"rfi": notes[0], "vs": notes[1]}, "vs": {}}
            s = rfi_sets[size][seat]
            entry["rfi"] = {
                "na": seat == "BB", "raise": sorted(s), "call": [],
                "playPct": pct(s), "raisePct": pct(s), "callPct": 0.0,
                "label": "加注", "callLabel": "—",
                "tokens": resolve_rfi(RFI_TABLES.get(size, {}).get(seat) or RFI8.get(seat, [])),
            }
            for bucket in ("EP", "LP", "SB"):
                info = vs_ranges.get((size, seat, bucket))
                if not info:
                    continue
                entry["vs"][bucket] = {
                    "raise": sorted(info["three"]), "call": sorted(info["call"]),
                    "raisePct": pct(info["three"]), "callPct": pct(info["call"]),
                    "playPct": pct(info["three"] | info["call"]),
                    "label": "3-Bet", "callLabel": "跟注",
                    "raiseTokens": info["threeTokens"],
                    "callTokens": info["callTokens"],
                    "eqKey": f"{size}|{seat}|{bucket}",
                    "openers": info["openers"], "openerPct": info["pct"],
                }
            positions.append(entry)
        tables_out[str(size)] = {"positions": positions}

    out = {"hands": hands, "tables": tables_out, "defaultSize": 8}
    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("data.json", os.path.getsize(os.path.join(HERE, "data.json")), "bytes",
          "(FAST)" if FAST else "")

    for size in sorted(TABLES):
        print(f"--- {size} 人桌 ---")
        for p in tables_out[str(size)]["positions"]:
            r = "n/a" if p["rfi"]["na"] else f"{p['rfi']['playPct']}%"
            vs = {b: (v["raisePct"], v["callPct"]) for b, v in p["vs"].items()}
            print(f"  {p['id']:6s} rfi {r:>6s} vs {vs}")


if __name__ == "__main__":
    build()
