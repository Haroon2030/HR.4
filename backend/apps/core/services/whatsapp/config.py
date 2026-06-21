"""Evolution API runtime config — DB settings with env fallback."""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class EvolutionRuntimeConfig:
    whatsapp_enabled: bool
    api_url: str
    api_key: str
    instance_name: str
    source: str  # 'db' | 'env' | ''


def get_evolution_runtime_config() -> EvolutionRuntimeConfig:
    """Prefer saved setup settings; fall back to environment variables."""
    try:
        from apps.setup.models import EvolutionWhatsAppSettings

        obj = EvolutionWhatsAppSettings.get_solo()
        url = (obj.api_url or '').strip().rstrip('/')
        key = (obj.api_key or '').strip()
        instance = (obj.instance_name or '').strip()
        if url and key:
            return EvolutionRuntimeConfig(
                whatsapp_enabled=bool(obj.is_enabled),
                api_url=url,
                api_key=key,
                instance_name=instance,
                source='db',
            )
    except Exception:
        pass

    return EvolutionRuntimeConfig(
        whatsapp_enabled=bool(getattr(settings, 'WHATSAPP_ENABLED', False)),
        api_url=(getattr(settings, 'EVOLUTION_API_URL', '') or '').strip().rstrip('/'),
        api_key=(getattr(settings, 'EVOLUTION_API_KEY', '') or '').strip(),
        instance_name=(getattr(settings, 'EVOLUTION_INSTANCE', '') or '').strip(),
        source='env' if getattr(settings, 'EVOLUTION_API_URL', '') else '',
    )
