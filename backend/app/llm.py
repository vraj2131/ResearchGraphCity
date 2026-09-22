from __future__ import annotations

import json
import os
from typing import Any

import requests
from pydantic import ValidationError

from .config import load_project_env
from .schemas import AssistantResponse, BridgeSummaryPacket, BuildingSummaryPacket, CityNavigationResponse, SummaryResponse


load_project_env()

SUMMARY_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "short_name": {"type": "string"},
        "one_sentence_summary": {"type": "string"},
        "evidence_points": {"type": "array", "items": {"type": "string"}},
        "recommended_bridge_id": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
    },
    "required": ["short_name", "one_sentence_summary", "evidence_points", "recommended_bridge_id", "confidence"],
    "additionalProperties": False,
}
NAVIGATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "route_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "target_type": {"type": "string", "enum": ["building", "bridge", "street", "community"]},
                    "target_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["label", "target_type", "target_id", "reason"],
                "additionalProperties": False,
            },
        },
        "focus_building_ids": {"type": "array", "items": {"type": "string"}},
        "focus_bridge_ids": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": ["answer", "route_steps", "focus_building_ids", "focus_bridge_ids", "confidence"],
    "additionalProperties": False,
}
ASSISTANT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "answer_markdown": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "citation_ids": {"type": "array", "items": {"type": "string"}},
                    "support_score": {"type": "number"},
                },
                "required": ["claim", "citation_ids", "support_score"],
                "additionalProperties": False,
            },
        },
        "route_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "target_type": {
                        "type": "string",
                        "enum": ["building", "bridge", "street", "community", "paper"],
                    },
                    "target_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["label", "target_type", "target_id", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer_markdown", "claims", "route_steps"],
    "additionalProperties": False,
}


def unavailable_summary(reason: str = "GROQ_API_KEY is not configured") -> SummaryResponse:
    return SummaryResponse(
        short_name="Summary unavailable",
        one_sentence_summary=reason,
        evidence_points=[reason],
        recommended_bridge_id=None,
        confidence=0.0,
    )


def parse_summary_json(content: str) -> SummaryResponse:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Groq response was not valid JSON") from exc
    try:
        return SummaryResponse.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("Groq response did not match summary schema") from exc


def unavailable_navigation(reason: str = "GROQ_API_KEY is not configured") -> CityNavigationResponse:
    return CityNavigationResponse(
        answer=reason,
        route_steps=[],
        focus_building_ids=[],
        focus_bridge_ids=[],
        confidence=0.0,
        model_available=False,
    )


def parse_navigation_json(content: str) -> CityNavigationResponse:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Groq response was not valid JSON") from exc
    try:
        return CityNavigationResponse.model_validate({**payload, "model_available": True})
    except ValidationError as exc:
        raise ValueError("Groq response did not match navigation schema") from exc


def parse_assistant_json(content: str) -> AssistantResponse:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Groq response was not valid JSON") from exc
    try:
        return AssistantResponse.model_validate({**payload, "confidence": 0.0, "model_available": True})
    except ValidationError as exc:
        raise ValueError("Groq response did not match assistant schema") from exc


class GroqSummaryProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    def generate_building_summary(self, packet: BuildingSummaryPacket) -> SummaryResponse:
        if not self.api_key:
            return unavailable_summary()
        return self._generate("Summarize this research graph city building using only provided evidence.", packet.model_dump(mode="json"))

    def generate_bridge_summary(self, packet: BridgeSummaryPacket) -> SummaryResponse:
        if not self.api_key:
            return unavailable_summary()
        return self._generate("Summarize this research graph city bridge using only provided numeric evidence.", packet.model_dump(mode="json"))

    def generate_city_navigation(self, question: str, city_index: dict[str, Any]) -> CityNavigationResponse:
        if not self.api_key:
            return unavailable_navigation()
        return self._generate_navigation(
            "Answer the user's navigation question using only this compact research graph city index. "
            "Return the most useful buildings and bridges to inspect. Use exact IDs from the index.",
            {"question": question, "city_index": city_index},
        )

    def generate_assistant_answer(self, question: str, evidence_packet: dict[str, Any]) -> AssistantResponse:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        response = requests.post(
            self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Answer research questions using only the evidence packet. Cover relevant domains, papers, "
                            "authors, methods, datasets, publication trends, and graph relationships when asked. Every factual claim must "
                            "cite one or more exact evidence_id values. Never invent an entity or relationship."
                        ),
                    },
                    {"role": "user", "content": json.dumps({"question": question, "evidence": evidence_packet})},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "research_graph_answer", "strict": True, "schema": ASSISTANT_JSON_SCHEMA},
                },
            },
            timeout=45,
        )
        response.raise_for_status()
        return parse_assistant_json(response.json()["choices"][0]["message"]["content"])

    def _generate(self, instruction: str, packet: dict[str, Any]) -> SummaryResponse:
        response = requests.post(
            self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Return evidence-based JSON only. Never invent graph relationships.",
                    },
                    {"role": "user", "content": instruction + "\n\n" + json.dumps(packet)},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "graph_city_summary",
                        "strict": True,
                        "schema": SUMMARY_JSON_SCHEMA,
                    },
                },
            },
            timeout=30,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return parse_summary_json(content)

    def _generate_navigation(self, instruction: str, packet: dict[str, Any]) -> CityNavigationResponse:
        response = requests.post(
            self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Return navigation JSON only. Use only IDs present in the provided graph city index. Never invent buildings, bridges, or papers.",
                    },
                    {"role": "user", "content": instruction + "\n\n" + json.dumps(packet)},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "graph_city_navigation",
                        "strict": True,
                        "schema": NAVIGATION_JSON_SCHEMA,
                    },
                },
            },
            timeout=30,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return parse_navigation_json(content)
