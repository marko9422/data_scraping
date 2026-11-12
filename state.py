"""Persistence for per-employer HTML snapshots and removal candidates."""
import json
from pathlib import Path

from scraping import make_filename


def snapshot_path(output_dir, site):
    return Path(output_dir) / make_filename(site)


def state_path(output_dir, site):
    name = Path(make_filename(site)).stem
    return Path(output_dir) / (name + "_state.json")


def load_state(path):
    path = Path(path)
    if not path.exists():
        return {"pending_removals": {}, "last_successful_scan": None}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse state file {path}: {exc}") from exc
    if not isinstance(state, dict):
        raise RuntimeError(f"Invalid state file: {path}")
    state.setdefault("pending_removals", {})
    state.setdefault("last_successful_scan", None)
    return state


def save_state(path, state):
    """Write atomically to avoid partially written JSON after an interruption."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
