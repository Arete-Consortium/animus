"""
Lugh external-source adapters.

This subpackage extends Lugh beyond GitHub repos + Claude Code transcripts
to ingest research papers, podcasts, HN, and AI-news feeds. Each adapter
produces `SourceItem`s which are deduped into `SourceCache` and optionally
scored for relevance against the user's portfolio.

v1 scope:
    arxiv    — per-category RSS feeds
    hn       — HN Algolia API
    podcasts — config-driven RSS subscriber
    youtube  — channel subscriber via yt-dlp auto-captions
    mer      — EVE Online Monthly Economic Report availability tracker

v2 (not yet wired):
    Supported Core memory write path, MCP tool surface, cron integration.
"""

from __future__ import annotations

from animus.lugh.sources.arxiv import ArxivSource
from animus.lugh.sources.arxiv import default_sources as default_arxiv_sources
from animus.lugh.sources.base import Scorer, Source, SourceCache, SourceItem
from animus.lugh.sources.hn import HackerNewsSource
from animus.lugh.sources.hn import default_sources as default_hn_sources
from animus.lugh.sources.mer import MERSource, default_mer_sources
from animus.lugh.sources.podcasts import PodcastSource, probe_feed
from animus.lugh.sources.registry import (
    add_podcast,
    add_youtube,
    default_registry,
    instantiate,
    load_registry,
    remove_source,
    save_registry,
)
from animus.lugh.sources.relevance import DEFAULT_KEYWORDS, KeywordScorer, default_scorer
from animus.lugh.sources.rss import FeedEntry, fetch_feed, parse_feed
from animus.lugh.sources.youtube import (
    DEFAULT_CHANNELS,
    YouTubeSource,
    clean_vtt,
    default_youtube_sources,
    probe_channel,
)

__all__ = [
    # sources
    "ArxivSource",
    "HackerNewsSource",
    "MERSource",
    "PodcastSource",
    "YouTubeSource",
    "default_arxiv_sources",
    "default_hn_sources",
    "default_mer_sources",
    "default_youtube_sources",
    # base
    "FeedEntry",
    "Scorer",
    "Source",
    "SourceCache",
    "SourceItem",
    # RSS
    "fetch_feed",
    "parse_feed",
    # youtube
    "DEFAULT_CHANNELS",
    "clean_vtt",
    "probe_channel",
    # registry
    "add_podcast",
    "add_youtube",
    "default_registry",
    "instantiate",
    "load_registry",
    "probe_feed",
    "remove_source",
    "save_registry",
    # relevance
    "DEFAULT_KEYWORDS",
    "KeywordScorer",
    "default_scorer",
]
