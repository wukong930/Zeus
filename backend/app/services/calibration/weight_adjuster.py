from dataclasses import dataclass


DEFAULT_ALPHA_PRIOR = 4.0
DEFAULT_BETA_PRIOR = 4.0
MIN_EFFECTIVE_WEIGHT = 0.1
MAX_EFFECTIVE_WEIGHT = 2.0


@dataclass(frozen=True)
class BayesianWeight:
    posterior_mean: float
    effective_weight: float
    sample_size: int
    hit_count: int
    miss_count: int
    prior_dominant: bool


def calculate_bayesian_weight(
    *,
    hits: int,
    total: int,
    base_weight: float = 1.0,
    alpha_prior: float = DEFAULT_ALPHA_PRIOR,
    beta_prior: float = DEFAULT_BETA_PRIOR,
    decay_detected: bool = False,
    min_weight: float = MIN_EFFECTIVE_WEIGHT,
    max_weight: float = MAX_EFFECTIVE_WEIGHT,
) -> BayesianWeight:
    if hits < 0 or total < 0 or hits > total:
        raise ValueError("hits and total must satisfy 0 <= hits <= total")
    if alpha_prior <= 0 or beta_prior <= 0:
        raise ValueError("alpha_prior and beta_prior must be positive")

    posterior_mean = (alpha_prior + hits) / (alpha_prior + beta_prior + total)
    effective_weight = base_weight * (posterior_mean / 0.5)
    if decay_detected:
        effective_weight *= 0.5
    effective_weight = max(min_weight, min(max_weight, effective_weight))

    return BayesianWeight(
        posterior_mean=posterior_mean,
        effective_weight=effective_weight,
        sample_size=total,
        hit_count=hits,
        miss_count=total - hits,
        prior_dominant=total < 10,
    )
