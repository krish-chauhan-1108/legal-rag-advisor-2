# Legal source corpus

`corpus.json` contains the section-level text for the three criminal-law Acts:

- BNS: 358 sections
- BNSS: 531 sections
- BSA: 170 sections

It also contains reviewed subsection records for Section 1(1) of each Act.
Records were generated from the official India Code gazette PDFs and carry a
SHA-256 hash of the exact stored text. The API validates every hash at startup.

`contract_corpus.json` adds a first, deliberately limited set of India-wide
central contract provisions: Indian Contract Act sections 10, 27, 73, and 74.
Each record includes its official India Code PDF URL, source snapshot version,
and jurisdiction. State or union territory laws are not yet registered, so do
not cite them as verified sources.

The LLM never writes authoritative quotation text. It may identify an Act and
section, but the backend only returns text from this registry. Unknown or
malformed citations remain unverified instead of being presented as statutory
wording.

## Rebuilding the corpus

The maintenance script is `build_corpus.py`. It is intentionally not part of
the request path. To rebuild it, place the official PDFs in `data/uploads/`
using the filenames defined in the script, then run:

```powershell
python legal_sources/build_corpus.py
```

The parser fails if any expected numbered section cannot be located. Review
the generated diff before committing a source update, especially if India
Code publishes an amended or reformatted edition.
