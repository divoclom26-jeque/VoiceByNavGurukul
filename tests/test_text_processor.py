import pytest
from app.core.text_processor import TextProcessor


def test_clean_markdown_elements():
    raw_md = """
# Chapter 1: The Odyssey

---

Here is a paragraph with **bold text** and *italic words*, along with `inline_code`.
Check this link: [OpenAI](https://openai.com) and this image: ![diagram](https://example.com/pic.png).

> This is a famous blockquote.

- Bullet item one
- Bullet item two
1. Numbered item one
2. Numbered item two

***
```python
def secret_function():
    pass
```
The final thought.
"""
    cleaned = TextProcessor.clean_markdown(raw_md)

    assert "#" not in cleaned
    assert "---" not in cleaned
    assert "***" not in cleaned
    assert "**" not in cleaned
    assert "*" not in cleaned
    assert "`" not in cleaned
    assert "https://" not in cleaned
    assert "secret_function" not in cleaned  # Code block omitted
    assert "OpenAI" in cleaned
    assert "Bullet item one" in cleaned
    assert "Numbered item one" in cleaned
    assert "This is a famous blockquote." in cleaned


def test_abbreviation_normalization():
    text = "Dr. Smith and Mr. Brown met Prof. Davis at the univ. dept. vs. the committee."
    cleaned = TextProcessor.normalize_abbreviations(text)

    assert "Doctor" in cleaned
    assert "Mister" in cleaned
    assert "Professor" in cleaned
    assert "university" in cleaned
    assert "department" in cleaned
    assert "versus" in cleaned


def test_symbols_and_currency_normalization():
    text = "The cost was $25.50 and ₹500, with a discount of 15% for #1 customer & friends @ noon."
    cleaned = TextProcessor.normalize_symbols(text)

    assert "25.50 dollars" in cleaned
    assert "500 rupees" in cleaned
    assert "15 percent" in cleaned
    assert "number 1" in cleaned
    assert " and " in cleaned
    assert " at " in cleaned


def test_smart_chunker_sentence_boundaries():
    text = (
        "Alice was beginning to get very tired of sitting by her sister on the bank. "
        "Once or twice she had peeped into the book her sister was reading, but it had no pictures or conversations in it. "
        "What is the use of a book, thought Alice, without pictures or conversations?"
    )
    blocks = TextProcessor.split_into_blocks(text, max_chars=120)

    assert len(blocks) >= 2
    for b in blocks:
        assert len(b) <= 120
        assert any(char.isalnum() for char in b)


def test_smart_chunker_hindi_danda():
    text = (
        "एक बार की बात है। एक छोटे से गाँव में एक किसान रहता था। "
        "वह बहुत परिश्रमी और ईमानदार व्यक्ति था। क्या आप जानते हैं कि उसकी कहानी क्या थी? "
        "वह हर सुबह सूर्योदय से पहले उठकर अपने खेतों की देखभाल करता था।"
    )
    blocks = TextProcessor.split_into_blocks(text, max_chars=80)

    assert len(blocks) >= 3
    for b in blocks:
        assert len(b) <= 80
