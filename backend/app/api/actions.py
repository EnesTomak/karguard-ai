"""Action approval / rejection endpoint."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import ActionCard, ActionStatus

router = APIRouter()

# In-memory action store: action_id -> (run_id, ActionCard)
_actions: dict[str, tuple[str, ActionCard]] = {}


def register_actions(actions: list[ActionCard], run_id: str):
    """Store action cards from the pipeline, keyed by run_id."""
    for a in actions:
        _actions[a.action_id] = (run_id, a)


@router.post("/actions/{action_id}/approve", response_model=ActionCard)
async def approve_action(action_id: str):
    """Approve an action card."""
    entry = _actions.get(action_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Aksiyon bulunamadı.")
    card = entry[1]
    card.status = ActionStatus.APPROVED
    return card


@router.post("/actions/{action_id}/reject", response_model=ActionCard)
async def reject_action(action_id: str):
    """Reject an action card."""
    entry = _actions.get(action_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Aksiyon bulunamadı.")
    card = entry[1]
    card.status = ActionStatus.REJECTED
    return card


@router.get("/actions/{run_id}", response_model=list[ActionCard])
async def list_actions(run_id: str):
    """List all action cards for a specific run."""
    return [card for rid, card in _actions.values() if rid == run_id]


def get_actions_for_sku(run_id: str, sku: str) -> list[ActionCard]:
    """Get actions for a specific run and SKU."""
    return [card for rid, card in _actions.values() if rid == run_id and card.sku == sku]
