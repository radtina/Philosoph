/****************************************************************************
 * GLOBAL STATE
 ****************************************************************************/
const philosophers = window.PHILOSOPHERS;

let selectedPhilosopherInstances = [];
let panelCounter = 0;
let conversations = {};
let globalConversation = [];
let instancePanels = {};
let speakerMemories = {};
let isGenerating = false;
let currentRightClickPanelId = null;

const API_URL = "/api/respond";

/****************************************************************************
 * DOM ELEMENTS
 ****************************************************************************/
const philosopherListDiv = document.getElementById('philosopherList');
const philosopherPanelsDiv = document.getElementById('philosopherPanels');
const startButton = document.getElementById('startButton');
const topicInput = document.getElementById('topicInput');
const contextMenu = document.getElementById('contextMenu');
const removePhilosopherMenuItem = document.getElementById('removePhilosopher');

/****************************************************************************
 * INITIALIZATION
 ****************************************************************************/
populatePhilosopherList();

function populatePhilosopherList() {
  philosophers.forEach((philosopher, index) => {
    const div = document.createElement('div');
    div.className = 'philosopher-item';
    div.textContent = philosopher.name;
    div.dataset.index = index;
    div.addEventListener('click', (e) => {
      const idx = e.currentTarget.dataset.index;
      addPhilosopherInstance(philosophers[idx], [...globalConversation]);
    });
    philosopherListDiv.appendChild(div);
  });
}

/****************************************************************************
 * ADD / REMOVE PHILOSOPHER INSTANCES
 ****************************************************************************/
function addPhilosopherInstance(philosopher, initialHistory = []) {
  if (selectedPhilosopherInstances.length < 3) {
    selectedPhilosopherInstances.push({
      philosopher,
      instanceId: panelCounter++
    });
  } else {
    const oldest = selectedPhilosopherInstances.shift();
    delete conversations[oldest.instanceId];
    removePanelFromDOM(oldest.instanceId);
    selectedPhilosopherInstances.push({
      philosopher,
      instanceId: panelCounter++
    });
  }

  const newInstance = selectedPhilosopherInstances[selectedPhilosopherInstances.length - 1];
  conversations[newInstance.instanceId] = initialHistory.slice();
  createPhilosopherPanel(newInstance);
}

function removePhilosopherInstance(instanceId) {
  const instance = selectedPhilosopherInstances.find(inst => inst.instanceId === instanceId);
  selectedPhilosopherInstances = selectedPhilosopherInstances.filter(
    inst => inst.instanceId !== instanceId
  );
  delete conversations[instanceId];
  if (instance) {
    delete speakerMemories[instance.philosopher.name];
  }
  removePanelFromDOM(instanceId);
}

function removePanelFromDOM(instanceId) {
  const panel = instancePanels[instanceId];
  if (panel && philosopherPanelsDiv.contains(panel)) {
    philosopherPanelsDiv.removeChild(panel);
  }
  delete instancePanels[instanceId];
}

/****************************************************************************
 * PANEL CREATION & UPDATE
 ****************************************************************************/
function createPhilosopherPanel(instance) {
  if (!conversations[instance.instanceId]) {
    conversations[instance.instanceId] = [];
  }

  const panel = document.createElement('div');
  panel.className = 'philosopher-panel';
  panel.dataset.instanceId = instance.instanceId;

  const nameDiv = document.createElement('div');
  nameDiv.className = 'philosopher-name';
  nameDiv.textContent = instance.philosopher.name;
  panel.appendChild(nameDiv);

  const conversationDiv = document.createElement('div');
  conversationDiv.className = 'conversation';
  panel.appendChild(conversationDiv);

  const continueButton = document.createElement('button');
  continueButton.className = 'next-button';
  continueButton.textContent = 'Continue';
  continueButton.addEventListener('click', async () => {
    if (isGenerating) return;
    const topic = topicInput.value.trim();
    if (!topic) {
      alert("Error: Please enter a topic before continuing the conversation.");
      return;
    }

    const message = await generatePanelResponse("continue", instance);
    renderGeneratedMessages(message ? [message] : []);
  });
  panel.appendChild(continueButton);

  panel.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    currentRightClickPanelId = instance.instanceId;
    showContextMenu(e.pageX, e.pageY);
  });

  instancePanels[instance.instanceId] = panel;
  philosopherPanelsDiv.appendChild(panel);
}

/****************************************************************************
 * SPEECH BUBBLES
 ****************************************************************************/
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

function renderGeneratedMessages(messages) {
  messages.forEach(message => {
    const instance = selectedPhilosopherInstances.find(
      item => item.philosopher.name === message.speaker
    );
    if (!instance) return;

    conversations[instance.instanceId].push({
      content: message.content,
      speaker: message.speaker
    });
    globalConversation.push({
      content: message.content,
      speaker: message.speaker
    });

    const panel = instancePanels[instance.instanceId];
    if (panel) {
      const conversationDiv = panel.querySelector('.conversation');
      addSpeechBubbleElement(conversationDiv, message.content);
    }
  });
}

/****************************************************************************
 * START CONVERSATION
 ****************************************************************************/
startButton.addEventListener('click', async () => {
  const topic = topicInput.value.trim();
  if (!topic) {
    alert('Please enter a topic.');
    return;
  }

  if (selectedPhilosopherInstances.length === 0) {
    alert('Please select at least one philosopher.');
    return;
  }

  globalConversation = [];
  speakerMemories = {};

  selectedPhilosopherInstances.forEach((instance) => {
    conversations[instance.instanceId] = [];
    const panel = instancePanels[instance.instanceId];
    if (panel) {
      const conversationDiv = panel.querySelector('.conversation');
      conversationDiv.innerHTML = "";
    }
  });

  for (const instance of selectedPhilosopherInstances) {
    const message = await generatePanelResponse("opening", instance);
    renderGeneratedMessages(message ? [message] : []);
  }
});

/****************************************************************************
 * SINGLE-SPEAKER RESPONSE API
 ****************************************************************************/
async function generatePanelResponse(phase, instance) {
  if (isGenerating) return null;

  isGenerating = true;
  setControlsDisabled(true);

  const topic = topicInput.value.trim();
  const speaker = instance.philosopher.name;

  const payload = {
    topic: topic,
    speaker: speaker,
    personality: instance.philosopher.prompt,
    phase: phase,
    conversation: getConversationForApi(phase === "opening"),
    memory: speakerMemories[speaker] || null
  };

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errorText = await response.text();
      alert("Backend error: " + errorText);
      return null;
    }

    const data = await response.json();
    speakerMemories[speaker] = data.updated_memory || speakerMemories[speaker] || {};

    const content = cleanAttributions(data.generated_text || "");
    if (!content) return null;

    return {
      speaker: data.speaker || speaker,
      content: content
    };
  } catch (error) {
    alert("Network error: " + error.message);
    return null;
  } finally {
    isGenerating = false;
    setControlsDisabled(false);
  }
}

function getConversationForApi(includeTopic) {
  const conversation = includeTopic
    ? [{ content: topicInput.value.trim(), speaker: "Topic" }]
    : [];

  return conversation.concat(globalConversation.map(msg => ({
    content: msg.content,
    speaker: msg.speaker || "Unknown"
  })));
}

function setControlsDisabled(disabled) {
  startButton.disabled = disabled;
  document.querySelectorAll('.next-button').forEach(button => {
    button.disabled = disabled;
  });
}

function cleanAttributions(text) {
  text = text.replace(/^[\p{L}\s.'()-]+\s+said:\s*/iu, '');
  text = text.replace(/^[\p{L}\s.'()-]+:\s*/iu, '');
  text = text.replace(/^"(.+)"$/s, '$1');
  text = text.replace(/^'(.+)'$/s, '$1');
  text = text.replace(/^["']+|["']+$/g, '');
  return text.trim();
}


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
