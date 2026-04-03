// frontend/src/components/PosterPreview.tsx
// ─────────────────────────────────────────────────────────────────────────────
// Left panel — shows the poster at actual platform dimensions.
// Spec §4.1: "Poster rendered at 1:1 platform size. Toggle between all generated platform variants"
//
// PROPS:
//   posterUrls: { instagram: string, facebook: string, linkedin: string, tiktok: string }
//   selectedPlatform: "instagram" | "facebook" | "linkedin" | "tiktok"
//   onPlatformChange: (platform: string) => void
//
// PLATFORM DIMENSIONS (from spec):
//   instagram → 1080×1080px (square)
//   facebook  → 1200×630px  (landscape)
//   linkedin  → 1200×627px  (landscape)
//   tiktok    → 1080×1920px (portrait)
//
// IMPORTANT — PRESIGNED URLS:
//   The poster_urls are time-limited S3 presigned URLs (expire in 1 hour).
//   Do NOT cache them in localStorage. Always fetch fresh from the API.
//
// WHAT TO BUILD:
//   - Platform toggle tabs at the top
//   - <img> or <Image> (Next.js) showing the poster for selected platform
//   - Scale down if poster is larger than viewport, but preserve aspect ratio
// ─────────────────────────────────────────────────────────────────────────────

export default function PosterPreview() {
  return <div>PosterPreview — implement platform toggle and image display</div>
}
