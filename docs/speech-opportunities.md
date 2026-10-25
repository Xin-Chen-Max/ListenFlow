# American English speech opportunities

## Scope and architecture

Text and dictionary context suggest places to listen. They do not establish what a speaker pronounced. No acoustic feature is verified in this release. The existing faster-whisper/CTranslate2 transcription, retained source audio, SQLite library, editing, playback and exports remain the foundation.

The `pronunciation/` package separates dictionary lookup, context, rules and result serialization. `speech_patterns.py` remains the compatibility entrypoint. Dictionary loading, analysis and response encoding run off the API event loop. Analysis is derived, not stored in SQLite.

## Pronunciations and licensing

The original CMU US English dictionary is bundled at commit `74790861f652b15e4ac49015a90074ad62a27690`, with its original license. See [data provenance](../pronunciation/data/cmudict/PROVENANCE.md). No Python wrapper or new runtime dependency is included. There is no resource download at runtime.

Canonical phones are the CMU 39-phone ARPABET inventory with vowel lexical stress 0/1/2. All alternatives are retained, without rankings. Broad IPA is an optional dictionary display; it is not a narrow phonetic transcription. Unknown words and unsupported normalization are diagnosed rather than guessed. A provider interface leaves G2P for later.

## Taxonomy and status

Stable categories: linking, reduction, elision, assimilation, consonant phenomena and prosody. The registry includes prerequisites, limitations and teaching explanations for six initial rule families. Prosody and other unimplemented families remain unsupported.

`candidate` means text/dictionary evidence supports an opportunity. `uncertain` means alternatives or context affect eligibility. `observed` and `not_observed` are reserved for a separately validated acoustic verifier. No match makes neither acoustic claim. Confidence is null because rule matches, dictionary order and alignments are not calibrated probabilities.

## Later stages

Contracts define word alignment, phone alignment and acoustic verification separately. Existing ASR words provide timing only. [WhisperX](https://github.com/m-bain/whisperX) is a possible future word aligner; [MFA](https://huggingface.co/MontrealCorpusTools/english_us_arpa) a possible phone aligner. Neither is installed or implemented here. Forced alignment fits supplied units to audio and does not verify a flap, deletion or reduction. MFA's model documentation explicitly excludes accurate pronunciation assessment.

Future adapters must report provider/model/version/inventory, transcript fingerprint and source recording, and own only their temporary files. Original recordings remain retained until explicit deletion. Acoustic scoring requires separate rule-specific validation before it can issue acoustic statuses.

## Capability record

- Supported text capabilities: offline dictionary alternatives, inventory, taxonomy, six generic candidate rule families, timed replay and shared contracts.
- Experimental: conditional stress/variant reasoning and the continuity filter planned for context rules.
- Acoustically verified: none.
- Unimplemented: G2P inference, prosody measurement, aligner adapters and acoustic scoring.

## Supported text rules

| Rule ID | Context | Example | Important exclusion |
|---|---|---|---|
| linking.c_v | Dictionary final consonant + initial vowel | need it; turn off | turn back; strong punctuation |
| linking.v_v | Adjacent dictionary vowel sounds | see it | a university (initial /j/) |
| assimilation.yod | Final /t,d/ + initial /j/ | did you; meet you | did we |
| reduction.function_word | Listed grammatical word with strong and weak dictionary alternatives and a neighbor | want to; for a moment | content words; isolated to |
| elision.cluster_td | Final /t,d/ after a listed cluster consonant before a consonant | kept moving; last night | last apple |
| consonant.flap | Intervocalic /t,d/, preceding lexically stressed vowel and following unstressed vowel | better; get it | attack; get Tom |

These are broad listening opportunities, not predictions of a speaker's realization. Yod coalescence, cluster simplification, flapping and weak forms are conditional because rate, emphasis or grammatical context are not measured. Variant-dependent eligibility is uncertain. All dictionary alternatives remain visible; only supporting variants are marked. No automatic “wanna” substitution is performed.

The weak-form lexicon is intentionally limited to a, an, and, at, can, for, from, of, or, the, to. The cluster predecessor set is S/Z/F/V/SH/ZH/N/L/P/K/B/G/M/NG. Flapping conservatively requires adjacent vowel-stop-vowel phones, excluding other common environments. These filters are incomplete and have no measured precision/recall.

## Tokens, boundaries and replay

Original token offsets, case and curly apostrophes are preserved; normalization supports ASCII English words and internal apostrophes. Unknown words, numbers, hyphenated forms and other unsupported normalization receive coverage diagnostics. No sound is guessed from spelling.

Existing word times are reused only when the whole word sequence matches saved text, intervals are finite, ordered, positive-duration and within the segment. Stale/missing words use segment replay. Invalid segment timing yields diagnostics and no timed opportunity. No phone times are manufactured.

Adjacent segments require valid word times, no intervening strong punctuation or known speaker change, and a gap from 0 to 250 ms (1 ms numerical tolerance). The gap setting is configurable in the analysis interface and is a heuristic, not a validated phonetic threshold. The same pause/speaker guards apply to aligned within-segment word boundaries. Missing timing blocks cross-segment analysis; a whole segment can still offer coarse reading/replay opportunities. Dictionary lexical stress is not sentence emphasis.

Results are grouped by rule and token span, preserving distinct overlapping rules. Fingerprints include saved text, segment/word times and speakers; result IDs derive from the fingerprint, rule version and token span. No server-side analysis cache or database migration is used. The browser caches bounded results per recording/revision and invalidates them on saved edits.

## API and learner interface

The existing `/api/library/{id}/patterns` route and `patterns` array remain. The default full view preserves existing presentation/timing fields and detailed evidence. Optional summary/range queries support the inline UI; see [API notes](api.md). Library item and analysis fingerprints must agree before cards are displayed. Superseded browser requests cannot replace newer saved edits.

Each punctuation-delimited sentence shows a compact Possible pattern line. Linking uses a tie (‿), weak forms show an example such as to → /tə/, and possible cluster omission crosses out only the eligible /t,d/ phone. A tap/coalescence example illustrates its environment. Question marks mark conditional opportunities. These are illustrative dictionary-derived examples with stress marks omitted, not selected recorded pronunciations. All dictionary alternatives remain in full details.

Select a cue or Details beneath that sentence to open its explanation and replay in place. The existing Patterns button opens the first sentence's details within its segment. Conditional assumptions and dictionary ARPABET/IPA/rule/provenance remain expandable. Missing source audio disables replay. Unknown-word coverage, request failure and a successful no-match result have distinct messages. There is no Verified in audio badge because the verified capability list is empty.

Reading cues are outside the editable/searchable text. Editing and search temporarily show the original plain transcript; exports and Copy continue to use saved transcript text. Sentence splitting is a punctuation heuristic, not linguistic sentence parsing. Unicode code-point offsets from Python are reconciled with browser string offsets. Existing word nodes survive summary arrival, preserving selections/highlighting and transcript scroll position.

Historical items reuse their library metadata. An IntersectionObserver requests 24-segment summaries near the transcript viewport; full evidence is fetched for one segment only when expanded. Revision-scoped caches reuse repeated details and abort requests superseded by edits. No whole-transcript result transfer or word repaint is needed by the UI. The unbounded API remains for compatibility.

## Verification and measurement

### Inline UI and bounded loading (2026-10-24)

Passed: 158 backend/smoke/publication tests and 16 subtests (21.09 s), one inherited TestClient deprecation warning. Full Chrome acceptance passed with real local ASR, playback/highlighting/sentence loops, edits/exports/clips/restart/deletion/retry, plus sentence-local cue placement, possible-omission marks, all five requested phrases, lazy error/retry and fingerprint/late-response protection. Browser checks also covered multi-sentence segments, emoji/code-point offsets, search hiding annotations, unchanged raw text/exports, selection and word-node identity surviving summary refresh, missing audio and mobile overflow. No browser errors or external requests were recorded.

A warm-server Chrome run opening a 1,200-segment historical fixture through Library measured 1,038 ms from item click to first cues, 408 ms for first detail click, 133 ms for repeated cached details with no extra request. Opening, clicking and jumping to the last segment used three bounded pattern requests: initial summary 272,835 bytes, detail 37,663 bytes, final-page summary 279,205 bytes. No unbounded analysis request was made. Playwright interaction/wait overhead is included; this is one synthetic run, not a latency guarantee or general accuracy evidence.

Reproduce CPU transport measurements with `python scripts/benchmark_patterns.py --bounded`. Same Python/Windows/CPU environment and 24,000-word fixture below: current full response 41,471,537 compact-JSON bytes, cold analysis 1.9901 s and serialization 0.2585 s; warm analysis 1.3947 s and serialization 0.2606 s. A 24-segment summary produced 360 opportunities / 275,099 bytes, analysis 0.0410 s / serialization 0.0020 s. Single-segment details produced 15 opportunities / 37,663 bytes, analysis 0.0217 s / serialization 0.0003 s. These measurements include hashing the full transcript but evaluate/serialize only the requested context window. The complete library transcript still loads initially, and a first process request may need dictionary loading. No model or audio is analyzed by this benchmark.

Earlier LF-012 evidence follows as history.

Checkpoint A: five dictionary/license/inventory/contract checks passed (0.73 s). Checkpoint B: 49 foundation/rule checks passed (0.87 s). Checkpoint C: full backend/smoke/publication suite passed 143 tests and 16 subtests (21.00 s), with one existing TestClient deprecation warning. The exported source passed 132 tests (11.37 s) with the same warning and documented FFmpeg environment variables. JavaScript syntax and full Chrome workflow passed, including errors/retry, unknown/no-match states, all five requested phrases, stale fingerprint/late-response protection, cross-segment replay, word underlines, legacy audio, editing/exports/restart/deletion and ASR job retry. No browser JavaScript errors or external requests were reported.

Run focused rules with `python -m pytest tests/test_pronunciation.py tests/test_speech_patterns.py -q`; API/persistence with tests/test_listenflow.py; full desktop/browser checks as described in [validation](validation.md). Tests use positive and negative phone environments, alternatives, lexical versus sentence stress, repeated words, contractions, OOV/normalization, sound versus spelling, cross-segment punctuation/speaker/gap/timing guards, edits, legacy audio, IDs/fingerprints/null confidence, status safety and source provenance. Browser acceptance uses real local ASR for the existing workflow; extra text/timing fixtures test UI behavior and do not validate pronunciation.

`python scripts/benchmark_patterns.py` measures a reproducible synthetic long transcript and writes ignored evidence. On 2026-10-24, Python 3.12.14, Windows 11 build 26200, AMD64 Family 25 Model 97 Stepping 2 (32 logical CPUs): 1,200 segments, 24,000 words, 5,760 seconds of fixture timing produced 18,000 overlapping opportunities. Cold analysis including dictionary load: 1.9329 s; warm runs: 1.9226 and 1.7084 s. JSON serialization took 0.2286/0.3816/0.2667 s and produced 39,582,798 bytes. This is one repeated-text CPU experiment, not an accuracy result, GPU benchmark or latency guarantee. That measurement records LF-012 before inline bounded loading. The legacy unbounded endpoint still has a large response; the current UI uses bounded summaries/details instead. Word underlines use indexed token IDs.

Unsupported: G2P inference, prosody measurement, acoustic scoring, actual WhisperX/MFA adapters, automatic realignment and end-to-end pronunciation verification. Experimental: conditional candidate assumptions and the continuity heuristic, whose accuracy is unmeasured. Acoustically verified: none. Container builds and new clean Windows/remote CI runs are unrun for this increment. No runtime package versions changed.
