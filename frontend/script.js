document.addEventListener('DOMContentLoaded', () => {
    const topicInput = document.getElementById('topic-input');
    const API_KEY = "myresearchapikey123"; // Matches .env FASTAPI_API_KEY
    const researchBtn = document.getElementById('research-btn');
    const loadingState = document.getElementById('loading-state');
    const loadingMessage = document.getElementById('loading-message');
    const errorMessage = document.getElementById('error-message');
    const resultContainer = document.getElementById('result-container');
    const resultTopic = document.getElementById('result-topic');
    const resultContent = document.getElementById('result-content');

    const loadingPhrases = ['Searching the web...', 'Reading documents...', 'Analyzing data...', 'Generating report...'];
    let phraseInterval;


    researchBtn.addEventListener('click', handleResearch);
    topicInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleResearch();
    });

    async function handleResearch() {
        const topic = topicInput.value.trim();

        // Basic validation
        if (!topic) {
            showError("Please enter a topic to research.");
            return;
        }

        // Reset UI state
        hideError();
        hideResult();
        showLoading();
        researchBtn.disabled = true;

        try {
            // Fetch request to FastAPI backend
            const response = await fetch('http://127.0.0.1:8000/research', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': API_KEY
                },
                body: JSON.stringify({ topic: topic })
            });

            // Handle non-200 responses gracefully
            if (!response.ok) {
                if (response.status === 401 || response.status === 403) {
                    throw new Error("Authentication failed.");
                }
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `Server error: ${response.statusText}`);
            }

            const data = await response.json();

            // Validate backend response format
            if (data.status === 'success' && data.data) {
                // Safely extract the report from the data object
                let reportContent = data.data;
                if (typeof data.data === 'object') {
                    reportContent = data.data.report || JSON.stringify(data.data, null, 2);
                }
                showResult(data.topic || topic, reportContent);
            } else {
                throw new Error("Unexpected response format from the server.");
            }

        } catch (error) {
            // Handle fetch errors (network down, cors, etc.)
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                showError("Our servers are currently unreachable. Please check your internet connection or try again later.");
            } else {
                showError(error.message);
            }
        } finally {
            hideLoading();
            researchBtn.disabled = false;
        }
    }

    // --- UI Helper Functions ---

    function showLoading() {
        loadingState.classList.remove('hidden');
        let phraseIndex = 0;
        loadingMessage.textContent = loadingPhrases[phraseIndex];

        // Animate loading message to show progress visually
        phraseInterval = setInterval(() => {
            phraseIndex = (phraseIndex + 1) % loadingPhrases.length;
            loadingMessage.textContent = loadingPhrases[phraseIndex];
        }, 2000);
    }

    function hideLoading() {
        loadingState.classList.add('hidden');
        clearInterval(phraseInterval);
    }

    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.classList.remove('hidden');
    }

    function hideError() {
        errorMessage.classList.add('hidden');
    }

    function showResult(topic, content) {
        resultTopic.textContent = `Research: ${topic}`;
        resultContent.textContent = content; // Using textContent preserves line breaks via CSS white-space: pre-wrap
        resultContainer.classList.remove('hidden');
    }

    function hideResult() {
        resultContainer.classList.add('hidden');
    }
});
