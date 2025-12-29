"""JSON operational state management with backup/restore."""

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SyncState:
    """Operational state persisted between runs."""

    last_full_sync: Optional[datetime] = None
    last_incremental_sync: Optional[datetime] = None
    last_tvmaze_page: int = 0
    highest_tvmaze_id: int = 0
    last_filter_hash: Optional[str] = None
    last_updates_check: Optional[datetime] = None

    @classmethod
    def load(cls, path: Path) -> "SyncState":
        """
        Load state from JSON file.

        Recovery logic:
        1. Try loading state.json
        2. If corrupt/missing, try state.json.bak
        3. If both fail, return fresh state

        Logs warnings on recovery.
        """
        # Try loading primary state file
        if path.exists():
            try:
                with open(path, 'r') as f:
                    data = json.load(f)

                if validate_state(data):
                    logger.info(f"Loaded state from {path}")
                    return cls.from_dict(data)
                else:
                    logger.warning(f"State file {path} failed validation, trying backup")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load state from {path}: {e}, trying backup")

        # Try loading backup
        backup_path = path.parent / f"{path.name}.bak"
        if backup_path.exists():
            try:
                with open(backup_path, 'r') as f:
                    data = json.load(f)

                if validate_state(data):
                    logger.warning(f"Restored state from backup {backup_path}")
                    return cls.from_dict(data)
                else:
                    logger.error(f"Backup state file {backup_path} also failed validation")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load backup state from {backup_path}: {e}")

        # Return fresh state if all else fails
        logger.warning("Starting with fresh state (no valid state file found)")
        return cls()

    def save(self, path: Path) -> None:
        """
        Save state to JSON file atomically.

        Process:
        1. Serialize to JSON
        2. Write to state.json.tmp
        3. Atomic rename to state.json
        """
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temporary file
        tmp_path = path.parent / f"{path.name}.tmp"
        try:
            with open(tmp_path, 'w') as f:
                json.dump(self.to_dict(), f, indent=2)

            # Atomic rename
            tmp_path.replace(path)
            logger.debug(f"Saved state to {path}")

        except IOError as e:
            logger.error(f"Failed to save state to {path}: {e}")
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    def backup(self, path: Path) -> None:
        """
        Create backup of current state.

        Copies state.json to state.json.bak.
        Called only after successful sync cycle completion.
        """
        if not path.exists():
            logger.warning(f"Cannot backup non-existent state file {path}")
            return

        backup_path = path.parent / f"{path.name}.bak"
        try:
            shutil.copy2(path, backup_path)
            logger.debug(f"Created state backup at {backup_path}")
        except IOError as e:
            logger.error(f"Failed to create state backup: {e}")

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON encoding."""
        return {
            "last_full_sync": self.last_full_sync.isoformat() if self.last_full_sync else None,
            "last_incremental_sync": self.last_incremental_sync.isoformat() if self.last_incremental_sync else None,
            "last_tvmaze_page": self.last_tvmaze_page,
            "highest_tvmaze_id": self.highest_tvmaze_id,
            "last_filter_hash": self.last_filter_hash,
            "last_updates_check": self.last_updates_check.isoformat() if self.last_updates_check else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SyncState":
        """Deserialize from dictionary."""
        # Parse datetime strings
        last_full_sync = None
        if data.get("last_full_sync"):
            try:
                last_full_sync = datetime.fromisoformat(data["last_full_sync"])
            except (ValueError, TypeError):
                logger.warning("Invalid last_full_sync in state, ignoring")

        last_incremental_sync = None
        if data.get("last_incremental_sync"):
            try:
                last_incremental_sync = datetime.fromisoformat(data["last_incremental_sync"])
            except (ValueError, TypeError):
                logger.warning("Invalid last_incremental_sync in state, ignoring")

        last_updates_check = None
        if data.get("last_updates_check"):
            try:
                last_updates_check = datetime.fromisoformat(data["last_updates_check"])
            except (ValueError, TypeError):
                logger.warning("Invalid last_updates_check in state, ignoring")

        return cls(
            last_full_sync=last_full_sync,
            last_incremental_sync=last_incremental_sync,
            last_tvmaze_page=data.get("last_tvmaze_page", 0),
            highest_tvmaze_id=data.get("highest_tvmaze_id", 0),
            last_filter_hash=data.get("last_filter_hash"),
            last_updates_check=last_updates_check,
        )


def validate_state(data: dict) -> bool:
    """
    Validate state JSON structure.

    Checks:
    - Required keys present
    - Values are correct types
    - Dates parse correctly

    Returns False if invalid (triggers backup restore).
    """
    if not isinstance(data, dict):
        logger.error("State data is not a dictionary")
        return False

    # Check for required keys
    required_keys = ["last_tvmaze_page", "highest_tvmaze_id"]
    for key in required_keys:
        if key not in data:
            logger.error(f"Missing required key in state: {key}")
            return False

    # Validate types
    if not isinstance(data["last_tvmaze_page"], int):
        logger.error("last_tvmaze_page must be an integer")
        return False

    if not isinstance(data["highest_tvmaze_id"], int):
        logger.error("highest_tvmaze_id must be an integer")
        return False

    # Validate datetime strings if present
    datetime_fields = ["last_full_sync", "last_incremental_sync", "last_updates_check"]
    for field in datetime_fields:
        if data.get(field):
            try:
                datetime.fromisoformat(data[field])
            except (ValueError, TypeError):
                logger.error(f"Invalid datetime format for {field}")
                return False

    return True
