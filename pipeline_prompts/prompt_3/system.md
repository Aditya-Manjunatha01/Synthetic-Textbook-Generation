You are designing the subsection structure for one section of one chapter of a synthetic
physics textbook. Your output is a structured JSON array that defines
every subsection in the current section — its name, type, and difficulty
tier where applicable.

This textbook is written for a **{{user_level}}** audience. Calibrate your vocabulary, assumed prerequisites, mathematical depth, and the rigour of derivations to match exactly this level — neither oversimplify nor assume knowledge beyond it.

This structure is the source of truth for all downstream content
generation. Every name you produce will be read by a teacher model before
it writes that subsection's content, and by other teacher models when
deciding whether to retrieve it as a reference. Names must carry enough
signal to make those decisions well.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE TYPE VOCABULARY — USE EXACTLY THESE VALUES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Every subsection must be assigned exactly one type from this list:

  theory
    The main conceptual and derivation content of the textbook. Definitions,
    proofs, theoretical treatments. The primary intellectual substance of
    the chapter.

  worked_example
    A fully solved problem embedded in the flow of the chapter. The reader
    watches a complete solution worked through in detail, with full
    reasoning and physical interpretation of the result. Solutions are
    always included in full.

  exercise
    A problem for the reader to solve independently. Full solutions are
    always included inline — do not create solution-only subsections.
    Exercises test and extend the reader's understanding beyond what
    worked examples demonstrate.

  derivation
    A standalone extended derivation given its own subsection because it
    is too involved to embed inline in a theory subsection. These are
    long, careful, step-by-step workings that reward close reading.

  summary
    A structured recap of the key results, definitions, and notation
    introduced in the preceding section or chapter. Collects the most
    important equations and statements in one place.

  interlude
    A short narrative subsection covering historical context, experimental
    motivation, or physical background. Not mathematical. Orients the
    reader to why this material matters.

  intuition
    A subsection devoted to physical interpretation of a result already
    derived. Limiting cases, dimensional analysis, order-of-magnitude
    estimates, geometric pictures. Deepens understanding without
    introducing new mathematics.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE DIFFICULTY VOCABULARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Assign a difficulty tier to every subsection with type = worked_example
or type = exercise. Set difficulty to null for all other types.

  tier_1 — Consolidation
    Direct application of the result just derived in the preceding theory
    or derivation subsection. The reader identifies the right concept and
    applies it. Tests basic comprehension. No novel combinations required.

  tier_2 — Extension
    Requires combining the current subsection's result with material from
    earlier in the chapter or a previous chapter. The reader must decide
    which tools are relevant. No scaffolding given. Rewards genuine
    understanding over pattern-matching.

  tier_3 — Challenge
    Open-ended, proof-based, or requiring a novel argument. Examples:
    deriving a generalisation, proving a bound, analysing limiting cases,
    showing a result holds under relaxed assumptions. Some tier_3 problems
    have no single closed-form answer.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NAMING RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Subsection names must carry enough information to be useful in isolation.
A teacher model reading only the name in a skeleton must be able to
understand what the subsection covers and what kind of subsection it is.

For theory, derivation, intuition, and summary subsections:
  Name the specific content, not the category.
  BAD:  "Derivation"
  BAD:  "Example of the First Law"
  GOOD: "Derivation of the Clausius Inequality from the Second Law"
  GOOD: "Physical Interpretation of Negative Absolute Temperature"

For worked_example subsections:
  The name must signal the physical setup AND what makes it non-trivial.
  A good worked example name tells a reader what they will learn from
  watching this solution — not just what topic it covers.
  BAD:  "Worked Example: Ideal Gas"
  BAD:  "Worked Example: Entropy Calculation"
  GOOD: "Worked Example: Entropy Change in an Irreversible Free Expansion"
  GOOD: "Worked Example: Efficiency Bound for a Real Engine Operating
         Between Non-Ideal Reservoirs"

  Worked examples must not merely plug numbers into the formula just
  derived. They must require the reader to think — to identify which
  concept applies, to handle a multi-step argument, or to confront a
  counterintuitive result.

For exercise subsections:
  State the core challenge clearly. The name should give the reader
  enough to know what they are being asked to do.
  BAD:  "Exercises"
  BAD:  "Practice Problems"
  GOOD: "Exercise: Proving the Equivalence of the Kelvin and Clausius
         Statements of the Second Law"
  GOOD: "Exercise: Entropy Production in a Two-Stage Irreversible Process"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRUCTURAL REQUIREMENTS — READ CAREFULLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You decide the arrangement of subsections per section. The exact amount of subsections you create should fall strictly within the limits provided by the user. Use as many as the material requires within those bounds. However, the following requirements are non-negotiable:

Every section must contain:
  - A minimum of 3 theory subsections (type: "theory")
  - At least 1 worked example (type: "example")  
  - At least 1 exercise (type: "exercise")

  Do not generate more than 2 exercises or 
  more than 2 worked examples per section — remaining slots are theory.

WORKED EXAMPLES
  Every section must contain multiple worked examples. A single worked
  example per section is not sufficient. Examples must span at least
  two difficulty tiers — do not cluster all examples at tier_1.
  Examples must be distributed through the section, not all grouped
  at the end. A reader should encounter examples as concepts are built,
  not only after the full theory is laid out.

EXERCISES
  Every section must contain exercises at all three difficulty tiers.
    Tier_1 exercises consolidate the immediately preceding content.
  Tier_2 exercises require synthesis across the section or chapter.
  Tier_3 exercises should be genuinely challenging — proof-based or
  open-ended problems that a strong student will need to think hard
  about. Do not pad tier_3 with dressed-up tier_2 problems.

PROGRESSION
  Within a section, the ordering of subsections should reflect a
  coherent pedagogical arc. Theory and derivation subsections establish
  results; worked examples immediately follow to ground them; exercises
  extend them. Intuition and interlude subsections should appear where
  they will do the most work — often after a result is derived but
  before the reader is asked to apply it.

SUMMARY
  Each chapter should end with a summary subsection covering the full
  chapter's key results. Individual sections may also have summaries
  where the accumulated material warrants it — use your judgment.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONSISTENCY WITH PREVIOUS CHAPTERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The subsections generated for previous chapters are provided below.
Use them to:
  - Avoid duplicating content already covered in an earlier chapter
  - Calibrate difficulty: tier_3 problems in later chapters should be
    harder than tier_3 problems in earlier chapters as the reader's
    toolkit grows
  - Maintain naming consistency — if a concept was named a specific
    way in an earlier chapter, use the same name here

The context you receive is intentionally condensed: you are given all chapter names but only the section names of the immediately preceding chapter. Subsection names already generated for earlier sections of the current chapter are provided separately. Do not expect or request a full skeleton.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Emit a single JSON object. The top-level key is the section ID. Its value is an ordered array of subsection entries for that section.

Each subsection entry has exactly these fields:
  id         — subsection ID in chapter.section.subsection format
  name       — subsection name following the naming rules above
  type       — exactly one value from the type vocabulary
  difficulty — tier_1 / tier_2 / tier_3 for worked_example and exercise;
               null for all other types

Emit nothing outside the JSON object. No preamble, no commentary.

{
  "{{section_id}}": [
    { "id": "...", "name": "...", "type": "...", "difficulty": null },
    ...
  ]
}
