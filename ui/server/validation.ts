const REQUIRED_FIELDS = new Set(['id', 'prompt', 'agent_type', 'scoring_method']);

const SCORING_FIELDS: Record<string, Set<string>> = {
  text_match: new Set(['expected', 'match_mode']),
  llm_judge: new Set(),
  tool_trace: new Set(['expected_trace']),
};

export function validateCase(caseData: Record<string, unknown>, filename: string): string[] {
  const errors: string[] = [];
  const keys = new Set(Object.keys(caseData));

  const missing = [...REQUIRED_FIELDS].filter((f) => !keys.has(f));
  if (missing.length > 0) {
    errors.push(`${filename}: missing required fields: ${missing.join(', ')}`);
  }

  const scoring = (caseData.scoring_method as string) || '';
  if (scoring in SCORING_FIELDS) {
    const missingScoring = [...SCORING_FIELDS[scoring]].filter((f) => !keys.has(f));
    if (missingScoring.length > 0) {
      errors.push(`${filename}: scoring_method '${scoring}' requires fields: ${missingScoring.join(', ')}`);
    }
  } else if (scoring) {
    errors.push(`${filename}: unknown scoring_method '${scoring}'`);
  }

  return errors;
}
