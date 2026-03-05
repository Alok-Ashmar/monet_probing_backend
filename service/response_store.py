from types import SimpleNamespace
from typing import Any

from models.schemas import NSIGHT_v2, SurveyResponse
from service.db_switcher import DBSwitcher
from service.ServerLogger import ServerLogger

logger = ServerLogger()
db_switcher = DBSwitcher(logger=logger)


async def store_probe_response(
    *,
    engine_response: dict,
    current_client_response: SurveyResponse,
    state: dict,
) -> Any:
    """
    Build an NSIGHT_v2 object from the engine's streaming-ended payload and
    the current Redis probe state, then persist it via DBSwitcher.

    Args:
        engine_response:          The parsed JSON from the engine's streaming-ended message.
        current_client_response:  The last SurveyResponse received from the client.
        state:                    The current probe state dict loaded from Redis.

    Returns:
        The result of db_switcher.simple_store_response, or None on error.
    """
    metrics = engine_response.get("response", {}).get("metrics", {})

    nsight_v2 = NSIGHT_v2(
        quality=metrics.get("quality", 0),
        relevance=metrics.get("relevance", 0),
        detail=metrics.get("detail", 0),
        confusion=metrics.get("confusion", 0),
        negativity=metrics.get("negativity", 0),
        consistency=metrics.get("consistency", 0),
        confidence=metrics.get("confidence", 0),
        keywords=metrics.get("keywords", []),
        reason=metrics.get("reason", ""),
        gibberish_score=metrics.get("gibberish_score", 0),
        question=current_client_response.question,
        response=current_client_response.response,
    )

    # Reconstruct probe-like object from Redis state, falling back to client response fields
    probe = SimpleNamespace(
        ended=state.get("ended", True),
        mo_id=state.get("mo_id", current_client_response.mo_id),
        su_id=state.get("su_id", current_client_response.su_id),
        qs_id=state.get("qs_id", current_client_response.qs_id),
        counter=state.get("counter", 0),
        session_no=state.get("session_no", 0),
    )

    db_type = DBSwitcher.get_db_type(
        str(current_client_response.su_id),
        str(current_client_response.qs_id),
    )

    return await db_switcher.simple_store_response(
        db_type=db_type,
        nsight_v2=nsight_v2,
        survey_response=current_client_response,
        probe=probe,
        session_no=probe.session_no,
    )
