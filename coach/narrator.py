from __future__ import annotations

import json
import anthropic


def build_system_prompt(athlete: dict) -> str:
    """Build the narrator system prompt with coach persona and athlete context.

    The system prompt defines WHO the coach is and HOW it communicates.
    The coaching JSON (injected per-request in the user message) provides
    WHAT to talk about.
    """
    race = athlete.get("race", {})
    name = athlete.get("name", "athlete")
    altitude = athlete.get("altitude_m", 0)
    weight = athlete.get("weight_kg", "?")
    hr_zones = athlete.get("hr_zones", {})
    history = athlete.get("history", {})
    recent = history.get("recent_race", {})

    hr_info = ""
    if hr_zones:
        hr_info = f"""
- HR zones: Z1 {hr_zones.get('z1', [])}, Z2 {hr_zones.get('z2', [])}, Z3 {hr_zones.get('z3', [])}, Z4 {hr_zones.get('z4', [])}, Z5 {hr_zones.get('z5', [])} bpm"""

    recent_info = ""
    if recent:
        recent_info = f"""
- Recent race: {recent.get('distance_km', '?')}km / {recent.get('vert_m', '?')}m D+ in {recent.get('time', '?')} at {recent.get('avg_hr', '?')}bpm avg HR
- Baseline weekly volume: {history.get('baseline_weekly_km', '?')}km"""

    return f"""You are an experienced trail and ultramarathon running coach. You specialize in mountain ultras and are deeply familiar with the Copper Canyons (Barrancas del Cobre) and Tarahumara running culture.

## Your Athlete
- Name: {name}
- Weight: {weight}kg
- Training altitude: {altitude}m (Toluca, Mexico)
- Target race: {race.get('name', 'Unknown')} — {race.get('distance_km', '?')}km / {race.get('vert_m', '?')}m D+
- Race date: {race.get('date', 'TBD')}{hr_info}{recent_info}

## Training Plan Overview
- 30-week periodized plan: Base (weeks 1-12), Specific (13-27), Taper (28-30)
- Every 4th week is a recovery week (25-30% volume reduction)
- Plan started March 2, 2026
- The coaching data includes FULL training history (all completed weeks with actual vs planned), current week analysis, and upcoming plan targets. Use this to track progression and identify patterns.

## Your Coaching Style
- Direct and honest — you don't sugarcoat bad weeks, but you frame everything constructively
- Data-informed but not data-obsessed — lead with insight, back with numbers
- You know when to push and when to hold back
- You use trail running language naturally (vert, bonk, negative split, power hike, send it)
- You're aware {name} trains at {altitude}m altitude — factor this into advice
- You can reference specific past weeks from the training_history data to show patterns
- Keep responses conversational and concise (2-4 short paragraphs for reports, 1-2 for questions)

## HARD CONSTRAINTS — you MUST follow these:
- NEVER contradict the coaching data provided. The numbers are ground truth.
- NEVER invent or fabricate metrics, distances, times, or data not present in the coaching JSON.
- NEVER give medical advice. If an injury or health concern arises, say "see a physio" or "check with your doctor."
- You CAN add motivational context, race perspective, and connect dots between weeks.
- You CAN ask follow-up questions to clarify ambiguous input.
- If you don't have enough data to answer, say so honestly.

## Response Format
- Use plain text, not markdown (this will be displayed in a chat interface)
- No headers, bullet points, or formatting — write like you're texting your athlete
- Use line breaks between paragraphs for readability"""


class Narrator:
    """Claude API wrapper for translating coaching data into natural language.

    This is the ONLY component that calls the Claude API.
    It receives pre-digested CoachingOutput JSON — never raw activity data.
    """

    def __init__(self, api_key: str, athlete: dict, model: str = "claude-haiku-4-5-20251001"):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._system_prompt = build_system_prompt(athlete)
        self._model = model

    def narrate_report(self, coaching_data: dict) -> str:
        """Generate a coaching narrative for a weekly report.

        Args:
            coaching_data: The output of CoachingOutput.to_dict()

        Returns:
            Natural language coaching narrative, or a fallback message on API failure.
        """
        user_message = (
            "Here is this week's coaching data. Write a coaching narrative "
            "covering: how the week went (compliance), current readiness, "
            "any trends worth noting, and what to focus on next. "
            "Keep it conversational and concise.\n\n"
            f"COACHING DATA:\n{json.dumps(coaching_data, indent=2, default=str)}"
        )
        return self._call_api(user_message)

    def answer_question(
        self,
        question: str,
        category: str,
        coaching_data: dict,
    ) -> str:
        """Answer a user question using coaching data as context.

        Args:
            question: The user's natural language question.
            category: Question type from classifier ('data', 'coaching',
                      'knowledge', 'general').
            coaching_data: The output of CoachingOutput.to_dict()

        Returns:
            Natural language answer, or a fallback message on API failure.
        """
        category_guidance = {
            "data": "The athlete is asking a data question. Answer concisely with the specific numbers from the coaching data. Don't editorialize unless the numbers warrant a brief note.",
            "coaching": "The athlete is asking for coaching advice. Use the readiness, trends, and adjustment data to give a thoughtful recommendation. Be direct.",
            "knowledge": "The athlete is asking a knowledge question about training, nutrition, recovery, or injury. Draw on your coaching expertise to answer. Remember your hard constraints — no medical advice.",
            "general": "The athlete is asking a general question. Answer naturally, staying in your role as their trail running coach.",
        }

        guidance = category_guidance.get(category, category_guidance["general"])

        user_message = (
            f"QUESTION TYPE: {category}\n"
            f"GUIDANCE: {guidance}\n\n"
            f"ATHLETE'S QUESTION: {question}\n\n"
            f"CURRENT COACHING DATA:\n{json.dumps(coaching_data, indent=2, default=str)}"
        )
        return self._call_api(user_message)

    def stream_answer(
        self,
        question: str,
        category: str,
        coaching_data: dict,
        history: list[dict] | None = None,
    ):
        """Yield tokens from Claude streaming API.

        Same inputs as answer_question(), but yields individual text deltas
        for SSE forwarding. Falls back to a single error token on failure.

        Args:
            history: Recent conversation exchanges from load_history().
                     Each entry has 'question' and 'response' keys.
        """
        category_guidance = {
            "data": "The athlete is asking a data question. Answer concisely with the specific numbers from the coaching data. Don't editorialize unless the numbers warrant a brief note.",
            "coaching": "The athlete is asking for coaching advice. Use the readiness, trends, and adjustment data to give a thoughtful recommendation. Be direct.",
            "knowledge": "The athlete is asking a knowledge question about training, nutrition, recovery, or injury. Draw on your coaching expertise to answer. Remember your hard constraints — no medical advice.",
            "general": "The athlete is asking a general question. Answer naturally, staying in your role as their trail running coach.",
        }

        guidance = category_guidance.get(category, category_guidance["general"])

        # Build messages array with conversation history
        messages: list[dict] = []
        if history:
            for msg in history:
                messages.append({"role": "user", "content": msg["question"]})
                messages.append({"role": "assistant", "content": msg["response"]})

        user_message = (
            f"QUESTION TYPE: {category}\n"
            f"GUIDANCE: {guidance}\n\n"
            f"ATHLETE'S QUESTION: {question}\n\n"
            f"CURRENT COACHING DATA:\n{json.dumps(coaching_data, indent=2, default=str)}"
        )
        messages.append({"role": "user", "content": user_message})

        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=1024,
                system=self._system_prompt,
                messages=messages,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                        yield event.delta.text
        except Exception as e:
            yield f"Coach narrative unavailable (error: {e})."

    def _call_api(self, user_message: str) -> str:
        """Make a single Claude API call with error handling.

        Returns the response text, or a fallback message on failure.
        """
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text
        except Exception as e:
            return (
                f"Coach narrative unavailable (API error: {e}). "
                "The structured coaching data was saved successfully — "
                "you can regenerate the narrative later with: "
                "python coach.py report --week N --regenerate"
            )
