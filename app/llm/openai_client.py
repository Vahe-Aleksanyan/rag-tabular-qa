from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    model: str


def get_openai_config() -> OpenAIConfig:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Put it in .env (do not commit).")
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    return OpenAIConfig(api_key=api_key, model=model)


class OpenAIClient:
    def __init__(self, cfg: Optional[OpenAIConfig] = None):
        cfg = cfg or get_openai_config()
        self.model = cfg.model
        self.client = OpenAI(api_key=cfg.api_key)

    def text(self, system: str, user: str) -> str:
        resp = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.output_text

    def json_schema(self, system: str, user: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a JSON object that strictly matches the given JSON Schema.
        Uses Structured Outputs via response_format=json_schema (strict).
        """
        resp = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text={
            "format": {
                "type": "json_schema",
                "name": "query_plan",
                "schema": schema,
                "strict": True,
        }
},


        )
        # output_text will be the JSON string; strict ensures it matches schema
        import json
        return json.loads(resp.output_text)
