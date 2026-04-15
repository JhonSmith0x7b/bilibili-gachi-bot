import json
import logging
import os
from typing import Dict, List


def _parse_group_target(raw_group_id: str) -> Dict[str, str | bool]:
    group_id = str(raw_group_id).strip()
    if not group_id:
        raise ValueError("Group ID cannot be empty.")
    return {
        "group_id": group_id.removeprefix("@"),
        "at_all": group_id.startswith("@"),
    }


def _parse_bindings_from_json(raw_bindings: str) -> Dict[str, List[Dict[str, str | bool]]]:
    data = json.loads(raw_bindings)
    if not isinstance(data, dict):
        raise ValueError("BILIBILI_ROOM_GROUP_BINDINGS must be a JSON object.")

    bindings: Dict[str, List[Dict[str, str | bool]]] = {}
    for room_id, group_ids in data.items():
        normalized_room_id = str(room_id).strip()
        if not normalized_room_id:
            continue

        if not isinstance(group_ids, list):
            raise ValueError(f"Invalid group config for room {normalized_room_id}: expected list.")

        bindings[normalized_room_id] = [_parse_group_target(group_id) for group_id in group_ids if str(group_id).strip()]
    return bindings


def get_live_room_group_bindings() -> Dict[str, List[Dict[str, str | bool]]]:
    raw_bindings = os.environ.get("BILIBILI_ROOM_GROUP_BINDINGS", "").strip()
    if not raw_bindings:
        raise ValueError("BILIBILI_ROOM_GROUP_BINDINGS is not set.")

    bindings = _parse_bindings_from_json(raw_bindings)
    logging.info("Loaded %s room bindings from BILIBILI_ROOM_GROUP_BINDINGS.", len(bindings))
    return bindings
