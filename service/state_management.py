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
    """
    Manages the in-memory probe state for a single survey session.

    Holds session bookkeeping fields (session_no, counter, ended, simple_store)
    and provides helpers to serialise/deserialise them for Redis storage.
    """

    def __init__(
        self,
        mo_id: str,
        survey_id: str,
        question_id: str,
        simple_store: bool = True,
        session_no: int = 0,
    ) -> None:
        """
        Initialise a new ProbeStateManager.

        Args:
            mo_id:        Member / respondent ID.
            survey_id:    Survey ID (su_id).
            question_id:  Question ID (qs_id).
            simple_store: Whether to persist responses to the database.
            session_no:   Starting session number (incremented on new root-question hits).
        """
        self.mo_id = mo_id
        self.su_id = survey_id
        self.qs_id = question_id
        self.session_no = session_no
        self.counter = 0
        self.ended = False
        self.simple_store = simple_store

    def to_state(self) -> dict:
        """
        Serialise the mutable session fields to a plain dict suitable for Redis storage.

        Returns:
            A dict with keys: session_no, counter, ended, simple_store.
            (mo_id, su_id, qs_id are fixed identifiers stored in the Redis key itself.)
        """
        return {
            "session_no": self.session_no,
            "counter": self.counter,
            "ended": self.ended,
            "simple_store": self.simple_store,
        }

    def apply_state(self, state: dict) -> None:
        """
        Restore mutable session fields from a previously serialised state dict.

        Handles type coercion defensively — Redis stores everything as strings/JSON,
        so each field is cast explicitly.

        Args:
            state: A dict previously produced by to_state() and round-tripped through Redis.
        """
        if not state:
            return

        try:
            self.session_no = int(state.get("session_no", self.session_no))
        except (TypeError, ValueError):
            pass

        try:
            self.counter = int(state.get("counter", self.counter))
        except (TypeError, ValueError):
            pass

        try:
            self.ended = bool(state.get("ended", self.ended))
        except (TypeError, ValueError):
            pass

        try:
            raw = state.get("simple_store", self.simple_store)
            if isinstance(raw, str):
                self.simple_store = raw.strip().lower() not in ("false", "0", "no")
            else:
                self.simple_store = bool(raw)
        except (TypeError, ValueError):
            pass

    def clear_memory(self) -> None:
        """
        Clear the LangChain Redis chat history for the current session.

        Logs an error but does not raise if the Redis operation fails.
        """
        try:
            session_id = f"{self.su_id}-{self.qs_id}-{self.mo_id}:{self.session_no}"
            history = RedisChatMessageHistory(session_id=session_id, redis_url=REDIS_URL)
            history.clear()
        except Exception as e:
            logger.error("Failed to clear Redis chat history")
            logger.error(e)

def _probe_state_key(su_id: str, qs_id: str, mo_id: str) -> str:
    """
    Build the canonical Redis key for a probe state entry.

    Args:
        su_id:  Survey ID.
        qs_id:  Question ID.
        mo_id:  Member / respondent ID.

    Returns:
        A string of the form ``probe_state:<su_id>:<qs_id>:<mo_id>``.
    """
    return f"probe_state:{su_id}:{qs_id}:{mo_id}"


def _load_probe_state(key: str) -> dict:
    """
    Load a probe state dict from Redis.

    Args:
        key: Redis key produced by _probe_state_key().

    Returns:
        The deserialised state dict, or ``{}`` if the key does not exist or
        an error occurs.
    """
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
    """
    Persist a probe state dict to Redis.

    Uses ``SETEX`` when ``PROBE_STATE_TTL > 0`` so the key expires automatically.
    Falls back to ``SET`` (no expiry) when TTL is zero or negative.

    Args:
        key:   Redis key produced by _probe_state_key().
        state: State dict to serialise and store.
    """
    try:
        payload = json.dumps(state)
        if PROBE_STATE_TTL > 0:
            redis_client.setex(key, PROBE_STATE_TTL, payload)
        else:
            redis_client.set(key, payload)
    except Exception as e:
        logger.error("Failed to save probe state to Redis")
        logger.error(e)