"""Evidence-only statistics for a speaking transcript, and the band rounding rule.

Nothing here judges a band. The numbers are counts the model can quote as evidence
when it applies the criteria in the skill's references/criteria.md.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from fractions import Fraction
from typing import Any

# Letters, digits and in-word apostrophes ("don't", "it's").
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")
_SENTENCE_END = re.compile(r"[.!?]+")

# Hesitation sounds and filler phrases, with the pattern each is counted by.
# "kind of" / "sort of" after a determiner ("what kind of music") are ordinary noun
# phrases, not fillers, so they are excluded. "like" is only counted as "like,"
# (followed by a comma): telling filler "like" from the verb or preposition needs
# meaning, not counting, and a transcript without punctuation will show none.
_DETERMINERS = frozenset(
    "what which this that these those a an the any every some each same different one another all no "
    "my your his her our their".split()
)
FILLERS: dict[str, re.Pattern[str]] = {
    "um": re.compile(r"\bu+m+\b"),
    "uh": re.compile(r"\bu+h+\b"),
    "er": re.compile(r"\ber\b"),
    "erm": re.compile(r"\berm+\b"),
    "you know": re.compile(r"\byou know\b"),
    "I mean": re.compile(r"\bi mean\b"),
    "sort of": re.compile(r"\bsort of\b"),
    "kind of": re.compile(r"\bkind of\b"),
    "basically": re.compile(r"\bbasically\b"),
    "actually": re.compile(r"\bactually\b"),
    "like,": re.compile(r"\blike,"),
}

LINKING_DEVICES = [
    "however", "although", "even though", "whereas", "on the other hand", "in contrast",
    "nevertheless", "despite", "instead", "otherwise", "unless",
    "for example", "for instance", "such as",
    "in addition", "moreover", "furthermore", "what's more", "as well as", "apart from", "also",
    "as a result", "therefore", "consequently", "because of this", "that's why", "that is why",
    "firstly", "secondly", "thirdly", "finally", "first of all", "to begin with", "meanwhile",
    "in fact", "overall", "in conclusion", "to sum up", "in other words",
]
_LINKING = {d: re.compile(r"\b" + re.escape(d) + r"\b") for d in LINKING_DEVICES}

STOPWORDS = frozenset("""
a about above after again all also am an and any are as at be because been before being but by can
could did do does doing don't down during each even few for from further get got had has have having
he her here hers herself him himself his how i i'm i've i'd i'll if in into is isn't it it's its itself
just let's me more most much my myself no nor not now of off on once only or other our ours ourselves
out over own really same she should so some such than that that's the their theirs them themselves
then there there's these they they're this those through to too under until up very was wasn't we
we're were what when where which while who whom why will with would you you're your yours yourself
yeah yes oh ok okay well thing things lot get gets going go went one two
""".split())
_FILLER_WORDS = frozenset({"um", "uh", "er", "erm", "basically", "actually", "like", "know", "mean", "kind", "sort"})

PART2_TALK_SECONDS = 120


def _count_filler(name: str, pattern: re.Pattern[str], low: str) -> int:
    if name not in ("sort of", "kind of"):
        return len(pattern.findall(low))
    count = 0
    for m in pattern.finditer(low):
        before = _WORD.findall(low[max(0, m.start() - 40) : m.start()])
        if not before or before[-1] not in _DETERMINERS:
            count += 1
    return count


def normalise(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'").lower()


def words(text: str) -> list[str]:
    return _WORD.findall(normalise(text))


def count_sentences(text: str) -> int:
    parts = [p for p in _SENTENCE_END.split(text) if _WORD.search(p)]
    return len(parts)


def analyse(transcript: str, part: str, duration_seconds: int | None = None) -> dict[str, Any]:
    low = normalise(transcript)
    toks = words(transcript)
    n = len(toks)
    sentences = count_sentences(transcript)
    unique = len(set(toks))

    fillers = [{"item": k, "count": _count_filler(k, p, low)} for k, p in FILLERS.items()]
    fillers = [f for f in fillers if f["count"]]
    linking = [{"item": d, "count": len(p.findall(low))} for d, p in _LINKING.items()]
    linking = [x for x in linking if x["count"]]

    content = Counter(t for t in toks if t not in STOPWORDS and t not in _FILLER_WORDS and len(t) > 2 and not t.isdigit())
    repeated = [{"word": w, "count": c} for w, c in content.most_common() if c >= 3][:10]

    wpm = round(n / (duration_seconds / 60), 1) if duration_seconds else None

    notes = [
        "Type-token ratio falls as a text gets longer, so compare it only between answers of similar length.",
        "Filler counts are pattern matches; 'actually', 'you know' and 'I mean' can also be used normally.",
        "'like' is counted only when followed by a comma.",
    ]
    if sentences <= 1 and n > 40:
        notes.append("The transcript has little or no sentence punctuation (common in voice transcripts), so "
                     "sentence count and average sentence length are not meaningful.")

    part2_note = None
    if part == "2":
        if duration_seconds:
            if duration_seconds < PART2_TALK_SECONDS:
                part2_note = (f"{n} words in {duration_seconds} s ({wpm} words per minute). The talk stopped "
                              f"before the two minutes Part 2 asks the candidate to keep talking for.")
            else:
                part2_note = f"{n} words in {duration_seconds} s ({wpm} words per minute); the talk filled the two minutes."
        else:
            part2_note = (f"{n} words; no duration given. Speaking rates differ too much between people to judge "
                          "from word count alone whether the talk filled two minutes.")

    return {
        "kind": "analysis",
        "part": part,
        "word_count": n,
        "sentence_count": sentences,
        "avg_sentence_length": round(n / sentences, 1) if sentences else 0.0,
        "unique_words": unique,
        "type_token_ratio": round(unique / n, 3) if n else 0.0,
        "fillers": fillers,
        "filler_total": sum(f["count"] for f in fillers),
        "repeated_words": repeated,
        "linking_devices": linking,
        "linking_total": sum(x["count"] for x in linking),
        "duration_seconds": duration_seconds,
        "words_per_minute": wpm,
        "part2_length_note": part2_note,
        "notes": notes,
    }


def round_half_band(average: float) -> float:
    """Round to the nearest half band; .25 rounds up to the half band, .75 up to the whole band.

    This is the rule ielts.org publishes for the OVERALL band. It does not publish how the
    Speaking average itself is rounded, so applying it here is an assumption.
    """
    doubled = Fraction(average) * 2
    return math.floor(doubled + Fraction(1, 2)) / 2
