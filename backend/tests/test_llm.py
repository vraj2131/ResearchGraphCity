import pytest

from app.llm import parse_assistant_json, parse_navigation_json, parse_summary_json


def test_parse_summary_json_rejects_invalid_json():
    with pytest.raises(ValueError, match="valid JSON"):
        parse_summary_json("not-json")


def test_parse_summary_json_rejects_missing_required_fields():
    with pytest.raises(ValueError, match="schema"):
        parse_summary_json('{"short_name": "Only one field"}')


def test_parse_navigation_json_accepts_structured_route_targets():
    result = parse_navigation_json(
        """
        {
          "answer": "Start with the graph methods building, then inspect the bridge.",
          "route_steps": [
            {"label": "Graph methods", "target_type": "building", "target_id": "B_R_0001", "reason": "Best label match"}
          ],
          "focus_building_ids": ["B_R_0001"],
          "focus_bridge_ids": ["BR_R_0001_0002"],
          "confidence": 0.72
        }
        """
    )

    assert result.focus_building_ids == ["B_R_0001"]
    assert result.route_steps[0]["target_type"] == "building"


def test_parse_navigation_json_rejects_invalid_json():
    with pytest.raises(ValueError, match="valid JSON"):
        parse_navigation_json("not-json")


def test_parse_assistant_json_accepts_grounded_claim_shape():
    response = parse_assistant_json(
        '''{
          "answer_markdown": "A graph-learning result.",
          "claims": [{"claim": "Paper W1 is relevant.", "citation_ids": ["paper:W1"], "support_score": 0.8}],
          "route_steps": [{"label": "Paper", "target_type": "paper", "target_id": "P_000001", "reason": "Top match"}]
        }'''
    )

    assert response.claims[0].citation_ids == ["paper:W1"]
    assert response.route_steps[0].target_type == "paper"
