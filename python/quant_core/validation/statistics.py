"""Paired stationary resampling and a centered maximum-mean search diagnostic."""

from decimal import Decimal, localcontext
from random import Random
from statistics import median

from quant_core.analytics import CONTEXT, mean, paired_metrics
from quant_core.data import number


def stationary_indices(length, expected_block, random):
    if type(length) is not int or type(expected_block) is not int or not 1 <= expected_block <= length:
        raise ValueError("Block length must be in [1, sample length]")
    index = random.randrange(length)
    indices = [index]
    for _ in range(length - 1):
        # Exact restart probability 1 / expected_block, using integer RNG only.
        index = random.randrange(length) if random.randrange(expected_block) == 0 else (index + 1) % length
        indices.append(index)
    return tuple(indices)


def _settings(length, block, repetitions, seed):
    if type(repetitions) is not int or repetitions < 100 or type(seed) is not int or seed < 0:
        raise ValueError("Bootstrap requires >=100 repetitions and a nonnegative integer seed")
    if type(block) is not int or not 1 <= block <= length:
        raise ValueError("Block exceeds sample length")


def _interval(values):
    values = sorted(values)
    # Declared nearest-rank 2.5% and 97.5% percentiles, no interpolation.
    return (values[max(0, (len(values) * 25 + 999) // 1000 - 1)],
            values[max(0, (len(values) * 975 + 999) // 1000 - 1)]) if values else (None, None)


def paired_bootstrap(candidate, benchmark, block=20, repetitions=500, seed=0):
    candidate, benchmark = tuple(map(number, candidate)), tuple(map(number, benchmark))
    if not candidate or len(candidate) != len(benchmark):
        raise ValueError("Bootstrap needs aligned nonempty return series")
    _settings(len(candidate), block, repetitions, seed)
    random, excess, differences = Random(seed), [], []
    with localcontext(CONTEXT):
        for _ in range(repetitions):
            indices = stationary_indices(len(candidate), block, random)
            metrics = paired_metrics(tuple(candidate[i] for i in indices), tuple(benchmark[i] for i in indices))
            excess.append(metrics["mean_daily_excess"])
            if metrics["sharpe_difference"] is not None:
                differences.append(metrics["sharpe_difference"])
        return {"expected_block_sessions": block, "repetitions": repetitions, "seed": seed,
                "mean_excess_95": _interval(excess), "sharpe_difference_95": _interval(differences),
                "defined_sharpe_replicates": len(differences)}


def search_diagnostic(candidates, benchmark, block=20, repetitions=500, seed=0):
    """White-style least-favorable centered maximum mean, NOT a Sharpe test or DSR."""
    benchmark = tuple(map(number, benchmark))
    panel = tuple(tuple(map(number, row)) for row in candidates)
    if not panel or not benchmark or any(len(row) != len(benchmark) for row in panel):
        raise ValueError("Search diagnostic requires a complete aligned candidate panel")
    _settings(len(benchmark), block, repetitions, seed)
    with localcontext(CONTEXT):
        excess = tuple(tuple(x - y for x, y in zip(row, benchmark)) for row in panel)
        means = tuple(mean(row) for row in excess)
        statistic = max(Decimal(0), *means)
        centered = tuple(tuple(x - m for x in row) for row, m in zip(excess, means))
        random, exceedances = Random(seed), 0
        for _ in range(repetitions):
            indices = stationary_indices(len(benchmark), block, random)
            boot = max(Decimal(0), *(mean(tuple(row[i] for i in indices)) for row in centered))
            exceedances += boot >= statistic
        return {"statistic": "maximum_mean_daily_excess_centered_stationary_bootstrap_v1",
                "candidate_count": len(panel), "maximum_mean_excess": statistic,
                "p_value": Decimal(exceedances + 1) / (repetitions + 1),
                "expected_block_sessions": block, "repetitions": repetitions, "seed": seed}


def fold_score_bootstrap(left, right, benchmark, fold_indices, block, repetitions=500, seed=0):
    """Difference of median fold Sharpe advantages; date blocks stay within folds."""
    left, right, benchmark = tuple(map(number, left)), tuple(map(number, right)), tuple(map(number, benchmark))
    folds = tuple(tuple(indices) for indices in fold_indices)
    if not left or len(left) != len(right) or len(left) != len(benchmark) or not folds:
        raise ValueError("Fold comparison requires aligned series and folds")
    if any(not indices or any(type(i) is not int or not 0 <= i < len(left) for i in indices) for indices in folds):
        raise ValueError("Invalid fold indices")
    flattened = tuple(i for indices in folds for i in indices)
    if flattened != tuple(range(len(left))):
        raise ValueError("Folds must partition all chronological observations exactly once")
    for indices in folds:
        _settings(len(indices), block, repetitions, seed)
    random, differences = Random(seed), []
    with localcontext(CONTEXT):
        for _ in range(repetitions):
            left_scores, right_scores = [], []
            for indices in folds:
                sampled = tuple(indices[i] for i in stationary_indices(len(indices), block, random))
                b = tuple(benchmark[i] for i in sampled)
                lscore = paired_metrics(tuple(left[i] for i in sampled), b)["sharpe_difference"]
                rscore = paired_metrics(tuple(right[i] for i in sampled), b)["sharpe_difference"]
                if lscore is None or rscore is None:
                    break
                left_scores.append(lscore)
                right_scores.append(rscore)
            if len(left_scores) == len(folds):
                differences.append(median(left_scores) - median(right_scores))
        return {"expected_block_sessions": block, "repetitions": repetitions, "seed": seed,
                "median_fold_score_difference_95": _interval(differences), "defined_replicates": len(differences)}
