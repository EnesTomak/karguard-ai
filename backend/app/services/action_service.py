"""Action card business rules and edit helpers."""

from __future__ import annotations

from app.models.schemas import ActionCard, ActionEditRequest, ActionStatus


def assert_action_editable(card: ActionCard) -> None:
    """Only pending cards can be edited."""
    if card.status != ActionStatus.PENDING:
        raise ValueError("Only pending actions can be edited.")


def apply_action_edit(card: ActionCard, req: ActionEditRequest) -> ActionCard:
    """Apply partial edit payload to an action card."""
    update: dict = {}

    if req.action_type is not None:
        update["action_type"] = req.action_type
    if req.title is not None:
        update["title"] = req.title
    if req.reason is not None:
        update["reason"] = req.reason
    if req.expected_impact is not None:
        update["expected_impact"] = req.expected_impact
    if req.risk_level is not None:
        update["risk_level"] = req.risk_level

    if not update:
        return card

    return card.model_copy(update=update)

