// Typed client for the Cinemory API.

export interface ReelRequest {
  name: string;
  chapters: number;
  per_chapter: number;
  occasion?: string;
}

export interface ReelResponse {
  reel_name: string;
  occasion?: string;
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

export interface Occasion {
  key: string;
  label: string;
  music_style: string;
  tempo: number;
  seconds_per_clip: number;
  transition: string;
  title_style: string;
  aspect_ratio: string;
}

export class CinemoryClient {
  constructor(private readonly baseUrl: string) {}

  async health(): Promise<Health> {
    const res = await fetch(`${this.baseUrl}/health`);
    if (!res.ok) throw new Error(`health failed: ${res.status}`);
    return (await res.json()) as Health;
  }

  async occasions(): Promise<Occasion[]> {
    const res = await fetch(`${this.baseUrl}/occasions`);
    if (!res.ok) throw new Error(`occasions failed: ${res.status}`);
    return ((await res.json()) as { occasions: Occasion[] }).occasions;
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
