// frontend/src/components/QAReport.tsx
// ─────────────────────────────────────────────────────────────────────────────
// Centre panel — shows the QA Agent's automated pre-flight check results.
// Spec §4.1: "Pass/fail status for each automated check with confidence score"
//
// PROPS:
//   qaReport: {
//     brand_colours: boolean,      // hex comparison pass/fail
//     logo_placement: boolean,     // within safe zones
//     contrast_ratio: number,      // >= 4.5:1 for WCAG AA
//     restricted_content: boolean, // no sensitive imagery
//     dimensions: boolean,         // correct platform dimensions
//     text_rendering: boolean,     // Sinhala/Tamil renders correctly
//     overall_confidence: number   // 0.0 – 1.0
//   }
//
// WHAT TO BUILD:
//   - A list of check items, each showing: check name + PASS (green) / FAIL (red) badge
//   - Overall confidence score as a large number (e.g., "87% confident")
//   - A note: "If confidence < 60%, the AI regenerated this poster automatically"
//
// WHY THIS PANEL MATTERS:
//   Reviewers should NOT spend time checking brand colours manually.
//   The QA Agent already did that. The reviewer's job is creative + cultural judgement.
// ─────────────────────────────────────────────────────────────────────────────

export default function QAReport() {
  return <div>QAReport — implement pass/fail checklist and confidence score</div>
}
