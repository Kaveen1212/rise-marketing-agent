// frontend/src/lib/api.ts
// ─────────────────────────────────────────────────────────────────────────────
// Typed API client — wraps all fetch() calls to the FastAPI backend.
// All components should import from here, never use fetch() directly.
//
// BASE URL: process.env.NEXT_PUBLIC_API_URL (e.g., http://localhost:8000/v1/poster)
//
// FUNCTIONS TO IMPLEMENT:
//
//   submitBrief(brief: BriefCreate): Promise<BriefResponse>
//     → POST /poster/briefs
//
//   getBriefStatus(briefId: string): Promise<BriefDetail>
//     → GET /poster/briefs/{brief_id}
//
//   getReviewQueue(): Promise<{ posters: ReviewQueueItem[], count: number }>
//     → GET /poster/review/queue
//
//   getReviewDetail(briefId: string): Promise<ReviewDetail>
//     → GET /poster/review/{brief_id}
//
//   approvePoster(briefId: string, payload: ApproveRequest): Promise<ApproveResponse>
//     → POST /poster/review/{brief_id}/approve
//
//   revisePoster(briefId: string, payload: ReviseRequest): Promise<ReviseResponse>
//     → POST /poster/review/{brief_id}/revise
//
//   rejectPoster(briefId: string, payload: RejectRequest): Promise<RejectResponse>
//     → POST /poster/review/{brief_id}/reject
//
//   getQueueStatus(): Promise<QueueStatusResponse>
//     → GET /poster/queue/status
//
// AUTH PATTERN:
//   Every function adds: Authorization: Bearer ${getToken()}
//   getToken() reads from localStorage or Supabase auth session
//
// ERROR HANDLING:
//   If response.ok === false, throw an ApiError with status + message.
//   Components catch ApiError and show user-friendly messages.
// ─────────────────────────────────────────────────────────────────────────────

export {}
