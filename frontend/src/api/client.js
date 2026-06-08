const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return response.json();
}

export function getHealth() {
  return request("/health");
}

export function searchGraphNodes(payload) {
  return request("/graph/nodes/search", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getGraphRelationships(payload) {
  return request("/graph/relationships/connected", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function sendAgentChat(payload) {
  return request("/agent/chat", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listExperimentDatasets() {
  return request("/datasets");
}

export function createExperimentDataset(payload) {
  return request("/datasets", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateExperimentDataset(datasetId, payload) {
  return request(`/datasets/${datasetId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function deleteExperimentDataset(datasetId) {
  const response = await fetch(`${API_BASE}/datasets/${datasetId}`, {
    method: "DELETE"
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
}

export async function streamAgentChat(payload, onEvent) {
  const response = await fetch(`${API_BASE}/agent/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok || !response.body) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() || "";
    for (const part of parts) {
      const event = parseSseEvent(part);
      if (event) {
        await onEvent(event);
      }
    }
  }

  buffer += decoder.decode();
  const event = parseSseEvent(buffer);
  if (event) {
    await onEvent(event);
  }
}

function parseSseEvent(block) {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .join("\n");

  if (!data) {
    return null;
  }

  try {
    return JSON.parse(data);
  } catch {
    return { event: "message", answer: data };
  }
}

export async function analyzeOmicsFile(file, payload = {}) {
  const form = new FormData();
  form.append("file", file);
  form.append("request", JSON.stringify(payload));

  const response = await fetch(`${API_BASE}/omics-stats/analyze`, {
    method: "POST",
    body: form
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return response.json();
}

export async function previewOmicsFile(file) {
  const form = new FormData();
  form.append("file", file);

  const response = await fetch(`${API_BASE}/omics-stats/preview`, {
    method: "POST",
    body: form
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return response.json();
}
