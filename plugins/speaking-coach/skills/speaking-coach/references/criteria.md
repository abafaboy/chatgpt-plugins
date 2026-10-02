# The four speaking criteria, in plain language

This is a practice guide written for this plugin. It is **not** the official band descriptors and is not
endorsed by IELTS, the British Council, IDP or Cambridge. The four criteria count equally. Use it to decide
roughly where an answer sits, then explain the decision with evidence from the transcript.

The band notes describe what a listener typically notices around each level. Real answers are uneven:
pick the level that fits most of the evidence, and say what pulled it up or down.

---

## 1. Fluency and Coherence

**What it looks at:** whether the speaker can keep going without long stops, and whether the listener can
follow the thread — ideas in a sensible order, joined so the listener knows how one point relates to the
next.

**Useful evidence:** pauses and restarts, filler counts and words per minute from the analysis, how long
answers are, whether the speaker answers the actual question, the linking devices found (and whether
they are used correctly or just dropped in).

- **Around 5:** answers often stall or loop back; the speaker leans on a few joiners ("and", "because",
  "so") and the same fillers. Longer turns, especially Part 2, run out of things to say or drift.
- **Around 6:** willing to talk at length, but there are noticeable breakdowns where the speaker searches
  for words or restarts. Links are present but sometimes mechanical or not quite right.
- **Around 7:** talks at length with only occasional hesitation, usually while thinking of *what* to say
  rather than *how* to say it. Uses a range of connectors and discourse markers appropriately.
- **Around 8:** smooth and easy to follow throughout; any pauses sound like natural thinking. Ideas are
  developed with reasons and examples, and the organisation feels effortless rather than signposted.

## 2. Lexical Resource (vocabulary)

**What it looks at:** how much vocabulary the speaker can draw on, whether words are used with the right
meaning and in natural combinations, and whether they can explain something another way when a word is
missing.

**Useful evidence:** repeated content words and type-token ratio from the analysis (compare only between
answers of similar length), specific topic words, word combinations that sound natural or unnatural,
moments of paraphrasing.

- **Around 5:** enough words for familiar topics, but the same basic words recur and less familiar topics
  expose gaps. Word choice errors sometimes make the meaning unclear.
- **Around 6:** enough range to discuss topics in some detail and to get round gaps; some words are used
  in slightly wrong combinations, but the meaning still comes across.
- **Around 7:** chooses words precisely for most topics, including some less everyday vocabulary and
  natural expressions; occasional slips in collocation or tone.
- **Around 8:** wide, flexible vocabulary that conveys fine shades of meaning; natural expressions are used
  accurately, with only rare misjudgements.

## 3. Grammatical Range and Accuracy

**What it looks at:** two things together — the variety of sentence structures the speaker uses
(complex sentences, conditionals, relative clauses, passives, a mix of tenses) and how often those
structures come out correctly.

**Useful evidence:** quote actual sentences: correct complex ones, and errors (tense, agreement, articles,
word order). Note whether errors make the meaning hard to follow. Average sentence length from the
analysis is a weak signal only — voice transcripts often lack punctuation.

- **Around 5:** mostly short, simple sentences; attempts at longer ones often break down. Errors are
  frequent and occasionally confuse the listener.
- **Around 6:** a mix of simple and complex sentences, but the complex ones carry noticeable errors.
  Meaning is rarely lost.
- **Around 7:** uses complex structures regularly and with some flexibility; many sentences have no errors
  at all, although some mistakes remain.
- **Around 8:** a wide range of structures used naturally; most sentences are error-free and the remaining
  mistakes are small and occasional.

## 4. Pronunciation

**What it looks at:** how easily the listener understands the speaker — individual sounds, word stress,
sentence stress and rhythm, intonation, and how words link together. An accent is not a problem in itself;
the question is how much effort the listener has to make.

**Only assess this if the user actually spoke aloud.** A typed answer, or a transcript of speech you did not
hear, gives no evidence about pronunciation — leave it out.

- **Around 5:** generally understandable, but mispronounced sounds or flat, choppy rhythm sometimes make the
  listener work hard or miss words.
- **Around 6:** mostly clear, using some features such as stress and intonation, but control is uneven and
  some words are hard to catch.
- **Around 7:** easy to understand throughout, with good control of stress and intonation; occasional
  sounds or stresses slip.
- **Around 8:** consistently clear and natural-sounding; the accent has little or no effect on how easily
  the listener follows.

---

## Working out the estimate

1. Score each criterion as a whole number 0–9 using the notes above, with evidence.
2. Pass the scores to `record_speaking_scores`; it averages them. ielts.org states the criteria are equally
   weighted, but it does not publish how the Speaking average is rounded — the tool borrows the published
   rule for the overall band (to the nearest half band, .25 up to the half band, .75 up to the whole band)
   and says that this is an assumption.
3. Without a pronunciation score, the tool reports the three-criterion average and no band.
