import hashlib
from dataclasses import dataclass

from redis import Redis
from redis.exceptions import RedisError

from schemas import ChatResponse


@dataclass
class CacheStore:
    redis_url: str
    ttl_seconds: int
    key_prefix: str
    enabled: bool = True

    def __post_init__(self):
        self.client = None
        if not self.enabled:
            return

        try:
            self.client = Redis.from_url(self.redis_url, decode_responses=True)
            self.client.ping()
        except RedisError:
            self.client = None
            self.enabled = False

    def get_mailbox_version(self, mailbox_id: str):
        key = self._mailbox_version_key(mailbox_id)
        value = self._get(key)
        if value is None:
            return 0
        try:
            return int(value)
        except ValueError:
            return 0

    def bump_mailbox_version(self, mailbox_id: str):
        if not self._is_ready():
            return 0
        try:
            return int(self.client.incr(self._mailbox_version_key(mailbox_id)))
        except RedisError:
            return 0

    def get_chat_response(self, mailbox_id: str, question: str, top_k: int):
        version = self.get_mailbox_version(mailbox_id)
        payload = self._get(self._chat_key(mailbox_id, version, question, top_k))
        if payload is None:
            return None
        try:
            return ChatResponse.model_validate_json(payload)
        except (ValueError, TypeError):
            return None

    def set_chat_response(self, mailbox_id: str, question: str, top_k: int, response: ChatResponse):
        version = self.get_mailbox_version(mailbox_id)
        self._set(
            self._chat_key(mailbox_id, version, question, top_k),
            response.model_dump_json(),
        )

    def _chat_key(self, mailbox_id: str, version: int, question: str, top_k: int):
        question_hash = hashlib.sha256(question.strip().lower().encode("utf-8")).hexdigest()
        return self._prefixed(
            "chat",
            "v1",
            mailbox_id,
            str(version),
            question_hash,
            f"topk:{top_k}",
        )

    def _mailbox_version_key(self, mailbox_id: str):
        return self._prefixed("mailbox_version", mailbox_id)

    def _prefixed(self, *parts: str):
        return ":".join([self.key_prefix, *parts])

    def _get(self, key: str):
        if not self._is_ready():
            return None
        try:
            return self.client.get(key)
        except RedisError:
            return None

    def _set(self, key: str, value: str):
        if not self._is_ready():
            return
        try:
            self.client.set(key, value, ex=self.ttl_seconds)
        except RedisError:
            return

    def _is_ready(self):
        return self.enabled and self.client is not None
