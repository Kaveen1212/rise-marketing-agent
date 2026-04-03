// frontend/src/app/page.tsx
// ─────────────────────────────────────────────────────────────────────────────
// Marketing Dashboard — the main queue view.
// Spec §4.1: Marketing Head sees full queue: pending review, approved, scheduled, published, rejected.
//
// WHAT TO BUILD HERE:
//   - Fetch GET /poster/queue/status on load → show counts per stage
//   - Fetch GET /poster/review/queue → show cards for posters awaiting review
//   - Each card links to /review/[brief_id] for the full review interface
//   - Auto-refresh every 30 seconds (the queue changes as briefs come in)
//
// COMPONENTS TO USE:
//   <QueueDashboard />   — the status count tiles (generating/pending/approved/published)
//   <ReviewCard />       — one card per poster awaiting review (thumbnail + metadata)
// ─────────────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  return <div>Dashboard — implement QueueDashboard here</div>
}
