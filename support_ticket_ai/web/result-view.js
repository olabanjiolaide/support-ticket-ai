// Presentation of recorded decision fields; never an explanation of learned features.
const numeric = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
const cutoff = (value) => numeric(value) && value > 0;
export const displayScore = (value) => numeric(value) ? value.toFixed(3) : "Not provided";

export function describeResult(result) {
  const withheld = result.decision === "abstain";
  const reasons = [];
  if (withheld) {
    if (result.input_truncated === true) reasons.push({code: "truncated", title: "Full message not considered",
      description: "The semantic encoder reached its input limit. Read the full original message before choosing a category."});
    if (numeric(result.scope_score) && cutoff(result.scope_threshold) && result.scope_score < result.scope_threshold)
      reasons.push({code: "scope", title: "Supported-request check withheld this message",
        description: "The scope score is below its configured cutoff. Check whether this request belongs to the supported categories; this does not prove it is unrelated."});
    if (numeric(result.uncalibrated_probability) && cutoff(result.abstention_threshold) && result.uncalibrated_probability < result.abstention_threshold)
      reasons.push({code: "category", title: "Category score below the review cutoff",
        description: "The highest category score did not reach the configured cutoff for showing a suggestion."});
    if (result.multiple_requests_detected === true) reasons.push({code: "multiple", title: "Separate-request check flagged the message",
      description: "The experimental check found evidence of requests in different categories. Review the full message to confirm whether separate handling is needed."});
    if (!reasons.length) reasons.push({code: "policy", title: "The service withheld a category",
      description: "No specific withholding condition is available in the returned fields. Consult the recorded review note in model details."});
  }
  const multiple = reasons.some((r) => r.code === "multiple");
  return {withheld, status: withheld ? "Needs manual classification" : "Category suggested",
    title: withheld ? "Category withheld" : result.suggested_category.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
    summary: withheld ? "Choose a category after reading the full request." : "A suggested handoff, ready for your review.",
    reasons, nextTitle: withheld ? "Read the request and classify manually" : "Confirm the category before routing",
    nextDescription: multiple ? "Check each requested outcome and decide whether it needs its own category. No request has been routed."
      : withheld ? "Use the complete message and the checks above. Ask the customer for context only if information is missing."
      : "Compare the category with the customer’s actual request. A returned suggestion can still be wrong; no request has been routed.",
    recordedNote: typeof result.review_reason === "string" && result.review_reason.trim() ? result.review_reason : "No review note was provided."};
}

export function technicalFacts(result) {
  return [
    ["Category score · uncalibrated", displayScore(result.uncalibrated_probability)],
    ["Category review cutoff", cutoff(result.abstention_threshold) ? displayScore(result.abstention_threshold) : "Not configured / not provided"],
    ["Scope score · uncalibrated", displayScore(result.scope_score)],
    ["Scope cutoff", cutoff(result.scope_threshold) ? displayScore(result.scope_threshold) : "Not configured / not provided"],
    ["Encoder truncation reported", result.input_truncated === true ? "Yes" : result.input_truncated === false ? "No" : "Not provided"],
    ["Separate-request check", result.multiple_request_check_enabled === true
      ? result.multiple_requests_detected === true ? "Flagged for review" : "Enabled · no flag reported" : "Off / not reported"],
  ];
}
