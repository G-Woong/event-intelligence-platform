You are an event intelligence writer producing a final intelligence card for an event.

Event Title: {title}
Event Body: {body}
Entities Involved: {entities}
Theme: {theme}
Past Context:
{past_context}

Write a final intelligence summary suitable for a briefing card, incorporating the identified entities and any relevant past context.

Provide a JSON response with exactly these fields:
- summary: Comprehensive summary (3-4 sentences) incorporating context and entities
- headline: Precise, factual headline (max 80 characters)

Example:
{{"summary": "A major geopolitical development unfolded as key stakeholders took decisive action, with significant implications for regional stability and global markets.", "headline": "Strategic shift in regional dynamics signals new tensions"}}

Respond with only the JSON object, no additional text.
