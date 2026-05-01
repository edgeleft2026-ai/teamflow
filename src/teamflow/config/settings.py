from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

_ENV_FILE = Path(".env")
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)


class FeishuConfig(BaseModel):
    app_id: str = ""
    app_secret: str = ""
    brand: str = "feishu"
    admin_open_id: str = ""


class AgentConfig(BaseModel):
    provider: str = ""
    api_mode: str = ""
    mcp_tools: str = "im.v1.*,docx.v1.*"
    max_iterations: int = 10
    timeout_seconds: int = 120
    fast_model: str = "openai/gpt-4o-mini"
    smart_model: str = "openai/gpt-4o"
    reasoning_model: str = "openai/gpt-4o"


class GiteaConfig(BaseModel):
    base_url: str = ""
    access_token: str = ""
    default_private: bool = True
    auto_create: bool = True
    org_name: str = ""


class LoggingConfig(BaseModel):
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


_ENV_MAP: list[tuple[str, str, str]] = [
    ("feishu", "app_id", "FEISHU_APP_ID"),
    ("feishu", "app_secret", "FEISHU_APP_SECRET"),
    ("feishu", "brand", "FEISHU_BRAND"),
    ("feishu", "admin_open_id", "FEISHU_ADMIN_OPEN_ID"),
    ("agent", "provider", "AGENT_PROVIDER"),
    ("agent", "api_mode", "AGENT_API_MODE"),
    ("agent", "mcp_tools", "AGENT_MCP_TOOLS"),
    ("agent", "max_iterations", "AGENT_MAX_ITERATIONS"),
    ("agent", "timeout_seconds", "AGENT_TIMEOUT_SECONDS"),
    ("agent", "fast_model", "TEAMFLOW_FAST_MODEL"),
    ("agent", "smart_model", "TEAMFLOW_SMART_MODEL"),
    ("agent", "reasoning_model", "TEAMFLOW_REASONING_MODEL"),
    ("gitea", "base_url", "GITEA_BASE_URL"),
    ("gitea", "access_token", "GITEA_ACCESS_TOKEN"),
    ("gitea", "default_private", "GITEA_DEFAULT_PRIVATE"),
    ("gitea", "auto_create", "GITEA_AUTO_CREATE"),
    ("gitea", "org_name", "GITEA_ORG_NAME"),
    ("logging", "level", "LOG_LEVEL"),
    ("logging", "log_dir", "LOG_DIR"),
    ("logging", "file_enabled", "LOG_FILE_ENABLED"),
    ("logging", "file_level", "LOG_FILE_LEVEL"),
    ("logging", "file_max_bytes", "LOG_FILE_MAX_BYTES"),
    ("logging", "file_backup_count", "LOG_FILE_BACKUP_COUNT"),
    ("logging", "json_format", "LOG_JSON_FORMAT"),
    ("logging", "color", "LOG_COLOR"),
]


def _apply_env_overrides(config_data: dict) -> None:
    for section, key, env_var in _ENV_MAP:
        value = os.getenv(env_var)
        if value is not None:
            target = config_data.setdefault(section, {})
            if isinstance(target.get(key), bool):
                target[key] = value.lower() != "false"
            elif isinstance(target.get(key), int):
                try:
                    target[key] = int(value)
                except ValueError:
                    pass
            else:
                target[key] = value


def load_config(path: Path | str | None = None) -> TeamFlowConfig:
    """Load TeamFlow configuration from YAML with env var overrides.

    Resolution order (latter wins):
    1. Pydantic model defaults
    2. YAML config file (config.yaml or TEAMFLOW_CONFIG_PATH)
    3. Environment variables / .env file (highest priority for all settings)

    Recommended: keep non-sensitive settings in config.yaml,
    secrets (app_secret, access_token, API keys) in .env file.
    """
    if path is None:
        env_path = os.getenv("TEAMFLOW_CONFIG_PATH")
        if env_path:
            path = Path(env_path)
        else:
            path = Path("config.yaml")
    else:
        path = Path(path)

    config_data: dict = {
        "feishu": {},
        "agent": {},
        "gitea": {},
        "logging": {},
    }

    if Path(path).exists():
        with open(path) as f:
            yaml_data = yaml.safe_load(f) or {}
        for section, data in yaml_data.items():
            if isinstance(data, dict) and section in config_data:
                config_data[section].update(data)

    _apply_env_overrides(config_data)

    return TeamFlowConfig(**config_data)
