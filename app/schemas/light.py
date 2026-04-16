from pydantic import BaseModel, Field


class LightControlRequest(BaseModel):
    state: str = Field(..., description="Target light state: on/off")


class LightControlResponse(BaseModel):
    status: str
    state: str
    topic: str
    payload: dict
