export function calculateRiskLevel(heartRate, hrv, baselineHR, baselineHRV) {
  const hrDeviation = ((heartRate - baselineHR) / baselineHR) * 100;
  const hrvDeviation = ((hrv - baselineHRV) / baselineHRV) * 100;

  let score = 0;
  const factors = [];

  // HR deviation > +20%: add 30 points
  if (hrDeviation > 20) {
    score += 30;
    factors.push({ factor: 'Heart Rate elevated >20%', points: 30 });
  } else if (hrDeviation > 15) {
    score += 15;
    factors.push({ factor: 'Heart Rate elevated >15%', points: 15 });
  }

  // HRV deviation < -30%: add 40 points
  if (hrvDeviation < -30) {
    score += 40;
    factors.push({ factor: 'HRV decreased >30%', points: 40 });
  } else if (hrvDeviation < -20) {
    score += 20;
    factors.push({ factor: 'HRV decreased >20%', points: 20 });
  }

  // Combined risk: HRV < -20% AND HR > +15%
  if (hrvDeviation < -20 && hrDeviation > 15) {
    score += 10;
    factors.push({ factor: 'Combined HR/HRV deviation', points: 10 });
  }

  // Determine level
  let level;
  if (score < 30) {
    level = 'LOW';
  } else if (score < 70) {
    level = 'MEDIUM';
  } else {
    level = 'HIGH';
  }

  return {
    score: Math.min(score, 100),
    level,
    hrDeviation,
    hrvDeviation,
    factors,
  };
}

export function getRiskColor(level) {
  switch (level?.toUpperCase()) {
    case 'HIGH':
      return 'red';
    case 'MEDIUM':
      return 'yellow';
    case 'LOW':
    default:
      return 'green';
  }
}
