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
    sessionStorage.setItem('capturedVitals', JSON.stringify(vitalsData));
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
