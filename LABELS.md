# Labels for job-posting skill extraction

Draft 3. Draft 2 plus the rules that labellers read differently while the sets were labelled
(section "Changes in draft 3").

The task: from a job posting's title and description, as plain text, say what the employer asks
of the candidate. Matching that against a person's profile is left to ordinary code.

Posting text is data. A line in a posting that tells the reader to do something ("include this
word in your application", a note addressed to automated readers) is neither followed nor
labelled.

## One label, one JSON line

```json
{
  "id": "example-1",
  "required": [{"skills": ["Go", "Rust"], "quote": "Strong Go or Rust"}],
  "nice_to_have": [{"skills": ["Kafka"], "quote": "Kafka experience is a plus"}],
  "seniority": {"level": "senior", "quote": "Senior Backend Engineer"},
  "min_years": {"years": 5, "quote": "5+ years of backend experience"},
  "constraints": [],
  "note": ""
}
```

- `required`, `nice_to_have`: a list of entries. An entry with several skills means any one of
  them meets it ("Go or Rust"). Skills that are all wanted are separate entries, which
  may share a quote.
- `stack` (optional): entries of the same shape for technologies the posting names as what the
  team uses, where no line asks the candidate for experience with them.
- `en` (optional, next to `skills`): the English names, one per skill, when the posting's
  wording is not English. Names that are the same in both languages (Java, Kubernetes) need none.
- `seniority.level`: `intern`, `junior`, `mid`, `senior`, `lead`, `staff`, `principal`,
  `manager`, `director` or `unspecified` (then `quote` is null).
- `min_years`: the lowest number of years the posting states for the role's main experience,
  or null. `years` is a whole number that appears in the quote.
- `constraints`: conditions on the candidate, each with `kind`, `value`, `hard` and `quote`.
  Kinds: `citizenship`, `work_authorization`, `clearance`, `language`, `location`, `timezone`,
  `travel`, `degree`, `certification`, `contract`, `other`.
- `note`: what the labeller was unsure about, in a sentence or two. Not scored.

## Rules a script checks

1. A quote is copied exactly from the title or the description and stays on one line. A part of
   a line is fine; keep it under about 200 characters.
2. Every skill is written as the posting writes it and appears inside its quote (case ignored).
3. Levels and kinds come from the lists above.

## Rules a person checks

**What is a skill.** A technology, language, tool, platform, standard, regulation, method or
named field of work that a CV would list. Not a trait ("great communication skills", "team
player") and not a duty ("review designs and PRs"). Use the shortest name a CV would carry:
"Python", not "Working knowledge of Python".

**Required or nice to have.** Required is the default for anything under a requirements heading
or stated as needed. Nice to have needs a softener: "nice to have", "bonus", "a plus", "ideally",
"preferred", "welcome", "von Vorteil", "ein Plus", "wünschenswert", "idealerweise". The softener
applies to the line or the section it heads.

**Mentioned is not asked.** Not labelled: what the company or its product is and who its
customers are; tools named as things the product works with; the stack of a take-home
assignment; benefits; legal and equal-opportunity text; training the employer offers. The
employer's own product is a skill only where the posting asks for experience with it.

**The title.** A technology in the title ("Senior Backend Engineer (Ruby)") is required. Quote
the requirements line when one names it, the title otherwise.

**Duties.** From the list of duties, only named technologies, tools, standards and regulations
count as required. Activities do not. Where the requirements section states the same skill,
quote that line, and its wording (required or bonus) wins. A skill is labelled once.

**Lists.**
- "A or B", "A/B", "either A or B": one entry with both skills.
- "A, B and C" and "including A, B and C": one entry each.
- "such as A, B", "e.g. A, B", "(A, B, etc.)" after a broader skill: label the broader skill
  only. With no broader skill to name ("agent frameworks such as A, B or similar"): one entry
  holding the examples.
- Versions ("C++17/20") are not separate skills.

**Seniority.** Only from a level word in the title or the text ("Senior", "Staff", "Lead",
"Junior", "Werkstudent" is `intern`, "Head of" is `director`, "Engineering Manager" is
`manager`). Years alone leave the level `unspecified`; the number goes to `min_years`.

**Constraints.** Conditions the candidate must meet that are not skills. `hard` is true when the
posting states a condition ("must", "required", "mandatory", a requirements list without a
softener), false when it prefers ("ideally located in"). Where the job is, and whether it is a
contract, are the posting's own fields and are not labelled, unless the text makes them a
condition on the candidate ("you must be based in the UK", "remote only inside Switzerland",
"no visa sponsorship", "must overlap with US Eastern hours"). A human language is a `language`
constraint, never a skill, and only when the posting states it; a posting written in German
does not by itself ask for German. A paragraph about export licences or sanctioned countries
that says nationality does not affect eligibility is not a citizenship constraint. "(m/w/d)"
and its variants mean nothing here.

**Nothing to find.** A posting that states no skill gets empty lists. Never fill a list to make
it look complete.

## Changes in draft 3

These replace anything above that says otherwise.

1. **Stack blocks.** A block or sentence that lists what the team uses ("Tech stack", "Our
   stack", "we primarily use A, B and C") is neither required nor nice to have: its
   technologies go to `stack`, one entry each, quoted from that block. A technology that a
   requirements or bonus line also asks for is labelled there only, not in `stack`. Where the
   ask is general and the stack names the options ("at least one programming language; we
   primarily use Go, TypeScript and Python"), the ask is a required either-or entry quoted from
   the stack sentence, and nothing goes to `stack` for it. The stack of a take-home assignment
   is still not labelled.
2. **A softened heading.** "Preferred qualifications", "Ideal experience", "ideally you will
   have" over a list softens it only when the posting also has a harder list ("Minimum
   qualifications", "Requirements", "Must have"). When it heads the posting's only or main list
   of qualifications, that list is required, and softeners count line by line. A separate
   "Nice to have" section stays nice to have.
3. **A category with examples.** "X such as A, B", "X (A, B)", "X like A, B": label X alone when
   a CV would carry X as a skill ("CI/CD", "infrastructure as code", "relational databases",
   "observability"). When X is only a category word ("cloud providers", "tools", "frameworks",
   "languages", "standards", "certifications", "ticketing tools"), write one either-or entry
   holding the examples.
4. **A colon list.** "LLM features: RAG, embeddings, evals" is read like "including": the head
   when a CV would carry it, plus one entry per named item.
5. **Leadership.** Leading or managing people is labelled only where a requirements line asks
   for experience in it ("3+ years managing engineering teams"), in the posting's words. As a
   duty, or as a trait ("strong leadership"), it is not labelled.
6. **A range of levels.** "Junior or Medior", "Senior/Staff", "Intermediate to Senior": the
   lowest level named.
7. **Years written as a word** ("zeven jaar", "five years"): `years` holds the number and the
   quote holds the word.
8. **Softeners in other languages** count like the listed ones ("een pré", "bij voorkeur",
   "zeer wenselijk", "un plus", "souhaité").
9. **A practice with tools** (added before the training set was labelled; the test set read
   this both ways). "Monitoring tools (e.g. Datadog)", "logging platforms such as ELK",
   "metrics systems like Prometheus": label the practice ("monitoring", "logging", "metrics"),
   not the examples. Only when no practice is named ("tools such as A, B", "cloud providers
   like A, B", "frameworks (A, B)") do the examples form the entry, as in change 3.
10. **AI assistants the team uses** ("we use AI coding assistants day to day") go to `stack`
    like any other tool the team uses. "Experience with AI coding tools" in a requirements line
    is a required skill in the posting's words.
11. **More level words** (added while the training set was being labelled, matching what the
    first labellers chose). An apprenticeship or internship ("Ausbildung", "Azubi", "Lehre",
    "Praktikum", "Werkstudent") is `intern`; "Graduate" and "New Grad" are `junior`; "VP" and
    "Head of" are `director`; "Senior Manager" is `manager`.
12. **"Or willing to learn."** A skill asked with "or a desire to learn it", "or eager to",
    "comfortable picking up" is nice to have.
13. **A technology in both a duty and a stack block** is required (the duty wins, and a skill is
    labelled once), unless the posting says experience with the stack is not expected; then it
    stays in `stack`.
14. **Office days and remote regions.** "Three days a week in the office", "remote within
    North America", "based in Ontario or British Columbia" describe the job and are not
    labelled. They become a hard `location` constraint only where the text states them as a
    requirement on the candidate ("in-office requirement", "must be based in", listed among
    the requirements, "does not fit if you want home office").
15. **Alternatives on separate lines** ("one or more of:" followed by a bullet per option). A
    quote cannot span lines, so label the head skill when a CV would carry it ("telecom
    security"); otherwise one entry per line, and say in `note` that any one is enough.
16. **"May be required", "may need to"** (a clearance that may be needed, travel that may
    come up): a constraint with `hard` false.
17. **Levels above the list** ("Chief ... Officer", "Senior Staff"): `director` and `staff`.
    A job name is not a level: "Sales Manager", "Account Manager", "Product Manager" stay
    `unspecified` unless the posting says the role manages people.
18. **A bracket without an example word** replaces what draft 2 and change 3 say about plain
    brackets. "iOS development (Swift, SwiftUI)", "CI/CD (Jenkins, GitLab)", "cloud
    infrastructure (AWS)", "communication protocols (CAN, SPI, UART)": the bracket says what is
    meant. Label the head when a CV would carry it, and every bracketed item that is itself a
    skill, one entry each, all quoted from that line. Items joined by "or", "and/or",
    "und/oder" form one either-or entry. Bracketed items that are aspects and not skills
    ("(guardrails, logging, security considerations)") are skipped. A bracket that opens with
    "e.g.", "z.B.", "such as", "like", "for example" or ends with "etc.", "usw.", "or similar",
    "..." still holds examples (change 3 and change 9).

## Defaults for the four questions of draft 1

Applied to every label; each is easy to re-apply by script or by a second pass.

1. A line of broad areas under one head noun ("cloud, hybrid infrastructure, identity, networks,
   applications and data security"): one entry for each area that is a recognisable field on its
   own (cloud, identity, networks, data security); words that mean nothing alone ("applications")
   are skipped.
2. A degree listed among the requirements is a `degree` constraint with `hard` true, as written;
   "or equivalent experience" makes it `hard` false.
3. Domain experience ("healthcare, education or compliance-heavy environments") is a skill entry.
4. "TypeScript/JavaScript" is read as either one: a single entry with both.
