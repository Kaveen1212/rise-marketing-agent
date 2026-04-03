// frontend/src/hooks/useReview.ts
// ─────────────────────────────────────────────────────────────────────────────
// React hook that manages all state for the review interface page.
// The review/[brief_id]/page.tsx should be a "dumb" component that just
// passes data from this hook down to the panels.
//
// WHAT TO BUILD:
//
//   function useReview(briefId: string) {
//     // State
//     const [detail, setDetail] = useState<ReviewDetail | null>(null)
//     const [scores, setScores] = useState<Partial<ReviewScores>>({})
//     const [feedback, setFeedback] = useState("")
//     const [isSubmitting, setIsSubmitting] = useState(false)
//     const [error, setError] = useState<string | null>(null)
//
//     // Computed
//     const average = (brand + clarity + visual + cultural) / 4
//     const canApprove = allScoresFilled && noCriticalFail && average >= 3.5
//     const isAmber = average >= 3.5 && average < 4.0
//
//     // Data fetching
//     useEffect(() => {
//       getReviewDetail(briefId).then(setDetail)
//     }, [briefId])
//
//     // Actions
//     const approve = async () => { ... }
//     const revise  = async () => { ... }
//     const reject  = async () => { ... }
//
//     return { detail, scores, feedback, setFeedback, setScore,
//              canApprove, isAmber, isSubmitting, error,
//              approve, revise, reject }
//   }
//
// WHY A CUSTOM HOOK?
//   It keeps all review logic in one testable place.
//   The page component stays clean — it just renders based on hook output.
// ─────────────────────────────────────────────────────────────────────────────

export {}
