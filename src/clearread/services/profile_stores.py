"""Every per-profile store, opened inside one account's folder (v1.6)."""

from dataclasses import dataclass
from pathlib import Path

from clearread.core.config import AppConfig
from clearread.services.ai_client import DiskResponseCache
from clearread.services.document_library import DocumentLibrary
from clearread.services.glossary import GlossaryStore
from clearread.services.groups import GroupStore
from clearread.services.reading_stats import StatsStore

CACHE_DIR_NAME = "cache"
AI_CACHE_FILE = "ai_cache.json"
GLOSSARY_FILE = "glossary.json"
STATS_FILE = "stats.json"
FOLDERS_FILE = "folders.json"
TOPICS_FILE = "topics.json"


@dataclass(frozen=True)
class ProfileStores:
    directory: Path
    config: AppConfig
    glossary: GlossaryStore
    topics: GroupStore
    folders: GroupStore
    stats: StatsStore
    library: DocumentLibrary
    ai_cache: DiskResponseCache


def open_profile_stores(profile_dir: Path) -> ProfileStores:
    return ProfileStores(
        directory=profile_dir,
        config=AppConfig.load(profile_dir),
        glossary=GlossaryStore(profile_dir / GLOSSARY_FILE),
        topics=GroupStore(profile_dir / TOPICS_FILE),
        folders=GroupStore(profile_dir / FOLDERS_FILE),
        stats=StatsStore(profile_dir / STATS_FILE),
        library=DocumentLibrary(profile_dir / CACHE_DIR_NAME),
        ai_cache=DiskResponseCache(profile_dir / AI_CACHE_FILE),
    )
