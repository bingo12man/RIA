
from app.services.transliteration import tamil_to_tanglish


def test_common_tamil_sentence():
    assert tamil_to_tanglish(
        "எனக்கு தமிழ் தெரியும்"
    ) == "enakku tamil theriyum"


def test_conversational_tamil():
    assert tamil_to_tanglish(
        "நீங்க எப்படி இருக்கீங்க?"
    ) == "neenga epdi irukkeenga?"


def test_natural_tanglish():
    assert tamil_to_tanglish(
        "நான் நல்லா இருக்கேன்"
    ) == "naan nalla irukken"


def test_english_unchanged():
    assert tamil_to_tanglish(
        "Hello RIA"
    ) == "Hello RIA"


def test_long_tanglish_sentence():
    text = (
        "நீங்க ரொம்ப சோர்வாக இருக்கீங்களா? "
        "வேலை மற்றும் ப்ராஜெக்ட்ல பேலன்ஸ் பண்றது கஷ்டமா இருக்குதா? "
        "கொஞ்சம் ரெஸ்ட் எடுங்க. நான் இருக்கேன்."
    )

    result = tamil_to_tanglish(text)

    assert "sorva" in result
    assert "project-la" in result
    assert "balance" in result
    assert "panradhu" in result
    assert "rest edunga" in result
    assert not any("\u0B80" <= c <= "\u0BFF" for c in result)
