from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class FeishuConfig(BaseModel):
    app_id: str
    app_secret: str
    brand: str = "feishu"
    admin_open_id: str = ""


class TeamFlowConfig(BaseModel):
    feishu: FeishuConfig


def load_config(path: Path | str | None = None) -> TeamFlowConfig:
    """Load TeamFlow configuration from YAML file.

    Resolution order:
    1. Explicit path argument
    2. TEAMFLOW_CONFIG_PATH environment variable
    3. config.yaml in current directory
    """
    if path is None:
        env_path = os.getenv("TEAMFLOW_CONFIG_PATH")
        if env_path:
            path = Path(env_path)
        else:
            path = Path("config.yaml")
    else:
        path = Path(path)

    with open(path) as f:
        data = yaml.safe_load(f)
    return TeamFlowConfig(**data)
