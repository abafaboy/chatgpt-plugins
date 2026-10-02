"""Speaking Band Coach: IELTS-style speaking practice — mock test, transcript statistics, criterion scores.

Not affiliated with or endorsed by IELTS, the British Council, IDP or Cambridge University
Press & Assessment. Every question in data/questions.json was written for this plugin.
"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from importlib import resources
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult

from plugkit import READ_ONLY, error, result, tracked, widget_html

from .analysis import analyse, round_half_band
from .widget import BODY, EXTRA_CSS, SCRIPT

PLUGIN = "speaking-coach"
WIDGET = "ui://speaking-coach/card.html"
MAX_CHARS = 20_000

# Test format, from https://ielts.org/take-a-test/test-types/ielts-academic-test/ielts-academic-format-speaking
# (read 2 Oct 2026), Part 2: "The examiner gives you a task card which asks you to talk about a
# particular topic." ... one minute to prepare, with pencil and paper ... "you should be able to
# think of appropriate things to say, and have time to structure your talk so that you keep talking
# for 2 minutes." ... "Part 2 lasts 3–4 minutes, including the preparation time."
# "Time allowed: 11–14 minutes". Kept as constants so they can be changed in one place.
FORMAT_SOURCE = "https://ielts.org/take-a-test/test-types/ielts-academic-test/ielts-academic-format-speaking"
PART2_PREP_SECONDS = 60
PART2_SPEAK_SECONDS = 120

DISCLAIMER = (
    "Practice estimate only, not an official score. Speaking Band Coach is not affiliated with or "
    "endorsed by IELTS, the British Council, IDP or Cambridge University Press & Assessment."
)
ROUNDING_NOTE = (
    "The four criteria are equally weighted. ielts.org says an average ending in .25 rounds up to the "
    "next half band and .75 up to the next whole band for the OVERALL band; it does not publish how the "
    "Speaking average is rounded, so applying that rule here is an assumption."
)

Part = Literal["1", "2", "3", "full"]
AnalysedPart = Literal["1", "2", "3"]


@lru_cache(maxsize=1)
def question_bank() -> dict[str, Any]:
    raw = resources.files("speaking_coach").joinpath("data", "questions.json").read_text(encoding="utf-8")
    return json.loads(raw)


class Part1Out(BaseModel):
    id: str
    topic: str
    questions: list[str]


class Part2Out(BaseModel):
    id: str
    topic: str
    prompt: str
    bullets: list[str]
    final: str
    prep_seconds: int
    speaking_seconds: int


class Part3Out(BaseModel):
    id: str
    topic: str
    questions: list[str]


class TestOut(BaseModel):
    kind: Literal["test"]
    test_id: str
    part: Part
    seed: int
    part1: Part1Out | None
    part2: Part2Out | None
    part3: Part3Out | None
    format_source: str


class Count(BaseModel):
    item: str
    count: int


class WordCount(BaseModel):
    word: str
    count: int


class AnalysisOut(BaseModel):
    kind: Literal["analysis"]
    part: AnalysedPart
    word_count: int
    sentence_count: int
    avg_sentence_length: float
    unique_words: int
    type_token_ratio: float
    fillers: list[Count]
    filler_total: int
    repeated_words: list[WordCount]
    linking_devices: list[Count]
    linking_total: int
    duration_seconds: int | None
    words_per_minute: float | None
    part2_length_note: str | None
    notes: list[str]


class Criterion(BaseModel):
    key: str
    name: str
    score: int | None
    assessed: bool


class ScoresOut(BaseModel):
    kind: Literal["scores"]
    criteria: list[Criterion]
    criteria_assessed: int
    average: float
    estimated_band: float | None
    pronunciation_assessed: bool
    rounding_note: str
    strengths: list[str]
    improvements: list[str]
    better_answer_example: str | None
    disclaimer: str


apps = Apps()


def _match(items: list[dict[str, Any]], topic: str) -> list[dict[str, Any]]:
    needle = topic.strip().lower()
    return [x for x in items if needle in x["topic"].lower()]


@apps.tool(
    resource_uri=WIDGET,
    name="start_speaking_test",
    title="Start a speaking practice test",
    description=(
        "Start an IELTS-style speaking practice test from an original question bank. 'full' gives a "
        "Part 1 topic (4 questions), a Part 2 cue card (1 minute to prepare, then speak for 2 minutes) "
        "and that card's 4 Part 3 discussion questions; '1', '2' or '3' gives just that part. Optional "
        "topic filter (substring of the topic name) and seed for a repeatable test. Ask the questions "
        "one at a time and wait for each answer."
    ),
    annotations=READ_ONLY,
    meta={"openai/toolInvocation/invoking": "Preparing the test…", "openai/toolInvocation/invoked": "Test ready"},
)
@tracked(PLUGIN)
def start_speaking_test(
    part: Annotated[Part, Field(description="Which part to practise, or 'full' for all three.")] = "full",
    topic: Annotated[str | None, Field(description="Topic name or part of it, e.g. 'music', 'travel'.", max_length=60)] = None,
    seed: Annotated[int | None, Field(description="Seed for a repeatable selection.", ge=0, le=2**31 - 1)] = None,
) -> Annotated[CallToolResult, TestOut]:
    bank = question_bank()
    p1_pool, p2_pool = bank["part1"], bank["part2"]
    if topic is not None and topic.strip():
        p1_match, p2_match = _match(p1_pool, topic), _match(p2_pool, topic)
        if part == "1":
            ok = bool(p1_match)
        elif part in ("2", "3"):
            ok = bool(p2_match)
        else:
            ok = bool(p1_match or p2_match)
        if not ok:
            names = [x["topic"] for x in (p1_pool if part == "1" else p2_pool)][:8]
            return error(f"No topic matches '{topic.strip()}'. Some available topics: {', '.join(names)}.")
        # In a full test the filter narrows whichever parts it matches; the others stay random.
        p1_pool = p1_match or p1_pool
        p2_pool = p2_match or p2_pool

    if seed is None:
        seed = random.SystemRandom().randrange(2**31)
    rng = random.Random(seed)
    p1 = rng.choice(p1_pool)
    card = rng.choice(p2_pool)

    part1 = Part1Out(**p1) if part in ("1", "full") else None
    part2 = (
        Part2Out(id=card["id"], topic=card["topic"], prompt=card["prompt"], bullets=card["bullets"],
                 final=card["final"], prep_seconds=PART2_PREP_SECONDS, speaking_seconds=PART2_SPEAK_SECONDS)
        if part in ("2", "full") else None
    )
    part3 = Part3Out(id=card["id"], topic=card["topic"], questions=card["part3"]) if part in ("3", "full") else None

    ids = [x.id for x in (part1, part2) if x] or ([part3.id] if part3 else [])
    test_id = f"{part}-{'-'.join(ids)}-s{seed}"

    lines = [f"Practice test {test_id}. Ask ONE question at a time and wait for the answer."]
    if part1:
        lines.append(f"Part 1 ({part1.topic}): " + " | ".join(part1.questions))
    if part2:
        lines.append(
            f"Part 2 cue card: {part2.prompt} You should say: {'; '.join(part2.bullets)}; {part2.final} "
            f"({PART2_PREP_SECONDS} s to prepare, then talk for up to {PART2_SPEAK_SECONDS} s.)"
        )
    if part3:
        lines.append(f"Part 3 ({part3.topic}): " + " | ".join(part3.questions))
    data = TestOut(kind="test", test_id=test_id, part=part, seed=seed, part1=part1, part2=part2, part3=part3,
                   format_source=FORMAT_SOURCE)
    return result("\n".join(lines), data.model_dump())


@apps.tool(
    resource_uri=WIDGET,
    name="analyse_speaking_transcript",
    title="Analyse a speaking transcript",
    description=(
        "Count evidence in the user's spoken or typed answers: words, sentences, vocabulary variety "
        "(type-token ratio), filler words, most repeated words, linking devices and, if a duration is "
        "given, words per minute. Makes no band judgement; use the numbers as evidence when assessing "
        "the criteria. Pass only the user's own words, not the examiner's questions."
    ),
    annotations=READ_ONLY,
    meta={"openai/toolInvocation/invoking": "Analysing…", "openai/toolInvocation/invoked": "Analysed"},
)
@tracked(PLUGIN)
def analyse_speaking_transcript(
    transcript: Annotated[str, Field(description="The user's answers for one part, as spoken or typed.", min_length=1)],
    part: Annotated[AnalysedPart, Field(description="Which part the answers belong to.")],
    duration_seconds: Annotated[int | None, Field(description="How long the user spoke, if known.", ge=1, le=3600)] = None,
) -> Annotated[CallToolResult, AnalysisOut]:
    if len(transcript) > MAX_CHARS:
        return error(f"The transcript is {len(transcript)} characters; the limit is {MAX_CHARS}. Analyse one part at a time.")
    if not transcript.strip():
        return error("The transcript is empty.")
    data = analyse(transcript, part, duration_seconds)
    fill = ", ".join(f"{f['item']} ×{f['count']}" for f in data["fillers"]) or "none"
    link = ", ".join(f"{x['item']} ×{x['count']}" for x in data["linking_devices"]) or "none"
    text = (
        f"Part {part}: {data['word_count']} words, {data['sentence_count']} sentences "
        f"(avg {data['avg_sentence_length']}), {data['unique_words']} unique words "
        f"(TTR {data['type_token_ratio']}). Fillers: {fill}. Linking devices: {link}."
    )
    if data["words_per_minute"] is not None:
        text += f" {data['words_per_minute']} words per minute."
    if data["part2_length_note"]:
        text += f" {data['part2_length_note']}"
    return result(text, AnalysisOut(**data).model_dump())


Band = Annotated[int, Field(ge=0, le=9)]
Note = Annotated[str, Field(max_length=300)]


@apps.tool(
    resource_uri=WIDGET,
    name="record_speaking_scores",
    title="Show speaking criterion scores",
    description=(
        "Show your criterion scores (0–9) for Fluency and Coherence, Lexical Resource, Grammatical Range "
        "and Accuracy and, only if the user actually spoke, Pronunciation, with strengths, improvements and "
        "an improved sample answer. Returns the average and an estimated practice band. Leave pronunciation "
        "out for typed answers; then no band is estimated. Never present the result as an official score."
    ),
    annotations=READ_ONLY,
    meta={"openai/toolInvocation/invoking": "Scoring…", "openai/toolInvocation/invoked": "Scored"},
)
@tracked(PLUGIN)
def record_speaking_scores(
    fluency_coherence: Annotated[Band, Field(description="Fluency and Coherence, 0–9.")],
    lexical_resource: Annotated[Band, Field(description="Lexical Resource, 0–9.")],
    grammatical_range_accuracy: Annotated[Band, Field(description="Grammatical Range and Accuracy, 0–9.")],
    strengths: Annotated[list[Note], Field(description="Up to 5 strengths, each citing evidence.", max_length=5)],
    improvements: Annotated[list[Note], Field(description="Up to 5 concrete improvements.", max_length=5)],
    pronunciation: Annotated[Band | None, Field(description="Pronunciation, 0–9. Omit unless the user spoke aloud.")] = None,
    better_answer_example: Annotated[
        str | None, Field(description="An improved version of one of the user's answers.", max_length=1500)
    ] = None,
) -> Annotated[CallToolResult, ScoresOut]:
    scores = {
        "fluency_coherence": ("Fluency and Coherence", fluency_coherence),
        "lexical_resource": ("Lexical Resource", lexical_resource),
        "grammatical_range_accuracy": ("Grammatical Range and Accuracy", grammatical_range_accuracy),
        "pronunciation": ("Pronunciation", pronunciation),
    }
    criteria = [Criterion(key=k, name=n, score=s, assessed=s is not None) for k, (n, s) in scores.items()]
    assessed = [c.score for c in criteria if c.score is not None]
    average = sum(assessed) / len(assessed)
    pron = pronunciation is not None
    band = round_half_band(average) if pron else None

    parts = ", ".join(f"{c.name} {c.score if c.assessed else 'not assessed'}" for c in criteria)
    if band is not None:
        text = f"{parts}. Average {average:g} → estimated practice band {band:.1f}."
    else:
        text = (f"{parts}. Average of the three assessed criteria {round(average, 2):g}. Pronunciation was not "
                "assessed, so no band is estimated.")
    text += " " + DISCLAIMER
    data = ScoresOut(
        kind="scores", criteria=criteria, criteria_assessed=len(assessed), average=round(average, 3),
        estimated_band=band, pronunciation_assessed=pron, rounding_note=ROUNDING_NOTE,
        strengths=strengths, improvements=improvements, better_answer_example=better_answer_example,
        disclaimer=DISCLAIMER,
    )
    return result(text, data.model_dump())


apps.add_html_resource(
    WIDGET,
    widget_html("Speaking Band Coach", BODY, SCRIPT, EXTRA_CSS),
    title="Speaking Band Coach card",
    description="Shows a practice test with a Part 2 timer, transcript statistics, or a criterion score card.",
    csp=ResourceCsp(connect_domains=[], resource_domains=[]),
    prefers_border=True,
)

mcp = MCPServer(
    "speaking-coach",
    title="Speaking Band Coach",
    version="0.1.0",
    instructions=(
        "IELTS-style speaking practice (not affiliated with IELTS, the British Council, IDP or Cambridge). "
        "Workflow: call start_speaking_test; ask ONE question at a time in English and wait for each answer; "
        "before Part 2 give the user one minute to prepare and up to two minutes to talk; after each part call "
        "analyse_speaking_transcript with only the user's words; judge Fluency and Coherence, Lexical Resource, "
        "Grammatical Range and Accuracy (and Pronunciation only if the user spoke aloud) quoting evidence from "
        "the transcript and the numbers; then call record_speaking_scores. Results are practice estimates, "
        "never official scores."
    ),
    extensions=[apps],
)
