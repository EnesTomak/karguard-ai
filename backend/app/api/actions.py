"""Action approval and listing endpoints."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import ActionCard, ActionEditRequest, ActionStatus
from app.services.action_service import apply_action_edit, assert_action_editable
from app.services.storage_service import (
    get_action as db_get_action,
    list_actions as db_list_actions,
    list_actions_for_sku as db_list_actions_for_sku,
    update_action_status as db_update_action_status,
    upsert_actions,
)

router = APIRouter()

# In-memory cache: action_id -> (run_id, ActionCard)
_actions: dict[str, tuple[str, ActionCard]] = {}


def register_actions(actions: list[ActionCard], run_id: str):
    """Store action cards in memory and SQLite."""
    for card in actions:
        _actions[card.action_id] = (run_id, card)
    upsert_actions(run_id, actions)


def _get_action_entry(action_id: str) -> tuple[str, ActionCard] | None:
    entry = _actions.get(action_id)
    if entry is not None:
        return entry
    return db_get_action(action_id)


@router.post("/actions/{action_id}/approve", response_model=ActionCard)
async def approve_action(action_id: str):
    """Approve an action card."""
    entry = _get_action_entry(action_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Action not found.")

    run_id, card = entry
    card.status = ActionStatus.APPROVED
    _actions[action_id] = (run_id, card)
    db_update_action_status(action_id, ActionStatus.APPROVED)
    return card


@router.post("/actions/{action_id}/reject", response_model=ActionCard)
async def reject_action(action_id: str):
    """Reject an action card."""
    entry = _get_action_entry(action_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Action not found.")

    run_id, card = entry
    card.status = ActionStatus.REJECTED
    _actions[action_id] = (run_id, card)
    db_update_action_status(action_id, ActionStatus.REJECTED)
    return card


@router.patch("/actions/{action_id}/edit", response_model=ActionCard)
async def edit_action(action_id: str, req: ActionEditRequest):
    """Edit a pending action card."""
    entry = _get_action_entry(action_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Action not found.")

    run_id, card = entry
    try:
        assert_action_editable(card)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    edited = apply_action_edit(card, req)
    _actions[action_id] = (run_id, edited)
    upsert_actions(run_id, [edited])
    return edited


@router.get("/actions/{run_id}", response_model=list[ActionCard])
async def list_actions(run_id: str):
    """List action cards for a run."""
    mem = [card for rid, card in _actions.values() if rid == run_id]
    if mem:
        return mem
    return db_list_actions(run_id)


def get_actions_for_sku(run_id: str, sku: str) -> list[ActionCard]:
    """Get actions for a run/SKU pair."""
    mem = [card for rid, card in _actions.values() if rid == run_id and card.sku == sku]
    if mem:
        return mem
    return db_list_actions_for_sku(run_id, sku)
