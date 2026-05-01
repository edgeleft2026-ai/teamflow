"""Model metadata registry — providers, models, and live models.dev enrichment.

Static provider/model lists aligned with hermes-agent hermes_cli/models.py
CANONICAL_PROVIDERS and _PROVIDER_MODELS.  Live metadata enrichment via
models.dev API (https://models.dev/api.json) with disk-cache fallback.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelInfo:
    """Rich metadata for a single model."""

    id: str
    name: str = ""
    provider_id: str = ""
    family: str = ""

    tool_call: bool = True
    reasoning: bool = False
    vision: bool = False
    pdf: bool = False
    structured_output: bool = False

    context_window: int = 128_000
    max_output: int = 8_192

    cost_input: float = 0.0
    cost_output: float = 0.0
    cost_cache_read: float | None = None

    def supports_tools(self) -> bool:
        return self.tool_call

    def supports_reasoning(self) -> bool:
        return self.reasoning


@dataclass
class ProviderEntry:
    """Canonical provider definition (aligned with hermes-agent ProviderEntry)."""

    slug: str
    label: str
    desc: str = ""
    auth_type: str = "api_key"  # api_key | oauth_device_code | oauth_external | external_process
    env_vars: tuple[str, ...] = ()  # ordered env var names to try
    api_mode: str = "chat_completions"
    base_url: str = ""
    doc_url: str = ""

    @property
    def primary_env_var(self) -> str:
        return self.env_vars[0] if self.env_vars else ""

    def check_credential(self) -> str | None:
        """Check if any env var has a value set. Returns the value or None."""
        import os
        for ev in self.env_vars:
            val = os.environ.get(ev, "")
            if val:
                return val
        return None


# ---------------------------------------------------------------------------
# Provider aliases (aligned with hermes-agent _PROVIDER_ALIASES)
# ---------------------------------------------------------------------------

# Mapping from internal provider IDs to LiteLLM-compatible provider names.
# LiteLLM uses specific provider prefixes in model strings like "provider/model".
LITELLM_PROVIDER_MAP: dict[str, str] = {
    "minimax-cn": "minimax",
    "minimax": "minimax",
    "kimi-coding": "moonshot",
    "kimi-coding-cn": "moonshot",
    "zai": "zhipu",
    "alibaba": "dashscope",
    "copilot": "github",
    "gemini": "gemini",
    "google-gemini-cli": "gemini",
    "deepseek": "deepseek",
    "xai": "xai",
    "anthropic": "anthropic",
    "openai": "openai",
    "openai-codex": "openai",
    "openrouter": "openrouter",
    "huggingface": "huggingface",
    "bedrock": "bedrock",
    "groq": "groq",
    "mistral": "mistral",
    "nous": "openrouter",
    "ollama-cloud": "ollama",
    "ollama": "ollama",
    "arcee": "openai",
    "kilocode": "openrouter",
    "opencode-zen": "openrouter",
    "opencode-go": "openrouter",
    "nvidia": "nvidia_nim",
    "xiaomi": "openai",
    "stepfun": "openai",
    "qwen-oauth": "dashscope",
    "copilot-acp": "github",
    "ai-gateway": "openrouter",
    "azure-foundry": "azure",
}


def to_litellm_model(internal_provider: str, model_name: str) -> str:
    """Convert internal provider+model to LiteLLM-compatible model string."""
    llm_provider = LITELLM_PROVIDER_MAP.get(internal_provider, internal_provider)
    return f"{llm_provider}/{model_name}"


# Mapping from internal provider ID to the env var that LiteLLM actually reads.
# LiteLLM uses its own naming convention (e.g. MINIMAX_API_KEY, not MINIMAX_CN_API_KEY).
LITELLM_ENV_MAP: dict[str, str] = {
    "minimax-cn": "MINIMAX_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "kimi-coding": "MOONSHOT_API_KEY",
    "kimi-coding-cn": "MOONSHOT_API_KEY",
    "zai": "ZHIPUAI_API_KEY",
    "alibaba": "DASHSCOPE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "xai": "XAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "huggingface": "HF_TOKEN",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
    "ollama-cloud": "OLLAMA_API_KEY",
    "arcee": "ARCEEAI_API_KEY",
    "kilocode": "KILOCODE_API_KEY",
    "opencode-zen": "OPENCODE_ZEN_API_KEY",
    "opencode-go": "OPENCODE_GO_API_KEY",
    "stepfun": "STEPFUN_API_KEY",
}


# Providers that need a non-default base URL for LiteLLM.
# LiteLLM reads these from env vars like MINIMAX_API_BASE.
LITELLM_BASE_URL_OVERRIDES: dict[str, str] = {
    "minimax-cn": "https://api.minimaxi.com/v1",
}


def get_litellm_env(provider_id: str) -> str:
    """Get the LiteLLM-compatible env var name for a provider's API key."""
    return LITELLM_ENV_MAP.get(provider_id, "")


def get_litellm_base_url_override(provider_id: str) -> str | None:
    """Get the LiteLLM base URL override for a provider, if any."""
    return LITELLM_BASE_URL_OVERRIDES.get(provider_id)


PROVIDER_ALIASES: dict[str, str] = {
    "glm": "zai",
    "z-ai": "zai",
    "z.ai": "zai",
    "zhipu": "zai",
    "github": "copilot",
    "github-copilot": "copilot",
    "github-models": "copilot",
    "github-model": "copilot",
    "github-copilot-acp": "copilot-acp",
    "copilot-acp-agent": "copilot-acp",
    "google": "gemini",
    "google-gemini": "gemini",
    "google-ai-studio": "gemini",
    "kimi": "kimi-coding",
    "moonshot": "kimi-coding",
    "kimi-cn": "kimi-coding-cn",
    "moonshot-cn": "kimi-coding-cn",
    "step": "stepfun",
    "stepfun-coding-plan": "stepfun",
    "arcee-ai": "arcee",
    "arceeai": "arcee",
    "minimax-china": "minimax-cn",
    "minimax_cn": "minimax-cn",
    "claude": "anthropic",
    "claude-code": "anthropic",
    "deep-seek": "deepseek",
    "opencode": "opencode-zen",
    "zen": "opencode-zen",
    "go": "opencode-go",
    "opencode-go-sub": "opencode-go",
    "aigateway": "ai-gateway",
    "vercel": "ai-gateway",
    "vercel-ai-gateway": "ai-gateway",
    "kilo": "kilocode",
    "kilo-code": "kilocode",
    "kilo-gateway": "kilocode",
    "qwen": "alibaba",
    "alibaba-cloud": "alibaba",
    "dashscope": "alibaba",
    "openai": "openai",
    "groq": "groq",
    "mistral": "mistral",
    "togetherai": "togetherai",
    "fireworks": "fireworks",
    "ollama": "ollama",
    "perplexity": "perplexity",
    "cohere": "cohere",
}


def resolve_provider(name: str) -> str | None:
    """Normalize a human-readable provider name to a canonical ID."""
    if not name:
        return None
    lowered = name.lower().strip()
    return PROVIDER_ALIASES.get(lowered, lowered)


# ---------------------------------------------------------------------------
# Canonical provider list (aligned with hermes-agent CANONICAL_PROVIDERS)
# ---------------------------------------------------------------------------

CANONICAL_PROVIDERS: list[ProviderEntry] = [
    ProviderEntry("nous", "Nous Portal", "Nous Research subscription",
                  auth_type="oauth_device_code"),
    ProviderEntry("openrouter", "OpenRouter", "100+ models, pay-per-use",
                  env_vars=("OPENROUTER_API_KEY",),
                  base_url="https://openrouter.ai/api/v1"),
    ProviderEntry("ai-gateway", "Vercel AI Gateway", "200+ models, $5 free credit",
                  env_vars=("AI_GATEWAY_API_KEY",),
                  base_url="https://ai-gateway.vercel.sh/v1"),
    ProviderEntry("anthropic", "Anthropic", "Claude models — API key or Claude Code",
                  api_mode="anthropic_messages",
                  env_vars=("ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"),
                  base_url="https://api.anthropic.com"),
    ProviderEntry("openai-codex", "OpenAI Codex", "OpenAI Codex CLI",
                  auth_type="oauth_external"),
    ProviderEntry("xiaomi", "Xiaomi MiMo", "MiMo-V2.5 and V2 models",
                  env_vars=("XIAOMI_API_KEY",)),
    ProviderEntry("nvidia", "NVIDIA NIM", "Nemotron models",
                  env_vars=("NVIDIA_API_KEY",),
                  base_url="https://integrate.api.nvidia.com/v1"),
    ProviderEntry("qwen-oauth", "Qwen OAuth (Portal)", "reuses local Qwen CLI login",
                  auth_type="oauth_external"),
    ProviderEntry("copilot", "GitHub Copilot", "uses GITHUB_TOKEN or gh auth token",
                  env_vars=("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"),
                  base_url="https://models.inference.ai.azure.com"),
    ProviderEntry("copilot-acp", "GitHub Copilot ACP", "spawns copilot --acp --stdio",
                  auth_type="external_process"),
    ProviderEntry("huggingface", "Hugging Face", "Inference Providers — 20+ open models",
                  env_vars=("HF_TOKEN",),
                  base_url="https://api-inference.huggingface.com/models"),
    ProviderEntry("gemini", "Google AI Studio", "Gemini models — native Gemini API",
                  env_vars=("GOOGLE_API_KEY", "GEMINI_API_KEY")),
    ProviderEntry("google-gemini-cli", "Google Gemini (OAuth)",
                  "Google Gemini via OAuth + Code Assist (free tier)",
                  auth_type="oauth_external"),
    ProviderEntry("deepseek", "DeepSeek", "DeepSeek-V3, R1 — direct API",
                  env_vars=("DEEPSEEK_API_KEY",),
                  base_url="https://api.deepseek.com/v1"),
    ProviderEntry("xai", "xAI", "Grok models — direct API",
                  env_vars=("XAI_API_KEY",),
                  base_url="https://api.x.ai/v1"),
    ProviderEntry("zai", "Z.AI / GLM", "Zhipu AI direct API",
                  env_vars=("GLM_API_KEY", "ZAI_API_KEY", "ZHIPUAI_API_KEY"),
                  base_url="https://open.bigmodel.cn/api/paas/v4"),
    ProviderEntry("kimi-coding", "Kimi / Kimi Coding Plan", "api.kimi.com & Moonshot API",
                  env_vars=("KIMI_API_KEY", "KIMI_CODING_API_KEY", "MOONSHOT_API_KEY")),
    ProviderEntry("kimi-coding-cn", "Kimi / Moonshot (China)", "Moonshot CN direct API",
                  env_vars=("KIMI_CN_API_KEY",)),
    ProviderEntry("stepfun", "StepFun Step Plan", "agent/coding models via Step Plan API",
                  env_vars=("STEPFUN_API_KEY",)),
    ProviderEntry("minimax", "MiniMax", "global direct API",
                  env_vars=("MINIMAX_API_KEY",),
                  base_url="https://api.minimax.chat/v1"),
    ProviderEntry("minimax-cn", "MiniMax (China)", "domestic direct API",
                  env_vars=("MINIMAX_CN_API_KEY",)),
    ProviderEntry("alibaba", "Alibaba Cloud (DashScope)", "Qwen + multi-provider coding",
                  env_vars=("DASHSCOPE_API_KEY",),
                  base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    ProviderEntry("ollama-cloud", "Ollama Cloud", "cloud-hosted open models",
                  env_vars=("OLLAMA_API_KEY",)),
    ProviderEntry("arcee", "Arcee AI", "Trinity models — direct API",
                  env_vars=("ARCEEAI_API_KEY",)),
    ProviderEntry("kilocode", "Kilo Code", "Kilo Gateway API",
                  env_vars=("KILOCODE_API_KEY",)),
    ProviderEntry("opencode-zen", "OpenCode Zen", "35+ curated models, pay-as-you-go",
                  env_vars=("OPENCODE_ZEN_API_KEY",)),
    ProviderEntry("opencode-go", "OpenCode Go", "open models, $10/month subscription",
                  env_vars=("OPENCODE_GO_API_KEY",)),
    ProviderEntry("bedrock", "AWS Bedrock", "Claude, Nova, Llama, DeepSeek — IAM or API key",
                  api_mode="bedrock_converse"),
    ProviderEntry("azure-foundry", "Azure Foundry",
                  "OpenAI-style or Anthropic-style endpoint"),
]

_PROVIDER_BY_SLUG: dict[str, ProviderEntry] = {p.slug: p for p in CANONICAL_PROVIDERS}
_PROVIDER_LABELS: dict[str, str] = {p.slug: p.label for p in CANONICAL_PROVIDERS}
_PROVIDER_LABELS["custom"] = "Custom endpoint"


def get_provider_entry(provider_id: str) -> ProviderEntry | None:
    """Look up a canonical provider entry by slug (with alias resolution)."""
    pid = resolve_provider(provider_id)
    if not pid:
        return None
    return _PROVIDER_BY_SLUG.get(pid)


# ---------------------------------------------------------------------------
# Static model catalog (aligned with hermes-agent _PROVIDER_MODELS)
# Primary source for model listing; models.dev enriches metadata.
# ---------------------------------------------------------------------------

_PROVIDER_MODELS: dict[str, list[str]] = {
    "nous": [
        "moonshotai/kimi-k2.6", "xiaomi/mimo-v2.5-pro", "xiaomi/mimo-v2.5",
        "anthropic/claude-opus-4-7", "anthropic/claude-opus-4-6",
        "anthropic/claude-sonnet-4-6", "anthropic/claude-haiku-4-5",
        "openai/gpt-5.5", "openai/gpt-5.4-mini", "openai/gpt-5.3-codex",
        "google/gemini-3-pro-preview", "google/gemini-3-flash-preview",
        "qwen/qwen3.5-plus-02-15", "qwen/qwen3.5-35b-a3b",
        "stepfun/step-3.5-flash", "minimax/minimax-m2.7", "minimax/minimax-m2.5",
        "z-ai/glm-5.1", "z-ai/glm-5v-turbo", "z-ai/glm-5-turbo",
        "x-ai/grok-4.20-beta", "nvidia/nemotron-3-super-120b-a12b",
        "arcee-ai/trinity-large-thinking",
    ],
    "openai": [
        "gpt-5.4", "gpt-5.4-mini", "gpt-5-mini",
        "gpt-5.3-codex", "gpt-5.2-codex", "gpt-4.1",
        "gpt-4o", "gpt-4o-mini",
    ],
    "openai-codex": [
        "gpt-5.4", "gpt-5.4-mini", "gpt-5-mini",
        "gpt-5.3-codex", "gpt-5.2-codex", "gpt-4.1",
        "gpt-4o", "gpt-4o-mini",
    ],
    "copilot-acp": ["copilot-acp"],
    "copilot": [
        "gpt-5.4", "gpt-5.4-mini", "gpt-5-mini",
        "gpt-5.3-codex", "gpt-5.2-codex", "gpt-4.1",
        "gpt-4o", "gpt-4o-mini",
        "claude-sonnet-4-6", "claude-sonnet-4", "claude-sonnet-4-5",
        "claude-haiku-4-5", "gemini-3.1-pro-preview",
        "gemini-3-pro-preview", "gemini-3-flash-preview",
        "gemini-2.5-pro", "grok-code-fast-1",
    ],
    "gemini": [
        "gemini-3.1-pro-preview", "gemini-3-pro-preview",
        "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview",
    ],
    "google-gemini-cli": [
        "gemini-3.1-pro-preview", "gemini-3-pro-preview",
        "gemini-3-flash-preview",
    ],
    "zai": [
        "glm-5.1", "glm-5", "glm-5v-turbo", "glm-5-turbo",
        "glm-4.7", "glm-4.5", "glm-4.5-flash",
    ],
    "xai": ["grok-4.20-reasoning", "grok-4-1-fast-reasoning"],
    "nvidia": [
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-nano-30b-a3b",
        "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "qwen/qwen3.5-397b-a17b", "deepseek-ai/deepseek-v3.2",
        "moonshotai/kimi-k2.6", "minimaxai/minimax-m2.5",
        "z-ai/glm5", "openai/gpt-oss-120b",
    ],
    "kimi-coding": [
        "kimi-k2.6", "kimi-k2.5", "kimi-for-coding",
        "kimi-k2-thinking", "kimi-k2-thinking-turbo",
        "kimi-k2-turbo-preview", "kimi-k2-0905-preview",
    ],
    "kimi-coding-cn": [
        "kimi-k2.6", "kimi-k2.5", "kimi-k2-thinking",
        "kimi-k2-turbo-preview", "kimi-k2-0905-preview",
    ],
    "stepfun": ["step-3.5-flash", "step-3.5-flash-2603"],
    "minimax": ["MiniMax-M2.7", "MiniMax-M2.5", "MiniMax-M2.1", "MiniMax-M2"],
    "minimax-cn": ["MiniMax-M2.7", "MiniMax-M2.5", "MiniMax-M2.1", "MiniMax-M2"],
    "anthropic": [
        "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6",
        "claude-opus-4-5-20251101", "claude-sonnet-4-5-20250929",
        "claude-opus-4-20250514", "claude-sonnet-4-20250514",
        "claude-haiku-4-5-20251001",
    ],
    "deepseek": [
        "deepseek-v4-pro", "deepseek-v4-flash",
        "deepseek-chat", "deepseek-reasoner",
    ],
    "xiaomi": [
        "mimo-v2.5-pro", "mimo-v2.5",
        "mimo-v2-pro", "mimo-v2-omni", "mimo-v2-flash",
    ],
    "arcee": [
        "trinity-large-thinking", "trinity-large-preview", "trinity-mini",
    ],
    "opencode-zen": [
        "kimi-k2.5", "gpt-5.4-pro", "gpt-5.4",
        "gpt-5.3-codex", "gpt-5.2", "gpt-5.2-codex",
        "gpt-5.1", "gpt-5.1-codex", "gpt-5.1-codex-max",
        "gpt-5.1-codex-mini", "gpt-5", "gpt-5-codex",
        "gpt-5-nano", "claude-opus-4-6", "claude-opus-4-5",
        "claude-opus-4-1", "claude-sonnet-4-6",
        "claude-sonnet-4-5", "claude-sonnet-4",
        "claude-haiku-4-5", "claude-3-5-haiku",
        "gemini-3.1-pro", "gemini-3-pro", "gemini-3-flash",
        "minimax-m2.7", "minimax-m2.5", "minimax-m2.5-free",
        "minimax-m2.1", "glm-5", "glm-4.7", "glm-4.6",
        "kimi-k2-thinking", "kimi-k2", "qwen3-coder", "big-pickle",
    ],
    "opencode-go": [
        "kimi-k2.6", "kimi-k2.5", "glm-5.1", "glm-5",
        "mimo-v2.5-pro", "mimo-v2.5", "mimo-v2-pro", "mimo-v2-omni",
        "minimax-m2.7", "minimax-m2.5", "qwen3.6-plus", "qwen3.5-plus",
    ],
    "kilocode": [
        "anthropic/claude-opus-4.6", "anthropic/claude-sonnet-4.6",
        "openai/gpt-5.4", "google/gemini-3-pro-preview",
        "google/gemini-3-flash-preview",
    ],
    "alibaba": [
        "kimi-k2.5", "qwen3.5-plus", "qwen3-coder-plus", "qwen3-coder-next",
        "glm-5", "glm-4.7", "MiniMax-M2.5",
    ],
    "huggingface": [
        "moonshotai/Kimi-K2.5", "Qwen/Qwen3.5-397B-A17B",
        "Qwen/Qwen3.5-35B-A3B", "deepseek-ai/DeepSeek-V3.2",
        "MiniMaxAI/MiniMax-M2.5", "zai-org/GLM-5",
        "XiaomiMiMo/MiMo-V2-Flash", "moonshotai/Kimi-K2-Thinking",
        "moonshotai/Kimi-K2.6",
    ],
    "bedrock": [
        "us.anthropic.claude-sonnet-4-6",
        "us.anthropic.claude-opus-4-6-v1",
        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "us.amazon.nova-pro-v1:0", "us.amazon.nova-lite-v1:0",
        "us.amazon.nova-micro-v1:0", "deepseek.v3.2",
        "us.meta.llama4-maverick-17b-instruct-v1:0",
        "us.meta.llama4-scout-17b-instruct-v1:0",
    ],
    "azure-foundry": [],
    # OpenRouter and Vercel AI Gateway — curated subset of popular agentic models.
    "openrouter": [
        "anthropic/claude-sonnet-4-6", "anthropic/claude-opus-4-6",
        "anthropic/claude-haiku-4-5", "openai/gpt-5.4",
        "openai/gpt-5.4-mini", "openai/gpt-4o", "openai/gpt-4o-mini",
        "google/gemini-3-pro-preview", "google/gemini-3-flash-preview",
        "google/gemini-2.5-pro", "google/gemini-2.5-flash",
        "deepseek/deepseek-v4-pro", "deepseek/deepseek-chat",
        "meta-llama/llama-4-maverick", "qwen/qwen3.5-plus",
    ],
    "ai-gateway": [
        "anthropic/claude-sonnet-4-6", "anthropic/claude-haiku-4-5",
        "openai/gpt-5.4", "openai/gpt-5.4-mini", "openai/gpt-4o",
        "google/gemini-3-pro-preview", "google/gemini-3-flash-preview",
        "deepseek/deepseek-chat", "meta-llama/llama-4-maverick",
        "qwen/qwen3.5-plus",
    ],
    "ollama-cloud": [
        "llama3.3:latest", "qwen3:latest", "deepseek-r1:latest",
        "mistral:latest", "gemma3:latest", "phi4:latest",
    ],
    "qwen-oauth": [
        "qwen3.5-plus", "qwen3-coder-plus", "qwq-plus",
    ],
}


# ---------------------------------------------------------------------------
# models.dev live enrichment
# ---------------------------------------------------------------------------

_MODELS_DEV_URL = "https://models.dev/api.json"
_MODELS_DEV_CACHE_TTL = 3600
_DEFAULT_CACHE_DIR = Path("tmp/teamflow")

_models_dev_data: dict[str, Any] = {}
_models_dev_fetch_time: float = 0


def _get_cache_path() -> Path:
    return _DEFAULT_CACHE_DIR / "models_dev_cache.json"


def _load_disk_cache() -> dict[str, Any]:
    try:
        p = _get_cache_path()
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_disk_cache(data: dict[str, Any]) -> None:
    try:
        p = _get_cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def fetch_models_dev(force: bool = False) -> dict[str, Any]:
    """Fetch models.dev registry. Cached in-memory (1hr) + disk fallback.

    Returns the full registry dict, or empty on failure.
    """
    global _models_dev_data, _models_dev_fetch_time

    if not force and _models_dev_data and (time.time() - _models_dev_fetch_time) < _MODELS_DEV_CACHE_TTL:
        return _models_dev_data

    try:
        resp = requests.get(_MODELS_DEV_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data:
            _models_dev_data = data
            _models_dev_fetch_time = time.time()
            _save_disk_cache(data)
            logger.info("已获取 models.dev 数据: %d 个提供商", len(data))
            return data
    except Exception as e:
        logger.debug("获取 models.dev 失败: %s", e)

    if not _models_dev_data:
        _models_dev_data = _load_disk_cache()
        if _models_dev_data:
            _models_dev_fetch_time = time.time()
            logger.info("已从磁盘缓存加载 models.dev 数据")
    return _models_dev_data


def lookup_context_length(provider: str, model: str) -> int | None:
    """Look up context window from models.dev for a provider/model combo."""
    from teamflow.ai.model_registry import PROVIDER_ALIASES as _ALIASES
    mdev_id = _ALIASES.get(provider)
    if not mdev_id:
        pid = resolve_provider(provider)
        mdev_id = pid

    data = fetch_models_dev()
    pdata = data.get(mdev_id, {}) if mdev_id else {}
    if not isinstance(pdata, dict):
        return None

    models = pdata.get("models", {})
    if not isinstance(models, dict):
        return None

    entry = models.get(model) or models.get(model.lower())
    if isinstance(entry, dict):
        limit = entry.get("limit", {})
        if isinstance(limit, dict):
            ctx = limit.get("context", 0)
            if isinstance(ctx, (int, float)) and ctx > 0:
                return int(ctx)
    return None


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------


def list_providers() -> list[str]:
    """Return all canonical provider slugs."""
    return [p.slug for p in CANONICAL_PROVIDERS]


def list_models(provider: str) -> list[str]:
    """Return model IDs for a provider (from static catalog)."""
    pid = resolve_provider(provider)
    if not pid:
        return []
    return _PROVIDER_MODELS.get(pid, [])


def get_model_info(provider: str, model: str) -> ModelInfo | None:
    """Look up model metadata from static catalog first, enrich from models.dev."""
    pid = resolve_provider(provider)
    if not pid:
        return None

    # Build basic info from static catalog
    models = _PROVIDER_MODELS.get(pid, [])
    matched = None
    mlower = model.lower()
    for mid in models:
        if mid == model or mid.lower() == mlower:
            matched = mid
            break

    if matched is None:
        return None

    # Try models.dev enrichment
    ctx = lookup_context_length(pid, matched) or 128_000
    return ModelInfo(
        id=matched,
        provider_id=pid,
        tool_call=True,
        context_window=ctx,
    )


def get_model_capabilities(provider: str, model: str) -> dict[str, bool | int]:
    """Return capability flags for a model."""
    info = get_model_info(provider, model)
    if info is None:
        return {
            "supports_tools": True,
            "supports_reasoning": False,
            "supports_vision": False,
            "context_window": 200_000,
            "max_output": 8_192,
        }
    return {
        "supports_tools": info.tool_call,
        "supports_reasoning": info.reasoning,
        "supports_vision": info.vision,
        "context_window": info.context_window,
        "max_output": info.max_output,
    }


def list_agentic_models(provider: str) -> list[str]:
    """Return model IDs that support tool calling."""
    return list_models(provider)


# ---------------------------------------------------------------------------
# Model resolution helpers
# ---------------------------------------------------------------------------

_ANTHROPIC_MODEL_PATTERN = re.compile(
    r"^claude[ -]|^anthropic\.|^bedrock/.*claude", re.IGNORECASE,
)
_REASONING_EFFORT_PATTERN = re.compile(
    r"^(deepseek|moonshot|kimi)", re.IGNORECASE,
)
_INTERLEAVED_PATTERN = re.compile(
    r"^(deepseek|moonshot|kimi|qwq|o[0-9]+)", re.IGNORECASE,
)


def detect_api_mode(provider: str, model: str) -> str:
    """Detect api_mode from provider entry or model name."""
    entry = get_provider_entry(provider)
    if entry and entry.api_mode:
        return entry.api_mode
    if _ANTHROPIC_MODEL_PATTERN.search(model):
        return "anthropic_messages"
    return "chat_completions"


def supports_reasoning(provider: str, model: str) -> bool:
    """Check if a model supports extended thinking."""
    info = get_model_info(provider, model)
    if info:
        return info.reasoning
    return _REASONING_EFFORT_PATTERN.search(model) is not None


def has_interleaved_thinking(provider: str, model: str) -> bool:
    """Check if model returns reasoning_content interleaved with content."""
    return _INTERLEAVED_PATTERN.search(model) is not None
