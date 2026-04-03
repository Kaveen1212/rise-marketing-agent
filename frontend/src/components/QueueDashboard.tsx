// frontend/src/components/QueueDashboard.tsx
// ─────────────────────────────────────────────────────────────────────────────
// Dashboard page — pipeline status count tiles + pending review list.
// Spec §4.1: Marketing Head sees full queue.
//
// PROPS:
//   queueStatus: {
//     generating: number,
//     pending_review: number,
//     approved: number,
//     scheduled: number,
//     published_today: number
//   }
//
// WHAT TO BUILD:
//   - A row of 5 stat tiles (one per status), each with a count and colour
//   - Below: a list of review cards for posters in "pending_review"
//   - Each card: poster thumbnail, topic, platform badges, time waiting, → Review button
//   - Clicking Review → navigates to /review/[brief_id]
//
// AUTO-REFRESH:
//   Use setInterval or React Query's refetchInterval to refresh every 30 seconds.
//   Show a "Last updated X seconds ago" indicator.
// ─────────────────────────────────────────────────────────────────────────────

export default function QueueDashboard() {
  return <div>QueueDashboard — implement status tiles and pending review list</div>
}
