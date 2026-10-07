from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator

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
    timestamp: Optional[int] = Field(default=None, validation_alias=AliasChoices("timestamp", "time"))
    temperature: Optional[float] = Field(
        default=None, validation_alias=AliasChoices("temperature", "temp")
    )
    gas: Optional[float] = None
    humidity: Optional[float] = Field(
        default=None, validation_alias=AliasChoices("humidity", "hum")
    )
    motion: Optional[int] = Field(default=None, ge=0, le=1)
    label: Optional[str] = Field(default=None, max_length=64)

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value):
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            value = value.strip()
            try:
                return int(value)
            except ValueError:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            return value

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())


class CommandIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    target: Literal["buzzer", "led_green", "led_orange", "led_red"]
    action: Literal["on", "off", "blink"]
    duration_ms: Optional[int] = Field(default=None, ge=0, le=60000)