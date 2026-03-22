from __future__ import annotations

from coach.classifier import classify_question


class TestClassifyQuestion:
    """Tests for keyword-based question classification."""

    # Data questions — ask about specific metrics or past weeks
    def test_data_question_vert(self):
        assert classify_question("What was my vert last week?") == "data"

    def test_data_question_distance(self):
        assert classify_question("How far did I run this week?") == "data"

    def test_data_question_compliance(self):
        assert classify_question("What's my compliance score?") == "data"

    def test_data_question_hr(self):
        assert classify_question("What was my average heart rate?") == "data"

    def test_data_question_long_run(self):
        assert classify_question("How long was my long run?") == "data"

    def test_data_question_gym(self):
        assert classify_question("How many gym sessions did I do?") == "data"

    # Coaching questions — ask for advice or recommendations
    def test_coaching_question_push(self):
        assert classify_question("Should I push harder this week?") == "coaching"

    def test_coaching_question_ready(self):
        assert classify_question("Am I ready for more volume?") == "coaching"

    def test_coaching_question_skip(self):
        assert classify_question("Can I skip my rest day?") == "coaching"

    def test_coaching_question_adjust(self):
        assert classify_question("Should I adjust my plan?") == "coaching"

    def test_coaching_question_how_am_i(self):
        assert classify_question("How am I doing?") == "coaching"

    def test_coaching_question_hows_my_week(self):
        assert classify_question("How's my week looking?") == "coaching"

    # Knowledge questions — nutrition, injury, recovery, strength
    def test_knowledge_question_nutrition(self):
        assert classify_question("What should I eat before a long run?") == "knowledge"

    def test_knowledge_question_injury(self):
        assert classify_question("My knee hurts after downhills") == "knowledge"

    def test_knowledge_question_recovery(self):
        assert classify_question("How should I recover after a hard week?") == "knowledge"

    def test_knowledge_question_strength(self):
        assert classify_question("What strength exercises should I do?") == "knowledge"

    def test_knowledge_question_hydration(self):
        assert classify_question("How much water should I drink at altitude?") == "knowledge"

    # General — unmatched falls through
    def test_general_question(self):
        assert classify_question("Tell me about the Tarahumara") == "general"

    def test_general_greeting(self):
        assert classify_question("Hello coach") == "general"

    # Case insensitivity
    def test_case_insensitive(self):
        assert classify_question("WHAT WAS MY VERT?") == "data"

    # Empty / whitespace
    def test_empty_string(self):
        assert classify_question("") == "general"
