export async function getHealth() {
  const response = await fetch("/api/health");
  if (!response.ok) throw new Error("API health check failed");
  return response.json();
}
