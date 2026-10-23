"""Build all data for the 8-max preflop range chart."""
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
N_EIGHT = 50_000
N_VS_RANGE = 50_000

HERE = os.path.dirname(os.path.abspath(__file__))


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
    out = set()
    for tok in tokens:
        tok = tok.strip()
        if not tok:
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
    bad = [h for h in out if len(h) == 3 and h[:2] in (h[1] + h[0],) ]
    if bad:
        raise ValueError(bad)
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


def task_random(cls):
    hero = [eval7.Card(c) for c in COMBOS[cls][0]]
    s = seed_of(cls)
    v1 = eq_vs_random(hero, 1, N_HEADS, s)
    v7 = eq_vs_random(hero, 7, N_EIGHT, s + 17)
    return cls, v1, v7


def task_vs_range(args):
    cls, key, opp_strs = args
    opp_pairs = [(eval7.Card(a), eval7.Card(b)) for a, b in opp_strs]
    hero_combos = [(eval7.Card(a), eval7.Card(b)) for a, b in COMBOS[cls]]
    all_cards = [eval7.Card(r + s) for r in RANKS for s in SUITS]
    rng = random.Random(seed_of(cls + key) + 5)
    total = 0.0
    for _ in range(N_VS_RANGE):
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
    return cls, key, total / N_VS_RANGE


# ------------------------------------------------------------------- ranges
SEATS = ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB", "BB"]
CN = {"UTG": "枪口", "UTG+1": "枪口+1", "MP": "中位", "HJ": "劫位",
      "CO": "关位", "BTN": "按钮", "SB": "小盲", "BB": "大盲"}
BUCKET_OF = {"UTG": "EP", "UTG+1": "EP", "MP": "EP", "HJ": "LP", "CO": "LP",
             "BTN": "LP", "SB": "SB", "BB": None}
BUCKET_NAME = {"EP": "前位", "LP": "后位", "SB": "小盲"}

RFI = {
    "UTG": ["66+", "A9s+", "KTs+", "QTs+", "JTs", "T9s", "98s", "87s", "AJo+", "KJo+"],
    "UTG+1": ["55+", "A8s+", "KTs+", "QTs+", "JTs", "T9s", "98s", "87s", "76s",
              "AJo+", "KJo+", "QJo"],
    "MP": ["44+", "A7s+", "K9s+", "Q9s+", "J9s+", "T9s", "T8s", "98s", "97s", "87s", "86s",
           "ATo+", "KJo+"],
    "HJ": ["33+", "A2s+", "K8s+", "Q8s+", "J8s+", "T8s+", "97s+", "86s+", "75s+", "65s", "54s",
           "ATo+", "KJo+", "QJo"],
    "CO": ["22+", "A2s+", "K7s+", "Q7s+", "J7s+", "T7s+", "96s+", "85s+", "75s+", "64s+", "54s",
           "A9o+", "KTo+", "QTo+", "JTo"],
    "BTN": ["22+", "A2s+", "K2s+", "Q6s+", "J7s+", "T7s+", "96s+", "85s+", "74s+", "63s+",
            "52s+", "43s", "A5o+", "K8o+", "Q8o+", "J8o+", "T8o+", "98o"],
    "SB": ["22+", "A2s+", "K4s+", "Q6s+", "J7s+", "T7s+", "96s+", "85s+", "74s+", "63s+",
           "53s+", "43s", "A5o+", "K8o+", "Q9o+", "J9o+", "T9o"],
}

# hero seat -> bucket -> (3-bet tokens, call tokens)
VS_OPEN = {
    "UTG+1": {"EP": (["TT+", "AQs+", "AKo", "A5s-A3s", "KQs"],
                     ["77-99", "AJs", "ATs", "KJs", "QJs", "JTs", "T9s", "98s", "AQo"])},
    "MP": {"EP": (["99+", "AQs+", "AKo", "A5s-A2s", "KQs"],
                  ["55-88", "AJs", "ATs", "KJs", "QJs", "JTs", "T9s", "98s", "87s", "AQo", "KQo"])},
    "HJ": {"EP": (["88+", "AJs+", "AQo+", "A5s-A2s", "KQs"],
                  ["22-77", "ATs", "A9s", "KTs", "KJs", "QTs", "QJs", "JTs", "T9s", "98s",
                   "87s", "76s", "65s", "KQo"])},
    "CO": {
        "EP": (["77+", "ATs+", "AQo+", "A4s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs"],
               ["22-66", "A9s-A6s", "K9s", "QTs", "T9s", "98s", "87s", "76s", "65s", "54s",
                "AJo", "KQo", "KJo"]),
        "LP": (["66+", "AJs+", "AQo+", "A4s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs"],
               ["22-55", "A9s-A6s", "K9s", "K8s", "QTs", "Q9s", "J9s", "T9s", "98s", "87s",
                "76s", "65s", "54s", "AJo", "KQo", "KJo"]),
    },
    "BTN": {
        "EP": (["55+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs", "T9s", "98s"],
               ["22-44", "A9s-A6s", "K9s", "Q9s", "J9s", "T8s", "97s", "86s", "75s", "65s",
                "54s", "AJo", "ATo", "KJo", "QJo", "KQo"]),
        "LP": (["44+", "A9s+", "ATo+", "A5s-A2s", "KTs+", "QTs+", "JTs", "T9s", "98s", "KQo"],
               ["22-33", "A8s-A6s", "K8s", "K9s", "Q8s", "Q9s", "J8s", "J9s", "T7s", "T8s",
                "96s", "85s", "75s", "64s", "54s", "A9o", "KTo", "QTo", "JTo", "98o"]),
    },
    "SB": {
        "EP": (["66+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs", "T9s",
                "98s", "87s"], []),
        "LP": (["55+", "A9s+", "ATo+", "A5s-A2s", "KTs+", "QTs+", "JTs", "T9s", "98s", "KQo"],
               ["22-44", "A8s-A6s", "K9s", "Q9s", "J9s", "T8s", "97s", "86s", "75s", "65s",
                "54s"]),
    },
    "BB": {
        "EP": (["66+", "ATs+", "AQo+", "A5s-A2s", "KQs", "KJs", "KTs", "QJs", "JTs", "T9s",
                "98s", "87s", "76s", "65s"],
               ["22-55", "A9s-A6s", "K9s", "Q9s", "J9s", "T8s", "97s", "86s", "75s", "64s",
                "54s", "ATo", "AJo", "KJo", "QJo", "KTo", "QTo", "JTo", "T9o", "98o", "87o"]),
        "LP": (["55+", "A9s+", "ATo+", "A5s-A2s", "KTs+", "QTs+", "JTs", "T9s", "98s", "KQo",
                "KJo"],
               ["22-44", "A8s-A6s", "K2s-K7s", "Q6s-Q7s", "J7s", "T7s", "96s", "85s", "74s",
                "64s", "53s", "43s", "A2o-A5o", "K5o-K9o", "Q7o-Q9o", "J8o-J9o", "T8o-T9o",
                "97o", "86o", "76o", "65o"]),
        "SB": (["44+", "A7s+", "ATo+", "A5s-A2s", "K9s+", "QTs+", "JTs", "T9s", "98s", "KQo",
                "KJo", "QJo"],
               ["22-33", "A6s-A2s", "K4s-K8s", "Q5s-Q8s", "J7s-J8s", "T7s-T8s", "96s", "85s",
                "75s", "64s", "54s", "43s", "A2o-A5o", "K5o-K8o", "Q7o-Q9o", "J8o-J9o",
                "T8o-T9o", "98o", "87o", "76o"]),
    },
}

NOTES = {
    "UTG": dict(
        rfi="全场最紧的一档。后面 7 个人都可能拿到强牌，任何跟注都是灾难——只打最强的手牌，纯加注或弃牌。",
        vs="你是第一个行动，正常情况下前面不会有人开池。若真有人入池，说明牌桌非常松，按前位 3-bet 范围收紧处理。"),
    "UTG+1": dict(
        rfi="只比 UTG 略宽：加入中小对子和更多同花连张，但依然以高张强度为主。",
        vs="面对 UTG 这种最紧的范围，3-bet 要极化：只用 TT+/AQs+/AKo 加少数 A5s 诈唬，跟注也只选能压制对方的牌。"),
    "MP": dict(
        rfi="开始纳入全部同花 A 和更多同花连张。被 3-bet 后要更谨慎，因为后面还有 5 个人。",
        vs="开池者来自前位，范围仍是紧的。99+/AQs+/AKo 直接 3-bet，中小对子和同花连张跟注靠隐含赔率。"),
    "HJ": dict(
        rfi="偷盲开始有利可图。同花连张、小对子的隐含赔率明显上升，可以加入更多投机牌。",
        vs="面对前位紧范围，用 88+/AJs+/AQo+ 3-bet；小对子、同花连张跟注寻找便宜翻牌。"),
    "CO": dict(
        rfi="按钮前最后一道关。后面只剩 BTN / SB / BB，可以大幅放宽同花牌和中高张。",
        vs="前位开池时 77+/ATs+/AQo+ 3-bet；后位开池范围更宽，可以加更多 3-bet 诈唬和跟注。"),
    "BTN": dict(
        rfi="全场最宽。翻牌后永远最后一个行动，位置价值最大，可以用超过四成的牌开池偷盲。",
        vs="最理想的位置：面对前位用 55+/ATs+ 3-bet，面对后位可以放宽到 44+/A9s+，跟注范围也最宽。"),
    "SB": dict(
        rfi="翻牌后永远先行动，处境最差。建议纯 raise-or-fold：用较宽的范围直接加注施压，不要平跟。",
        vs="翻后没位置，所以几乎不跟注：要么 3-bet 施压，要么直接弃牌。跟注只有极少数能在翻后好操作的牌。"),
    "BB": dict(
        rfi="",
        vs="已投入 1BB，面对 2.5BB 开池跟注只需约 27% 的胜率，所以防守可以很宽。开池者位置越靠后范围越宽，你跟注也越宽。"),
}

COMBOS = {c: combos_of(c) for c in all_classes()}


def build():
    classes = all_classes()

    cache_path = os.path.join(HERE, "eq_cache.json")
    eq = {}
    if os.path.exists(cache_path):
        eq = {k: tuple(v) for k, v in json.load(open(cache_path, encoding="utf-8")).items()}
    missing = [c for c in classes if c not in eq]
    if missing:
        with Pool(min(20, os.cpu_count() or 4)) as p:
            for c, a, b in p.map(task_random, missing, chunksize=2):
                eq[c] = (a, b)
        json.dump({k: list(v) for k, v in eq.items()}, open(cache_path, "w", encoding="utf-8"))

    rank1 = {c: i + 1 for i, c in enumerate(sorted(classes, key=lambda c: -eq[c][0]))}
    rank7 = {c: i + 1 for i, c in enumerate(sorted(classes, key=lambda c: -eq[c][1]))}

    rfi_sets = {s: expand(RFI[s]) for s in SEATS if s in RFI}
    rfi_sets["BB"] = set()

    # ---- per (seat, bucket) opener range: only seats that actually act before
    vs_ranges = {}
    for i, seat in enumerate(SEATS):
        for b in ("EP", "LP", "SB"):
            eligible = [s for s in SEATS[:i] if BUCKET_OF[s] == b]
            if not eligible:
                continue
            u = set()
            for s in eligible:
                u |= rfi_sets[s]
            vs_ranges[(seat, b)] = {
                "openers": eligible,
                "hands": u,
                "pct": pct(u),
                "combos": [(a, b2) for h in u for a, b2 in COMBOS[h]],
            }

    # ---- equity vs those ranges
    tasks = [(c, f"{s}|{b}", v["combos"])
             for (s, b), v in vs_ranges.items() for c in classes]
    eq_vs = {c: {} for c in classes}
    with Pool(min(20, os.cpu_count() or 4)) as p:
        for c, key, v in p.map(task_vs_range, tasks, chunksize=1):
            eq_vs[c][key] = round(100 * v, 1)

    hands = {}
    for c in classes:
        hands[c] = {
            "eq1": round(100 * eq[c][0], 1),
            "eq7": round(100 * eq[c][1], 1),
            "rank1": rank1[c], "rank7": rank7[c],
            "combos": len(COMBOS[c]),
            "eqVs": eq_vs[c],
        }

    positions = []
    for i, seat in enumerate(SEATS):
        entry = {
            "id": seat, "cn": CN[seat], "behind": 7 - i, "notes": NOTES[seat],
            "vs": {},
        }
        if seat == "BB":
            entry["rfi"] = {"na": True, "raise": [], "call": [], "playPct": 0.0,
                            "raisePct": 0.0, "callPct": 0.0, "label": "加注",
                            "callLabel": "—", "tokens": []}
        else:
            s = rfi_sets[seat]
            entry["rfi"] = {"na": False, "raise": sorted(s), "call": [],
                            "playPct": pct(s), "raisePct": pct(s), "callPct": 0.0,
                            "label": "加注", "callLabel": "—", "tokens": RFI[seat]}

        for b in ("EP", "LP", "SB"):
            key = (seat, b)
            if key not in vs_ranges:
                continue
            if b not in VS_OPEN.get(seat, {}):
                continue
            three, call_t = VS_OPEN[seat][b]
            t3 = expand(three)
            cl = expand(call_t) - t3
            rng_info = vs_ranges[key]
            entry["vs"][b] = {
                "raise": sorted(t3), "call": sorted(cl),
                "raisePct": pct(t3), "callPct": pct(cl), "playPct": pct(t3 | cl),
                "label": "3-Bet", "callLabel": "跟注",
                "raiseTokens": three, "callTokens": [t for t in call_t],
                "eqKey": f"{seat}|{b}",
                "openers": rng_info["openers"],
                "openerPct": rng_info["pct"],
            }
        positions.append(entry)

    out = {"hands": hands, "positions": positions,
           "meta": {"totalCombos": TOTAL, "nHands": len(classes)}}
    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("data.json", os.path.getsize(os.path.join(HERE, "data.json")), "bytes")
    for p in positions:
        r = "n/a" if p["rfi"]["na"] else f"{p['rfi']['playPct']}%"
        vs = {b: (v["raisePct"], v["callPct"], v["openerPct"]) for b, v in p["vs"].items()}
        print(f"{p['id']:6s} rfi {r:>6s} vs {vs}")


if __name__ == "__main__":
    build()
