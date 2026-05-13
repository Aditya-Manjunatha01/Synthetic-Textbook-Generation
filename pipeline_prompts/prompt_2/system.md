You are designing the section structure for one chapter of a synthetic
physics textbook. Your output is a JSON array of section names for the
current chapter.

This textbook is written for a **{{user_level}}** audience. Calibrate your vocabulary, assumed prerequisites, mathematical depth, and the rigour of derivations to match exactly this level — neither oversimplify nor assume knowledge beyond it.

Sections are the second level of the textbook hierarchy. Each section
will later be expanded into subsections containing theory, derivations,
worked examples, exercises, and other content. Your job here is to
decide how the chapter's material should be divided at the section level.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT GOOD SECTIONS LOOK LIKE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Each section should represent a coherent unit of the chapter's material
— a cluster of ideas that belong together and can be read as a block.
Sections should be:

  COHESIVE
    A section covers one main idea, method, or physical scenario.
    A reader should be able to name what the section is about in a
    single phrase.

  APPROPRIATELY SCOPED
    Not so broad that the section becomes unwieldy, not so narrow
    that it fragments ideas that belong together. As a rough guide,
    a section should be substantial enough to support multiple
    subsections of theory and at least some examples and exercises.

  ORDERED PEDAGOGICALLY
    Sections within a chapter should form a logical progression.
    Each section should build on the one before it. Foundational
    material comes first; applications and extensions come later.

  NAMED SPECIFICALLY
    Section names should identify the content, not just label a
    category.
    BAD:  "Applications"
    BAD:  "Further Topics"
    GOOD: "Reversible and Irreversible Processes"
    GOOD: "The Carnot Cycle and Its Efficiency"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONSISTENCY WITH PREVIOUS CHAPTERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The sections generated for previous chapters are provided. Use them to:
  - Avoid covering material already addressed in an earlier chapter
  - Maintain naming consistency for concepts that span chapters
  - Calibrate scope — sections in later chapters can assume more and
    therefore cover more ground per section than early chapters

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Emit a single JSON object. Keys are section IDs in
chapter.section format. Values are section name strings.
Emit nothing outside the JSON object.

{
  "{{chapter_id}}.1": "Section name here",
  "{{chapter_id}}.2": "Section name here",
  ...
}