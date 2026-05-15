"""Action card registry with memory cache + SQLite fallback."""

from __future__ import annotations

from app.models.schemas import ActionCard, ActionStatus
from app.services.storage_service import (
    delete_actions as db_delete_actions,
    get_action as db_get_action,
    list_actions as db_list_actions,
    list_actions_for_sku as db_list_actions_for_sku,
    update_action_status as db_update_action_status,
    upsert_actions,
)

# In-memory cache: action_id -> (run_id, ActionCard)
_actions: dict[str, tuple[str, ActionCard]] = {}


def clear_cache() -> None:
    _actions.clear()


def clear_actions_for_run(run_id: str) -> None:
    stale_ids = [action_id for action_id, (rid, _) in _actions.items() if rid == run_id]
    for action_id in stale_ids:
        _actions.pop(action_id, None)
    db_delete_actions(run_id)


def register_actions(actions: list[ActionCard], run_id: str) -> None:
    for card in actions:
        _actions[card.action_id] = (run_id, card)
    upsert_actions(run_id, actions)


def get_action_entry(action_id: str) -> tuple[str, ActionCard] | None:
    entry = _actions.get(action_id)
    if entry is not None:
        return entry
    return db_get_action(action_id)


def set_action_entry(action_id: str, run_id: str, card: ActionCard) -> None:
    _actions[action_id] = (run_id, card)


def list_actions(run_id: str) -> list[ActionCard]:
    mem = [card for rid, card in _actions.values() if rid == run_id]
    if mem:
        return mem
    return db_list_actions(run_id)


def get_actions_for_sku(run_id: str, sku: str) -> list[ActionCard]:
    mem = [card for rid, card in _actions.values() if rid == run_id and card.sku == sku]
    if mem:
        return mem
    return db_list_actions_for_sku(run_id, sku)


def update_action_status(action_id: str, status: ActionStatus) -> ActionCard | None:
    entry = get_action_entry(action_id)
    if entry is None:
        return None

    run_id, card = entry
    card.status = status
    _actions[action_id] = (run_id, card)
    db_update_action_status(action_id, status)
    return card
