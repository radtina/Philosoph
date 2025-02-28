import os
from fastapi.staticfiles import StaticFiles
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

# OpenAI configuration for GPT-4 (or change model if needed)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("Warning: OPENAI_API_KEY not set; please set it before running.")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Pydantic models for input and output.
class Message(BaseModel):
    speaker: Optional[str] = None  # Default speaker if not provided.
    content: str

class GenerateRequest(BaseModel):
    personality: str         # The philosopher's personality prompt.
    conversation: List[Message]  # The conversation history (ordered list of messages).
    phase: Optional[str] = "debate"  # "opening" for initial stance; "debate" for further responses.

class GenerateResponse(BaseModel):
    generated_text: str

@app.post("/generate", response_model=GenerateResponse)
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
    
    phase = request.phase.lower()
    
    if phase == "opening":
        system_instructions = (
            f"{request.personality}\n\n"
            "You are engaged in an argumentative conversation about the topic'. "
            "Ensure that your opinions, whether negative or positive, always reflect your own personality and life experiences and thoughts about the discussed topic. "
        )
        final_instruction = "Say your opening argument—an initial stance regarding the topic. Your entire response should be less than 80 words. "
    else:  # Default to "debate" phase
        system_instructions = (
            f"{request.personality}\n\n"
            "Understand and analyze what the others said in the who context of the conversation. "
            "Debate and decide if you agree or disagree with anyone according to your own personality and life experiences. "
            "If you want to address the other people in the conversation, address them by name. "
            "Try to give your own life experiences as examples. "
            "Try to introduce new aspects of the topic that have not been discussed yet. "
            "Give more focus to the latest things said by the others and expand on them. "
        )
        final_instruction = "if you were the one who said the last thing in the conversation then your reponse should go deeper into your own points, if not, critique what the others have said. Your entire response should be less than 50 words. "
    
    # Build the messages list.
    messages = [{
        "role": "user",
        "content": system_instructions
    }]
    
    # Append each conversation message with explicit speaker attribution.
    for msg in request.conversation:
        let_speaker = msg.speaker.strip() if msg.speaker else ""
        speaker_name = let_speaker if let_speaker and let_speaker.lower() != "unknown" else "User"
        messages.append({
            "role": "user",
            "content": f'{speaker_name} said: "{msg.content}"'
        })
    
    # Append the final instruction.
    messages.append({
        "role": "user",
        "content": final_instruction
    })
    
    payload = {
        "model": "gpt-4",  # Change to "gpt-4" if available.
        "messages": messages,
        "max_tokens": 150,
        "temperature": 0.7,
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
