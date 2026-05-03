def margin_efficiency_score(margin_required: float, account_net_value: float) -> int:
    if account_net_value <= 0:
        return 50

    margin_ratio = margin_required / account_net_value
    score = 100 - margin_ratio * 200
    return round(max(0.0, min(100.0, score)))
