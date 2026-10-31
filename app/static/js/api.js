export class ApiError extends Error {
  constructor(code, message, status) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function parseResponse(response) {
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const errObj = data && data.error ? data.error : null;
    const code = errObj?.code || "request_failed";
    const message =
      errObj?.message ||
      (response.status === 422
        ? "Please enter a valid display name (1–20 characters)."
        : "Unable to complete request.");
    throw new ApiError(code, message, response.status);
  }
  return data;
}

export async function createRoom(playerName) {
  const response = await fetch("/api/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_name: playerName }),
  });
  return parseResponse(response);
}

export async function joinRoom(roomCode, playerName, existingToken = null) {
  const cleanCode = encodeURIComponent(roomCode.trim().toUpperCase());
  const headers = { "Content-Type": "application/json" };
  if (existingToken) {
    headers["X-Player-Token"] = existingToken;
  }
  const response = await fetch(`/api/rooms/${cleanCode}/join`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      player_name: playerName || "",
      player_token: existingToken || null,
    }),
  });
  return parseResponse(response);
}

export async function getPublicRoom(roomCode) {
  const cleanCode = encodeURIComponent(roomCode.trim().toUpperCase());
  const response = await fetch(`/api/rooms/${cleanCode}`, {
    method: "GET",
  });
  return parseResponse(response);
}
