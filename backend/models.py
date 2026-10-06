from typing import Literal, Optional
from pydantic import BaseModel, Field

SensorType = Literal["gas", "temperature", "humidity", "intrusion", "cyber"]
State = Literal["OK", "WARNING", "CRITICAL"]


class AlertIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    timestamp: int = Field(description="Epoch seconds")
    type: SensorType
    state: State
    value: Optional[float] = None
    unit: Optional[str] = Field(default=None, max_length=16)


class TelemetryIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    timestamp: int
    temperature: Optional[float] = None
    gas: Optional[float] = None
    humidity: Optional[float] = None


class CommandIn(BaseModel):
    device_id: str = "sentinel-x-01"
    target: Literal["buzzer", "led_green", "led_orange", "led_red"]
    action: Literal["on", "off", "blink"]
    duration_ms: Optional[int] = Field(default=None, ge=0, le=60000)