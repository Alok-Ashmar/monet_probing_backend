import os
import json
import websockets
from redis.asyncio import Redis
from models.schemas import SurveyResponse
from service.db_switcher import DBSwitcher
from service.ServerLogger import ServerLogger
from service.response_store import store_probe_response
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from service.state_management import _probe_state_key, _load_probe_state, _save_probe_state

active_connections = 0

def get_connection_counts():
    return {
        "active_connections": active_connections,
    }

# websocket_router = APIRouter(prefix="/ws", tags=["websocket", "probe_backend"])
websocket_router = APIRouter(prefix="/ws", tags=["websocket", "ai-qa"])
logger = ServerLogger()
db_switcher = DBSwitcher(logger=logger)

redis_client = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
PROBE_ENGINE_WS_URL = os.environ.get("PROBE_ENGINE_WS_URL", "ws://localhost:8002/ws/probe_engine")


# @websocket_router.websocket("/probe_backend")
# async def websocket_probe_backend(websocket: WebSocket):
@websocket_router.websocket("/ai-qa")
async def websocket_ai_qa(websocket: WebSocket):
    """
    A simple websocket route that proxies messages to and from the Probing Engine websocket.
    """
    global active_connections
    await websocket.accept()
    active_connections += 1

    try:
        async with websockets.connect(PROBE_ENGINE_WS_URL) as engine_ws:
            while True:
                data = await websocket.receive_text()
                client_response = SurveyResponse.model_validate_json(data)
                logger.info(f"Received: su_id={client_response.su_id}, qs_id={client_response.qs_id}")

                try:
                    db_type = DBSwitcher.get_db_type(str(client_response.su_id), str(client_response.qs_id))
                    if not db_type:
                        await websocket.send_json({
                            "error": True,
                            "message": "Invalid survey or question IDs",
                            "code": 400
                        })
                        continue

                    redis_key = f"survey_details:{client_response.su_id}:{client_response.qs_id}"
                    cached_payload = await redis_client.get(redis_key)
                    if not cached_payload:
                        output, error = await db_switcher.fetch_and_cache_survey_details(
                            su_id=client_response.su_id,
                            mo_id=client_response.mo_id,
                            qs_id=client_response.qs_id,
                            db_type=db_type,
                        )
                        if error or not output:
                            await websocket.send_json(error or {
                                "error": True,
                                "message": "Survey details not found",
                                "code": 404
                            })
                            continue
                        cached_payload = json.dumps(output)

                    survey_details = json.loads(cached_payload) if isinstance(cached_payload, (str, bytes, bytearray)) else cached_payload
                    root_question_text = survey_details.get("question", {}).get("question", "")

                    state_key = _probe_state_key(
                        str(client_response.su_id),
                        str(client_response.qs_id),
                        str(client_response.mo_id)
                    )
                    cached_probe_state = await _load_probe_state(state_key)

                    if not cached_probe_state:
                        cached_probe_state = {
                            "session_no": 0,
                            "su_id": str(client_response.su_id),
                            "mo_id": str(client_response.mo_id),
                            "qs_id": str(client_response.qs_id),
                            "counter": 0,
                            "ended": False,
                            "simple_store": True,
                        }
                    else:
                        if root_question_text and client_response.question == root_question_text:
                            cached_probe_state["session_no"] = cached_probe_state.get("session_no", 0) + 1
                            cached_probe_state["counter"] = 0
                            cached_probe_state["ended"] = False

                    cached_probe_state["counter"] = int(cached_probe_state.get("counter", 0)) + 1
                    await _save_probe_state(state_key, cached_probe_state)

                    await engine_ws.send(data)

                    async for message in engine_ws:
                        if isinstance(message, str):
                            raw_message = message
                            await websocket.send_text(message)
                        else:
                            raw_message = message.decode('utf-8') if hasattr(message, 'decode') else str(message)
                            await websocket.send_bytes(message)

                        try:
                            engine_response = json.loads(raw_message)
                        except json.JSONDecodeError as parse_error:
                            logger.error(f"Parse error: {parse_error}")
                            continue

                        if engine_response.get("message") == "streaming-ended":
                            quality_ended = engine_response.get("response", {}).get("ended", False)

                            if quality_ended:
                                cached_probe_state["ended"] = True
                                await _save_probe_state(state_key, cached_probe_state)

                            if cached_probe_state.get("simple_store", True):
                                try:
                                    await store_probe_response(
                                        db_type=db_type,
                                        engine_response=engine_response,
                                        client_response=client_response,
                                        state=cached_probe_state,
                                    )
                                except Exception as store_err:
                                    logger.error(f"Failed to store response: {store_err}")

                            logger.info(f"Current: session={cached_probe_state.get('session_no')}, counter={cached_probe_state.get('counter')}")
                            break

                except Exception as e:
                    logger.error(f"Processing error: {e}", exc_info=True)
                    await websocket.send_json({
                        "error": True,
                        "message": str(e),
                        "code": 500
                    })

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except ConnectionRefusedError:
        logger.error(f"Could not connect to the Probing Engine at {PROBE_ENGINE_WS_URL}")
        try:
            await websocket.close(code=1011, reason="Probing engine unreachable")
        except:
            await websocket.send_json({
                "error": True,
                "message": "Probing engine unreachable",
                "code": 1011
            })
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except:
            await websocket.send_json({
                "error": True,
                "message": "Internal error",
                "code": 1011
            })
    finally:
        active_connections -= 1
        logger.info(f"Connection closed. Active: {active_connections}")
