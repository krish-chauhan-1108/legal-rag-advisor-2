# Legal source corpus

`corpus.json` is a versioned, importable JSON corpus. It currently contains
only the verified Section 1(1) short-title samples for BNS, BNSS, and BSA.

The sample wording was checked against the official gazette PDFs already present
in this repository under `data/uploads/`:

- `250883_english_01042024.pdf` — BNS
- `250884_2_english_01042024.pdf` — BNSS
- `250882_english_01042024_0.pdf` — BSA

The registry validates each `source_hash` against `exact_text` at startup. Add
new records only after reviewing the authoritative source text and updating
`corpus_version`. The LLM never writes authoritative quotation text. A model
may return either an Act name (`act`) or short code (`code`); the backend
normalizes both without treating an unresolved candidate as verified.

## Corpus expansion status

The requested full-corpus expansion was not generated in this run. `pypdf`
successfully extracts text from the three supplied PDFs, but the extracted text
contains page artifacts and repeated numeric strings that resemble section
starts (including schedule/table content and footer text). A safe parser must
validate section continuity and boundaries before emitting records; no records
were generated from ambiguous matches, and the existing three reviewed samples
remain the complete corpus.

Observed source coverage:

- BNS: 102 pages; the main body appears to run through section 358.
- BNSS: 249 pages; the main body appears to run through section 531.
- BSA: extraction was not completed within the interactive time limit.

The PDFs were not modified, and no generated record should be treated as
complete coverage until the reproducible parser has passed boundary and hash
checks for each law.
