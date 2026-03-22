from __future__ import annotations

import re

# Patterns are checked in order; first match wins.
# Each pattern list maps to a question type.

_DATA_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(what|how)\b.*(distance|vert|elevation|km|miles|heart rate|hr|pace|compliance|score|long run|gym session)",
        r"\b(how (far|long|much|many))\b",
        r"\blast (week|month)\b",
        r"\bthis week\b.*\b(number|total|average|avg)\b",
        r"\bstats\b",
    ]
]

_COACHING_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bshould I\b",
        r"\bcan I\b.*\b(skip|push|increase|add|run)\b",
        r"\bam I\b.*\b(ready|on track|doing|overtraining|behind)\b",
        r"\b(adjust|change|modify)\b.*\b(plan|schedule|training)\b",
        r"\bhow('?s| is| am)\b.*\b(my|I|me)\b.*(week|training|doing|progress|look)",
        r"\b(push|back off|maintain|rest|recover)\b.*\?",
        r"\b(ready|readiness|fatigue|tired|fresh)\b",
    ]
]

_KNOWLEDGE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(eat|food|fuel|nutrition|carb|protein|calorie|diet|supplement)\b",
        r"\b(drink|hydrat|water|electrolyte)\b",
        r"\b(injur|pain|hurt|sore|ache|knee|ankle|shin|plantar|achilles|IT band)\b",
        r"\b(recover|recovery|ice|foam roll|massage|sleep)\b",
        r"\b(strength|exercise|stretch|mobility|warm.?up|cool.?down)\b",
        r"\b(altitude|elevation.*(effect|impact|adjust))\b",
    ]
]


def classify_question(question: str) -> str:
    """Classify a user question into a routing category.

    Returns one of: 'data', 'coaching', 'knowledge', 'general'.
    Uses keyword pattern matching — no API calls.
    Unmatched questions return 'general' (narrator handles with full context).
    """
    if not question or not question.strip():
        return "general"

    # Knowledge is checked before coaching: questions like "What should I eat?"
    # contain "should I" but are clearly knowledge queries. Knowledge keywords
    # are strong domain signals and don't overlap with coaching/data patterns.
    for pattern in _KNOWLEDGE_PATTERNS:
        if pattern.search(question):
            return "knowledge"

    # Coaching is checked before data: questions like "Should I push harder
    # this week?" contain metric words ("week") that would false-match data
    # patterns if coaching were checked second.
    for pattern in _COACHING_PATTERNS:
        if pattern.search(question):
            return "coaching"

    for pattern in _DATA_PATTERNS:
        if pattern.search(question):
            return "data"

    return "general"
