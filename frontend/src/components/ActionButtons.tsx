// frontend/src/components/ActionButtons.tsx
// ─────────────────────────────────────────────────────────────────────────────
// Right panel (bottom) — the three action buttons.
// Spec §4.1: "Approve & Schedule | Request Revision | Reject"
//
// PROPS:
//   canApprove: boolean         (computed from ScoreForm scores)
//   isAmberApproval: boolean    (average 3.5–3.9 — show soft warning)
//   isSubmitting: boolean       (disable all buttons during API call)
//   revisionCount: number       (disable Request Revision if >= 3)
//   onApprove: () => void
//   onRevise: () => void
//   onReject: () => void
//
// BUTTON STATES:
//
//   [Approve & Schedule]
//     - Disabled if canApprove === false
//     - Green if average >= 4.0
//     - Amber + warning tooltip if average is 3.5–3.9
//     - Label: "Approve & Schedule" (not just "Approve" — reminds reviewer it will publish)
//
//   [Request Revision]
//     - Disabled if revisionCount >= 3 (show tooltip: "Max revisions reached")
//     - Requires feedback text to be non-empty (validated in parent)
//     - Orange/yellow colour
//
//   [Reject]
//     - Always enabled (reviewer can always reject)
//     - Requires reject_reason to be non-empty
//     - Red colour, confirm dialog before submitting
// ─────────────────────────────────────────────────────────────────────────────

export default function ActionButtons() {
  return <div>ActionButtons — implement approve/revise/reject with correct disabled states</div>
}
