"""Structured-output example: turn a raw alarm message into a typed event.

Run against the configured provider (default local Ollama):
    python -m fabops.llm.examples "FX1-ETCHER-02-CHB 腔體壓力異常: ... 52.3 mTorr"
"""

from __future__ import annotations

import sys

from pydantic import BaseModel, Field

from fabops.authz.scope import SYSTEM_SCOPE, Scope
from fabops.llm.client import LLMClient


class AlarmEvent(BaseModel):
    equipment_id: str = Field(description="機台編號，例如 FX1-ETCHER-02")
    chamber_id: str | None = Field(description="腔體編號，例如 FX1-ETCHER-02-CHB")
    alarm_code: str | None = Field(description="Alarm code，例如 ETC-PRS-0412")
    parameter: str = Field(description="監控參數名稱")
    value: float
    unit: str
    limit: float | None = Field(description="上限值")


def parse_alarm(client: LLMClient, text: str, scope: Scope = SYSTEM_SCOPE) -> AlarmEvent:
    event, _ = client.structured(
        [{"role": "user", "content": f"從以下警報訊息擷取欄位：\n{text}"}],
        AlarmEvent,
        scope,
        purpose="parse_alarm",
    )
    return event


if __name__ == "__main__":
    msg = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "FX1-ETCHER-02-CHB ETC-PRS-0412 腔體壓力異常: chamber pressure = 52.3 mTorr (limit 45)"
    )
    print(parse_alarm(LLMClient.from_env(), msg).model_dump_json(indent=2))
