#!/usr/bin/env python3
"""回测公共向量化工具 —— NumPy / CuPy 双后端,供 backtest_all / backtest_funnel 复用。

核心思路:把全量历史一次性构造成 [期数, 号码数] 计数矩阵,用前缀累积
一次性算出所有期的「当前遗漏 / 历史最大遗漏 / 滑动窗口频率」,把原回测里
每期 O(历史长度) 的重算变成 O(1) 矩阵索引。
"""

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_backend(name="auto"):
    """返回 (xp, 后端名)。auto: GPU(CuPy) → NumPy。"""
    if name == "gpu":
        import warnings as _w
        _w.filterwarnings("ignore", message="CUDA path could not be detected")
        import cupy as xp
        return xp, "gpu"
    if name == "numpy":
        import numpy as xp
        return xp, "numpy"
    if name == "auto":
        try:
            import warnings as _w
            _w.filterwarnings("ignore", message="CUDA path could not be detected")
            import cupy as xp
            return xp, "gpu"
        except ImportError:
            import numpy as xp
            return xp, "numpy"
    raise ValueError(f"未知后端: {name}")


def build_counts(xp, draws_int, lo, M):
    """[T, pick] 号码整数矩阵 → [T, M] 计数矩阵(每期每号码出现次数)。

    comb 型每期号码不重复(计数 0/1);pos 型按位可重复(计数 0~pick)。
    """
    T, pick = draws_int.shape
    rows = xp.repeat(xp.arange(T), pick)
    flat = (draws_int - lo).reshape(-1)
    uniq, inv = xp.unique(rows * M + flat, return_inverse=True)
    cnt = xp.bincount(inv, minlength=uniq.size)
    out = xp.zeros((T, M), dtype=xp.int64)
    out[uniq // M, uniq % M] = cnt
    return out


def window_freq(xp, counts, win):
    """[T, M] 计数矩阵 → [T, M] 每期 t 的窗口频率 = counts[max(0,t-win):t] 之和。

    与原回测 freq(draws, start, end) 语义一致:窗口不含当前期。
    """
    T, M = counts.shape
    cs = xp.cumsum(counts, axis=0)  # cs[t] = counts[0..t] 和
    # off[t] = cs[t-1](前缀到 t 之前),t=0 → 0
    off = xp.concatenate([xp.zeros((1, M), dtype=cs.dtype), cs[:-1]], axis=0)
    if win >= T:
        return off
    # cs2[t] = cs[t-win-1](t > win 时;t ≤ win → 0),f[t] = cs[t-1] - cs[t-win-1]
    cs2 = xp.concatenate([xp.zeros((win + 1, M), dtype=cs.dtype), cs[:-(win + 1)]], axis=0)
    return off - cs2


def gaps_vec(xp, appear):
    """[T, M] 出现矩阵(bool,appear[t][n]=期 t 开出号码 n)→ (cg, mg) 各 [T, M]。

    语义与原回测 gaps(draws, end) 完全一致(开奖前视角,不含当前期):
      cg[t][n] = 截至期 t 号码 n 的当前遗漏(t - 最近出现位置;从未出现 = t)
      mg[t][n] = 截至期 t 号码 n 的历史最大遗漏(含进行中的未完成段)

    数据量 ≤ ~30 万元素(2MB),在 host(numpy) 端精确计算后传回 xp
    (CuPy 不支持 maximum.accumulate/cummax 前缀最大 scan)。
    """
    import numpy as np
    a = appear.get() if hasattr(appear, "get") else np.asarray(appear)
    T, M = a.shape
    t_idx = np.arange(T, dtype=np.int64)
    cg = np.empty((T, M), dtype=np.int64)
    mg = np.empty((T, M), dtype=np.int64)
    for n in range(M):
        col = a[:, n]
        pos = np.where(col)[0]
        if pos.size == 0:
            cg[:, n] = t_idx
            mg[:, n] = t_idx
            continue
        # 最近出现位置(含当前期),整体下移一行 → 位置 < t 的最近出现
        mark = np.full(T, -1, dtype=np.int64)
        mark[pos] = pos
        last = np.maximum.accumulate(mark)
        last_excl = np.concatenate([np.array([-1], dtype=np.int64), last[:-1]])
        cg[:, n] = np.where(last_excl >= 0, t_idx - last_excl, t_idx)
        # 历史最大遗漏:段长(首段 pos[0],段间 diff(pos)-1)的前缀最大 + 当前进行段
        segs = np.diff(pos) - 1
        running = np.maximum.accumulate(
            np.concatenate([np.array([pos[0]], dtype=np.int64), segs]))
        base = np.zeros(T, dtype=np.int64)
        base[pos] = running
        prefix = np.maximum.accumulate(base)
        # 进行中段与原版一致:截至 t-1(即 cg-1),避免边界差 1
        mg[:, n] = np.maximum(prefix, cg[:, n] - 1)
    return xp.asarray(cg), xp.asarray(mg)


def to_host(arr):
    """cupy 数组 → numpy(已是 numpy 则原样返回)。"""
    return arr.get() if hasattr(arr, "get") else arr


def fmt_backend(xp, name):
    """后端描述字符串。"""
    if name == "gpu":
        gpu_name = xp.cuda.runtime.getDeviceProperties(0)["name"].decode()
        return f"GPU(CuPy {xp.__version__} · {gpu_name})"
    return f"NumPy({xp.__version__})"
