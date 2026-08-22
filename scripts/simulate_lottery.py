#!/usr/bin/env python3
"""彩票开奖模拟器 —— 每期机选 N 注 + 随机开奖,统计各奖级中奖情况,并与理论概率对照。

用法:
  python scripts/simulate_lottery.py                    # 全部 5 彩种 × 100 万期 × 每期 5 注
  python scripts/simulate_lottery.py --type SSQ         # 只跑双色球
  python scripts/simulate_lottery.py --rounds 10000     # 改期数(默认 1000000)
  python scripts/simulate_lottery.py --per-draw 10      # 每期机选注数(默认 5)
  python scripts/simulate_lottery.py --seed 20260809 --show 3   # 固定种子 + 展示前 3 期明细
  python scripts/simulate_lottery.py --ssq-fuyun        # 双色球按"特别规定"执行期模拟(福运奖生效)
  python scripts/simulate_lottery.py --dlt-bigpool      # 大乐透按奖池≥8亿元档模拟(固定奖升级)

彩种 key: SSQ 双色球 / DLT 大乐透 / KL8 快乐八(选十) / PL5 排列5 / QXC 七星彩
规则口径(官方现行):
  · 双色球 2026 新规(第2026014期起):增设"福运奖"(奖池≥15亿启动、<3亿停止),
    中奖条件为恰好 3 个红球(3+0),固定 5 元;3+1 仍按最高奖级五等奖兑付。
    默认按"未执行特别规定"模拟,福运奖不计;--ssq-fuyun 启用。
  · 大乐透 2026 新规(第26014期起):9 奖级合并为 7 奖级,
    三等奖=5+0/4+2(5000 元)、四等奖=4+1(300 元)、五等奖=4+0/3+2(150 元)、
    六等奖=3+1/2+2(15 元)、七等奖=3+0/1+2/2+1/0+2(5 元);
    奖池≥8 亿元时固定奖升级为 6666/380/200/18/7 元(--dlt-bigpool)。
  · 快乐八选十含"中0个回本2元";七星彩为 2020-10 新版"前6位(0-9)+后区(0-14)"按位匹配。
"""

import argparse
import math
import random
import sys
import time
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BET_PRICE = 2.0  # 每注 2 元

# ═══════════════════════════════ 彩种配置 ═══════════════════════════════
# kind: "comb" = 无放回组合(set 匹配); "pos" = 按位可重复(逐位相等)
# main: (选号个数, 最小, 最大); bonus: 同结构或 None
# draw_pick: 开奖号码个数(仅快乐八 20 ≠ 投注 10,其余默认与 main 相同)
# prizes: 命中元组 → (奖级名, 基础奖金, 升级奖金, 条件性)
#   奖金 None = 浮动奖(不计入金额合计); 升级奖金仅大乐透奖池≥8亿档使用
#   条件性 True = 需命令行开关启用(双色球福运奖)
GAMES = {
    "SSQ": {
        "name": "双色球",
        "kind": "comb",
        "main": (6, 1, 33), "bonus": (1, 1, 16),
        "prizes": {
            (6, 1): ("一等奖", None, None, False), (6, 0): ("二等奖", None, None, False),
            (5, 1): ("三等奖", 3000, None, False),
            (5, 0): ("四等奖", 200, None, False), (4, 1): ("四等奖", 200, None, False),
            (4, 0): ("五等奖", 10, None, False), (3, 1): ("五等奖", 10, None, False),
            (2, 1): ("六等奖", 5, None, False), (1, 1): ("六等奖", 5, None, False),
            (0, 1): ("六等奖", 5, None, False),
            (3, 0): ("福运奖", 5, None, True),  # 特别规定执行期(奖池≥15亿启动,<3亿停止)
        },
    },
    "DLT": {
        "name": "大乐透",
        "kind": "comb",
        "main": (5, 1, 35), "bonus": (2, 1, 12),
        "prizes": {  # 2026 新规:9 级合并为 7 级,13 个中奖条件不变
            (5, 2): ("一等奖", None, None, False), (5, 1): ("二等奖", None, None, False),
            (5, 0): ("三等奖", 5000, 6666, False), (4, 2): ("三等奖", 5000, 6666, False),
            (4, 1): ("四等奖", 300, 380, False),
            (4, 0): ("五等奖", 150, 200, False), (3, 2): ("五等奖", 150, 200, False),
            (3, 1): ("六等奖", 15, 18, False), (2, 2): ("六等奖", 15, 18, False),
            (3, 0): ("七等奖", 5, 7, False), (1, 2): ("七等奖", 5, 7, False),
            (2, 1): ("七等奖", 5, 7, False), (0, 2): ("七等奖", 5, 7, False),
        },
    },
    "KL8": {
        "name": "快乐八(选十)",
        "kind": "comb",
        "main": (10, 1, 80), "bonus": None, "draw_pick": 20,
        "prizes": {  # 命中元组 = (中几个,)
            (10,): ("一等奖", None, None, False),
            (9,): ("二等奖", 8000, None, False), (8,): ("三等奖", 800, None, False),
            (7,): ("四等奖", 80, None, False), (6,): ("五等奖", 5, None, False),
            (5,): ("六等奖", 3, None, False), (0,): ("七等奖", 2, None, False),
            # 选十特殊:一个都不中回本 2 元
        },
    },
    "PL5": {
        "name": "排列5",
        "kind": "pos",
        "main": (5, 0, 9), "bonus": None,
        "prizes": {(5,): ("一等奖", 100000, None, False)},
    },
    "QXC": {
        "name": "七星彩",
        "kind": "pos",
        "main": (6, 0, 9), "bonus": (1, 0, 14),
        "prizes": {
            (6, 1): ("一等奖", None, None, False), (6, 0): ("二等奖", None, None, False),
            (5, 1): ("三等奖", 3000, None, False),
            (5, 0): ("四等奖", 500, None, False), (4, 1): ("四等奖", 500, None, False),
            (4, 0): ("五等奖", 30, None, False), (3, 1): ("五等奖", 30, None, False),
            (3, 0): ("六等奖", 5, None, False), (2, 1): ("六等奖", 5, None, False),
            (1, 1): ("六等奖", 5, None, False), (0, 1): ("六等奖", 5, None, False),
        },
    },
}

# ═══════════════════════════════ 号码生成 ═══════════════════════════════

def gen_one(cfg, spec):
    """生成一组号码:spec = (pick, lo, hi)。返回元组。"""
    pick, lo, hi = spec
    if cfg["kind"] == "comb":
        return tuple(random.sample(range(lo, hi + 1), pick))
    return tuple(random.randint(lo, hi) for _ in range(pick))

def gen_bet(cfg):
    main = gen_one(cfg, cfg["main"])
    bonus = gen_one(cfg, cfg["bonus"]) if cfg["bonus"] else None
    return main, bonus

def gen_draw(cfg):
    main = gen_one(cfg, (cfg.get("draw_pick", cfg["main"][0]), cfg["main"][1], cfg["main"][2]))
    bonus = gen_one(cfg, cfg["bonus"]) if cfg["bonus"] else None
    return main, bonus

def hit_of(cfg, bet, draw):
    """返回命中元组:(主区命中数[, 副区命中数])。"""
    bm, bb = bet
    dm, db = draw
    if cfg["kind"] == "comb":
        m = len(set(bm) & set(dm))
        if cfg["bonus"]:
            return (m, len(set(bb) & set(db)))
        return (m,)
    m = sum(1 for x, y in zip(bm, dm) if x == y)
    if cfg["bonus"]:
        return (m, 1 if bb[0] == db[0] else 0)
    return (m,)

# ═══════════════════════════════ 理论概率 ═══════════════════════════════

def theory_prob(cfg, hit):
    """单注命中指定组合的理论概率(精确公式,用于对照模拟频率)。"""
    kind = cfg["kind"]
    if kind == "comb":
        mp, lo, hi = cfg["main"]
        M = hi - lo + 1
        if "draw_pick" in cfg:  # 快乐八:开奖 20 选 10
            d = cfg["draw_pick"]
            p = math.comb(d, hit[0]) * math.comb(M - d, mp - hit[0]) / math.comb(M, mp)
        else:
            p = math.comb(mp, hit[0]) * math.comb(M - mp, mp - hit[0]) / math.comb(M, mp)
            if cfg["bonus"]:
                bp, blo, bhi = cfg["bonus"]
                B = bhi - blo + 1
                b = hit[1]
                p *= math.comb(bp, b) * math.comb(B - bp, bp - b) / math.comb(B, bp)
        return p
    # 按位:主区 0-9 共 10 个
    mp = cfg["main"][0]
    m = hit[0]
    p = math.comb(mp, m) * 0.1 ** m * 0.9 ** (mp - m)
    if cfg["bonus"]:
        b = hit[1]
        B = cfg["bonus"][2] - cfg["bonus"][1] + 1
        p *= (1.0 / B) if b else (B - 1.0) / B
    return p

# ═══════════════════════════════ 向量化模拟(GPU / NumPy) ═══════════════════════════════

VEC_BATCH = 200_000  # 每批模拟期数,控制显存/内存占用
CODE_MIN = 1100      # 命中编码上限(主区命中×100+副区命中;主区≤10,副区≤16)


def _code_of(hit):
    return hit[0] * 100 + (hit[1] if len(hit) > 1 else 0)


def _gen_vec_comb(xp, rng, n_sets, k, lo, hi):
    """批量无放回抽样(argsort 法):[n_sets, k],每行从 [lo, hi] 取 k 个不重复。"""
    M = hi - lo + 1
    u = rng.random((n_sets, M), dtype=xp.float32)
    return xp.argsort(u, axis=1)[:, :k] + lo


def _gen_vec_pos(xp, rng, n_sets, k, lo, hi):
    """批量按位随机(可重复):[n_sets, k]。"""
    return rng.integers(lo, hi + 1, size=(n_sets, k), dtype=xp.int64)


def _gen_and_match(cfg, n, per_draw, xp, rng):
    """向量化生成 n 期开奖 + n×per_draw 注,返回命中编码数组 [n*per_draw]。

    命中编码 = 主区命中数 × 100 + 副区命中数(组合型交集数/按位型相等数)。
    """
    mp, lo, hi = cfg["main"]
    M = hi - lo + 1
    d_pick = cfg.get("draw_pick", mp)
    if cfg["kind"] == "comb":
        draw_main = _gen_vec_comb(xp, rng, n, d_pick, lo, hi)
        bet_main = _gen_vec_comb(xp, rng, n * per_draw, mp, lo, hi)
        # 主区命中数:one-hot 交集求和
        d_oh = xp.zeros((n, M + 1), dtype=xp.bool_)
        d_oh[xp.arange(n)[:, None], draw_main] = True
        d_oh = xp.repeat(d_oh, per_draw, axis=0)  # [n*per_draw, M+1]
        b_oh = xp.zeros((n * per_draw, M + 1), dtype=xp.bool_)
        b_oh[xp.arange(n * per_draw)[:, None], bet_main] = True
        hit_m = xp.sum(b_oh & d_oh, axis=1)
        if cfg["bonus"]:
            # 副区同样用 one-hot 交集(comb 型为无序组合,不能逐位比较)
            bp, blo, bhi = cfg["bonus"]
            B = bhi - blo + 1
            draw_bonus = _gen_vec_comb(xp, rng, n, bp, blo, bhi)
            bet_bonus = _gen_vec_comb(xp, rng, n * per_draw, bp, blo, bhi)
            d_oh_b = xp.zeros((n, B + 1), dtype=xp.bool_)
            d_oh_b[xp.arange(n)[:, None], draw_bonus] = True
            d_oh_b = xp.repeat(d_oh_b, per_draw, axis=0)
            b_oh_b = xp.zeros((n * per_draw, B + 1), dtype=xp.bool_)
            b_oh_b[xp.arange(n * per_draw)[:, None], bet_bonus] = True
            hit_b = xp.sum(b_oh_b & d_oh_b, axis=1)
        else:
            hit_b = xp.zeros(n * per_draw, dtype=xp.int64)
    else:  # 按位型
        draw_main = _gen_vec_pos(xp, rng, n, mp, lo, hi)
        bet_main = _gen_vec_pos(xp, rng, n * per_draw, mp, lo, hi)
        hit_m = xp.sum(bet_main == xp.repeat(draw_main, per_draw, axis=0), axis=1)
        if cfg["bonus"]:
            bp, blo, bhi = cfg["bonus"]
            draw_bonus = _gen_vec_pos(xp, rng, n, bp, blo, bhi)
            bet_bonus = _gen_vec_pos(xp, rng, n * per_draw, bp, blo, bhi)
            hit_b = xp.sum(bet_bonus == xp.repeat(draw_bonus, per_draw, axis=0), axis=1)
        else:
            hit_b = xp.zeros(n * per_draw, dtype=xp.int64)
    return hit_m * 100 + hit_b


def simulate_fast(cfg, prizes, rounds, per_draw, xp):
    """向量化逐批模拟(GPU/NumPy),返回与 simulate 相同的统计 dict。"""
    rng = xp.random.default_rng()
    prize_codes = {hit: _code_of(hit) for hit in prizes}
    acc = {hit: 0 for hit in prizes}
    total_bets = rounds * per_draw
    for start in range(0, rounds, VEC_BATCH):
        n = min(VEC_BATCH, rounds - start)
        codes = _gen_and_match(cfg, n, per_draw, xp, rng)
        counts = xp.bincount(codes, minlength=CODE_MIN)
        if hasattr(counts, "get"):  # cupy 数组 → 转回 host
            counts = counts.get()
        for hit, code in prize_codes.items():
            acc[hit] += int(counts[code])
        if (start + n) % 200000 == 0:
            print(f"  ... 已模拟 {start + n:,} 期", flush=True)
    return acc, total_bets


# ═══════════════════════════════ 奖级解析 ═══════════════════════════════

def resolve_prizes(cfg, args):
    """按开关生成生效奖级表:{命中元组: (奖级名, 单注奖金)}。

    - 双色球福运奖(条件性)默认停用,--ssq-fuyun 启用
    - 大乐透固定奖按基础档,--dlt-bigpool 切到奖池≥8亿元升级档
    """
    out = {}
    for hit, (name, amount, amount_up, conditional) in cfg["prizes"].items():
        if conditional and not args.ssq_fuyun:
            continue
        out[hit] = (name, amount_up if (args.dlt_bigpool and amount_up is not None) else amount)
    return out

# ═══════════════════════════════ 模拟 ═══════════════════════════════

def fmt_num(cfg, n):
    if cfg["kind"] == "comb":
        return f"{n:02d}"
    return str(n)

def fmt_hit(cfg, hit):
    if cfg["bonus"]:
        return f"{hit[0]}+{hit[1]}"
    return str(hit[0])

def simulate(cfg, prizes, rounds, per_draw, show):
    """逐期模拟:随机开奖 + 机选 per_draw 注,按命中条件统计注数。"""
    total_bets = rounds * per_draw
    hit_counts = Counter()

    if show:
        print(f"\n── 前 {show} 期明细 ──")
    for i in range(rounds):
        draw = gen_draw(cfg)
        if i < show:
            dm, db = draw
            dstr = " ".join(fmt_num(cfg, n) for n in dm)
            if db:
                dstr += f"  + 副: {' '.join(fmt_num(cfg, n) for n in db)}"
            print(f"期 {i + 1:<6} 开奖: {dstr}")
        for _ in range(per_draw):
            bet = gen_bet(cfg)
            h = hit_of(cfg, bet, draw)
            pr = prizes.get(h)
            if i < show:
                bm, bb = bet
                bstr = " ".join(fmt_num(cfg, n) for n in bm)
                if bb:
                    bstr += f" +{' '.join(fmt_num(cfg, n) for n in bb)}"
                print(f"      {bstr}  →  {pr[0] if pr else '未中奖'}")
            if pr:
                hit_counts[h] += 1
        if (i + 1) % 200000 == 0:
            print(f"  ... 已模拟 {i + 1:,} 期", flush=True)
    return hit_counts, total_bets

# ═══════════════════════════════ 报告 ═══════════════════════════════

def render(cfg, prizes, hit_counts, total_bets, args):
    lines = []
    lines.append(f"奖级(命中条件)      中奖注数       频率(每注)      理论概率        频率/理论   单注奖金")
    lines.append("─" * 92)

    float_hits = []
    fixed_money = 0
    total_hits = 0
    for hit, (name, amount) in prizes.items():
        cnt = hit_counts.get(hit, 0)
        total_hits += cnt
        freq = cnt / total_bets
        theory = theory_prob(cfg, hit)
        if amount is None:
            float_hits.append((name, hit, cnt))
            amt_str, ratio = "浮动", "-"
        else:
            fixed_money += cnt * amount
            amt_str = f"{amount:,}"
            ratio = f"{freq / theory:.2f}x" if cnt > 0 and theory > 0 else "-"
        lines.append(
            f"{name} {fmt_hit(cfg, hit):<8} {cnt:>12,}  {freq * 100:>12.6f}%  "
            f"{theory * 100:>12.6f}%  {ratio:>10}  {amt_str:>8}"
        )
    lines.append("─" * 92)

    lines.append(f"中奖注数合计(任一奖级): {total_hits:,} / {total_bets:,}  = {total_hits / total_bets * 100:.4f}%")
    invest = total_bets * BET_PRICE
    if fixed_money:
        lines.append(f"固定奖奖金合计: {fixed_money:,} 元   固定奖返奖率: {fixed_money / invest * 100:.2f}%")
    for name, hit, cnt in float_hits:
        lines.append(f"浮动奖[{name} {fmt_hit(cfg, hit)}]: 中出 {cnt:,} 注(奖金按当期销量浮动,未计入金额)")
    return lines

def main():
    ap = argparse.ArgumentParser(
        description="彩票开奖模拟器:每期机选 N 注 + 随机开奖,统计各奖级中奖情况并对照理论概率。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="彩种 key: " + ", ".join(f"{k}={v['name']}" for k, v in GAMES.items()),
    )
    ap.add_argument("--type", default="ALL",
                    help="彩种: SSQ/DLT/KL8/PL5/QXC 或 ALL(默认全部)")
    ap.add_argument("--rounds", type=int, default=1000000,
                    help="模拟期数(默认 1000000)")
    ap.add_argument("--per-draw", type=int, default=5,
                    help="每期机选注数(默认 5)")
    ap.add_argument("--seed", type=int, default=None,
                    help="随机种子(可复现)")
    ap.add_argument("--show", type=int, default=0,
                    help="展示前 N 期开奖与投注明细(默认不展示)")
    ap.add_argument("--ssq-fuyun", action="store_true",
                    help="双色球按特别规定执行期模拟:福运奖(3+0, 5 元)生效")
    ap.add_argument("--dlt-bigpool", action="store_true",
                    help="大乐透按奖池≥8 亿元档模拟:固定奖升级(5000→6666 等)")
    ap.add_argument("--backend", default="auto", choices=["auto", "python", "numpy", "gpu"],
                    help="计算后端: auto(默认,GPU→NumPy→纯Python) / gpu / numpy / python")
    args = ap.parse_args()

    if args.rounds <= 0 or args.per_draw <= 0:
        ap.error("期数与每期注数必须为正整数")
    if args.seed is not None:
        random.seed(args.seed)

    # 计算后端解析
    xp = None
    backend = args.backend
    if backend == "auto":
        try:
            import warnings as _w
            _w.filterwarnings("ignore", message="CUDA path could not be detected")
            import cupy
            backend, xp = "gpu", cupy
        except ImportError:
            try:
                import numpy
                backend, xp = "numpy", numpy
            except ImportError:
                backend, xp = "python", None
    elif backend == "gpu":
        try:
            import cupy as xp
        except ImportError:
            ap.error("未安装 CuPy,请先执行: pip install cupy-cuda12x[ctk]")
    elif backend == "numpy":
        import numpy as xp

    keys = [k for k in GAMES if args.type.upper() == "ALL" or k == args.type.upper()]
    if not keys:
        ap.error(f"未知彩种: {args.type}(可用: ALL/SSQ/DLT/KL8/PL5/QXC)")

    print(f"彩票开奖模拟  ·  期数 {args.rounds:,}  ·  每期机选 {args.per_draw} 注  ·  单注 {BET_PRICE:g} 元")
    if args.ssq_fuyun:
        print("特别口径: 双色球执行特别规定(福运奖生效)")
    if args.dlt_bigpool:
        print("特别口径: 大乐透奖池≥8 亿元档(固定奖升级)")
    if backend == "gpu":
        gpu_name = xp.cuda.runtime.getDeviceProperties(0)["name"].decode()
        print(f"计算后端: GPU(CuPy {xp.__version__} · {gpu_name})")
    elif backend == "numpy":
        print(f"计算后端: NumPy({xp.__version__}) 向量化")
    else:
        print("计算后端: 纯 Python(逐期循环)")

    t0 = time.time()
    for key in keys:
        cfg = {**GAMES[key], "key": key}
        prizes = resolve_prizes(cfg, args)
        print(f"\n{'═' * 92}")
        print(f"  {cfg['name']}  ·  {args.rounds:,} 期 × {args.per_draw} 注 = {args.rounds * args.per_draw:,} 注")
        print(f"{'═' * 92}")
        if backend == "python":
            hit_counts, total = simulate(cfg, prizes, args.rounds, args.per_draw, args.show)
        else:
            hit_counts, total = simulate_fast(cfg, prizes, args.rounds, args.per_draw, xp)
            if args.show:  # 前 N 期明细走逐期逻辑生成
                simulate(cfg, prizes, min(args.show, args.rounds), args.per_draw, args.show)
        for line in render(cfg, prizes, hit_counts, total, args):
            print(line)
        print()
    print(f"全部完成,耗时 {time.time() - t0:.1f} 秒")
    print("说明: 模拟用于概率验证,结果与真实开奖相互独立;彩票为随机游戏,请理性娱乐、量力而行。")

if __name__ == "__main__":
    main()
