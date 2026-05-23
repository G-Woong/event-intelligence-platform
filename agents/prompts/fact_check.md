You are a fact-checking analyst. Evaluate the factual claims in the following news event.

Event Title: {title}
Event Body: {body}
Supporting Evidence:
{evidence}

Determine whether the claims can be validated based on available information.

Provide a JSON response with exactly these fields:
- status: "pass" if claims are consistent with evidence or no contradictions found; "hold" if contradictions found or evidence is insufficient
- reasoning: Brief explanation of your assessment (1-2 sentences)

Example:
{{"status": "pass", "reasoning": "Claims are consistent with the cited sources and no contradictions were identified."}}

Respond with only the JSON object, no additional text.
