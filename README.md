# Philosopher Chat Simulator

A FastAPI web app that lets you create an AI-powered panel debate between selected philosophers, public figures, fictional characters, and other personas. You choose a topic and participants; the app asks OpenAI to generate opening arguments and follow-up replies in each persona's voice.

## Features

- Select up to three debate participants from the persona sidebar.
- Enter a debate topic and start the conversation.
- Generate opening arguments for all selected panels.
- Continue individual philosopher panels while preserving shared debate context.
- Send the full ordered transcript to the philosopher selected by `Continue`.
- Maintain compact per-philosopher memory to reduce repetition and token use.
- Add small cached source notes for well-known philosophers where available.
- Strip accidental model-generated speaker prefixes such as `Socrates said:`.

## Project Structure

```text
.
├── backend.py              # FastAPI app and OpenAI proxy endpoint
├── requirements.txt        # Python dependencies
├── static/
│   ├── index.html          # Panel UI markup
│   ├── philosophers.js     # Persona names and prompts
│   ├── script.js           # Frontend state and request flow
│   └── style.css           # App styling
├── verify_improvements.py  # Local verification helper
└── ig.py                   # Separate Instagram follower comparison utility
```

## Requirements

- Python 3.7+
- An OpenAI API key

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local `.env` file:

```bash
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4
BRAVE_SEARCH_API_KEY=optional_brave_search_key
```

`.env` is ignored by git and should not be committed.

## Run

```bash
uvicorn backend:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://localhost:8000
```

## Usage

1. Click philosopher names in the sidebar to add panels.
2. Enter a debate topic.
3. Click `Start Conversation`.
4. Wait for opening arguments.
5. Click `Continue` on a panel to generate that participant's next reply.
6. Right-click a panel and choose `Remove Philosopher` to remove it.

## How It Works

The frontend sends requests to `POST /api/respond` with:

- the target speaker and personality prompt,
- the full conversation history,
- the debate topic,
- the speaker's compact memory,
- a phase: `opening` or `continue`.

The backend uses a single OpenAI call to return:

1. The visible philosopher response.
2. Updated compact memory for that same philosopher.
3. The source notes selected for that response, for debugging/API inspection.

This preserves the panel UI flow: the user decides who speaks by clicking `Continue`, while the backend gives that speaker the ordered transcript and their own memory. The older `POST /api/generate` and `POST /api/debate-round` endpoints are still available for compatibility, but the UI uses `/api/respond`.

## Source Grounding

The backend uses a small research pipeline before each response:

1. Loads curated notes from `source_profiles.json`.
2. Searches the web through Brave Search if `BRAVE_SEARCH_API_KEY` is configured.
3. Falls back to Wikipedia and Wikisource APIs when no Brave key is available.
4. Searches the Project Gutenberg catalog for public-domain works.
5. Adds direct Wikipedia extracts for known philosopher/work pages.
6. Fetches extra text only from trusted domains: SEP, IEP, Gutenberg, Wikipedia, and Wikisource.
7. Ranks retrieved notes against the philosopher, topic, and recent transcript.
8. Caches research in `research_cache.json` for reuse.

The UI still uses the original panel flow. Search happens behind the scenes through `/api/respond`, and `/api/research` is available for debugging the research layer directly.

The app does not run a broad crawler. It performs targeted lookup and targeted fetches against a small allowlist, then passes only short notes and source URLs into the model.

## Notes

- `static/philosophers.js` currently includes 58 personas.
- The frontend uses a relative `/api/respond` path, so it works from the same host/port that serves the page.
- Opening includes every selected panel.
- Continue actions target the selected panel while still using shared debate memory.
- Source notes combine curated local profiles with cached web research when available.
- `ig.py`, `followers.json`, `following.json`, and `not_following_you_back.txt` are unrelated to the Philosopher Chat Simulator app.
