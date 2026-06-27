import os
import json
import re
import time
import html
from urllib.parse import urlparse
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static", html=True), name="static")

@app.get("/")
def read_index():
    return FileResponse("static/index.html")

# OpenAI configuration for GPT-4 (or change model if needed)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable not set")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
SOURCE_PROFILES_PATH = "source_profiles.json"
RESEARCH_CACHE_PATH = "research_cache.json"
RESEARCH_CACHE_TTL_SECONDS = int(os.getenv("RESEARCH_CACHE_TTL_SECONDS", str(7 * 24 * 60 * 60)))
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")
RESEARCH_HTTP_HEADERS = {
    "User-Agent": "PhilosopherChatSimulator/1.0 (local research; contact: local-dev@example.com)"
}
TRUSTED_RESEARCH_DOMAINS = {
    "plato.stanford.edu": "sep",
    "iep.utm.edu": "iep",
    "www.gutenberg.org": "gutenberg",
    "gutenberg.org": "gutenberg",
    "en.wikipedia.org": "wikipedia",
    "en.wikisource.org": "wikisource",
}
MAX_TARGETED_FETCHES = int(os.getenv("MAX_TARGETED_FETCHES", "4"))
SOURCE_PROFILES = {}
RESEARCH_CACHE = {}

try:
    with open(SOURCE_PROFILES_PATH, "r", encoding="utf-8") as source_file:
        SOURCE_PROFILES = json.load(source_file)
except FileNotFoundError:
    SOURCE_PROFILES = {}

try:
    with open(RESEARCH_CACHE_PATH, "r", encoding="utf-8") as cache_file:
        RESEARCH_CACHE = json.load(cache_file)
except FileNotFoundError:
    RESEARCH_CACHE = {}

# Pydantic models for input and output.
class Message(BaseModel):
    speaker: Optional[str] = None  # Default speaker if not provided.
    content: str

class GenerateRequest(BaseModel):
    personality: str         # The philosopher's personality prompt.
    conversation: List[Message]  # The conversation history (ordered list of messages).
    phase: Optional[str] = "debate"  # "opening" for initial stance; "debate" for further responses.
    topic: Optional[str] = None  # The original topic for context.

class GenerateResponse(BaseModel):
    generated_text: str

class Participant(BaseModel):
    name: str
    prompt: str

class DebateRoundRequest(BaseModel):
    topic: str
    participants: List[Participant]
    conversation: List[Message]
    debate_state: Optional[Dict[str, Any]] = None
    phase: Optional[str] = "debate"
    max_speakers: Optional[int] = 3

class DebateMessage(BaseModel):
    speaker: str
    content: str
    intent: Optional[str] = None

class DebateRoundResponse(BaseModel):
    messages: List[DebateMessage]
    debate_state: Dict[str, Any]
    plan: List[Dict[str, Any]]

class SpeakerMemory(BaseModel):
    stance: Optional[str] = ""
    previous_points: List[str] = []
    concessions: List[str] = []
    open_targets: List[str] = []

class RespondRequest(BaseModel):
    topic: str
    speaker: str
    personality: str
    phase: Optional[str] = "continue"
    conversation: List[Message]
    memory: Optional[SpeakerMemory] = None
    source_notes: Optional[List[str]] = []

class RespondResponse(BaseModel):
    speaker: str
    generated_text: str
    updated_memory: SpeakerMemory
    source_notes_used: List[str] = []

class ResearchRequest(BaseModel):
    speaker: str
    topic: str
    conversation: Optional[List[Message]] = []

class ResearchResponse(BaseModel):
    speaker: str
    topic: str
    notes: List[str]
    sources: List[Dict[str, str]]
    cached: bool

def call_openai(messages, max_tokens=500, temperature=0.7):
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 0.95,
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=45)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request error: {str(e)}")

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    result = response.json()
    if "choices" not in result or not result["choices"]:
        raise HTTPException(status_code=500, detail="Unexpected response from OpenAI API")

    return result["choices"][0]["message"]["content"].strip()

def parse_json_object(text, fallback):
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return fallback
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return fallback

def normalize_conversation(conversation):
    lines = []
    for msg in conversation[-30:]:
        speaker = (msg.speaker or "User").strip() or "User"
        lines.append(f"{speaker}: {msg.content}")
    return "\n".join(lines)

def format_transcript_for_response(conversation):
    if len(conversation) <= 30:
        selected = conversation
        prefix = ""
    else:
        selected = conversation[-30:]
        prefix = "[Earlier messages are represented in the speaker memory. Recent transcript follows.]\n"

    lines = []
    for index, msg in enumerate(selected, start=max(1, len(conversation) - len(selected) + 1)):
        speaker = (msg.speaker or "Unknown").strip() or "Unknown"
        lines.append(f"{index}. {speaker}: {msg.content}")
    return prefix + "\n".join(lines)

def coerce_speaker_memory(raw_memory):
    if isinstance(raw_memory, SpeakerMemory):
        return raw_memory
    if isinstance(raw_memory, dict):
        return SpeakerMemory(**raw_memory)
    return SpeakerMemory()

def normalize_memory_dict(memory):
    return {
        "stance": memory.stance or "",
        "previous_points": memory.previous_points[-8:],
        "concessions": memory.concessions[-5:],
        "open_targets": memory.open_targets[-5:],
    }

def tokenize_for_source_lookup(text):
    stop_words = {
        "the", "and", "that", "this", "with", "from", "what", "when", "where",
        "would", "should", "could", "about", "into", "your", "their", "there",
        "have", "does", "will", "they", "them", "then", "than", "were", "been"
    }
    words = re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", text.lower())
    return {word for word in words if word not in stop_words}

def get_source_notes(speaker, topic, conversation, limit=6):
    profile = SOURCE_PROFILES.get(speaker)
    if not profile:
        return []

    lookup_text = topic + " " + " ".join(msg.content for msg in conversation[-8:])
    query_terms = tokenize_for_source_lookup(lookup_text)
    scored_notes = []

    for source in profile.get("sources", []):
        themes = set(source.get("themes", []))
        theme_score = len(query_terms.intersection(themes))
        for note in source.get("notes", []):
            note_terms = tokenize_for_source_lookup(note)
            note_score = len(query_terms.intersection(note_terms))
            score = theme_score * 2 + note_score
            if score > 0:
                scored_notes.append({
                    "score": score,
                    "work": source.get("work", "Source profile"),
                    "note": note
                })

    if not scored_notes:
        for source in profile.get("sources", [])[:2]:
            for note in source.get("notes", [])[:2]:
                scored_notes.append({
                    "score": 0,
                    "work": source.get("work", "Source profile"),
                    "note": note
                })

    scored_notes.sort(key=lambda item: item["score"], reverse=True)
    return [
        f"{item['work']}: {item['note']}"
        for item in scored_notes[:limit]
    ]

def research_cache_key(speaker, topic):
    normalized_topic = re.sub(r"\s+", " ", topic.lower()).strip()
    return f"{speaker.lower()}::{normalized_topic}"

def save_research_cache():
    try:
        with open(RESEARCH_CACHE_PATH, "w", encoding="utf-8") as cache_file:
            json.dump(RESEARCH_CACHE, cache_file, ensure_ascii=False, indent=2)
    except OSError:
        pass

def strip_html(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    value = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", value)
    return re.sub(r"\s+", " ", value).strip()

def trusted_provider_for_url(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host_without_www = host[4:]
    else:
        host_without_www = host
    return TRUSTED_RESEARCH_DOMAINS.get(host) or TRUSTED_RESEARCH_DOMAINS.get(host_without_www)

def extract_readable_text(raw_html):
    raw_html = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw_html)
    raw_html = re.sub(r"(?is)<br\s*/?>", "\n", raw_html)
    raw_html = re.sub(r"(?is)</p\s*>", "\n", raw_html)
    text = strip_html(raw_html)
    return re.sub(r"\s+", " ", text).strip()

def split_sentences(text):
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [sentence.strip() for sentence in sentences if len(sentence.strip()) > 60]

def relevant_excerpt(text, speaker, topic, max_chars=650):
    query_terms = tokenize_for_source_lookup(f"{speaker} {topic}")
    scored = []
    for sentence in split_sentences(text[:12000]):
        sentence_terms = tokenize_for_source_lookup(sentence)
        score = len(query_terms.intersection(sentence_terms))
        if speaker.lower() in sentence.lower():
            score += 3
        scored.append((score, sentence))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [sentence for score, sentence in scored[:3] if score > 0]
    if not selected:
        selected = split_sentences(text[:3000])[:2]
    excerpt = " ".join(selected)
    return excerpt[:max_chars].strip()

def targeted_fetch_result(result, speaker, topic):
    url = result.get("url", "")
    provider = trusted_provider_for_url(url)
    if not provider:
        return None
    if provider in {"wikipedia", "wikisource"}:
        return None

    try:
        response = requests.get(url, headers=RESEARCH_HTTP_HEADERS, timeout=12)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    content_type = response.headers.get("content-type", "")
    if "text" not in content_type and "html" not in content_type:
        return None

    text = extract_readable_text(response.text)
    excerpt = relevant_excerpt(text, speaker, topic)
    if not excerpt:
        return None

    title = result.get("title") or url
    return {
        "title": title,
        "url": url,
        "snippet": excerpt,
        "provider": f"{provider}:fetch",
    }

def build_research_queries(speaker, topic):
    base_topic = re.sub(r"[^\w\s-]", " ", topic).strip()
    queries = [
        f'{speaker} {base_topic} philosophy',
        f'{speaker} {base_topic} primary text',
        f'{speaker} stance on {base_topic}',
    ]

    profile = SOURCE_PROFILES.get(speaker, {})
    for source in profile.get("sources", [])[:2]:
        work = source.get("work", "")
        if work:
            queries.append(f'{speaker} "{work}" {base_topic}')

    return queries[:4]

def brave_web_search(query, count=5):
    if not BRAVE_SEARCH_API_KEY:
        return []

    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
        },
        params={
            "q": query,
            "count": count,
            "text_decorations": False,
            "search_lang": "en",
        },
        timeout=12,
    )
    if response.status_code != 200:
        return []

    data = response.json()
    results = []
    for item in data.get("web", {}).get("results", []):
        title = strip_html(item.get("title", ""))
        description = strip_html(item.get("description", ""))
        url = item.get("url", "")
        if title and description:
            results.append({
                "title": title,
                "url": url,
                "snippet": description,
                "provider": "brave",
            })
    return results

def wikipedia_search(query, limit=5):
    response = requests.get(
        "https://en.wikipedia.org/w/api.php",
        headers=RESEARCH_HTTP_HEADERS,
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": limit,
            "prop": "extracts|info",
            "exintro": True,
            "explaintext": True,
            "inprop": "url",
            "redirects": 1,
        },
        timeout=12,
    )
    if response.status_code != 200:
        return []

    pages = response.json().get("query", {}).get("pages", {})
    results = []
    for page in pages.values():
        title = page.get("title", "")
        extract = strip_html(page.get("extract", ""))
        url = page.get("fullurl", "")
        if title and extract:
            results.append({
                "title": title,
                "url": url,
                "snippet": extract[:600],
                "provider": "wikipedia",
            })
    return results

def wikisource_search(query, limit=4):
    response = requests.get(
        "https://en.wikisource.org/w/api.php",
        headers=RESEARCH_HTTP_HEADERS,
        params={
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
        },
        timeout=12,
    )
    if response.status_code != 200:
        return []

    results = []
    for item in response.json().get("query", {}).get("search", []):
        title = item.get("title", "")
        snippet = strip_html(item.get("snippet", ""))
        if title and snippet:
            results.append({
                "title": title,
                "url": f"https://en.wikisource.org/wiki/{title.replace(' ', '_')}",
                "snippet": snippet,
                "provider": "wikisource",
            })
    return results

def gutenberg_catalog_search(query, limit=4):
    try:
        response = requests.get(
            "https://gutendex.com/books/",
            headers=RESEARCH_HTTP_HEADERS,
            params={"search": query},
            timeout=12,
        )
    except requests.RequestException:
        return []

    if response.status_code != 200:
        return []

    results = []
    for item in response.json().get("results", [])[:limit]:
        title = item.get("title", "")
        authors = ", ".join(author.get("name", "") for author in item.get("authors", []))
        subjects = "; ".join(item.get("subjects", [])[:4])
        formats = item.get("formats", {})
        url = (
            formats.get("text/html")
            or formats.get("text/html; charset=utf-8")
            or formats.get("text/plain; charset=utf-8")
            or formats.get("text/plain")
            or f"https://www.gutenberg.org/ebooks/{item.get('id')}"
        )
        snippet_parts = [part for part in [authors, subjects] if part]
        if title and snippet_parts:
            results.append({
                "title": title,
                "url": url,
                "snippet": " | ".join(snippet_parts),
                "provider": "gutenberg",
            })
    return results

def wikipedia_page_extract(title):
    response = requests.get(
        "https://en.wikipedia.org/w/api.php",
        headers=RESEARCH_HTTP_HEADERS,
        params={
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "extracts|info",
            "exintro": True,
            "explaintext": True,
            "inprop": "url",
            "redirects": 1,
        },
        timeout=12,
    )
    if response.status_code != 200:
        return None

    pages = response.json().get("query", {}).get("pages", {})
    for page in pages.values():
        if "missing" in page:
            continue
        extract = strip_html(page.get("extract", ""))
        if extract:
            return {
                "title": page.get("title", title),
                "url": page.get("fullurl", ""),
                "snippet": extract[:700],
                "provider": "wikipedia",
            }
    return None

def profile_work_titles(speaker):
    profile = SOURCE_PROFILES.get(speaker, {})
    titles = []
    for source in profile.get("sources", []):
        work = source.get("work", "")
        if not work:
            continue
        if "," in work:
            work = work.split(",", 1)[1].strip()
        titles.append(canonical_work_title(speaker, work))
    return titles

def canonical_work_title(speaker, work):
    aliases = {
        ("Aristotle", "Politics"): "Politics (Aristotle)",
        ("Aristotle", "Categories"): "Categories (Aristotle)",
        ("Plato", "Republic"): "Republic (Plato)",
        ("Plato", "Apology"): "Apology (Plato)",
        ("Plato", "Phaedo"): "Phaedo",
        ("John Locke", "Second Treatise of Government"): "Two Treatises of Government",
        ("Karl Marx", "Capital"): "Das Kapital",
        ("Friedrich Nietzsche", "On the Genealogy of Morality"): "On the Genealogy of Morality",
    }
    return aliases.get((speaker, work), work)

def dedupe_search_results(results):
    seen = set()
    deduped = []
    for result in results:
        key = result.get("url") or result.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped

def rank_research_results(results, speaker, topic):
    query_terms = tokenize_for_source_lookup(f"{speaker} {topic}")
    topic_terms = tokenize_for_source_lookup(topic)
    ranked = []
    for result in results:
        haystack = f"{result.get('title', '')} {result.get('snippet', '')}"
        terms = tokenize_for_source_lookup(haystack)
        score = len(query_terms.intersection(terms))
        if speaker.lower() in haystack.lower():
            score += 4
        provider = result.get("provider", "")
        if provider.startswith("sep"):
            score += 5
        if provider.startswith("iep"):
            score += 4
        if provider.startswith("wikipedia:work"):
            score += 20
        if provider.startswith("wikipedia:profile"):
            score += 10
        if provider.startswith("wikisource") or provider.startswith("gutenberg"):
            score += 2
        if provider.endswith(":fetch"):
            score += 3
        title = result.get("title", "").lower()
        if topic_terms.intersection(terms) and any(word in title for word in ["ethics", "morals", "republic", "treatise", "genealogy", "groundwork"]):
            score += 3
        ranked.append((score, result))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked]

def results_to_research_notes(results, limit=6):
    notes = []
    sources = []
    for result in results[:limit]:
        title = result.get("title", "Untitled source")
        snippet = strip_html(result.get("snippet", ""))
        url = result.get("url", "")
        provider = result.get("provider", "web")
        if not snippet:
            continue
        notes.append(f"{title} ({provider}): {snippet[:450]}")
        sources.append({
            "title": title,
            "url": url,
            "provider": provider,
        })
    return notes, sources

def web_research_notes(speaker, topic, conversation, limit=6):
    key = research_cache_key(speaker, topic)
    cached = RESEARCH_CACHE.get(key)
    now = time.time()
    if cached and now - cached.get("timestamp", 0) < RESEARCH_CACHE_TTL_SECONDS:
        return cached.get("notes", [])[:limit], cached.get("sources", []), True

    all_results = []
    for query in build_research_queries(speaker, topic):
        all_results.extend(brave_web_search(query, count=4))
        if not BRAVE_SEARCH_API_KEY:
            all_results.extend(wikipedia_search(query, limit=3))
            all_results.extend(wikisource_search(query, limit=3))
        all_results.extend(gutenberg_catalog_search(query, limit=2))

    direct_results = []
    speaker_page = wikipedia_page_extract(speaker)
    if speaker_page:
        speaker_page["provider"] = "wikipedia:profile"
        direct_results.append(speaker_page)
    for work_title in profile_work_titles(speaker)[:3]:
        work_page = wikipedia_page_extract(work_title)
        if work_page:
            work_page["provider"] = "wikipedia:work"
            direct_results.append(work_page)
    all_results = direct_results + all_results

    ranked_results = rank_research_results(dedupe_search_results(all_results), speaker, topic)
    if not ranked_results:
        ranked_results = rank_research_results(dedupe_search_results(direct_results), speaker, topic)

    fetched_results = []
    for result in ranked_results[:MAX_TARGETED_FETCHES]:
        fetched = targeted_fetch_result(result, speaker, topic)
        if fetched:
            fetched_results.append(fetched)

    combined_results = dedupe_search_results(fetched_results + ranked_results)
    ranked_combined = rank_research_results(combined_results, speaker, topic)
    notes, sources = results_to_research_notes(ranked_combined, limit=limit)

    RESEARCH_CACHE[key] = {
        "timestamp": now,
        "speaker": speaker,
        "topic": topic,
        "notes": notes,
        "sources": sources,
    }
    save_research_cache()
    return notes, sources, False

@app.post("/api/research", response_model=ResearchResponse)
def research(request: ResearchRequest):
    notes, sources, cached = web_research_notes(
        request.speaker,
        request.topic,
        request.conversation or [],
    )
    return ResearchResponse(
        speaker=request.speaker,
        topic=request.topic,
        notes=notes,
        sources=sources,
        cached=cached,
    )

@app.post("/api/respond", response_model=RespondResponse)
def respond(request: RespondRequest):
    phase = (request.phase or "continue").lower()
    memory = coerce_speaker_memory(request.memory)
    memory_dict = normalize_memory_dict(memory)
    transcript = format_transcript_for_response(request.conversation)
    curated_notes = get_source_notes(request.speaker, request.topic, request.conversation)
    web_notes, web_sources, _ = web_research_notes(
        request.speaker,
        request.topic,
        request.conversation,
    )
    source_notes = curated_notes[:4] + web_notes[:4]
    if request.source_notes:
        source_notes.extend(request.source_notes[:4])

    if phase == "opening":
        task = (
            "Give your opening argument about the topic. State your position clearly, "
            "ground it in your philosophy, and avoid replying to nonexistent prior speakers."
        )
    else:
        task = (
            "Continue the conversation as the selected speaker. You have heard the full ordered transcript. "
            "Respond to specific previous arguments, including your own earlier claims when useful. "
            "Build on the discussion instead of restarting."
        )

    messages = [
        {
            "role": "system",
            "content": (
                f"{request.personality}\n\n"
                "You are generating exactly one panel response for a philosopher debate app. "
                f"You are {request.speaker}. Stay in character, reason clearly, and do not include a speaker label. "
                "Return only valid JSON. Do not include markdown."
            )
        },
        {
            "role": "user",
            "content": (
                f"Topic: {request.topic}\n"
                f"Speaker: {request.speaker}\n"
                f"Phase: {phase}\n\n"
                f"Current speaker memory JSON:\n{json.dumps(memory_dict, ensure_ascii=False)}\n\n"
                f"Relevant source notes:\n{json.dumps(source_notes[:8], ensure_ascii=False)}\n\n"
                f"Ordered transcript:\n{transcript}\n\n"
                f"Task: {task}\n\n"
                "Return JSON with this exact shape:\n"
                "{\n"
                '  "generated_text": "90-170 word response shown to the user",\n'
                '  "updated_memory": {\n'
                '    "stance": "current position of this speaker on the topic",\n'
                '    "previous_points": ["short points this speaker has made"],\n'
                '    "concessions": ["short concessions or acknowledgments"],\n'
                '    "open_targets": ["specific claims or speakers this speaker should address later"]\n'
                "  }\n"
                "}\n"
                "Keep memory arrays short. The visible response must not start with the speaker name."
            )
        }
    ]

    raw = call_openai(messages, max_tokens=650, temperature=0.7)
    fallback = {
        "generated_text": raw,
        "updated_memory": memory_dict,
    }
    parsed = parse_json_object(raw, fallback)
    generated_text = clean_generated_text(str(parsed.get("generated_text", raw)))
    updated_memory = parsed.get("updated_memory", memory_dict)

    if not isinstance(updated_memory, dict):
        updated_memory = memory_dict

    normalized_memory = SpeakerMemory(
        stance=str(updated_memory.get("stance", memory_dict["stance"]))[:1000],
        previous_points=[str(item)[:300] for item in updated_memory.get("previous_points", [])][-8:],
        concessions=[str(item)[:300] for item in updated_memory.get("concessions", [])][-5:],
        open_targets=[str(item)[:300] for item in updated_memory.get("open_targets", [])][-5:],
    )

    return RespondResponse(
        speaker=request.speaker,
        generated_text=generated_text,
        updated_memory=normalized_memory,
        source_notes_used=source_notes[:8],
    )

def default_debate_state(topic, participants):
    return {
        "topic": topic,
        "summary": "The debate has not developed yet.",
        "claims": [],
        "open_questions": [],
        "agreements": [],
        "disagreements": [],
        "persona_states": {
            participant.name: {
                "current_position": "",
                "concessions": [],
                "targets": []
            }
            for participant in participants
        }
    }

def update_debate_state(topic, participants, conversation, prior_state):
    fallback = prior_state or default_debate_state(topic, participants)
    participant_names = [participant.name for participant in participants]
    transcript = normalize_conversation(conversation)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a debate analyst. Update a compact structured memory for a philosophical debate. "
                "Return only valid JSON. Do not include markdown."
            )
        },
        {
            "role": "user",
            "content": (
                f"Topic: {topic}\n"
                f"Participants: {', '.join(participant_names)}\n\n"
                f"Prior state JSON:\n{json.dumps(fallback, ensure_ascii=False)}\n\n"
                f"Recent transcript:\n{transcript}\n\n"
                "Return JSON with this exact shape:\n"
                "{\n"
                '  "topic": string,\n'
                '  "summary": string,\n'
                '  "claims": [{"id": string, "speaker": string, "claim": string, "challenged_by": [string], "status": "active|contested|conceded|resolved"}],\n'
                '  "open_questions": [string],\n'
                '  "agreements": [string],\n'
                '  "disagreements": [string],\n'
                '  "persona_states": {"Name": {"current_position": string, "concessions": [string], "targets": [string]}}\n'
                "}\n"
                "Keep at most 8 claims, 5 open questions, 4 agreements, and 4 disagreements. "
                "Include every participant in persona_states."
            )
        }
    ]

    raw = call_openai(messages, max_tokens=900, temperature=0.2)
    state = parse_json_object(raw, fallback)
    state.setdefault("topic", topic)
    state.setdefault("summary", fallback.get("summary", ""))
    state.setdefault("claims", fallback.get("claims", []))
    state.setdefault("open_questions", fallback.get("open_questions", []))
    state.setdefault("agreements", fallback.get("agreements", []))
    state.setdefault("disagreements", fallback.get("disagreements", []))
    state.setdefault("persona_states", {})

    for participant in participants:
        state["persona_states"].setdefault(participant.name, {
            "current_position": "",
            "concessions": [],
            "targets": []
        })

    return state

def plan_debate_turn(topic, participants, conversation, debate_state, phase, max_speakers):
    participant_names = [participant.name for participant in participants]
    if phase in ("opening", "conclusion"):
        return [
            {
                "speaker": participant.name,
                "objective": "Give an opening position." if phase == "opening" else "Give a final synthesis and position.",
                "target": ""
            }
            for participant in participants
        ]

    fallback_count = max(1, min(max_speakers or 3, len(participants)))
    fallback = [
        {
            "speaker": participant.name,
            "objective": "Address the most important unresolved disagreement.",
            "target": ""
        }
        for participant in participants[:fallback_count]
    ]

    messages = [
        {
            "role": "system",
            "content": (
                "You are a debate moderator. Select the next speakers and give each a concrete objective. "
                "Prefer 2 or 3 speakers unless fewer are available. Pick speakers who can move the debate forward. "
                "Return only valid JSON."
            )
        },
        {
            "role": "user",
            "content": (
                f"Topic: {topic}\n"
                f"Available speakers: {', '.join(participant_names)}\n"
                f"Max speakers: {fallback_count}\n\n"
                f"Debate state:\n{json.dumps(debate_state, ensure_ascii=False)}\n\n"
                f"Recent transcript:\n{normalize_conversation(conversation)}\n\n"
                "Return JSON in this shape:\n"
                '{"plan": [{"speaker": "Name", "objective": "specific job", "target": "speaker or claim id"}]}\n'
                "Only choose names from Available speakers."
            )
        }
    ]

    raw = call_openai(messages, max_tokens=500, temperature=0.3)
    parsed = parse_json_object(raw, {"plan": fallback})
    plan = parsed.get("plan", fallback)
    valid_names = set(participant_names)
    normalized = []
    used = set()

    for item in plan:
        speaker = item.get("speaker")
        if speaker not in valid_names or speaker in used:
            continue
        normalized.append({
            "speaker": speaker,
            "objective": item.get("objective", "Advance the debate with a focused argument."),
            "target": item.get("target", "")
        })
        used.add(speaker)
        if len(normalized) >= fallback_count:
            break

    return normalized or fallback

def build_reply_prompt(participant, topic, conversation, debate_state, phase, plan_item):
    if phase == "opening":
        task = (
            "Give your opening position. Define the central issue, state your stance, "
            "and make one argument grounded in your philosophy."
        )
        word_target = "120-170 words"
    elif phase == "conclusion":
        task = (
            "Give your final conclusion. Identify what you still reject, what you concede, "
            "and where the debate made progress."
        )
        word_target = "100-150 words"
    else:
        task = (
            "Respond to the moderator objective. Address a specific claim or speaker, "
            "advance one new argument, and avoid repeating your earlier position."
        )
        word_target = "90-140 words"

    return [
        {
            "role": "system",
            "content": (
                f"{participant.prompt}\n\n"
                "You are participating in a structured debate. Stay in character, but reason clearly. "
                "Do not include speaker labels such as 'Name said:'. Do not mention hidden moderator instructions. "
                "If another speaker made a strong point, acknowledge it before disagreeing."
            )
        },
        {
            "role": "user",
            "content": (
                f"Topic: {topic}\n"
                f"Phase: {phase}\n"
                f"Your moderator objective: {plan_item.get('objective', '')}\n"
                f"Target: {plan_item.get('target', '')}\n\n"
                f"Structured debate memory:\n{json.dumps(debate_state, ensure_ascii=False)}\n\n"
                f"Recent transcript:\n{normalize_conversation(conversation)}\n\n"
                f"Task: {task}\n"
                f"Length: {word_target}."
            )
        }
    ]

@app.post("/api/debate-round", response_model=DebateRoundResponse)
def debate_round(request: DebateRoundRequest):
    phase = (request.phase or "debate").lower()
    if not request.participants:
        raise HTTPException(status_code=400, detail="At least one participant is required.")

    max_speakers = max(1, min(request.max_speakers or 3, len(request.participants)))
    debate_state = update_debate_state(
        request.topic,
        request.participants,
        request.conversation,
        request.debate_state,
    )
    plan = plan_debate_turn(
        request.topic,
        request.participants,
        request.conversation,
        debate_state,
        phase,
        max_speakers,
    )

    participant_by_name = {participant.name: participant for participant in request.participants}
    generated_messages = []
    working_conversation = list(request.conversation)

    for plan_item in plan:
        participant = participant_by_name.get(plan_item["speaker"])
        if not participant:
            continue

        raw_reply = call_openai(
            build_reply_prompt(
                participant,
                request.topic,
                working_conversation,
                debate_state,
                phase,
                plan_item,
            ),
            max_tokens=450,
            temperature=0.7,
        )
        cleaned_reply = clean_generated_text(raw_reply)
        if not cleaned_reply:
            continue

        generated = DebateMessage(
            speaker=participant.name,
            content=cleaned_reply,
            intent=plan_item.get("objective", "")
        )
        generated_messages.append(generated)
        working_conversation.append(Message(speaker=participant.name, content=cleaned_reply))

    if generated_messages:
        debate_state = update_debate_state(
            request.topic,
            request.participants,
            working_conversation,
            debate_state,
        )

    return DebateRoundResponse(
        messages=generated_messages,
        debate_state=debate_state,
        plan=plan,
    )

def clean_generated_text(text):
    text = re.sub(r"^[\w\s.'()-]+\s+said:\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"^[\w\s.'()-]+:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r'^"(.+)"$', r"\1", text, flags=re.DOTALL)
    text = re.sub(r"^'(.+)'$", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"""^["']+|["']+$""", "", text)
    return text.strip()

@app.post("/api/generate", response_model=GenerateResponse)
def generate_response(request: GenerateRequest):
    """
    This endpoint receives a personality prompt, a conversation history,
    and an optional phase ("opening" or "debate").
    
    It constructs a messages list for the Chat Completion API by:
      1. Setting a system message that defines the philosopher's personality
         and instructs them about the debate task.
         - In "opening" phase: generate an initial stance (for or against) the topic.
         - In "debate" phase: generate a deeper response that defends and critiques.
         In both cases, answers should be less than 150 words.
      2. Adding each conversation message with explicit speaker attribution.
      3. Appending a final instruction message.
    """
    
    phase = (request.phase or "debate").lower()
    topic = request.topic or "the given topic"
    
    if phase == "opening":
        system_instructions = (
            f"{request.personality}\n\n"
            "You are engaged in an argumentative conversation. Your task is to present a substantive, "
            "well-reasoned opening argument about the topic that reflects your philosophical perspective.\n\n"
            "Requirements:\n"
            "- Provide a clear position (for or against, or nuanced stance)\n"
            "- Ground your argument in your core philosophical principles\n"
            "- Use concrete examples or thought experiments to illustrate your point\n"
            "- Anticipate counterarguments and address them preemptively\n"
            "- Write with philosophical depth; don't be superficial\n"
            "- Be genuinely open to being convinced by strong arguments from other philosophers\n"
            "- Do NOT include speaker attributions like 'X said:' in your response\n\n"
            "Topic: " + topic
        )
        final_instruction = (
            "Present your opening argument about this topic. "
            "Be substantive and philosophical. Show your reasoning, not just your conclusion. "
            "Aim for 150-200 words if needed to make your point clear."
        )
    elif phase == "conclusion":
        system_instructions = (
            f"{request.personality}\n\n"
            "You have just participated in a philosophical debate. Your task is to provide a final conclusion "
            "that synthesizes the discussion, identifies agreement and disagreement, and states your ultimate position.\n\n"
            "Requirements:\n"
            "- Summarize the key points of agreement (if any) that have emerged in the debate\n"
            "- Clearly identify points of disagreement with specific philosophers\n"
            "- State whether you believe consensus has been reached on any aspect of the topic\n"
            "- Articulate your final position on the topic, grounded in your philosophy\n"
            "- Acknowledge the strongest points made by others, even if you disagree with their conclusion\n"
            "- If the debate has changed your thinking, explicitly acknowledge how your position has evolved\n"
            "- If you have been partially convinced by another philosopher, say which specific points persuaded you\n"
            "- Be concise but substantive—this is your final word, not a debate continuation\n"
            "- Do NOT include speaker attributions like 'X said:' in your response\n\n"
            "Topic: " + topic
        )
        final_instruction = (
            "Provide your conclusion to this philosophical debate. "
            "State what agreements have emerged, where you disagree with others, and what your final position is on this topic. "
            "Aim for 100-150 words to synthesize the discussion clearly."
        )
    else:  # Default to "debate" phase
        system_instructions = (
            f"{request.personality}\n\n"
            "You are in an ongoing philosophical debate. Your task is to deepen the conversation "
            "by addressing what others have said with substantive critique, new insights, or expansions.\n\n"
            "Requirements:\n"
            "- Directly address other philosophers by name when relevant\n"
            "- Identify the strongest and weakest points in their arguments\n"
            "- Explain WHY you agree or disagree, grounded in your philosophy\n"
            "- Introduce new dimensions or counterexamples they haven't considered\n"
            "- Challenge their assumptions; don't just restate your position\n"
            "- Show intellectual honesty: acknowledge valid points from opponents\n"
            "- If another philosopher's argument persuades you or contains genuine merit, explicitly say so\n"
            "- Be willing to shift your position or partially concede if presented with compelling reasoning\n"
            "- Show intellectual growth—don't rigidly defend your stance if faced with stronger logic\n"
            "- Do NOT include speaker attributions like 'X said:' in your response\n\n"
            "Topic: " + topic
        )
        final_instruction = (
            "Respond to the ongoing debate. If you spoke last, deepen your argument with new insights. "
            "If others spoke last, critique their positions substantively. "
            "Aim for 100-150 words to make real philosophical progress."
        )
    
    # Build the messages list.
    messages = [{
        "role": "system",
        "content": system_instructions
    }]
    
    # Append each conversation message with explicit speaker attribution.
    for msg in request.conversation:
        let_speaker = msg.speaker.strip() if msg.speaker else ""
        speaker_name = let_speaker if let_speaker and let_speaker.lower() != "unknown" else "User"
        role = "user" if speaker_name in ("User", "Topic") else "assistant"
        messages.append({
            "role": role,
            "content": f'{speaker_name}: {msg.content}'
        })
    
    # Append the final instruction.
    messages.append({
        "role": "user",
        "content": final_instruction
    })
    
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "max_tokens": 500,  # Increased from 150 to allow deeper arguments
        "temperature": 0.7,  # Lowered from 0.9 for more focused reasoning
        "top_p": 0.95,  # Added for better quality diversity
    }
    
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    
    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=30)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request error: {str(e)}")
    
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    
    result = response.json()
    
    if "choices" in result and len(result["choices"]) > 0:
        generated_text = result["choices"][0]["message"]["content"].strip()
    else:
        raise HTTPException(status_code=500, detail="Unexpected response from OpenAI API")
    
    return GenerateResponse(generated_text=generated_text)
