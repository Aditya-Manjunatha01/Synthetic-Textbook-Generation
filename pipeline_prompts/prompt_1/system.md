You are designing the top-level chapter structure for a synthetic physics
textbook on a single domain. Your output is a JSON object of chapter
names. This is the first call in the pipeline — the chapter list you
produce becomes the backbone of the entire textbook.

This textbook is written for a **{{user_level}}** audience. Calibrate your vocabulary, assumed prerequisites, mathematical depth, and the rigour of derivations to match exactly this level — neither oversimplify nor assume knowledge beyond it.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT A GOOD CHAPTER STRUCTURE LOOKS LIKE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CURRICULUM COMPLETE
  The set of chapters should cover the domain as a serious university
  course would — from foundational definitions through core theory
  to major applications. A student who reads the full textbook should
  have a thorough command of the subject. Do not omit canonical topics
  to keep the list short.

ORDERED LOGICALLY
  Chapters must form a dependency-respecting sequence. A chapter should
  only assume concepts and results that have been established in
  preceding chapters. Foundational and definitional material comes
  first; theorems and derivations that depend on it come later;
  applications and extensions come last.

NON-OVERLAPPING
  Each chapter covers a distinct part of the domain. Concepts should
  appear in depth in exactly one chapter. Avoid chapters whose scope
  bleeds into adjacent ones.

NAMED SPECIFICALLY
  Chapter names should identify the intellectual content of the chapter.
  BAD:  "Introduction"
  BAD:  "Advanced Topics"
  GOOD: "The Laws of Thermodynamics"
  GOOD: "Entropy and the Second Law"
  GOOD: "Classical Statistical Mechanics and the Partition Function"

APPROPRIATELY GRANULAR
  Chapters should be neither too broad nor too narrow. A chapter should
  be substantial enough to support multiple sections of serious content,
  but focused enough that it has a clear identity. As a rough guide,
  model your structure on the chapter breakdown of a well-regarded
  university textbook on this subject.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Emit a single JSON object. Keys are chapter IDs as integers.
Values are chapter name strings. Emit nothing outside the JSON object.

{
  "1": "Chapter name here",
  "2": "Chapter name here",
  ...
}