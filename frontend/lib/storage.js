export function saveAnalysis(analysisData) {
  try {
    const data = {
      ...analysisData,
      timestamp: new Date().toISOString(),
    };
    sessionStorage.setItem('latestAnalysis', JSON.stringify(data));
  } catch (error) {
    console.error('Error saving analysis to sessionStorage:', error);
  }
}

export function getAnalysis() {
  try {
    const data = sessionStorage.getItem('latestAnalysis');
    if (!data) return null;

    const parsed = JSON.parse(data);
    const timestamp = new Date(parsed.timestamp);
    const now = new Date();
    const fiveMinutes = 5 * 60 * 1000;

    if (now - timestamp > fiveMinutes) {
      sessionStorage.removeItem('latestAnalysis');
      return null;
    }

    return parsed;
  } catch (error) {
    console.error('Error getting analysis from sessionStorage:', error);
    return null;
  }
}

export function clearAnalysis() {
  try {
    sessionStorage.removeItem('latestAnalysis');
  } catch (error) {
    console.error('Error clearing analysis from sessionStorage:', error);
  }
}

export function saveVitals(vitalsData) {
  try {
    const data = {
      ...vitalsData,
      timestamp: new Date().toISOString(),
    };
    sessionStorage.setItem('capturedVitals', JSON.stringify(data));
  } catch (error) {
    console.error('Error saving vitals to sessionStorage:', error);
  }
}

export function getVitals() {
  try {
    const data = sessionStorage.getItem('capturedVitals');
    return data ? JSON.parse(data) : null;
  } catch (error) {
    console.error('Error getting vitals from sessionStorage:', error);
    return null;
  }
}

// ============== Conversation Context Storage ==============

/**
 * Save conversation context from check-in for triage continuation
 * @param {Object} conversationData - Contains messages, subjective_data, subjective_summary
 */
export function saveConversationContext(conversationData) {
  try {
    const data = {
      ...conversationData,
      timestamp: new Date().toISOString(),
    };
    sessionStorage.setItem('conversationContext', JSON.stringify(data));
  } catch (error) {
    console.error('Error saving conversation context:', error);
  }
}

/**
 * Get saved conversation context (valid for 10 minutes)
 * @returns {Object|null} Conversation data or null if expired/not found
 */
export function getConversationContext() {
  try {
    const data = sessionStorage.getItem('conversationContext');
    if (!data) return null;

    const parsed = JSON.parse(data);
    const timestamp = new Date(parsed.timestamp);
    const now = new Date();
    const tenMinutes = 10 * 60 * 1000;

    if (now - timestamp > tenMinutes) {
      sessionStorage.removeItem('conversationContext');
      return null;
    }

    return parsed;
  } catch (error) {
    console.error('Error getting conversation context:', error);
    return null;
  }
}

/**
 * Clear conversation context (after triage is complete)
 */
export function clearConversationContext() {
  try {
    sessionStorage.removeItem('conversationContext');
  } catch (error) {
    console.error('Error clearing conversation context:', error);
  }
}

/**
 * Check if there's a pending triage (has both vitals and conversation context)
 * @returns {Object|null} {vitals, conversationContext} or null
 */
export function getPendingTriage() {
  const vitals = getVitals();
  const context = getConversationContext();
  
  if (!vitals || !context) return null;
  
  // Check timestamps are within 2 minutes of each other (same session)
  const vitalsTime = new Date(vitals.timestamp || Date.now());
  const contextTime = new Date(context.timestamp);
  const twoMinutes = 2 * 60 * 1000;
  
  if (Math.abs(vitalsTime - contextTime) > twoMinutes) {
    // Data from different sessions, clear old data
    clearConversationContext();
    return null;
  }
  
  return { vitals, conversationContext: context };
}

/**
 * Clear all triage-related data
 */
export function clearTriageData() {
  try {
    sessionStorage.removeItem('capturedVitals');
    sessionStorage.removeItem('conversationContext');
    sessionStorage.removeItem('latestAnalysis');
  } catch (error) {
    console.error('Error clearing triage data:', error);
  }
}
