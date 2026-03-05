from pydantic import BaseModel


class PutRequest(BaseModel):
    value: str
    ttl: int | None = None  # TTL in seconds, None = never expires


class KVResponse(BaseModel):
    key: str
    value: str


class ErrorResponse(BaseModel):
    detail: str
