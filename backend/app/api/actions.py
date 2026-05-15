"""Action approval and listing endpoints."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import ActionCard, ActionEditRequest, ActionStatus
from app.services.action_service import apply_action_edit, assert_action_editable
from app.services.action_registry import (
    get_action_entry,
    get_actions_for_sku as registry_get_actions_for_sku,
    list_actions as registry_list_actions,
    register_actions as registry_register_actions,
    set_action_entry,
    update_action_status as registry_update_action_status,
)

router = APIRouter()

def register_actions(actions: list[ActionCard], run_id: str):
    """Store action cards in memory and SQLite."""
    registry_register_actions(actions, run_id)


@router.post("/actions/{action_id}/approve", response_model=ActionCard)
async def approve_action(action_id: str):
    """Approve an action card."""
    updated = registry_update_action_status(action_id, ActionStatus.APPROVED)
    if updated is None:
        raise HTTPException(status_code=404, detail="Action not found.")
    return updated


@router.post("/actions/{action_id}/reject", response_model=ActionCard)
async def reject_action(action_id: str):
    """Reject an action card."""
    updated = registry_update_action_status(action_id, ActionStatus.REJECTED)
    if updated is None:
        raise HTTPException(status_code=404, detail="Action not found.")
    return updated


@router.patch("/actions/{action_id}/edit", response_model=ActionCard)
async def edit_action(action_id: str, req: ActionEditRequest):
    """Edit a pending action card."""
    entry = get_action_entry(action_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Action not found.")

    run_id, card = entry
    try:
        assert_action_editable(card)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    edited = apply_action_edit(card, req)
    set_action_entry(action_id, run_id, edited)
    registry_register_actions([edited], run_id)
    return edited


@router.get("/actions/{run_id}", response_model=list[ActionCard])
async def list_actions(run_id: str):
    """List action cards for a run."""
    return registry_list_actions(run_id)


def get_actions_for_sku(run_id: str, sku: str) -> list[ActionCard]:
    """Get actions for a run/SKU pair."""
    return registry_get_actions_for_sku(run_id, sku)
