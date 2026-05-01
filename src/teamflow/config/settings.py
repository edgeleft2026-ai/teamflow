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


class AgentConfig(BaseModel):
    """Agent configuration for the AI/smart channel."""

    provider: str = ""  # provider ID (openai, deepseek, anthropic, ...)
    api_mode: str = ""  # chat_completions | anthropic_messages
    mcp_tools: str = "im.v1.*,docx.v1.*"
    max_iterations: int = 10
    timeout_seconds: int = 120
    fast_model: str = "openai/gpt-4o-mini"
    smart_model: str = "openai/gpt-4o"
    reasoning_model: str = "openai/gpt-4o"


class GiteaConfig(BaseModel):
    """Gitea (self-hosted Git service) configuration."""

    base_url: str = ""
    access_token: str = ""
    default_private: bool = True
    auto_create: bool = True
    org_name: str = ""


class LoggingConfig(BaseModel):
    """Logging configuration for production-grade log management."""

    level: str = "INFO"
    log_dir: str = "logs"
    file_enabled: bool = True
    file_level: str = "DEBUG"
    file_max_bytes: int = 10 * 1024 * 1024
    file_backup_count: int = 5
    json_format: bool = False
    color: bool = True
    module_levels: dict[str, str] = {}


class TeamFlowConfig(BaseModel):
    feishu: FeishuConfig
    agent: AgentConfig = AgentConfig()
    gitea: GiteaConfig = GiteaConfig()
    logging: LoggingConfig = LoggingConfig()


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
