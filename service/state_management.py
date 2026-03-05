import os
import json
from redis import Redis
from service.ServerLogger import ServerLogger
from langchain_community.chat_message_histories import RedisChatMessageHistory

logger = ServerLogger()
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
PROBE_STATE_TTL = int(os.environ.get("REDIS_TTL_SECONDS_SESSION", 3600))
redis_client = Redis.from_url(REDIS_URL)

class ProbeStateManager:
    def __init__(self, mo_id: str, survey_id: str, question_id: str, simple_store: bool = True, session_no: int = 0):
        self.mo_id = mo_id
        self.su_id = survey_id
        self.qs_id = question_id
        self.session_no = session_no
        self.counter = 0
        self.ended = False
        self.simple_store = simple_store

    def to_state(self) -> dict:
        return {
            "session_no": self.session_no,
            "counter": self.counter,
            "ended": self.ended,
            "simple_store": self.simple_store,
        }

    def apply_state(self, state: dict):
        if not state:
            return
        try:
            self.session_no = int(state.get("session_no", self.session_no))
        except Exception:
            pass
        try:
            self.counter = int(state.get("counter", self.counter))
        except Exception:
            pass
        try:
            self.ended = bool(state.get("ended", self.ended))
        except Exception:
            pass
        try:
            self.simple_store = bool(state.get("simple_store", self.simple_store))
        except Exception:
            pass

    def clear_memory(self):
        try:
            session_id = f"{self.su_id}-{self.qs_id}-{self.mo_id}:{self.session_no}"
            history = RedisChatMessageHistory(session_id=session_id, redis_url=REDIS_URL)
            history.clear()
        except Exception as e:
            logger.error("Failed to clear Redis chat history")
            logger.error(e)

def _probe_state_key(su_id: str, qs_id: str, mo_id: str) -> str:
    return f"probe_state:{su_id}:{qs_id}:{mo_id}"

def _load_probe_state(key: str) -> dict:
    try:
        cached = redis_client.get(key)
        if not cached:
            return {}
        return json.loads(cached)
    except Exception as e:
        logger.error("Failed to load probe state from Redis")
        logger.error(e)
        return {}

def _save_probe_state(key: str, state: dict) -> None:
    try:
        payload = json.dumps(state)
        if PROBE_STATE_TTL > 0:
            redis_client.setex(key, PROBE_STATE_TTL, payload)
        else:
            redis_client.set(key, payload)
    except Exception as e:
        logger.error("Failed to save probe state to Redis")
        logger.error(e)