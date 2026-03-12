"""
modules/resume/yaml_loader.py — Master resume YAML utilities.
"""
import yaml
from pathlib import Path
from shared.logger import get_logger

logger = get_logger(__name__)

MASTER_RESUME_PATH = Path("config/master_resume.yaml")


def load_master_resume() -> dict:
    """Load the master resume YAML template."""
    if not MASTER_RESUME_PATH.exists():
        raise FileNotFoundError(
            f"Master resume not found at {MASTER_RESUME_PATH}. "
            "Update config/master_resume.yaml with your experience."
        )
    with open(MASTER_RESUME_PATH) as f:
        return yaml.safe_load(f) or {}


def save_resume_yaml(data: dict, path: Path) -> None:
    """Save a resume dict to YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    logger.info(f"Resume YAML saved: {path}")
