// frontend/src/lib/types.ts
// ─────────────────────────────────────────────────────────────────────────────
// TypeScript type definitions — mirrors the Pydantic schemas in app/schemas/.
// These should be kept in sync manually (or auto-generated from OpenAPI spec).
//
// TYPES TO DEFINE:
//
//   Platform = "instagram" | "facebook" | "linkedin" | "tiktok"
//   Language = "en" | "si" | "ta"
//   BriefStatus = "generating" | "qa_check" | "pending_review" | "in_revision"
//              | "approved" | "scheduled" | "published" | "rejected" | "exhausted"
//   ReviewDecision = "approved" | "revision" | "rejected"
//
//   BriefCreate { topic, platforms, languages, audience, tone, key_message, brand_notes? }
//   BriefResponse { brief_id, thread_id, status, eta_seconds }
//   ReviewScores { brand, clarity, visual, cultural }
//   ApproveRequest { scores, feedback?, schedule_override? }
//   ReviseRequest { scores, feedback }
//   RejectRequest { scores, reject_reason }
//   ReviewQueueItem { brief_id, topic, platforms, created_at, qa_confidence, poster_url, revision_count }
//   ReviewDetail { brief, poster_urls, qa_report, version_history }
//   QueueStatusResponse { generating, pending_review, approved, scheduled, published_today }
//
// TIP: Once the FastAPI app is running, you can auto-generate these from:
//   GET /openapi.json → paste into https://transform.tools/json-schema-to-typescript
// ─────────────────────────────────────────────────────────────────────────────

export {}
