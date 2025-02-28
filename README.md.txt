# **Philosopher Chat Simulator**

A web application that simulates an argumentative conversation among various figures (philosophers, movie characters, celebrities, etc.) powered by OpenAI's GPT models. Users provide a topic, and each figure (with its own personality) generates opening arguments and continues the debate sequentially.

## Features

- User Input:
Enter a topic to start a new conversation. When a new topic is provided, the conversation history resets.

- Opening Arguments:
Each figure generates an initial stance (for or against the topic). Their responses are stored with speaker attribution (e.g., Plato said: "...").

- Debate Progression:
When a user clicks the "Continue" button on a figure's panel, only that panel is updated with a deeper response that critiques and defends its initial stance, referencing previous arguments by name.

- Conversation History Management:
The entire conversation history (all messages) is sent as context to the LLM, but only new messages are appended to the UI.

- Customizable Personalities:
Each figure (philosopher, movie character, celebrity, etc.) has a personality prompt that can be edited via a right-click context menu.

## Project Structure

'
my-app/
├── backend.py            # FastAPI backend code for generating responses.
├── index.html            # Frontend HTML file.
├── style.css             # CSS styling for the UI.
├── script.js             # Main JavaScript logic for the frontend.
├── philosophers.js       # Example data file for philosophers (50 entries).
└── README.md             # This file.
'

Prerequisites

Python 3.7+
Node.js (if modifying frontend build tools)
A GitHub account
An OpenAI API key with access to GPT-4 or GPT-3.5-turbo (set as an environment variable)

Setup Instructions

Backend

Clone the Repository:

git clone https://github.com/yourusername/philosopher-chat-simulator.git
cd philosopher-chat-simulator

Create a Virtual Environment and Install Dependencies:

python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt

Your requirements.txt should include at least:

fastapi
uvicorn
requests
python-dotenv

Set Environment Variables:
Create a .env file or set the environment variable manually. For example, using a .env file:

ini
Copy
OPENAI_API_KEY=your_openai_api_key_here
Load the environment variable with python-dotenv if needed.

Run the Backend Server:


uvicorn backend:app --reload --host 0.0.0.0 --port 8000
The backend should now be running at http://127.0.0.1:8000 (Swagger docs available at /docs).

Frontend
Open index.html:
Open the index.html file directly in your browser or use a simple HTTP server (like live-server or Python's http.server):

bash
Copy
# Using Python 3
python -m http.server 8001
Configure API URL:
In script.js, ensure the API_URL variable is updated to point to your deployed backend (for local development, it should be http://127.0.0.1:8000/generate).

Deployment on Render
To deploy the backend on Render:

Push Your Code to GitHub:
Ensure all your files (backend.py, requirements.txt, etc.) are committed.

Create a New Web Service on Render:

Connect your GitHub repository.
Configure the build and start commands (use uvicorn backend:app --host 0.0.0.0 --port 8000 as the start command).
Set the environment variable OPENAI_API_KEY in Render’s dashboard.
Deploy and Test:
Once deployed, update your frontend’s API_URL to the Render URL (e.g., https://yourapp.onrender.com/generate).

Usage
Enter a Topic:
Type a topic into the input field and click "Start Conversation". This resets the conversation history and prompts each figure to generate their initial argument.

Continue the Debate:
Click the "Continue" button on any figure’s panel to generate a deeper response. Only the panel that is clicked updates with the new speech bubble.

Edit Personalities:
Right-click on a figure’s panel to access the context menu for editing that figure’s personality prompt.