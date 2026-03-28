"""
CORTEX Influencer Intelligence Engine -- Phase D, D-4
======================================================

Full two-pass pipeline:
  0. Adjacent niche mapping  -- expand discovery beyond direct niche
  1. Discovery               -- find relevant creators (Exa + DeepSeek scoring)
  2. Video rank              -- score recent videos by recency + title/tags + niche fit
  3. Transcript fetch        -- youtube-transcript-api (free, no key, concurrent)
  3.5 First-pass scan        -- cheap DeepSeek classifier (4 flags + confidence, ~EUR 0.0003/video)
  4. Combined score + select -- metadata score x content score, clickbait penalty applied
  5. Deep extraction         -- full DeepSeek extraction on top N only (~EUR 0.002/video)
  6. Storage                 -- SurfSense with information-dense title encoding
  7. Switching pattern       -- title history scan for praise->criticism pairs

Two pools on the same infrastructure:
  "niche"       : tied to VentureDiscoveryParameters, discovery space in SurfSense
  "core_intel"  : always-on AI/AGI/tech creators, cortex_main space in SurfSense

Cost model per influencer per cycle:
  - Adjacent map:    ~EUR 0.001 (1 DeepSeek, run once per niche)
  - Discovery:       ~EUR 0.002 (2 Exa + 1 DeepSeek)
  - 15 transcripts:  free
  - First-pass scan: ~EUR 0.005 (15 x EUR 0.0003)
  - Deep extract:    ~EUR 0.010 (5 x EUR 0.002)
  - SurfSense:       free (self-hosted)
  Total:            ~EUR 0.015/influencer
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from python.helpers.cortex_discovery_params import (
    InfluencerWatch,
    PainSignal,
    add_influencer,
    load_influencers,
    save_influencers,
)


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VideoCandidate:
    video_id: str
    title: str
    url: str
    published_at: Optional[str] = None
    description: str = ""
    tags: str = ""                        # concatenated tag string from video metadata
    relevance_score: float = 0.0          # updated to combined_score after first-pass scan

    @property
    def age_days(self) -> Optional[int]:
        if not self.published_at:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(self.published_at[:19], fmt[:len(self.published_at[:19])])
                return (datetime.utcnow() - dt).days
            except ValueError:
                continue
        return None


@dataclass
class ExtractedIntelligence:
    pain_signals: List[PainSignal] = field(default_factory=list)
    tools_mentioned: List[str] = field(default_factory=list)
    market_observations: List[str] = field(default_factory=list)
    key_quotes: List[str] = field(default_factory=list)
    summary: str = ""
    creator: str = ""
    video_title: str = ""
    video_url: str = ""
    published_at: str = ""
    niche: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Video Scoring (metadata pass — runs before transcript fetch)
# ─────────────────────────────────────────────────────────────────────────────

_PAIN_TITLE_KEYWORDS = [
    "problem", "mistake", "avoid", "wrong", "truth", "honest",
    "review", "alternative", "instead", "switch", "left", "quit",
    "broken", "failed", "gap", "missing", "overrated", "scam",
    "warning", "don't", "never", "stopped using", "moved to",
]

_OPPORTUNITY_TITLE_KEYWORDS = [
    "opportunity", "untapped", "nobody", "hidden", "underrated",
    "niche", "trend", "growing", "demand", "profitable",
]


def score_video(video: VideoCandidate, niche: str, tags: str = "") -> float:
    """
    Score a video 0-1 on metadata alone (before transcript).
    tags: concatenated tag string — treated as extension of title for keyword scoring.
    Weights: recency 40%, title+tags signals 35%, niche keyword fit 25%.
    """
    # Combine title and tags as scoring text
    scoring_text = (video.title + " " + tags + " " + video.tags).lower()
    niche_words = set(re.findall(r"\w+", niche.lower()))

    # Recency
    age = video.age_days
    if age is None:
        recency = 0.5
    elif age <= 30:
        recency = 1.0
    elif age <= 90:
        recency = 0.85
    elif age <= 180:
        recency = 0.65
    elif age <= 365:
        recency = 0.35
    else:
        recency = 0.1

    # Title + tags signal
    pain_hits = sum(1 for kw in _PAIN_TITLE_KEYWORDS if kw in scoring_text)
    opp_hits = sum(1 for kw in _OPPORTUNITY_TITLE_KEYWORDS if kw in scoring_text)
    title_signal = min(1.0, (pain_hits * 0.15) + (opp_hits * 0.1))

    # Niche keyword overlap
    text_words = set(re.findall(r"\w+", scoring_text))
    common = niche_words & text_words
    niche_fit = min(1.0, len(common) / max(len(niche_words), 1) * 2)

    return round(recency * 0.40 + title_signal * 0.35 + niche_fit * 0.25, 3)


def compute_combined_score(video_score: float, scan_result: Dict[str, Any]) -> float:
    """
    Merge metadata score with first-pass LLM scan result into a final ranking score.

    Weights:
      video_score (recency + title + niche)  35%
      LLM confidence                         30%
      has_specific_pain                      15%
      paying_evidence                        12%
      switching_intent                        8%

    Clickbait penalty: multiply by 0.6 if content_delivers=False.
    Score range: 0.0 - 1.0 (approximately; capped at 1.0 after penalty).
    """
    confidence = max(0.0, min(100.0, float(scan_result.get("confidence", 50)))) / 100.0
    has_pain   = 1.0 if scan_result.get("has_specific_pain") else 0.0
    paying     = 1.0 if scan_result.get("paying_evidence") else 0.0
    switching  = 1.0 if scan_result.get("switching_intent") else 0.0
    delivers   = bool(scan_result.get("content_delivers", True))

    raw = (
        video_score * 0.35
        + confidence * 0.30
        + has_pain   * 0.15
        + paying     * 0.12
        + switching  * 0.08
    )
    return round(min(1.0, raw) * (0.6 if not delivers else 1.0), 3)


# ─────────────────────────────────────────────────────────────────────────────
# Stage 0 -- Adjacent Niche Mapping
# ─────────────────────────────────────────────────────────────────────────────

async def map_adjacent_niches(
    niche: str,
    market: str = "global",
    agent=None,
) -> List[str]:
    """
    Expand discovery beyond the direct niche. Returns 5-7 adjacent communities
    whose members experience the same pain points or are directly connected.

    Examples for "restaurant SEO services":
      -> local marketing agencies, restaurant consultants, POS system users,
         hospitality groups, food bloggers who run local businesses

    Cost: ~EUR 0.001 (one DeepSeek classification call). Run once per niche.
    Falls back to empty list if unavailable -- discovery continues with direct niche.
    """
    try:
        from python.helpers.cortex_model_router import CortexModelRouter
        from python.helpers.dirty_json import DirtyJson

        prompt = (
            f"Niche: '{niche}' | Market: {market}\n\n"
            "List 5-7 adjacent communities, roles, or industries whose members "
            "experience similar pain points or are directly connected to this niche. "
            "Think: who buys from this niche, who serves them, who has tried and failed "
            "here, what other industries overlap or feed into it.\n"
            "Return a JSON array of short strings (5-8 words each). JSON only:\n"
            "[\"adjacent community 1\", \"adjacent community 2\", ...]"
        )

        raw = await CortexModelRouter.call_routed_model(
            "classification",
            "You are a market analyst. Identify adjacent communities. JSON array only.",
            prompt,
            agent,
        )
        parsed = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, list):
            return [str(x) for x in parsed if isinstance(x, str) and len(x) < 80][:7]
        return []

    except Exception as e:
        print(f"[CORTEX influencer_monitor] Adjacent niche mapping failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 -- Influencer Discovery
# ─────────────────────────────────────────────────────────────────────────────

async def discover_influencers_for_niche(
    niche: str,
    market: str = "global",
    limit: int = 8,
    agent=None,
) -> List[InfluencerWatch]:
    """
    Find relevant YouTube/Substack creators using Exa + adjacent niches.
    DeepSeek scores each for: niche fit, trailblazing quality, cross-platform
    credibility signals visible in Exa snippets (LinkedIn mentions, peer citations).

    Returns ranked InfluencerWatch list (NOT yet saved to watchlist).
    Cost: ~EUR 0.003 (adjacent map + 2 Exa searches + 1 DeepSeek scoring call).
    """
    try:
        from python.helpers.cortex_exa_client import CortexExaClient
        from python.helpers.cortex_model_router import CortexModelRouter
        from python.helpers.dirty_json import DirtyJson

        exa_key = (
            getattr(getattr(agent, "config", None), "exa_api_key", "")
            or os.getenv("EXA_API_KEY", "")
        )
        exa = CortexExaClient(api_key=exa_key)

        # Map adjacent niches first
        adjacent = await map_adjacent_niches(niche, market, agent)
        adjacent_query = adjacent[0] if adjacent else ""

        # Two Exa queries: direct niche + top adjacent niche
        results_direct = await exa.search(
            f"{niche} {market} YouTube creator channel review problems 2025",
            num_results=min(limit * 2, 12),
            use_autoprompt=True,
        )

        results_adjacent: list = []
        if adjacent_query:
            results_adjacent = await exa.search(
                f"{adjacent_query} {market} YouTube creator channel problems pain 2025",
                num_results=6,
                use_autoprompt=True,
            )

        all_results = results_direct + results_adjacent
        if not all_results:
            return []

        snippets = "\n".join(
            f"{i+1}. [{'adjacent' if i >= len(results_direct) else 'direct'}] "
            f"URL: {r.url} | Title: {r.title} | Snippet: {r.content[:200]}"
            for i, r in enumerate(all_results[:18])
        )

        prompt = (
            f"Niche: '{niche}' | Market: {market}\n"
            f"Adjacent niches also relevant: {', '.join(adjacent[:3]) if adjacent else 'none'}\n\n"
            f"Search results:\n{snippets}\n\n"
            "Identify YouTube/Substack/newsletter creators who regularly discuss problems, "
            "gaps, and opportunities in this niche or adjacent niches. "
            "EXCLUDE: product landing pages, generic how-to channels, brand accounts.\n"
            "PREFER creators with: cross-platform presence (LinkedIn, Twitter cited in snippet), "
            "peer citations ('recommended by', 'as seen on'), practitioner credentials, "
            "consistent niche focus.\n"
            "For each valid creator found, return JSON array:\n"
            "[\n"
            '  {"handle": "@channelname or author name",\n'
            '   "platform": "youtube" | "substack" | "twitter",\n'
            '   "channel_url": "full URL",\n'
            '   "relevance_score": 0-100,\n'
            '   "credibility_note": "cross-platform or peer signals found",\n'
            '   "pool": "niche" | "core_intel"\n'
            '  }\n'
            "]\n"
            "Return [] if no valid creators found. JSON only."
        )

        raw = await CortexModelRouter.call_routed_model(
            "classification",
            "You are an influencer analyst identifying credible niche creators. JSON only.",
            prompt,
            agent,
        )

        parsed = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw
        if not isinstance(parsed, list):
            return []

        influencers = []
        for item in sorted(parsed, key=lambda x: float(x.get("relevance_score", 0)), reverse=True):
            if not item.get("channel_url"):
                continue
            if float(item.get("relevance_score", 0)) < 40:
                continue
            # For core_intel pool creators, use the declared niche or infer from URL
            creator_niche = niche if item.get("pool", "niche") == "niche" else "core_intel_ai"
            influencers.append(InfluencerWatch(
                platform=item.get("platform", "youtube"),
                handle=item.get("handle", ""),
                channel_url=item.get("channel_url", ""),
                niche=creator_niche,
            ))

        return influencers[:limit]

    except Exception as e:
        print(f"[CORTEX influencer_monitor] Discovery error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 -- Video Listing + Ranking (metadata pass)
# ─────────────────────────────────────────────────────────────────────────────

async def get_recent_relevant_videos(
    influencer: InfluencerWatch,
    niche: str,
    max_age_days: int = 180,
    top_n: int = 15,          # bumped from 5 — first-pass scan selects the best
    agent=None,
) -> List[VideoCandidate]:
    """
    Find recent, niche-relevant videos for an influencer using Exa.
    Returns top_n candidates ordered by metadata score only.
    Combined score (metadata + first-pass scan) is applied in process_influencer().
    """
    try:
        from python.helpers.cortex_exa_client import CortexExaClient

        exa_key = (
            getattr(getattr(agent, "config", None), "exa_api_key", "")
            or os.getenv("EXA_API_KEY", "")
        )
        exa = CortexExaClient(api_key=exa_key)

        handle = influencer.handle.lstrip("@") if influencer.handle else ""
        channel_domain = "site:youtube.com" if "youtube" in influencer.channel_url.lower() else ""

        query_parts = [channel_domain] if channel_domain else []
        if handle:
            query_parts.append(f'"{handle}"')
        query_parts.append(niche)
        query_parts.append("problem OR review OR alternative OR pain 2024 OR 2025")

        cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
        results = await exa.search(
            " ".join(query_parts),
            num_results=min(top_n * 2, 20),
            use_autoprompt=False,
            start_published_date=cutoff,
        )

        candidates: List[VideoCandidate] = []
        for r in results:
            video_id = _extract_video_id(r.url)
            if not video_id and "youtube.com" in r.url.lower():
                continue

            # Tags: sometimes present in Exa content field as comma-separated list after main text
            tags = _extract_tags_from_content(r.content or "")

            candidate = VideoCandidate(
                video_id=video_id or "",
                title=r.title,
                url=r.url,
                published_at=getattr(r, "published_date", None),
                description=(r.content or "")[:300],
                tags=tags,
            )
            candidate.relevance_score = score_video(candidate, niche, tags)
            candidates.append(candidate)

        # Dedup against last processed
        if influencer.last_video_id:
            candidates = [c for c in candidates if c.video_id != influencer.last_video_id]

        candidates.sort(key=lambda c: c.relevance_score, reverse=True)
        return candidates[:top_n]

    except Exception as e:
        print(f"[CORTEX influencer_monitor] Video listing error ({influencer.handle}): {e}")
        return []


def _extract_tags_from_content(content: str) -> str:
    """
    Try to extract YouTube tags from Exa content field.
    Tags sometimes appear as comma-separated text near the end of the content snippet.
    Returns empty string if not found -- always safe to ignore.
    """
    # Look for comma-dense short phrases (typical tag format)
    lines = content.split("\n")
    for line in reversed(lines[-5:]):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3 and all(len(p) < 30 for p in parts):
            return line.strip()
    return ""


def _extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2.5 -- Switching Signal Pattern Detection
# ─────────────────────────────────────────────────────────────────────────────

async def detect_switching_pattern(
    influencer: InfluencerWatch,
    niche: str,
    agent=None,
) -> Optional[Dict[str, str]]:
    """
    Scan the creator's title history (without date filter) to detect the
    praise->criticism switching pattern: "Best [tool] 2022" → "Why I quit [tool] 2024".

    These pairs are the highest-signal content: they document a complete journey
    from adoption to abandonment -- exactly the switching intent we're looking for.

    Returns: {"positive_title": str, "negative_title": str, "tool": str, "signal": str}
    or None if no pattern found.
    Cost: ~EUR 0.001 (1 Exa + 1 DeepSeek).
    """
    try:
        from python.helpers.cortex_exa_client import CortexExaClient
        from python.helpers.cortex_model_router import CortexModelRouter
        from python.helpers.dirty_json import DirtyJson

        exa_key = os.getenv("EXA_API_KEY", "")
        exa = CortexExaClient(api_key=exa_key)

        handle = influencer.handle.lstrip("@") if influencer.handle else ""
        if not handle:
            return None

        # Fetch without date filter to see longer history
        results = await exa.search(
            f'site:youtube.com "{handle}" {niche}',
            num_results=20,
            use_autoprompt=False,
        )

        if len(results) < 3:
            return None

        title_list = "\n".join(
            f"- [{getattr(r, 'published_date', 'unknown')}] {r.title}"
            for r in results
        )

        prompt = (
            f"Creator: {handle} | Niche: {niche}\n\n"
            f"Video title history:\n{title_list}\n\n"
            "Do any of these titles form a switching pattern? "
            "A switching pattern = the creator first endorsed something "
            "(tutorial, 'best X', 'how to use X') and later criticized it "
            "('why I quit X', 'stopped using X', 'moved away from X', 'honest review').\n"
            "If found, return JSON:\n"
            '{"found": true, "positive_title": "...", "negative_title": "...", '
            '"tool": "tool or topic name", "signal": "1 sentence"}\n'
            "If not found: {\"found\": false}"
        )

        raw = await CortexModelRouter.call_routed_model(
            "classification",
            "You are analyzing a creator's video history for switching patterns. JSON only.",
            prompt,
            agent,
        )
        parsed = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, dict) and parsed.get("found"):
            return parsed
        return None

    except Exception as e:
        print(f"[CORTEX influencer_monitor] Switching pattern detection error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 -- Transcript Fetching
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_youtube_transcript(
    video_url_or_id: str,
    preferred_languages: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Fetch transcript for a YouTube video (free, no API key).
    Prefers manual transcripts over auto-generated.
    Falls back gracefully -- returns None if unavailable.
    """
    if preferred_languages is None:
        preferred_languages = ["en", "en-US", "en-GB"]

    video_id = _extract_video_id(video_url_or_id) or video_url_or_id.strip()
    if not video_id or len(video_id) != 11:
        return None

    try:
        from youtube_transcript_api import (
            YouTubeTranscriptApi,
            TranscriptsDisabled,
            NoTranscriptFound,
        )

        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        transcript = None
        try:
            transcript = transcript_list.find_manually_created_transcript(preferred_languages)
        except Exception:
            pass
        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(preferred_languages)
            except Exception:
                pass
        if transcript is None:
            try:
                transcript = next(iter(transcript_list), None)
            except Exception:
                pass

        if not transcript:
            return None

        chunks = transcript.fetch()
        text = " ".join(chunk["text"] for chunk in chunks)
        text = re.sub(r"\[.*?\]", "", text)      # remove [Music], [Applause]
        text = re.sub(r"\s+", " ", text).strip()

        # Quality check: skip if transcript is too short or mostly artifacts
        if len(text) < 200:
            return None
        music_ratio = text.lower().count("[") / max(len(text), 1)
        if music_ratio > 0.05:
            return None

        return text

    except (ImportError, Exception) as e:
        if "ImportError" in type(e).__name__ or "No module" in str(e):
            print("[CORTEX influencer_monitor] youtube-transcript-api not installed. "
                  "Run: pip install youtube-transcript-api")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3.5 -- First-Pass Classifier (cheap scan before full extraction)
# ─────────────────────────────────────────────────────────────────────────────

async def quick_scan_video(
    title: str,
    transcript_start: str,
    niche: str,
    agent=None,
) -> Dict[str, Any]:
    """
    First-pass classifier. Runs on the first 1,500 chars of each transcript.
    Cost: ~EUR 0.0003 per video (cheapest DeepSeek model via classification route).

    Returns dict with 4 binary flags + confidence score:
      has_specific_pain  -- specific, verifiable pain (not vague complaints)
      paying_evidence    -- people paying for something that fails them
      switching_intent   -- mentions alternatives, actively leaving something
      content_delivers   -- content matches title promise (anti-clickbait)
      confidence         -- 0-100 overall niche relevance
      signal             -- 1 sentence: why relevant or not

    These feed into compute_combined_score() for final ranking.
    """
    try:
        from python.helpers.cortex_model_router import CortexModelRouter
        from python.helpers.dirty_json import DirtyJson

        prompt = (
            f"Video title: '{title}'\n"
            f"Niche: '{niche}'\n"
            f"Transcript (first 1500 chars):\n{transcript_start[:1500]}\n\n"
            "Classify this video content for venture discovery. JSON only:\n"
            "{\n"
            '  "has_specific_pain": true/false,\n'
            '  "paying_evidence": true/false,\n'
            '  "switching_intent": true/false,\n'
            '  "content_delivers": true/false,\n'
            '  "confidence": 0-100,\n'
            '  "signal": "1 sentence"\n'
            "}\n"
            "has_specific_pain: specific verifiable pain, not vague ('agencies give bad results' "
            "not 'SEO is hard').\n"
            "paying_evidence: people paying for something that fails them.\n"
            "switching_intent: mentions alternatives, actively looking to leave.\n"
            "content_delivers: first 1500 chars contain actual substance, not just intro filler."
        )

        raw = await CortexModelRouter.call_routed_model(
            "classification",
            "You are classifying video content for venture pain signal discovery. JSON only.",
            prompt,
            agent,
        )
        parsed = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, dict):
            return {
                "has_specific_pain": bool(parsed.get("has_specific_pain", False)),
                "paying_evidence":   bool(parsed.get("paying_evidence", False)),
                "switching_intent":  bool(parsed.get("switching_intent", False)),
                "content_delivers":  bool(parsed.get("content_delivers", True)),
                "confidence":        max(0, min(100, int(parsed.get("confidence", 30)))),
                "signal":            str(parsed.get("signal", "")),
            }
    except Exception as e:
        print(f"[CORTEX influencer_monitor] Quick scan error ({title[:40]}): {e}")

    # Fallback: neutral scan result — video stays in pool but won't be boosted
    return {
        "has_specific_pain": False,
        "paying_evidence": False,
        "switching_intent": False,
        "content_delivers": True,
        "confidence": 30,
        "signal": "scan unavailable",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 -- Deep Extraction (runs only on top-ranked videos after combined score)
# ─────────────────────────────────────────────────────────────────────────────

_TRANSCRIPT_CHUNK = 6000


async def extract_intelligence(
    transcript: str,
    niche: str,
    creator_name: str,
    video_title: str,
    video_url: str = "",
    published_at: str = "",
    agent=None,
) -> ExtractedIntelligence:
    """
    Full extraction from transcript. Cost: ~EUR 0.002.
    Runs only on videos that passed the first-pass combined score threshold.
    """
    from python.helpers.cortex_model_router import CortexModelRouter
    from python.helpers.dirty_json import DirtyJson

    chunk = transcript[:_TRANSCRIPT_CHUNK]

    prompt = (
        f"Creator: '{creator_name}' | Video: '{video_title}' | Niche: '{niche}'\n\n"
        f"Transcript:\n{chunk}\n\n"
        "Extract (JSON only):\n"
        "{\n"
        '  "pain_signals": [\n'
        '    {"pain": "1-sentence specific pain", '
        '"paying_evidence": true/false, '
        '"strength": 1-3, '
        '"tool_mentioned": "tool name or null"}\n'
        "  ],\n"
        '  "tools_mentioned": ["tool or product names"],\n'
        '  "market_observations": ["market facts, trends, sizing"],\n'
        '  "key_quotes": ["verbatim insightful quotes (max 3)"],\n'
        '  "summary": "2-3 sentences for venture discovery"\n'
        "}\n"
        "strength: 1=mentioned, 2=clear complaint, 3=actively switching/leaving."
    )

    result = ExtractedIntelligence(
        creator=creator_name,
        video_title=video_title,
        video_url=video_url,
        published_at=published_at,
        niche=niche,
    )

    try:
        raw = await CortexModelRouter.call_routed_model(
            "classification",
            "You are a venture intelligence analyst extracting structured insights. JSON only.",
            prompt,
            agent,
        )
        parsed = DirtyJson.parse_string(raw) if isinstance(raw, str) else raw

        for item in parsed.get("pain_signals", []):
            result.pain_signals.append(PainSignal(
                source=f"youtube:{creator_name}",
                source_url=video_url,
                raw_text=f"{video_title}: {item.get('pain', '')}",
                extracted_pain=item.get("pain", ""),
                tool_mentioned=item.get("tool_mentioned"),
                paying_evidence=bool(item.get("paying_evidence", False)),
                strength=int(item.get("strength", 1)),
            ))
        result.tools_mentioned = parsed.get("tools_mentioned", [])
        result.market_observations = parsed.get("market_observations", [])
        result.key_quotes = parsed.get("key_quotes", [])
        result.summary = parsed.get("summary", "")

    except Exception as e:
        print(f"[CORTEX influencer_monitor] Extraction error ({video_title[:50]}): {e}")
        result.pain_signals = [PainSignal(
            source=f"youtube:{creator_name}",
            source_url=video_url,
            raw_text=video_title,
            extracted_pain=f"Video by {creator_name}: {video_title}",
            paying_evidence=False,
            strength=1,
        )]
        result.summary = f"Video '{video_title}' by {creator_name} (extraction failed)"

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Stage 5 -- SurfSense Storage
# ─────────────────────────────────────────────────────────────────────────────

_CORE_INTEL_KEYWORDS = [
    "ai", "artificial intelligence", "agi", "llm", "autonomous agent",
    "large language model", "machine learning", "automation", "robotics",
    "neural", "foundation model", "generative ai", "core_intel",
]


def _resolve_space(niche: str) -> str:
    niche_lower = niche.lower()
    if any(kw in niche_lower for kw in _CORE_INTEL_KEYWORDS):
        return "cortex_main"
    return "discovery"


def _build_surfsense_title(
    intelligence: ExtractedIntelligence,
    video: VideoCandidate,
) -> str:
    """
    Information-dense title — the only metadata field SurfSense allows.
    Format: [Creator] | [Video Title] | [YYYY-MM] | [Niche] | [N signals (X paying)] | tools: ...
    """
    date_part = (video.published_at or intelligence.published_at or "")[:7]
    pain_count = len(intelligence.pain_signals)
    paying = sum(1 for s in intelligence.pain_signals if s.paying_evidence)

    parts = [intelligence.creator, intelligence.video_title[:100]]
    if date_part:
        parts.append(date_part)
    parts.append(intelligence.niche[:60])
    parts.append(f"{pain_count} signals ({paying} paying)")
    if intelligence.tools_mentioned:
        parts.append("tools: " + ", ".join(intelligence.tools_mentioned[:4]))

    return " | ".join(parts)


async def publish_to_surfsense(
    intelligence: ExtractedIntelligence,
    video: VideoCandidate,
    agent=None,
) -> bool:
    """Store extracted intelligence to SurfSense. Space auto-routed by niche."""
    try:
        from python.helpers.cortex_surfsense_client import CortexSurfSenseClient

        space = _resolve_space(intelligence.niche)
        title = _build_surfsense_title(intelligence, video)

        sections = [
            f"# {intelligence.video_title}",
            f"**Creator:** {intelligence.creator}",
            f"**Published:** {intelligence.published_at or 'Unknown'}",
            f"**URL:** {intelligence.video_url}",
            f"**Niche:** {intelligence.niche}",
            "",
            "## Summary",
            intelligence.summary,
            "",
        ]
        if intelligence.pain_signals:
            sections.append("## Pain Signals")
            for s in intelligence.pain_signals:
                paying = " [PAYING]" if s.paying_evidence else ""
                sections.append(f"- (strength {s.strength}){paying} {s.extracted_pain}")
            sections.append("")
        if intelligence.tools_mentioned:
            sections += ["## Tools / Competitors", ", ".join(intelligence.tools_mentioned), ""]
        if intelligence.market_observations:
            sections.append("## Market Observations")
            sections += [f"- {o}" for o in intelligence.market_observations]
            sections.append("")
        if intelligence.key_quotes:
            sections.append("## Key Quotes")
            sections += [f'> "{q}"' for q in intelligence.key_quotes]
            sections.append("")

        content = "\n".join(sections)

        client = CortexSurfSenseClient.from_agent_config(agent) if agent else None
        if client is None or not client.is_configured():
            jwt = os.getenv("SURFSENSE_JWT", "")
            api_url = os.getenv("SURFSENSE_API_URL", "")
            if not jwt or not api_url:
                return False
            client = CortexSurfSenseClient(api_url=api_url, jwt_token=jwt)

        await client.push_document(space, {
            "title": title,
            "content": content,
            "metadata": {"source_url": intelligence.video_url},
        })
        print(f"[CORTEX influencer_monitor] Stored [{space}]: {title[:80]}")
        return True

    except Exception as e:
        print(f"[CORTEX influencer_monitor] SurfSense error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Stage 6 -- Full Two-Pass Pipeline per Influencer
# ─────────────────────────────────────────────────────────────────────────────

async def process_influencer(
    influencer: InfluencerWatch,
    niche: str,
    market: str = "global",
    max_videos: int = 5,
    max_age_days: int = 180,
    agent=None,
) -> List[PainSignal]:
    """
    Two-pass full pipeline for one influencer:
      Pass 1 -- fetch up to 15 videos + transcripts (free), quick scan all (~EUR 0.005)
      Pass 2 -- deep extract top max_videos by combined score (~EUR 0.010)

    Also runs switching pattern detection on title history.
    Updates influencer.last_video_id + last_checked.
    Returns all PainSignal objects extracted.
    """
    all_signals: List[PainSignal] = []

    # Get candidate videos (metadata score only at this point)
    videos = await get_recent_relevant_videos(
        influencer, niche, max_age_days=max_age_days,
        top_n=15, agent=agent,
    )

    if not videos:
        print(f"[CORTEX influencer_monitor] No new videos for {influencer.handle}")
        influencer.last_checked = datetime.utcnow().isoformat()
        return []

    # Switching pattern detection (non-blocking, runs in background of first pass)
    switching = await detect_switching_pattern(influencer, niche, agent)
    if switching:
        print(
            f"[CORTEX influencer_monitor] Switching pattern found for {influencer.handle}: "
            f"{switching.get('signal', '')}"
        )

    print(f"[CORTEX influencer_monitor] {influencer.handle}: "
          f"first-pass scanning {len(videos)} videos")

    # --- PASS 1: Fetch all transcripts (free) + quick scan ---
    ranked: List[Tuple[VideoCandidate, str, Dict]] = []

    for video in videos:
        transcript: str = ""
        if video.video_id:
            fetched = await fetch_youtube_transcript(video.url)
            if fetched:
                transcript = fetched
        if not transcript:
            transcript = f"{video.title}. {video.description}"

        scan = await quick_scan_video(video.title, transcript[:1500], niche, agent)
        combined = compute_combined_score(video.relevance_score, scan)
        video.relevance_score = combined
        ranked.append((video, transcript, scan))

    # Sort by combined score
    ranked.sort(key=lambda x: x[0].relevance_score, reverse=True)

    # Log first-pass results
    top_signals = [(v.title[:50], f"{v.relevance_score:.2f}") for v, _, _ in ranked[:5]]
    print(f"[CORTEX influencer_monitor] Top 5 after first-pass: {top_signals}")

    # --- PASS 2: Deep extract top max_videos ---
    newest_video_id: Optional[str] = None

    for video, transcript, scan in ranked[:max_videos]:
        try:
            intelligence = await extract_intelligence(
                transcript=transcript,
                niche=niche,
                creator_name=influencer.handle or influencer.channel_url,
                video_title=video.title,
                video_url=video.url,
                published_at=video.published_at or "",
                agent=agent,
            )
            all_signals.extend(intelligence.pain_signals)
            await publish_to_surfsense(intelligence, video, agent)

            if newest_video_id is None and video.video_id:
                newest_video_id = video.video_id

        except Exception as e:
            print(f"[CORTEX influencer_monitor] Deep extract error ({video.title[:40]}): {e}")
            continue

    # Update state
    if newest_video_id:
        influencer.last_video_id = newest_video_id
    influencer.last_checked = datetime.utcnow().isoformat()

    print(
        f"[CORTEX influencer_monitor] {influencer.handle}: "
        f"{len(all_signals)} signals from {min(max_videos, len(ranked))} deep-extracted videos "
        f"(scanned {len(videos)} total)"
    )
    return all_signals


# ─────────────────────────────────────────────────────────────────────────────
# Monitoring Cycle
# ─────────────────────────────────────────────────────────────────────────────

async def run_monitoring_cycle(
    niche: Optional[str] = None,
    market: str = "global",
    max_videos_per_influencer: int = 3,
    max_age_days: int = 180,
    agent=None,
) -> Dict[str, List[PainSignal]]:
    """
    Process all active watched influencers. Updates watchlist on disk.
    Returns {handle: [PainSignal]} dict.
    """
    influencers = [i for i in load_influencers() if i.active]

    if niche:
        influencers = [
            i for i in influencers
            if i.niche == niche or any(kw in i.niche.lower() for kw in _CORE_INTEL_KEYWORDS)
        ]

    if not influencers:
        print(f"[CORTEX influencer_monitor] No active influencers to monitor")
        return {}

    results: Dict[str, List[PainSignal]] = {}
    updated = list(load_influencers())

    for influencer in influencers:
        signals = await process_influencer(
            influencer, niche=influencer.niche, market=market,
            max_videos=max_videos_per_influencer,
            max_age_days=max_age_days, agent=agent,
        )
        results[influencer.handle or influencer.channel_url] = signals
        for i, iw in enumerate(updated):
            if iw.id == influencer.id:
                updated[i] = influencer
                break

    save_influencers(updated)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# User-Facing API
# ─────────────────────────────────────────────────────────────────────────────

def add_to_watchlist(
    channel_url: str,
    niche: str,
    handle: str = "",
    platform: str = "youtube",
) -> InfluencerWatch:
    """
    Add a creator to the permanent watchlist. Deduplicates by channel_url.
    For core intelligence pool: use niche containing AI/AGI keywords
    (e.g. "core_intel_ai") -- auto-routes to cortex_main SurfSense space.
    """
    iw = InfluencerWatch(
        platform=platform,
        handle=handle or channel_url,
        channel_url=channel_url,
        niche=niche,
    )
    add_influencer(iw)
    print(f"[CORTEX influencer_monitor] Added to watchlist: {handle or channel_url} [{niche}]")
    return iw


_CORE_INTEL_SEED: List[Tuple[str, str, str]] = [
    # (handle, channel_url, niche)
    # User-configured via add_to_watchlist() -- examples only:
    # ("@lexfridman", "https://youtube.com/@lexfridman", "core_intel_ai"),
]


def seed_core_intel_watchlist() -> None:
    """Add core intelligence creators to watchlist if not already present."""
    existing_urls = {i.channel_url for i in load_influencers()}
    for handle, url, niche in _CORE_INTEL_SEED:
        if url not in existing_urls:
            add_to_watchlist(url, niche=niche, handle=handle, platform="youtube")
