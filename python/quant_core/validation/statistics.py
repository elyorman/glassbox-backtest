"""Paired stationary resampling, a centered maximum-mean search diagnostic and the deflated Sharpe ratio."""

from decimal import Decimal, localcontext
from math import e
from random import Random
from statistics import NormalDist, median

from quant_core.analytics import CONTEXT, mean, paired_metrics
from quant_core.data import number

EULER_GAMMA = 0.5772156649015329  # Euler-Mascheroni constant, binary floating point like NormalDist.


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


def return_moments(returns):
    """Per-period Sharpe ratio (mean over sample deviation), count, skewness and raw kurtosis.

    Skewness is m3 / m2^1.5 and kurtosis m4 / m2^2 from population central
    moments, so normal returns give 0 and 3, as Bailey and Lopez de Prado use them.
    """
    values = tuple(map(number, returns))
    if len(values) < 2:
        raise ValueError("Return moments need at least two returns")
    with localcontext(CONTEXT):
        count, center = len(values), mean(values)
        m2, m3, m4 = (sum(((v - center) ** power for v in values), Decimal(0)) / count for power in (2, 3, 4))
        if m2 == 0:
            raise ValueError("Returns with zero variance have no Sharpe ratio")
        return {"observations": count, "sharpe": center / (m2 * count / (count - 1)).sqrt(),
                "skewness": m3 / (m2 * m2.sqrt()), "kurtosis": m4 / (m2 * m2)}


def expected_maximum_sharpe(trials, sharpe_variance):
    """Bailey and Lopez de Prado (2014), Eq. 1 with zero mean: the expected best of `trials` unskilled Sharpe ratios."""
    if type(trials) is not int or trials < 2:
        raise ValueError("Trials must be an integer of at least 2")
    variance = number(sharpe_variance)
    if variance < 0:
        raise ValueError("Sharpe variance cannot be negative")
    normal = NormalDist()
    z = ((1 - EULER_GAMMA) * normal.inv_cdf(1 - 1 / trials)
         + EULER_GAMMA * normal.inv_cdf(1 - 1 / (trials * e)))
    with localcontext(CONTEXT):
        return variance.sqrt() * Decimal(repr(z))


def deflated_sharpe_ratio(sharpe, observations, skewness, kurtosis, trials, sharpe_variance):
    """Bailey and Lopez de Prado (2014), Eq. 2. Sharpe and its variance are per period, never annualized."""
    if type(observations) is not int or observations < 2:
        raise ValueError("Observations must be an integer of at least 2")
    sharpe, skewness, kurtosis = number(sharpe), number(skewness), number(kurtosis)
    threshold = expected_maximum_sharpe(trials, sharpe_variance)
    with localcontext(CONTEXT):
        spread = 1 - skewness * sharpe + (kurtosis - 1) / 4 * sharpe ** 2
        if spread <= 0:
            raise ValueError("Skewness and kurtosis leave no valid Sharpe ratio variance")
        z = (sharpe - threshold) * Decimal(observations - 1).sqrt() / spread.sqrt()
    return Decimal(repr(NormalDist().cdf(float(z))))


def deflated_sharpe(returns, trials, sharpe_variance):
    """The deflated Sharpe ratio of a per-period return series, with every input and intermediate value."""
    moments = return_moments(returns)
    return {**moments, "trials": trials, "sharpe_variance": number(sharpe_variance),
            "expected_maximum_sharpe": expected_maximum_sharpe(trials, sharpe_variance),
            "deflated_sharpe_ratio": deflated_sharpe_ratio(moments["sharpe"], moments["observations"],
                                                           moments["skewness"], moments["kurtosis"],
                                                           trials, sharpe_variance)}
