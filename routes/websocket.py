import os
import json
import asyncio
import websockets
from redis import Redis
from models.schemas import SurveyResponse
from service.db_switcher import DBSwitcher
from service.ServerLogger import ServerLogger
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from service.state_management import _probe_state_key, _load_probe_state, _save_probe_state

websocket_router = APIRouter(prefix="/ws", tags=["websocket", "ai-qa"])
logger = ServerLogger()
db_switcher = DBSwitcher(logger=logger)

redis_client = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
PROBE_ENGINE_WS_URL = os.environ.get("PROBE_ENGINE_WS_URL", "ws://localhost:8002/ws/probe_engine")


@websocket_router.websocket("/ai-qa")
async def websocket_ai_qa(websocket: WebSocket):
    """
    A simple websocket route that proxies messages to and from the Probing Engine websocket.
    """
    await websocket.accept()
    
    try:
        current_state_key = None
        # Connect to the target probing engine websocket
        async with websockets.connect(PROBE_ENGINE_WS_URL) as engine_ws:
            
            async def forward_client_to_engine():
                nonlocal current_state_key
                """
                Receives messages from the client and forwards them to the probing engine.
                Tracks response counts to assign a session number for each probing session.
                """
                try:
                    while True:
                        data = await websocket.receive_text()
                        client_response = SurveyResponse.model_validate_json(data)

                        db_type = DBSwitcher.get_db_type(str(client_response.su_id), str(client_response.qs_id))
                        if not db_type:
                            await websocket.send_json(
                                {
                                    "error": True,
                                    "message": "Invalid survey or question IDs",
                                    "code": 400
                                }
                            )

                        redis_key = f"survey_details:{client_response.su_id}:{client_response.qs_id}"
                        cached_payload = redis_client.get(redis_key)
                        if not cached_payload:
                            output, error = await db_switcher.fetch_and_cache_survey_details(
                                db_type=db_type,
                                survey_response=client_response,
                            )
                            if error or not output:
                                await websocket.send_json(error or 
                                    {
                                        "error": True,
                                        "message": "Survey details not found",
                                        "code": 404
                                    }
                                )

                        state_key = _probe_state_key(
                            str(client_response.su_id),
                            str(client_response.qs_id),
                            str(client_response.mo_id)
                        )
                        cached_probe_state = _load_probe_state(state_key)
                        
                        # Set default values if not present
                        if not cached_probe_state:
                            cached_probe_state = {
                                "session_no": 0, 
                                "su_id": str(client_response.su_id),
                                "mo_id": str(client_response.mo_id),
                                "qs_id": str(client_response.qs_id),
                                "counter": 0,
                                "ended": False
                            }
                        else:
                            survey_details = json.loads(cached_payload) if isinstance(cached_payload, (str, bytes, bytearray)) else cached_payload
                            root_question_text = survey_details.get("question", {}).get("question", "")
                            
                            if root_question_text and client_response.question == root_question_text:
                                cached_probe_state["session_no"] = cached_probe_state.get("session_no", 0) + 1
                                cached_probe_state["counter"] = 0
                                cached_probe_state["ended"] = False
                        
                        # Increment the turn counter for active sessions before saving
                        cached_probe_state["counter"] = int(cached_probe_state.get("counter", 0)) + 1
                        
                        _save_probe_state(state_key, cached_probe_state)

                        # Track current state key for engine response proxy task
                        current_state_key = state_key

                        await engine_ws.send(data)
                except WebSocketDisconnect:
                    logger.info("Client disconnected from the websocket.")
                except Exception as e:
                    logger.error(f"Error forwarding message from client to probing engine: {e}")
                    await websocket.send_json(
                        {
                            "error": True,
                            "message": str(e),
                            "code": 500
                        }
                    )

            async def forward_engine_to_client():
                nonlocal current_state_key
                """
                Receives messages from the probing engine and forwards them to the client.
                Updates the session state if a stream ends.
                """
                try:
                    while True:
                        data = await engine_ws.recv()
                        
                        # Parse the engine's response to check if the session ended
                        engine_response = json.loads(data)
                        
                        # Update the current state key if the probe engine signals ending with ended=True
                        is_streaming_ended = (
                            engine_response.get("message") == "streaming-ended" and 
                            engine_response.get("response", {}).get("ended", False)
                        )
                        if is_streaming_ended:
                            if current_state_key:
                                state = _load_probe_state(current_state_key)
                                state["ended"] = True
                                _save_probe_state(current_state_key, state)
                        
                        await websocket.send_text(data)

                except websockets.exceptions.ConnectionClosed:
                    logger.info("Probing engine disconnected from the websocket.")
                    await websocket.close(
                        code=1001,
                        reason="Probing engine disconnected from the websocket."
                    )
                except Exception as e:
                    logger.error(f"Error forwarding message from probing engine to client: {e}")
                    await websocket.send_json(
                        {
                            "error": True,
                            "message": str(e),
                            "code": 500
                        }
                    )

            # Run both forwarding loops concurrently
            client_task = asyncio.create_task(forward_client_to_engine())
            engine_task = asyncio.create_task(forward_engine_to_client())
            
            # Wait until either the client or the target disconnects
            done, pending = await asyncio.wait(
                [client_task, engine_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel the remaining task
            for task in pending:
                task.cancel()
                
    except WebSocketDisconnect:
        print("Frontend client disconnected")
    except ConnectionRefusedError:
        print(f"Could not connect to the Probing Engine at {PROBE_ENGINE_WS_URL}")
        await websocket.close(code=1011, reason="Probing engine unreachable")
    except Exception as e:
        print(f"WebSocket proxy error: {e}")
        await websocket.close(code=1011, reason="Internal server error")
