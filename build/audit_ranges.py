# -*- coding: utf-8 -*-
"""全面审计范围表：找所有内部倒挂（dominance inversion）与结构问题。只报告，不修改。"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import build_data as B

RANKS = B.RANKS

# ---------- 1) 线上产物与本地 data.json 一致性 ----------
html = open('../docs/index.html', encoding='utf-8').read()
i = html.index('const D = ') + len('const D = ')
depth = 0; j = i
while True:
    c = html[j]
    if c == '{': depth += 1
    elif c == '}':
        depth -= 1
        if depth == 0: break
    j += 1
Ddoc = json.loads(html[i:j+1])
Dbuild = json.load(open('data.json', encoding='utf-8'))
print('== 线上 docs/index.html 与 data.json 一致:', Ddoc == Dbuild)

CLASSES = B.all_classes()

def dominates(a, b):
    """a 是否严格压制 b（同类别：对子按大小，同高牌按踢脚）。"""
    if len(a) == 2 and len(b) == 2:
        return RANKS.index(a[0]) < RANKS.index(b[0])
    if len(a) == 3 and len(b) == 3 and a[0] == b[0] and a[2] == b[2]:
        return RANKS.index(a[1]) < RANKS.index(b[1])
    return False

ORD = {'fold': 0, 'call': 1, 'raise': 2}

def audit_scenario(band, size, seat, scen, c):
    raise_set, call_set = set(c['raise']), set(c['call'])
    act = {}
    for h in CLASSES:
        act[h] = 'raise' if h in raise_set else ('call' if h in call_set else 'fold')
    errs, revs = [], []
    for a in CLASSES:
        for b in CLASSES:
            if a == b or not dominates(a, b):
                continue
            # 同点数 s vs o：同花版弃牌、杂花版反而能玩 -> 硬错误
            if len(a) == 3 and a[:2] == b[:2] and a[2] == 's' and b[2] == 'o':
                if ORD[act[b]] > ORD[act[a]]:
                    errs.append(f'{b}({act[b]}) 可玩但更强的 {a} 却 {act[a]}')
                continue
            oa, ob = ORD[act[a]], ORD[act[b]]
            if act[a] == 'fold' and ob > 0:
                errs.append(f'{b}({act[b]}) 可玩但压制它的 {a} 却弃牌')
            elif act[b] == 'raise' and oa == 1:
                revs.append(f'{b} 3bet 而 {a} 只跟注（可能是有意的极化，需人工判断）')
    return errs, revs, act

# ---------- 2) 扫 deep/mid/short 全部场景 ----------
print()
print('=' * 70)
total_err = 0
for band in ('deep', 'mid', 'short'):
    for size in sorted(Dbuild['bands'][band]['tables'], key=int):
        for pos in Dbuild['bands'][band]['tables'][size]['positions']:
            seat = pos['id']
            scenarios = [('RFI', pos['rfi'])] if not pos['rfi']['na'] else []
            for bk, v in pos['vs'].items():
                scenarios.append((f'vs-{bk}', v))
            for name, c in scenarios:
                errs, revs, act = audit_scenario(band, size, seat, name, c)
                # pct 字段一致性
                rp = B.pct(raise_set) if False else None
                if errs:
                    total_err += len(errs)
                    print(f'\n[{band}/{size}人/{seat}/{name}] {len(errs)} 处硬倒挂:')
                    for e in errs: print('   ✗', e)
                if revs and band == 'deep' and size == '8':
                    for r in revs: pass  # 3bet/跟注极化太多，只统计不打印
print()
print('硬倒挂总数:', total_err)
print('=' * 70)

# ---------- 3) 桶跨度：同一"面对开池"桶里最窄/最宽开池者 ----------
print()
print('== 桶跨度（同一桶内不同开池者范围的差异）==')
for size in sorted(B.TABLES, key=int, reverse=True):
    seats = B.TABLES[size]
    for bk in ('EP', 'LP', 'SB'):
        eligible = [s for s in seats if s in B.BUCKET_SEATS[size].get(bk, [])]
        if len(eligible) < 2: continue
        pcts = []
        for s in eligible:
            src = B.resolve_rfi(B.RFI_TABLES.get(size, {}).get(s) or B.RFI8.get(s, []))
            pcts.append(f'{s}={B.pct(B.expand(src))}%')
        print(f'  {size}人桌 桶{bk}: ' + '  '.join(pcts))

# ---------- 4) RFI 跨座位嵌套性（后位应 ⊇ 前位）----------
print()
print('== RFI 嵌套性违规（后位弃牌但前位开池的手牌）==')
for size in sorted(B.TABLES, key=int, reverse=True):
    seats = B.TABLES[size]
    sets_ = {}
    for s in seats:
        if s == 'BB': continue
        src = B.resolve_rfi(B.RFI_TABLES.get(size, {}).get(s) or B.RFI8.get(s, []))
        sets_[s] = B.expand(src)
    for i in range(len(seats)):
        for jj in range(i + 1, len(seats)):
            a, bb = seats[i], seats[jj]
            if a == 'BB' or bb == 'BB': continue
            miss = sets_[a] - sets_[bb]
            if miss:
                print(f'  {size}人桌 {bb} 没开但前位 {a} 开: {sorted(miss, key=lambda x: -B.n_combos({x}))}')

# ---------- 5) JAM_PC 异常：对子跳档 + 深度非单调 ----------
print()
print('== 极短码 JAM_PC 检查 ==')
for d, seats_ in sorted(B.JAM_PC.items(), key=lambda kv: int(kv[0])):
    for cls, toks in seats_.items():
        s = B.expand(toks)
        pairs = sorted([h for h in s if len(h) == 2], key=lambda x: RANKS.index(x[0]))
        # 找对子序列中的洞（在最大最小之间缺失）
        idxs = [RANKS.index(p[0]) for p in pairs]
        if idxs:
            holes = [RANKS[k]*2 for k in range(idxs[0], idxs[-1]) if k not in idxs]
            if holes:
                print(f'  {d}bb {cls}: 对子跳档，缺 {holes}  (有: {pairs})')
# 深度单调性：深 -> 紧
print('  -- 深度单调性（深码范围应 ⊆ 浅码范围；列出违反的手牌）--')
depths = sorted(B.JAM_PC.keys(), key=int)
for cls in B.JAM_PC[depths[0]].keys():
    prev = None
    for d in depths:
        cur = B.expand(B.JAM_PC[d][cls])
        if prev is not None:
            bad = cur - prev
            if bad:
                print(f'  {cls} {d}bb 比 {depths[depths.index(d)-1]}bb 多了: {sorted(bad)}')
        prev = cur

# ---------- 6) holdemmath HU 单调 ----------
pf = json.load(open('pushfold.json', encoding='utf-8'))
print()
print('== HU holdemmath 单调性 ==')
prev = None
for d in pf['depths']:
    s = B.expand(pf['hu'][str(d)]['SB']['h'])
    c = B.expand(pf['hu'][str(d)]['BB|SB']['h'])
    if prev:
        bad_s = s - prev[0]; bad_c = c - prev[1]
        if bad_s: print(f'  SB jam {d}bb 比 {prev[2]}bb 多: {sorted(bad_s)}')
        if bad_c: print(f'  BB call {d}bb 比 {prev[2]}bb 多: {sorted(bad_c)}')
    prev = (s, c, d)
print('  depths:', pf['depths'], ' SB%:', [pf['hu'][str(d)]['SB']['p'] for d in pf['depths']],
      ' BBcall%:', [pf['hu'][str(d)]['BB|SB']['p'] for d in pf['depths']])

# ---------- 7) 中码 ⊆ 深码 检查 ----------
print()
print('== 中码/短码与深码关系 ==')
for size in sorted(B.TABLES, key=int, reverse=True):
    dtab = {p['id']: p for p in Dbuild['bands']['deep']['tables'][str(size)]['positions']}
    mtab = {p['id']: p for p in Dbuild['bands']['mid']['tables'][str(size)]['positions']}
    for seat, dp in dtab.items():
        if dp['rfi']['na']: continue
        dset, mset = set(dp['rfi']['raise']), set(mtab[seat]['rfi']['raise'])
        if not mset <= dset:
            print(f'  {size}人/{seat} 中码比深码多开: {sorted(mset - dset)}')
        added = dset - mset
        # 列出中码砍掉的手牌数
    # 短码全下表 vs 深码
print('(中码剔除为设计行为，上面无输出即子集关系成立)')

# ---------- 8) 短码开池表 内部倒挂 ----------
print()
print('== 短码开池/全下表逐场景倒挂已含在第 2 节；这里单列 SHORT_RFI 的同花A链 ==')
for cls, toks in B.SHORT_RFI.items():
    s = B.expand(toks)
    ax = sorted([h for h in s if h[0] == 'A' and len(h) == 3 and h[2] == 's'], key=lambda x: RANKS.index(x[1]))
    print(f'  {cls}: suited A 有 {ax}')

# ---------- 9) 具体抽查：8人深码 BB 三桶的 raise/call 完整清单 ----------
print()
print('== 8人深码 BB 面对开池：三桶完整可玩清单（人工核对用）==')
bb8 = {p['id']: p for p in Dbuild['bands']['deep']['tables']['8']['positions']}['BB']
for bk in ('EP', 'LP', 'SB'):
    v = bb8['vs'][bk]
    print(f'\n  --- BB vs {bk} (开池者 {v["openers"]}, 范围 {v["openerPct"]}%) ---')
    print(f'  3bet {v["raisePct"]}%: {v["raiseTokens"]}')
    print(f'  跟注 {v["callPct"]}%: {v["callTokens"]}')
    # 各行踢脚覆盖图：每行列出 raise/call/fold
    for hi in 'AKQJT98765432':
        line = []
        for lo in 'AKQJT98765432':
            if hi == lo: line.append(f'{hi}{lo}:P' if hi+lo in raise_set or hi+lo in call_set else '.')
        s_row = [(lo, 'R' if hi+lo+'s' in raise_set else ('C' if hi+lo+'s' in call_set else '.')) for lo in 'AKQJT98765432' if lo != hi]
        o_row = [(lo, 'R' if hi+lo+'o' in raise_set else ('C' if hi+lo+'o' in call_set else '.')) for lo in 'AKQJT98765432' if lo != hi]
        print(f'    {hi}s: ' + ' '.join(f'{a}{b}' for a, b in s_row) + '   | ' + f'{hi}o: ' + ' '.join(f'{a}{b}' for a, b in o_row))
