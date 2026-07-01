// Typed client for the Cinemory API.

export interface ReelRequest {
  name: string;
  chapters: number;
  per_chapter: number;
}

export interface ReelResponse {
  reel_name: string;
  reel_url: string | null;
  reel_sha256: string;
  manifest_uri: string | null;
  manifest_hash: string;
  steps: number;
}

export interface Health {
  status: string;
  service: string;
  mode: string;
}

export class CinemoryClient {
  constructor(private readonly baseUrl: string) {}

  async health(): Promise<Health> {
    const res = await fetch(`${this.baseUrl}/health`);
    if (!res.ok) throw new Error(`health failed: ${res.status}`);
    return (await res.json()) as Health;
  }

  async createReel(req: ReelRequest): Promise<ReelResponse> {
    const res = await fetch(`${this.baseUrl}/reels`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(`createReel failed: ${res.status}`);
    return (await res.json()) as ReelResponse;
  }
}
