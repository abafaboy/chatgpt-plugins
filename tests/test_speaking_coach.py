import json

import pytest
from mcp import Client

import speaking_coach.server as srv
from speaking_coach.analysis import round_half_band

pytestmark = pytest.mark.anyio

SAMPLE = (
    "Um, I think music is important. However, I mean, I kind of like quiet songs. "
    "For example, I listen to jazz, you know, and jazz helps me. What kind of music? Uh, jazz."
)


@pytest.fixture
async def client():
    async with Client(srv.mcp, mode="legacy") as c:
        yield c


async def test_tools_are_read_only_and_bound_to_widget(client):
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == {"start_speaking_test", "analyse_speaking_transcript", "record_speaking_scores"}
    for t in tools:
        a = t.annotations
        assert a.read_only_hint is True and a.destructive_hint is False and a.open_world_hint is False
        assert t.meta["ui"]["resourceUri"] == srv.WIDGET
        assert t.output_schema is not None, t.name
        assert t.title


def test_question_bank_structure():
    bank = srv.question_bank()
    p1, p2 = bank["part1"], bank["part2"]
    assert len(p1) == 20 and len(p2) == 30
    ids = [x["id"] for x in p1 + p2]
    assert len(ids) == len(set(ids))
    asked = []
    for t in p1:
        assert t["topic"] and len(t["questions"]) == 4
        asked += t["questions"]
    for c in p2:
        assert c["topic"] and c["prompt"].startswith("Describe ") and c["prompt"].endswith(".")
        assert len(c["bullets"]) == 3 and all(b and not b.endswith("?") for b in c["bullets"])
        assert c["final"].startswith("and explain") and c["final"].endswith(".")
        assert len(c["part3"]) == 4
        asked += c["part3"]
    assert all(q.endswith("?") for q in asked)
    assert len(asked) == len(set(asked)) == 200


async def test_full_test_is_deterministic_with_seed(client):
    a = await client.call_tool("start_speaking_test", {"seed": 42})
    b = await client.call_tool("start_speaking_test", {"seed": 42})
    assert not a.is_error
    assert a.structured_content == b.structured_content
    sc = a.structured_content
    assert sc["kind"] == "test" and sc["part"] == "full" and sc["seed"] == 42
    assert len(sc["part1"]["questions"]) == 4
    assert sc["part2"]["prep_seconds"] == 60 and sc["part2"]["speaking_seconds"] == 120
    assert len(sc["part2"]["bullets"]) == 3
    assert sc["part3"]["id"] == sc["part2"]["id"] and len(sc["part3"]["questions"]) == 4
    assert sc["test_id"] == f"full-{sc['part1']['id']}-{sc['part2']['id']}-s42"
    assert "ONE question at a time" in a.content[0].text


async def test_seed_is_reported_when_not_given(client):
    r = await client.call_tool("start_speaking_test", {"part": "1"})
    seed = r.structured_content["seed"]
    again = await client.call_tool("start_speaking_test", {"part": "1", "seed": seed})
    assert again.structured_content["part1"] == r.structured_content["part1"]


@pytest.mark.parametrize("part,present", [("1", {"part1"}), ("2", {"part2"}), ("3", {"part3"})])
async def test_part_filters(client, part, present):
    r = await client.call_tool("start_speaking_test", {"part": part, "seed": 7})
    sc = r.structured_content
    for key in ("part1", "part2", "part3"):
        assert (sc[key] is not None) == (key in present), key


async def test_topic_filter_case_insensitive(client):
    r = await client.call_tool("start_speaking_test", {"part": "2", "topic": "PHOTOGRAPH", "seed": 1})
    assert r.structured_content["part2"]["topic"] == "A meaningful photograph"
    r = await client.call_tool("start_speaking_test", {"part": "1", "topic": "bicy", "seed": 1})
    assert r.structured_content["part1"]["topic"] == "Bicycles"
    # Full test: the filter narrows the part it matches, the other part stays random.
    r = await client.call_tool("start_speaking_test", {"topic": "noise", "seed": 3})
    assert r.structured_content["part1"]["topic"] == "Noise"
    assert r.structured_content["part2"] is not None


async def test_topic_with_no_match_is_an_error(client):
    r = await client.call_tool("start_speaking_test", {"part": "2", "topic": "quantum chromodynamics"})
    assert r.is_error
    assert "No topic matches" in r.content[0].text and "Some available topics" in r.content[0].text


async def test_analysis_numbers(client):
    r = await client.call_tool("analyse_speaking_transcript", {"transcript": SAMPLE, "part": "1"})
    assert not r.is_error
    sc = r.structured_content
    assert sc["word_count"] == 33
    assert sc["sentence_count"] == 5
    fillers = {f["item"]: f["count"] for f in sc["fillers"]}
    # "What kind of music?" is a noun phrase, not a filler; "like quiet songs" has no comma.
    assert fillers == {"um": 1, "uh": 1, "I mean": 1, "kind of": 1, "you know": 1}
    assert sc["filler_total"] == 5
    assert {x["item"]: x["count"] for x in sc["linking_devices"]} == {"however": 1, "for example": 1}
    assert sc["repeated_words"] == [{"word": "jazz", "count": 3}]
    assert sc["words_per_minute"] is None and sc["part2_length_note"] is None
    assert "band" not in r.content[0].text.lower()


async def test_analysis_part2_with_duration(client):
    r = await client.call_tool("analyse_speaking_transcript", {"transcript": SAMPLE, "part": "2", "duration_seconds": 30})
    sc = r.structured_content
    assert sc["words_per_minute"] == 66.0
    assert "33 words in 30 s" in sc["part2_length_note"] and "two minutes" in sc["part2_length_note"]
    r = await client.call_tool("analyse_speaking_transcript", {"transcript": SAMPLE, "part": "2"})
    assert "no duration given" in r.structured_content["part2_length_note"]


async def test_oversized_transcript_is_refused(client):
    r = await client.call_tool("analyse_speaking_transcript", {"transcript": "a " * (srv.MAX_CHARS // 2 + 1), "part": "1"})
    assert r.is_error and "limit" in r.content[0].text


async def test_scores_with_pronunciation(client):
    r = await client.call_tool("record_speaking_scores", {
        "fluency_coherence": 7, "lexical_resource": 7, "grammatical_range_accuracy": 6, "pronunciation": 7,
        "strengths": ["Used 'however' and 'for example' to link ideas."], "improvements": ["Fewer fillers."],
        "better_answer_example": "I'm really into jazz, mainly because…",
    })
    assert not r.is_error
    sc = r.structured_content
    assert sc["average"] == 6.75 and sc["estimated_band"] == 7.0
    assert sc["pronunciation_assessed"] is True and sc["criteria_assessed"] == 4
    assert "does not publish" in sc["rounding_note"]
    assert "not affiliated" in sc["disclaimer"] and "British Council" in sc["disclaimer"]
    assert "not an official score" in r.content[0].text


async def test_scores_without_pronunciation(client):
    r = await client.call_tool("record_speaking_scores", {
        "fluency_coherence": 6, "lexical_resource": 7, "grammatical_range_accuracy": 6,
        "strengths": [], "improvements": [],
    })
    sc = r.structured_content
    assert sc["estimated_band"] is None and sc["pronunciation_assessed"] is False
    assert sc["criteria_assessed"] == 3 and sc["average"] == pytest.approx(6.333, abs=1e-3)
    pron = [c for c in sc["criteria"] if c["key"] == "pronunciation"][0]
    assert pron == {"key": "pronunciation", "name": "Pronunciation", "score": None, "assessed": False}
    assert "not assessed" in r.content[0].text
    assert sc["disclaimer"] == srv.DISCLAIMER


@pytest.mark.parametrize("avg,band", [
    (6.25, 6.5), (6.75, 7.0), (6.5, 6.5), (6.125, 6.0), (6.375, 6.5), (6.625, 6.5), (6.875, 7.0),
    (6.0, 6.0), (8.75, 9.0), (0.25, 0.5),
])
def test_rounding_rule(avg, band):
    assert round_half_band(avg) == band


@pytest.mark.parametrize("args", [
    {"fluency_coherence": 10, "lexical_resource": 7, "grammatical_range_accuracy": 6},
    {"fluency_coherence": 7, "lexical_resource": -1, "grammatical_range_accuracy": 6},
    {"fluency_coherence": 7, "lexical_resource": 7, "grammatical_range_accuracy": 6, "pronunciation": 12},
    {"fluency_coherence": 7, "lexical_resource": 7, "grammatical_range_accuracy": 6, "strengths": ["x"] * 6},
    {"fluency_coherence": 7, "lexical_resource": 7, "grammatical_range_accuracy": 6, "improvements": ["x" * 301]},
])
async def test_out_of_range_input_is_rejected(client, args):
    args = {"strengths": [], "improvements": [], **args}
    r = await client.call_tool("record_speaking_scores", args)
    assert r.is_error


async def test_widget_resource(client):
    rr = await client.read_resource(srv.WIDGET)
    html = rr.contents[0].text
    assert rr.contents[0].mime_type == "text/html;profile=mcp-app"
    assert "plugkit" in html and "ui/notifications/tool-result" in html
    assert "Not affiliated" in html and "clearInterval" in html
    assert "getUserMedia" not in html and ".innerHTML" not in html


async def test_usage_is_logged_without_content(client, usage_log):
    await client.call_tool("analyse_speaking_transcript", {"transcript": "my secret jazz answer", "part": "1"})
    ev = json.loads(usage_log.read_text().splitlines()[-1])
    assert ev["plugin"] == "speaking-coach" and ev["tool"] == "analyse_speaking_transcript" and ev["ok"] is True
    assert "secret" not in usage_log.read_text()
