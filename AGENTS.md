# AGENTS.md

## Purpose
This repository is used for a mathematical modeling competition.
Codex should prioritize **clarity, simplicity, reproducibility, and fast iteration**.

Do not over-engineer the project. Avoid unnecessary abstractions, excessive classes, deep inheritance, or too many small files.

## 1. General Coding Rules
- Keep code concise, readable, and easy to debug.
- Each file should have one clear main responsibility.
- Reuse existing functions and modules whenever possible.
- Avoid duplicated logic across different questions.
- Do not create unnecessary wrappers, classes, interfaces, or configuration layers.
- Prefer simple functions over classes unless a class is clearly useful.
- Do not hard-code local absolute paths.
- All scripts should be runnable from the project root.
- Remove dead code, temporary debug prints, abandoned functions, and large commented-out code blocks.
- Do not add new third-party dependencies unless they are truly necessary.

## 2. Chinese Comments Are Required
All important code should contain **clear and concise Chinese comments**.

Chinese comments should explain:
- key formulas;
- unit conversions;
- time alignment;
- important data transformations;
- optimization constraints;
- non-obvious implementation logic;
- important input/output assumptions.

Do not comment every trivial line.
Comments should explain **why the code does something**, not simply repeat the code.

Example:

```python
# 将 10 分钟功率转换为该时间段对应的电量，单位为 kWh
energy_kwh = power_kw * (10 / 60)
```

## 3. Separate Files by Question
Code, configuration, intermediate outputs, and final outputs must be clearly separated by question.

Recommended structure:

```text
src/
├── common/          # Code genuinely shared by multiple questions
├── q1/              # Core implementation for Question 1
├── q2/              # Core implementation for Question 2
├── q3/              # Core implementation for Question 3
└── q4/              # Core implementation for Question 4

scripts/
├── run_q1.py
├── run_q2.py
├── run_q3.py
└── run_q4.py

outputs/
├── q1/
├── q2/
├── q3/
└── q4/
```

Naming rules:
- Question-specific files should use `q1_`, `q2_`, `q3_`, `q4_` prefixes, or be stored directly inside the corresponding question folder.
- Only code truly reused by multiple questions should be placed in `common/`.
- Avoid meaningless filenames such as `test1.py`, `new.py`, `final2.py`, or `temp_model.py`.

## 4. Data Rules
- Official raw data in `data/raw/` is read-only.
- Never overwrite or manually modify official source files.
- Cleaned or transformed data should be written to `data/processed/`.
- Data preprocessing must be reproducible through code.
- Keep units and time indexes explicit.
- Record any dropped, filled, corrected, clipped, or transformed values.

## 5. Output Rules
- Intermediate and final results for each question must be stored separately.
- Do not mix outputs from different questions.
- Official submission files should be stored separately from debugging outputs.
- Debug scripts must never overwrite official submission files.
- Output filenames should clearly indicate the question and content.

## 6. Modeling Boundary
Codex is responsible for implementation, not for silently changing the mathematical model.

Do NOT independently introduce or change:
- objective functions;
- constraints;
- model assumptions;
- parameter definitions;
- evaluation metrics;
- sample definitions;
- forecast targets;
- optimization rules;
- new models replacing an agreed model.

If such a decision is not explicitly defined by the problem statement, project documents, or team decision, add:

```text
TODO: 需建模手确认
```

Then clearly state what must be confirmed.

Do not guess a modeling decision just to make the code run.

## 7. Minimal-Change Principle
When modifying existing validated code:
- prefer the smallest correct change;
- do not perform large refactors unless necessary;
- do not rewrite working modules only for style reasons;
- preserve reusable logic between Q1 → Q2 → Q3 → Q4.

## 8. Validation Before Completion
Before declaring a coding task complete, check:
- input file paths;
- column names;
- missing values;
- time alignment;
- unit conversions;
- model constraints;
- output paths;
- output format;
- whether official templates are preserved.

For optimization tasks, also verify basic feasibility and constraint satisfaction.

## 9. Codex Work Summary
Before coding, identify:
1. which question is being implemented;
2. which files should be created or modified;
3. which existing modules can be reused;
4. whether any modeling decision requires confirmation.

After coding, briefly report:
- files created or modified;
- what was implemented;
- how to run it;
- generated outputs;
- unresolved `TODO: 需建模手确认` items.

## 10. Documentation and AI Usage Declaration
This competition requires a declaration of AI tool usage.

After every code generation or code modification:
- Update `README.md` accordingly.
- `README.md` should contain only explanations of the competition code, including project structure, module purposes, execution methods, inputs, outputs, and reproducibility notes.
- Do NOT record AI usage details in `README.md`.
- Record all AI tool usage separately in `README_AI.md`, including the AI tool/model used, purpose of use, affected files or modules, and a brief description of the assistance provided.
- Keep `README_AI.md` concise, factual, and continuously updated throughout the competition.
