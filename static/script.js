/****************************************************************************
 * GLOBAL STATE
 ****************************************************************************/
// Reference philosopher data from philosophers.js
const philosophers = window.PHILOSOPHERS;

// Array of philosopher instances: each is { philosopher: {...}, instanceId: number }
let selectedPhilosopherInstances = [];

// Unique panel ID counter
let panelCounter = 0;

// Per-instance conversation histories: { [instanceId]: [ { content: string } ] }
let conversations = {};

// Global conversation history (stores all messages from all philosophers)
// (Used solely for context passed to the API; UI updates are done per-panel)
let globalConversation = [];

// Map of DOM panel elements keyed by instanceId
let instancePanels = {};

// Flag to ensure only one generation happens at a time
let isGenerating = false;


/****************************************************************************
 * DOM ELEMENTS
 ****************************************************************************/
const philosopherListDiv = document.getElementById('philosopherList');
const philosopherPanelsDiv = document.getElementById('philosopherPanels');
const startButton = document.getElementById('startButton');
const topicInput = document.getElementById('topicInput');
const contextMenu = document.getElementById('contextMenu');
const removePhilosopherMenuItem = document.getElementById('removePhilosopher');
const editPromptMenuItem = document.getElementById('editPrompt'); // For editing prompt

// To track which instance (panel) was right-clicked
let currentRightClickPanelId = null;


/****************************************************************************
 * INITIALIZATION
 ****************************************************************************/
populatePhilosopherList();

/**
 * Populate the sidebar with philosopher items.
 * Double-clicking a name adds a new instance to the screen,
 * initializing its conversation with the existing global conversation.
 */
function populatePhilosopherList() {
  philosophers.forEach((philosopher, index) => {
    const div = document.createElement('div');
    div.className = 'philosopher-item';
    div.textContent = philosopher.name;
    div.dataset.index = index;
    div.addEventListener('click', (e) => {
      const idx = e.currentTarget.dataset.index;
      // Initialize new instance's history with a copy of globalConversation.
      addPhilosopherInstance(philosophers[idx], [...globalConversation]);
    });
    philosopherListDiv.appendChild(div);
  });
}


/****************************************************************************
 * ADD / REMOVE PHILOSOPHER INSTANCES
 ****************************************************************************/
/**
 * Create a new philosopher instance.
 * If fewer than 3 exist, add directly; otherwise, remove the oldest instance first.
 * The new instance is initialized with the given initialHistory.
 */
function addPhilosopherInstance(philosopher, initialHistory = []) {
  if (selectedPhilosopherInstances.length < 3) {
    selectedPhilosopherInstances.push({
      philosopher,
      instanceId: panelCounter++
    });
  } else {
    // Remove the oldest instance
    const oldest = selectedPhilosopherInstances.shift();
    delete conversations[oldest.instanceId];
    removePanelFromDOM(oldest.instanceId);
    selectedPhilosopherInstances.push({
      philosopher,
      instanceId: panelCounter++
    });
  }
  // Set the new instance's conversation to the passed history (global conversation)
  const newInstance = selectedPhilosopherInstances[selectedPhilosopherInstances.length - 1];
  conversations[newInstance.instanceId] = initialHistory.slice();
  createPhilosopherPanel(newInstance);
}

/**
 * Remove a philosopher instance (by instanceId) from state and DOM.
 */
function removePhilosopherInstance(instanceId) {
  selectedPhilosopherInstances = selectedPhilosopherInstances.filter(
    inst => inst.instanceId !== instanceId
  );
  delete conversations[instanceId];
  removePanelFromDOM(instanceId);
}

/**
 * Helper: Remove the DOM panel for a given instanceId.
 */
function removePanelFromDOM(instanceId) {
  const panel = instancePanels[instanceId];
  if (panel && philosopherPanelsDiv.contains(panel)) {
    philosopherPanelsDiv.removeChild(panel);
  }
  delete instancePanels[instanceId];
}


/****************************************************************************
 * BACKEND API CALL
 ****************************************************************************/
// Set your backend URL (update if deployed)
const API_URL = "https://philosoph.onrender.com/api/generate";

/**
 * Call the backend API to generate a philosopher's response.
 * The payload includes the philosopher's personality prompt and the global conversation history.
 */
async function getPhilosopherResponse(instanceId) {
  const instance = selectedPhilosopherInstances.find(inst => inst.instanceId == instanceId);
  if (!instance) return null;
  
  const personality = instance.philosopher.prompt;
  const payload = {
    personality: personality,
    // Use the global conversation as context.
    conversation: globalConversation.map(msg => ({ content: msg.content }))
  };

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      const errorData = await response.text();
      alert("Backend error: " + errorData);
      return null;
    }
    const data = await response.json();
    return data.generated_text;
  } catch (error) {
    alert("Network error: " + error.message);
    return null;
  }
}


/****************************************************************************
 * PANEL CREATION & UPDATE
 ****************************************************************************/
/**
 * Create a philosopher panel for a specific instance and attach it to the DOM.
 * This panel displays its own conversation history.
 */
function createPhilosopherPanel(instance) {
  if (!conversations[instance.instanceId]) {
    conversations[instance.instanceId] = [];
  }

  const panel = document.createElement('div');
  panel.className = 'philosopher-panel';
  panel.dataset.instanceId = instance.instanceId;

  // Title: philosopher's name
  const nameDiv = document.createElement('div');
  nameDiv.className = 'philosopher-name';
  nameDiv.textContent = instance.philosopher.name;
  panel.appendChild(nameDiv);

  // Conversation container
  const conversationDiv = document.createElement('div');
  conversationDiv.className = 'conversation';
  panel.appendChild(conversationDiv);

  // Populate with existing conversation messages (if any)
  // conversations[instance.instanceId].forEach((msg) => {
  //   addSpeechBubbleElement(conversationDiv, msg.content);
  // });

  // "Continue" button (renamed from "Next")
  const continueButton = document.createElement('button');
  continueButton.className = 'next-button';
  continueButton.textContent = 'Continue';
  continueButton.addEventListener('click', async () => {
    if (isGenerating) return; // Prevent simultaneous calls
    const topic = topicInput.value.trim();
    if (!topic) {
      alert("Error: Please enter a topic before continuing the conversation.");
      return;
    }
    isGenerating = true;
    // Call the backend to get the philosopher's response for this panel.
    const generatedText = await getPhilosopherResponse(instance.instanceId);
    if (generatedText) {
      // Append the new response only to this panel's conversation:
      conversations[instance.instanceId].push({ content: generatedText });
      globalConversation.push({ content: generatedText }); // Also update global context.
      // Update only this panel's display by adding one new bubble.
      const panelDOM = instancePanels[instance.instanceId];
      if (panelDOM) {
        const convDiv = panelDOM.querySelector('.conversation');
        addSpeechBubbleElement(convDiv, generatedText);
      }
    }
    isGenerating = false;
  });
  panel.appendChild(continueButton);

  // Right-click context menu for editing prompt or removal.
  panel.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    currentRightClickPanelId = instance.instanceId;
    showContextMenu(e.pageX, e.pageY);
  });

  // Save panel reference and append to the main container.
  instancePanels[instance.instanceId] = panel;
  philosopherPanelsDiv.appendChild(panel);
}


/****************************************************************************
 * SPEECH BUBBLES
 ****************************************************************************/
/**
 * Add a new speech bubble to a specific instance's conversation.
 * (This function simply updates the DOM for one panel.)
 */
function addSpeechBubbleElement(conversationDiv, text) {
  const bubble = document.createElement('div');
  bubble.className = 'speech-bubble';
  conversationDiv.appendChild(bubble);

  let index = 0;
  function typeCharacter() {
    if (index < text.length) {
      bubble.textContent += text.charAt(index);
      index++;
      setTimeout(typeCharacter, 20);
    }
  }
  typeCharacter();
}


/****************************************************************************
 * START CONVERSATION
 ****************************************************************************/
/**
 * On "Start Conversation", each philosopher generates an initial response.
 * Each philosopher prints his initial thought on his panel in one speech bubble.
 * The topic is used as the seed for each generation, but is not displayed as a bubble.
 */
startButton.addEventListener('click', async () => {
  const topic = topicInput.value.trim();
  if (!topic) {
    alert('Please enter a topic.');
    return;
  }
  // Reset global conversation.
  globalConversation = [];
  // For each instance, clear its conversation display (but do not re-render existing bubbles).
  selectedPhilosopherInstances.forEach((instance) => {
    conversations[instance.instanceId] = [];
    const panel = instancePanels[instance.instanceId];
    if (panel) {
      const conversationDiv = panel.querySelector('.conversation');
      conversationDiv.innerHTML = "";
    }
  });
  // Sequentially initialize each philosopher with their first response.
  // Each philosopher will generate one speech bubble.
  for (const instance of selectedPhilosopherInstances) {
    if (isGenerating) break;
    isGenerating = true;
    const personality = instance.philosopher.prompt;
    // For the first take, use the topic as the sole context.
    const payload = {
      personality: personality,
      conversation: [{ content: topic }]
    };
    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const errorData = await response.text();
        alert("Backend error: " + errorData);
        isGenerating = false;
        return;
      }
      const data = await response.json();
      const generatedText = data.generated_text;
      if (generatedText) {
        // Update this instance's conversation and global conversation.
        conversations[instance.instanceId].push({ content: generatedText });
        globalConversation.push({ content: generatedText });
        // Add one speech bubble to this panel.
        const panelDOM = instancePanels[instance.instanceId];
        if (panelDOM) {
          const convDiv = panelDOM.querySelector('.conversation');
          addSpeechBubbleElement(convDiv, generatedText);
        }
      }
    } catch (error) {
      alert("Network error: " + error.message);
    }
    isGenerating = false;
  }
});


/****************************************************************************
 * CONTEXT MENU (RIGHT-CLICK)
 ****************************************************************************/
removePhilosopherMenuItem.addEventListener('click', () => {
  if (currentRightClickPanelId !== null) {
    removePhilosopherInstance(currentRightClickPanelId);
    currentRightClickPanelId = null;
    hideContextMenu();
  }
});

editPromptMenuItem.addEventListener('click', () => {
  if (currentRightClickPanelId !== null) {
    const instance = selectedPhilosopherInstances.find(inst => inst.instanceId == currentRightClickPanelId);
    if (instance) {
      const newPrompt = prompt("Edit personality prompt:", instance.philosopher.prompt);
      if (newPrompt !== null) {
        instance.philosopher.prompt = newPrompt;
      }
    }
    hideContextMenu();
  }
});

document.addEventListener('click', () => {
  if (contextMenu.style.display === 'block') {
    hideContextMenu();
  }
});

function showContextMenu(x, y) {
  contextMenu.style.display = 'block';
  contextMenu.style.left = x + 'px';
  contextMenu.style.top = y + 'px';
}

function hideContextMenu() {
  contextMenu.style.display = 'none';
}
