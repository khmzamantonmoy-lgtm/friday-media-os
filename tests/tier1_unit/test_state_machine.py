"""
Tier 1 — Unit: State Machine
Zero GCP. Pure logic only.
"""
import pytest
from src.engine.state_machine import ContentState, StateMachine

ORDERED_STATES = [
    ContentState.NEW,
    ContentState.TOPIC_SELECTED,
    ContentState.SCRIPT_READY,
    ContentState.ASSETS_READY,
    ContentState.RENDERING,
    ContentState.RENDERED,
    ContentState.UPLOADING,
    ContentState.PUBLIC,
    ContentState.CAPTIONS_VERIFIED,
    ContentState.MEMORY_UPDATED,
    ContentState.COMPLETE,
]

def test_full_forward_path():
    for i in range(len(ORDERED_STATES) - 1):
        current = ORDERED_STATES[i]
        nxt = ORDERED_STATES[i + 1]
        assert StateMachine.can_transition(current, nxt), (
            f"Expected valid transition {current.value} -> {nxt.value}"
        )

def test_illegal_skip_transition():
    assert StateMachine.can_transition(ContentState.NEW, ContentState.COMPLETE) is False

def test_illegal_backward_transition():
    assert StateMachine.can_transition(ContentState.SCRIPT_READY, ContentState.NEW) is False

def test_retry_can_resume_any_stage():
    resume_states = [
        ContentState.TOPIC_SELECTED,
        ContentState.SCRIPT_READY,
        ContentState.ASSETS_READY,
        ContentState.RENDERING,
        ContentState.RENDERED,
        ContentState.UPLOADING,
        ContentState.PUBLIC,
        ContentState.CAPTIONS_VERIFIED,
        ContentState.MEMORY_UPDATED,
    ]
    for state in resume_states:
        assert StateMachine.can_transition(ContentState.RETRY, state), (
            f"RETRY -> {state.value} should be allowed"
        )

def test_failed_to_retry_allowed():
    assert StateMachine.can_transition(ContentState.FAILED, ContentState.RETRY) is True

def test_complete_is_strictly_terminal():
    for state in ContentState:
        if state != ContentState.COMPLETE:
            assert StateMachine.can_transition(ContentState.COMPLETE, state) is False, (
                f"COMPLETE should not transition to {state.value}"
            )

def test_failed_cannot_go_to_complete():
    assert StateMachine.can_transition(ContentState.FAILED, ContentState.COMPLETE) is False

def test_all_13_enum_values_defined():
    expected = {
        "NEW", "TOPIC_SELECTED", "SCRIPT_READY", "ASSETS_READY",
        "RENDERING", "RENDERED", "UPLOADING", "PUBLIC",
        "CAPTIONS_VERIFIED", "MEMORY_UPDATED", "COMPLETE",
        "FAILED", "RETRY"
    }
    actual = {s.value for s in ContentState}
    assert actual == expected

def test_every_non_terminal_has_failure_exit():
    terminal_or_recovery = {ContentState.COMPLETE, ContentState.RETRY, ContentState.FAILED}
    for state in ContentState:
        if state in terminal_or_recovery:
            continue
        can_fail = (
            StateMachine.can_transition(state, ContentState.FAILED) or
            StateMachine.can_transition(state, ContentState.RETRY)
        )
        assert can_fail, f"State {state.value} has no failure exit"

def test_transition_table_exhaustive():
    for state in ContentState:
        assert state in StateMachine._transitions, (
            f"{state.value} missing from _transitions"
        )
