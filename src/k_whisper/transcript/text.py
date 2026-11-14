"""Word joining and line width for scripts with and without spaces between words."""

import unicodedata


def is_wide(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F")


def is_unspaced(ch: str) -> bool:
    """Chinese and Japanese are written without spaces between words; Korean is wide too but uses spaces."""
    return is_wide(ch) and not ("ᄀ" <= ch <= "ᇿ" or "㄰" <= ch <= "㆏" or "가" <= ch <= "힯")


def text_width(text: str) -> int:
    """Width in Latin characters: a Chinese, Japanese or Korean character takes the room of two."""
    return sum(2 if is_wide(ch) else 1 for ch in text)


def join_words(words: list[str]) -> str:
    text = ""
    for word in words:
        if text and word and not (is_unspaced(text[-1]) or is_unspaced(word[0])):
            text += " "
        text += word
    return text


def text_pieces(text: str) -> list[str]:
    """Split a text into words; each Chinese or Japanese character counts as a word of its own."""
    pieces: list[str] = []
    for chunk in text.split():
        run = ""
        for ch in chunk:
            if is_unspaced(ch):
                if run:
                    pieces.append(run)
                    run = ""
                pieces.append(ch)
            else:
                run += ch
        if run:
            pieces.append(run)
    return pieces
