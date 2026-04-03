// frontend/src/components/VersionHistory.tsx
// ─────────────────────────────────────────────────────────────────────────────
// Left panel (bottom) — shows thumbnails of all previous poster versions.
// Spec §4.1: "Thumbnails of all previous versions with revision notes"
//
// PROPS:
//   versions: Array<{
//     version_number: number,
//     poster_url: string,          // presigned S3 URL for this version's thumbnail
//     created_at: string,
//     qa_confidence: number,
//     review_decision: "revision" | null,   // null if this is the current version
//     review_feedback: string | null        // the feedback that triggered revision
//   }>
//   currentVersion: number
//   onSelectVersion: (version: number) => void
//
// WHAT TO BUILD:
//   - Horizontal or vertical strip of version thumbnails
//   - Current version highlighted with a border
//   - For past versions: show the revision feedback as a tooltip or expandable note
//   - This tells the reviewer: "the AI has already tried X and fixed Y"
//
// WHY THIS MATTERS:
//   The reviewer can see if the AI is improving across revision cycles.
//   If version 3 looks worse than version 1, they can reject with that context.
// ─────────────────────────────────────────────────────────────────────────────

export default function VersionHistory() {
  return <div>VersionHistory — implement version thumbnails with revision notes</div>
}
