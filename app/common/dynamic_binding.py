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
    try:
        data = json.loads(raw_bindings)
    except json.JSONDecodeError as e:
        raise ValueError(f"BILIBILI_UID_GROUP_BINDINGS must be a valid JSON object: {e}")
        
    if not isinstance(data, dict):
        raise ValueError("BILIBILI_UID_GROUP_BINDINGS must be a JSON object.")

    bindings: Dict[str, List[Dict[str, str | bool]]] = {}
    for uid, group_ids in data.items():
        normalized_uid = str(uid).strip()
        if not normalized_uid:
            continue

        if not isinstance(group_ids, list):
            raise ValueError(f"Invalid group config for UID {normalized_uid}: expected list.")

        bindings[normalized_uid] = [_parse_group_target(group_id) for group_id in group_ids if str(group_id).strip()]
    return bindings


def get_dynamic_uid_group_bindings() -> Dict[str, List[Dict[str, str | bool]]]:
    raw_bindings = os.environ.get("BILIBILI_UID_GROUP_BINDINGS", "").strip()
    if not raw_bindings:
        logging.warning("BILIBILI_UID_GROUP_BINDINGS is not set. Dynamic monitoring will be disabled.")
        return {}

    try:
        bindings = _parse_bindings_from_json(raw_bindings)
        logging.info("Loaded %s UID bindings from BILIBILI_UID_GROUP_BINDINGS.", len(bindings))
        return bindings
    except Exception as e:
        logging.error(f"Error parsing BILIBILI_UID_GROUP_BINDINGS: {e}")
        return {}
