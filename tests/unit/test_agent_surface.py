"""The agent surface is real, import-safe and cannot drift from the card it publishes.

Three failures this suite exists to prevent, all of which a scaffolded surface invites:

1. **A card that lies.** A skill advertised with no tool behind it, or a tool nobody can
   discover. The set equality below is the standing gate.
2. **A third place an escalation stops.** The API and the CLI both route an escalated result to
   human review. If the agent path only returned the flag, rule R8 would hold on two surfaces
   out of three, which is the same as not holding.
3. **A surface that quietly needs a runtime.** The tools must import and run with no ADK and no
   cloud SDK, or the offline gate stops being offline the day somebody calls one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from account_takeover_investigator.agent import (
    SKILLS,
    TOOL_FUNCTIONS,
    agent_card_document,
    build_agent_card,
    investigate_session,
    list_ato_queue,
)
from account_takeover_investigator.config import build_container

from tests.conftest import local_settings
from tests.fixtures import sample_cases


def test_the_card_advertises_exactly_the_tools_the_runtime_binds() -> None:
    assert {skill.id for skill in SKILLS} == {fn.__name__ for fn in TOOL_FUNCTIONS}


def test_every_skill_carries_a_usable_description() -> None:
    """A runtime routes on the description; an empty one makes the skill unreachable."""
    for skill in SKILLS:
        assert skill.name.strip()
        assert len(skill.description.strip()) > 40, f"{skill.id} has no usable description"


def test_the_card_document_is_json_safe_and_names_the_region() -> None:
    document = agent_card_document(local_settings())
    assert document["name"] == "account-takeover-investigator"
    assert "asia-southeast1" in str(document["url"])
    assert [skill["id"] for skill in document["skills"]] == [s.id for s in SKILLS]


def test_the_api_serves_the_card_for_discovery(api_client: TestClient) -> None:
    resp = api_client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert resp.json()["skills"], "a card with no skills is not a discovery document"


def test_the_agent_path_routes_an_escalation_rather_than_only_flagging_it() -> None:
    result = investigate_session(
        "acct-takeover",
        "sess-1",
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        settings=local_settings(),
    )
    assert result["requires_human_review"] is True
    assert result["review_ref"], "the agent surface flagged an escalation it never routed"


def test_the_agent_path_does_not_manufacture_a_review_for_a_quiet_session() -> None:
    result = investigate_session("acct-quiet", "sess-1", settings=local_settings())
    assert result["requires_human_review"] is False
    assert result["review_ref"] == ""


def test_the_tool_output_is_masked_before_it_can_reach_a_model() -> None:
    """P-04 at the agent boundary: a tool result becomes model context, so it is minimised."""
    result = investigate_session(
        sample_cases.PII_SUBJECT_ID,
        "sess-1",
        settings=local_settings(),
    )
    rendered = repr(result)
    assert sample_cases.PLANTED_NRIC not in rendered
    assert "REDACTED" in rendered


def test_the_queue_tool_lists_what_this_process_routed() -> None:
    """A shared container: an escalation routed through it appears in its queue."""
    container = build_container(local_settings())
    investigate_session("acct-takeover", "sess-1", container=container)
    queue = list_ato_queue(container=container)
    assert queue["pending"] == 1
    assert queue["items"], "a routed escalation must be visible in the queue"


def test_the_tools_import_and_run_with_no_agent_runtime_installed(no_cloud_sdk: None) -> None:
    """``build_function_tools`` is the ONLY code path that may need a runtime."""
    from account_takeover_investigator.agent import tools

    assert tools.TOOL_FUNCTIONS
    assert build_agent_card(local_settings()).skills
    with pytest.raises(ModuleNotFoundError):
        tools.build_function_tools()
