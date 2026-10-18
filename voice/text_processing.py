
import re
import html


def clean_for_speech(text: str) -> str:
    """Convert Markdown-formatted AI responses into spoken text."""

    if not text:
        return ""

    text = html.unescape(text)

    # Remove fenced code blocks.
    text = re.sub(
        r"```[\s\S]*?```",
        " Code example omitted. ",
        text
    )

    # Convert Markdown links to their readable labels.
    text = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        text
    )

    # Remove Markdown heading markers.
    text = re.sub(
        r"(?m)^\s{0,3}#{1,6}\s+",
        "",
        text
    )

    # Remove unordered list markers.
    text = re.sub(
        r"(?m)^\s*[-*+]\s+",
        "",
        text
    )

    # Remove numbered list markers.
    text = re.sub(
        r"(?m)^\s*\d+[.)]\s+",
        "",
        text
    )

    # Remove bold, italic and inline code markers.
    text = text.replace("**", "")
    text = text.replace("__", "")
    text = text.replace("`", "")
    text = text.replace("*", "")

    # Remove Markdown blockquote markers.
    text = re.sub(
        r"(?m)^\s*>\s?",
        "",
        text
    )

    # Normalize whitespace.
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\.{2,}", ".", text)

    return text.strip(" .")


if __name__ == "__main__":
    sample = """
    **1. நரம்புகள் (Neurons)**

    * **நரம்புகள் என்றால் என்ன?**
      இவை தகவல்களை செயலாக்குகின்றன.

    **2. அடுக்குகள் (Layers)**

    * உள்ளீட்டு அடுக்கு
    * மறைக்கப்பட்ட அடுக்கு
    """

    print(clean_for_speech(sample))
