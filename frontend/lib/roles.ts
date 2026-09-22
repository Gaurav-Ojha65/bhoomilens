import { fetchAuthSession } from "aws-amplify/auth";

export type AppRole = "USER" | "SUPERVISOR";

export async function getCurrentRole(): Promise<AppRole> {
  const session = await fetchAuthSession();
  const claims = session.tokens?.idToken?.payload ?? {};
  const groups = claims["cognito:groups"];
  const normalized = Array.isArray(groups)
    ? groups.map(String).map((g) => g.toUpperCase())
    : typeof groups === "string"
      ? groups.split(",").map((g) => g.trim().toUpperCase())
      : [];

  return normalized.includes("SUPERVISOR") ? "SUPERVISOR" : "USER";
}
