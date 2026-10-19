let tokenProvider: (() => Promise<string | null>) | null = null;

export function setTokenProvider(provider: () => Promise<string | null>) {
  tokenProvider = provider;
}

export async function getAccessToken(): Promise<string | null> {
  if (!tokenProvider) return null;
  return tokenProvider();
}
