MANUAL_CONFIRMATION_SEVERITY = 3
EVALUATION_SEVERITY_THRESHOLD = 3


def verification_status_for(source_count: int, manually_confirmed: bool = False) -> str:
    if manually_confirmed:
        return "manual_confirmed"
    if source_count >= 2:
        return "cross_verified"
    return "single_source"


def requires_manual_confirmation(
    *,
    severity: int,
    source_count: int,
    verification_status: str,
) -> bool:
    if verification_status == "manual_confirmed":
        return False
    return severity >= MANUAL_CONFIRMATION_SEVERITY and source_count < 2


def is_evaluable_news_event(
    *,
    severity: int,
    source_count: int,
    verification_status: str,
) -> bool:
    if severity < EVALUATION_SEVERITY_THRESHOLD:
        return False
    return source_count >= 2 or verification_status == "manual_confirmed"
