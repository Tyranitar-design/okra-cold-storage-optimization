"""NSGA-III and ALNS heuristics for v3.0 capacity-chain layout problem.

与 v2.1 的 heuristics 区别
--------------------------
- v2.1: 基因型 a[i]∈{choice}, 每需求点单点分配
- v3.0: 基因型 g[j]∈{0..n_choices}, 每候选点选 (type, cap_idx) 或不开放
        分配 x[i,j,t] 由 LP 子问题最优求解（嵌入 evaluator）

这样启发式只搜索选址空间（27 维），LP 保证给定 z 后 x 最优。
评估器是 LayoutEvaluatorV3.evaluate(genome)。
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from src.algorithms.layout_evaluator_v3 import LayoutEvaluatorV3, PENALTY_INFEASIBLE


# ── Pareto utils ──────────────────────────────────────────────────────────────

def dominates_v3(a: tuple, b: tuple) -> bool:
    """三目标最小化下：a dominates b ⟺ 全部 ≤ 且至少一个 <。"""
    le = all(a[k] <= b[k] + 1e-9 for k in range(3))
    lt = any(a[k] < b[k] - 1e-9 for k in range(3))
    return le and lt


def pareto_filter_v3(points: list[tuple]) -> list[int]:
    """返回非支配点的索引列表。"""
    n = len(points)
    keep = [True] * n
    for i in range(n):
        if not keep[i]:
            continue
        for j in range(n):
            if i == j or not keep[j]:
                continue
            if dominates_v3(points[j], points[i]):
                keep[i] = False
                break
    return [i for i in range(n) if keep[i]]


def hypervolume_mc_v3(arr: np.ndarray, ref: np.ndarray, n_samples: int = 20000,
                     seed: int = 12345) -> float:
    """Monte Carlo 估计 3D 超体积。"""
    if len(arr) == 0:
        return 0.0
    lows = np.minimum(arr.min(axis=0), ref) - 1e-9
    box_vol = float(np.prod(np.maximum(ref - lows, 0)))
    if box_vol <= 0:
        return 0.0
    rng = np.random.default_rng(seed)
    samples = rng.uniform(lows, ref, size=(n_samples, arr.shape[1]))
    dominated = np.zeros(n_samples, dtype=bool)
    for p in arr:
        dominated |= np.all(samples >= p, axis=1)
    return float(dominated.mean() * box_vol)


# ── 可行性种子（贪心选址）────────────────────────────────────────────────────

def greedy_seed_genome(ev: LayoutEvaluatorV3, rng: random.Random,
                       n_facilities: int | None = None) -> list[int]:
    """贪心构造可行 genome：基于 set-cover 思路保证 precool 覆盖。

    策略：
    1. 用 set-cover 启发式选最少的 precool 设施覆盖所有需求点（2h 内可达）
    2. 给每种其他通道（cold/ca/frozen）选 1 个高产量候选点
    3. 剩余名额随机给已选候选点的容量档调整
    """
    cids = ev.candidate_ids
    dids = ev.demand_ids
    config = ev.config
    n_cand = ev.n_candidates
    if n_facilities is None:
        n_facilities = ev.assumptions.max_facilities

    # ── 1. precool set cover：贪心选最少 precool 设施覆盖所有需求点 ──
    uncovered = set(dids)
    precool_picks = []   # list of candidate_index
    while uncovered:
        # 找能覆盖最多 uncovered 的候选点
        best_jdx = -1
        best_cover = set()
        for jdx in range(n_cand):
            if jdx in [p for p in precool_picks]:
                continue
            cover = {d for d in uncovered if config.get_time(d, cids[jdx]) <= ev._precool_limit_h}
            if len(cover) > len(best_cover):
                best_cover = cover
                best_jdx = jdx
        if best_jdx < 0 or not best_cover:
            break  # 无法继续覆盖
        precool_picks.append(best_jdx)
        uncovered -= best_cover

    # ── 2. 给其他通道（cold/ca/frozen）各选 1 个产量大的候选点 ──
    other_types = [t for t in ev.active_types if t != "precool"]
    other_picks: dict[str, int] = {}
    by_prod = sorted(range(n_cand), key=lambda j: -ev._demand.get(cids[j], 0.0))
    for t in other_types:
        for jdx in by_prod:
            if jdx in precool_picks or jdx in other_picks.values():
                continue
            other_picks[t] = jdx
            break

    # ── 3. 装配 genome ──
    genome = [0] * n_cand
    # precool: 用 cap_idx=2 (中等容量已够，因 storage_days=2/24 极小)
    pre_cap = min(2, len(config.capacity_index["precool"]) - 1)
    for jdx in precool_picks:
        choice_idx = ev.choice_table.index(("precool", pre_cap))
        genome[jdx] = choice_idx + 1
    # 其他通道: 用最大容量档（保证 peak load 装得下）
    for t, jdx in other_picks.items():
        cap = len(config.capacity_index[t]) - 1   # 最大档
        choice_idx = ev.choice_table.index((t, cap))
        genome[jdx] = choice_idx + 1

    n_used = len(precool_picks) + len(other_picks)
    # 如果设施数超 max_facilities，强制裁掉部分非关键 precool（保留覆盖最多的几个）
    if n_used > ev.assumptions.max_facilities:
        # 重排 precool 按覆盖量降序
        coverage = [(jdx, sum(1 for d in dids if config.get_time(d, cids[jdx]) <= ev._precool_limit_h))
                    for jdx in precool_picks]
        coverage.sort(key=lambda x: -x[1])
        n_keep_pre = ev.assumptions.max_facilities - len(other_picks)
        if n_keep_pre < 1:
            n_keep_pre = 1
        keep_pre = {x[0] for x in coverage[:n_keep_pre]}
        for jdx in precool_picks:
            if jdx not in keep_pre:
                genome[jdx] = 0

    return genome


# ── ALNS ──────────────────────────────────────────────────────────────────────

@dataclass
class ALNSResult:
    method: str = "alns_v3"
    archive: list[tuple] = field(default_factory=list)
    iterations: int = 0
    elapsed_sec: float = 0.0
    best_cost: float | None = None
    n_evaluations: int = 0


def run_alns_v3(ev: LayoutEvaluatorV3, *, iterations: int = 1500, seed: int = 0,
                time_limit: float = 300.0) -> ALNSResult:
    """ALNS for v3.0 layout. Maintains a Pareto archive over (cost, loss_ton, carbon_ton)."""
    rng = random.Random(seed)
    t_start = time.time()

    # 多个种子（不同 facility 数）启动
    archive: list[tuple[tuple, list[int]]] = []
    for n_fac in [4, 5, 6, 7, 8]:
        seed_g = greedy_seed_genome(ev, rng, n_facilities=n_fac)
        r = ev.evaluate(seed_g)
        if r["feasible"]:
            archive.append(((r["cost"], r["loss_ton"], r["carbon_ton"]), seed_g))

    if not archive:
        # fallback：所有 type 各开一个
        seed_g = greedy_seed_genome(ev, rng, n_facilities=4)
        r = ev.evaluate(seed_g)
        archive.append(((r["cost"], r["loss_ton"], r["carbon_ton"]), seed_g))

    cur_objs, cur_genome = archive[0]
    n_eval = len(archive)
    best_cost = min(a[0][0] for a in archive)

    for it in range(iterations):
        if time.time() - t_start > time_limit:
            break

        # destroy & repair
        new_genome = list(cur_genome)
        op = rng.random()
        if op < 0.4:
            # 关闭一个开放设施
            opened = [j for j in range(ev.n_candidates) if new_genome[j] > 0]
            if len(opened) > 1:
                new_genome[rng.choice(opened)] = 0
        elif op < 0.7:
            # 开新设施
            closed = [j for j in range(ev.n_candidates) if new_genome[j] == 0]
            if closed:
                new_genome[rng.choice(closed)] = rng.randrange(1, ev.n_choices + 1)
        else:
            # 改变某个开放设施的 (type, cap_idx)
            opened = [j for j in range(ev.n_candidates) if new_genome[j] > 0]
            if opened:
                new_genome[rng.choice(opened)] = rng.randrange(1, ev.n_choices + 1)

        r = ev.evaluate(new_genome)
        n_eval += 1
        if not r["feasible"]:
            continue

        new_objs = (r["cost"], r["loss_ton"], r["carbon_ton"])
        # 更新 Pareto archive
        non_dom = True
        new_archive = []
        for objs, g in archive:
            if dominates_v3(new_objs, objs):
                continue  # new dominates this
            if dominates_v3(objs, new_objs):
                non_dom = False
            new_archive.append((objs, g))
        if non_dom:
            new_archive.append((new_objs, new_genome))
            archive = new_archive
        # 接受准则：simulated-annealing-lite (50% 接受非改善解)
        if r["cost"] < cur_objs[0] or rng.random() < 0.3:
            cur_objs, cur_genome = new_objs, new_genome
        if r["cost"] < best_cost:
            best_cost = r["cost"]

    return ALNSResult(
        archive=archive, iterations=it + 1, elapsed_sec=time.time() - t_start,
        best_cost=best_cost, n_evaluations=n_eval,
    )


# ── NSGA-III (简化实现，无需 pymoo)──────────────────────────────────────────

@dataclass
class NSGA3Result:
    method: str = "nsga3_v3"
    archive: list[tuple] = field(default_factory=list)
    generations: int = 0
    elapsed_sec: float = 0.0
    best_cost: float | None = None
    n_evaluations: int = 0


def _crossover(g1: list[int], g2: list[int], rng: random.Random) -> list[int]:
    """Uniform crossover."""
    return [g1[i] if rng.random() < 0.5 else g2[i] for i in range(len(g1))]


def _mutate(g: list[int], n_choices: int, rng: random.Random, p: float = 0.05) -> list[int]:
    """每位以概率 p 随机换值。"""
    return [(rng.randrange(0, n_choices + 1) if rng.random() < p else gi) for gi in g]


def _fast_non_dominated_sort(objs: list[tuple]) -> list[list[int]]:
    """Deb's fast non-dominated sort."""
    n = len(objs)
    fronts = [[]]
    rank = [0] * n
    dominated_by = [[] for _ in range(n)]
    n_dom = [0] * n
    for i in range(n):
        for j in range(n):
            if i == j: continue
            if dominates_v3(objs[i], objs[j]):
                dominated_by[i].append(j)
            elif dominates_v3(objs[j], objs[i]):
                n_dom[i] += 1
        if n_dom[i] == 0:
            fronts[0].append(i)
            rank[i] = 0
    k = 0
    while fronts[k]:
        next_front = []
        for i in fronts[k]:
            for j in dominated_by[i]:
                n_dom[j] -= 1
                if n_dom[j] == 0:
                    rank[j] = k + 1
                    next_front.append(j)
        k += 1
        fronts.append(next_front)
    return fronts[:-1]


def run_nsga3_v3(ev: LayoutEvaluatorV3, *, pop_size: int = 60, n_gen: int = 30,
                 seed: int = 0, time_limit: float = 300.0) -> NSGA3Result:
    """简化 NSGA-III: 非支配排序 + 拥挤距离选择 + uniform crossover + 随机突变。"""
    rng = random.Random(seed)
    t_start = time.time()
    n_choices = ev.n_choices
    n_cand = ev.n_candidates

    # 初始化种群（多种子）
    pop = []
    for _ in range(pop_size):
        n_fac = rng.randint(4, ev.assumptions.max_facilities)
        g = greedy_seed_genome(ev, rng, n_facilities=n_fac)
        pop.append(g)

    pop_objs = []
    n_eval = 0
    for g in pop:
        r = ev.evaluate(g); n_eval += 1
        if r["feasible"]:
            pop_objs.append((r["cost"], r["loss_ton"], r["carbon_ton"]))
        else:
            pop_objs.append((PENALTY_INFEASIBLE, PENALTY_INFEASIBLE, PENALTY_INFEASIBLE))

    best_cost = min(o[0] for o in pop_objs)

    for gen in range(n_gen):
        if time.time() - t_start > time_limit:
            break

        # 产生子代（pop_size 个）
        offspring = []
        offspring_objs = []
        for _ in range(pop_size):
            p1, p2 = rng.sample(range(pop_size), 2)
            child = _crossover(pop[p1], pop[p2], rng)
            child = _mutate(child, n_choices, rng, p=0.08)
            r = ev.evaluate(child); n_eval += 1
            if r["feasible"]:
                offspring.append(child)
                offspring_objs.append((r["cost"], r["loss_ton"], r["carbon_ton"]))
                if r["cost"] < best_cost:
                    best_cost = r["cost"]
            else:
                offspring.append(child)
                offspring_objs.append((PENALTY_INFEASIBLE,)*3)

        # 合并并选 pop_size 个最优（按 front rank）
        all_pop = pop + offspring
        all_objs = pop_objs + offspring_objs
        fronts = _fast_non_dominated_sort(all_objs)
        new_pop_idx = []
        for front in fronts:
            if len(new_pop_idx) + len(front) <= pop_size:
                new_pop_idx.extend(front)
            else:
                # 简化：随机选剩余名额（NSGA-III 应该用 reference points，这里简化）
                slots = pop_size - len(new_pop_idx)
                rng.shuffle(front)
                new_pop_idx.extend(front[:slots])
                break
        pop = [all_pop[i] for i in new_pop_idx]
        pop_objs = [all_objs[i] for i in new_pop_idx]

    # 提取 Pareto 前沿
    feasible_idx = [i for i, o in enumerate(pop_objs) if o[0] < PENALTY_INFEASIBLE / 2]
    feas_objs = [pop_objs[i] for i in feasible_idx]
    feas_pop = [pop[i] for i in feasible_idx]
    if feas_objs:
        nd_idx = pareto_filter_v3(feas_objs)
        archive = [(feas_objs[i], feas_pop[i]) for i in nd_idx]
    else:
        archive = []

    return NSGA3Result(
        archive=archive, generations=gen + 1, elapsed_sec=time.time() - t_start,
        best_cost=best_cost, n_evaluations=n_eval,
    )
