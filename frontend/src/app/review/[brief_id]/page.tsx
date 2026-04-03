// frontend/src/app/review/[brief_id]/page.tsx
// ─────────────────────────────────────────────────────────────────────────────
// The HITL Review Interface — the most important page in the system.
// Spec §4.1: Three-panel layout.
//
// LAYOUT:
//   ┌──────────────────┬──────────────────┬──────────────────┐
//   │  LEFT PANEL      │  CENTRE PANEL    │  RIGHT PANEL     │
//   │                  │                  │                  │
//   │  PosterPreview   │  QAReport        │  ScoreForm       │
//   │  (1:1 platform   │  (pass/fail per  │  (4 sliders,     │
//   │   dimension)     │   check)         │   1-5 each)      │
//   │                  │                  │                  │
//   │  VersionHistory  │  BriefSummary    │  FeedbackBox     │
//   │  (thumbnails of  │  (original brief │                  │
//   │   all versions)  │   that was sent) │  ActionButtons   │
//   │                  │                  │  [Approve]       │
//   │                  │                  │  [Request Rev.]  │
//   │                  │                  │  [Reject]        │
//   └──────────────────┴──────────────────┴──────────────────┘
//
// DATA FLOW:
//   1. On load: GET /poster/review/{brief_id} → fills all three panels
//   2. Reviewer scores → ScoreForm computes average → enables/disables Approve button
//   3. On Approve: POST /poster/review/{brief_id}/approve → graph resumes → publish
//   4. On Revise:  POST /poster/review/{brief_id}/revise  → graph resumes → designer
//   5. On Reject:  POST /poster/review/{brief_id}/reject  → graph ends
//
// KEY UI RULE (spec §4.2):
//   Approve button is DISABLED until:
//     - All 4 scores are filled in
//     - Average >= 3.5
//     - No individual score equals 1
// ─────────────────────────────────────────────────────────────────────────────

export default function ReviewPage({ params }: { params: { brief_id: string } }) {
  return <div>Review interface for brief {params.brief_id} — implement three-panel layout here</div>
}
