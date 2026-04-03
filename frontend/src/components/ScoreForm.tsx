// frontend/src/components/ScoreForm.tsx
// ─────────────────────────────────────────────────────────────────────────────
// Right panel (top) — the four-dimension scoring form.
// Spec §4.2: "4 dimension sliders (1-5) with descriptive anchors"
//
// PROPS:
//   scores: { brand: number | null, clarity: number | null, visual: number | null, cultural: number | null }
//   onChange: (dimension: string, value: number) => void
//   minApprovalScore: number  (3.5 from settings, passed down from API or env)
//
// DIMENSIONS (spec §4.2):
//   Brand Alignment   — 1: wrong colours/logo/font → 3: correct, minor issues → 5: pixel-perfect
//   Message Clarity   — 1: confusing, garbled      → 3: clear, accurate       → 5: compelling, natural
//   Visual Quality    — 1: blurry, amateur          → 3: clean, readable       → 5: publication-ready
//   Cultural Sensitivity — 1: offensive/tone-deaf  → 3: neutral               → 5: authentically Sri Lankan
//
// APPROVE BUTTON LOGIC (computed here or in parent):
//   const average = (brand + clarity + visual + cultural) / 4
//   const allScored = all four values are non-null
//   const noCriticalFail = no value === 1
//   const canApprove = allScored && noCriticalFail && average >= minApprovalScore
//   const isAmber = average >= 3.5 && average < 4.0  (show soft warning)
//
// WHAT TO BUILD:
//   - 4 slider inputs (range 1-5) OR 5-star radio buttons
//   - Anchor descriptions shown below each slider
//   - Live average score display
//   - Visual feedback: green (>=4.0), amber (3.5–3.9), red (<3.5 or critical fail)
// ─────────────────────────────────────────────────────────────────────────────

export default function ScoreForm() {
  return <div>ScoreForm — implement 4-dimension sliders with threshold logic</div>
}
