# RISKS

Ordered by expected damage. Each has a mitigation and a **tripwire** — how you find out early
rather than in week 12.

---

### R1 — Full-text availability is much lower than assumed
**Likelihood: certain.** 40–60% of papers in a typical query have no legally accessible PDF.
Paywalls, publisher-only HTML, or PDFs GROBID chokes on.

Half the pipeline (sections, limitations, future work, claim extraction from Results) needs full
text. If this is treated as an error path, coverage collapses.

**Mitigation.** ADR-010: abstract-only is a first-class depth. PDF resolution order: source-provided
`pdf_url` → arXiv → Unpaywall (`email=` param) → PMC OA → give up gracefully. Bias the harvest
toward arXiv and OA venues when the query is CS/engineering. Report the full-text ratio in
`RunStats` and in the report itself.

**Tripwire.** Week 3: run a resolver script over 200 papers from your actual query and print the
success rate. If it's under 35%, change the harvest mix before building anything downstream.

---

### R2 — The judge over-labels contradictions
Detector 5, the contradiction report, and the Contest score all sit on Job C's output. LLMs
readily call two claims contradictory when they simply measured different things.

**Mitigation.** `DIFF_SCOPE` as an explicit, well-prompted label; force the scope fields into the
judge's input; require the rationale to name *which* scope dimension differs when it says
`CONTRADICTS`. Set a confidence floor (0.7) for writing a `CONTRADICTS` edge.

**Tripwire.** Hand-label 60 claim pairs yourself. Measure precision/recall per label. If
`CONTRADICTS` precision is below ~0.7, fix the prompt before building detector 5. This
hand-labelled set doubles as an evaluation table in the report — it is not wasted work.

---

### R3 — Gap output is plausible-sounding noise
The failure that ruins the demo: a beautifully formatted "gap" that any domain person can see is
trivial or wrong.

**Mitigation.** The citation rule (a gap with no bounding papers is not shown), the corroboration
bonus, degree penalties on hub concepts, and minimum-support thresholds throughout
`GAP_DETECTORS.md`. Show bounding papers directly beside every gap in the UI so a reader can
check it in one click.

**Tripwire.** Week 9: take your top 10 gaps to a faculty member in that domain and ask them to
mark each *plausible / trivial / wrong*. Report the result honestly. "6 of 10 judged plausible by
a domain expert" is a strong evaluation result; a silent gap list is not.

---

### R4 — Concept normalization noise poisons detectors 1, 2 and 3
"IoT device", "IoT devices", "internet-of-things device" as three concepts turns Swanson ABC into
a random-phrase generator.

**Mitigation.** Lowercase → lemmatize → embed → agglomerative cluster at 0.85 → canonical label.
Maintain a small manual alias file (`config/concept_aliases.yaml`) for your demo domain; hand-curating
40 aliases is a legitimate engineering choice and takes an hour.

**Tripwire.** Week 6: print the top 100 concepts by frequency and read them. If you see obvious
duplicates, fix normalization before writing any detector.

---

### R5 — Cost or rate limits blow up on the extra-deep run
200 papers × claim extraction × thousands of judge calls, or S2 throttling mid-crawl.

**Mitigation.** Per-run USD budget as a stopping criterion; cached everything; batched judge calls;
Haiku-class model for Job C; OpenAlex (not S2) for the citation walk. Run extra-deep **once**,
early, save the artefacts, and demo from the saved run.

**Tripwire.** After the first standard run, read the `costs` table and extrapolate ×8. If
extra-deep projects over budget, cut judge batch size or drop to the local model before it becomes
an emergency.

---

### R6 — Live graph UI stutters at scale
Cytoscape re-layout on every node addition is fine at 50 nodes and unusable at 800.

**Mitigation.** Batch layout every 25 additions; use `fcose` with `randomize: false` for
incremental stability; virtualize the frontier table.

**Tripwire.** Synthetic test with 1000 nodes in week 8, before you have real data to hide behind.

**Run, 2026-09-19 — confirmed, not hypothetical.** `web/scripts/stress_test_layout.cjs`
runs the exact `fcose` layout call `GraphView.tsx` uses, headless, at increasing synthetic
scale: 100 nodes/188 edges → 0.5s, 500 nodes/1018 edges → 11.8s, 1000 nodes/1981 edges →
32.6s. Scaling is well worse than linear (5x the nodes from 100→500 costs 25x the time),
so this is exactly the "fine at 50, unusable at 800" pattern predicted, now measured
rather than assumed. The documented mitigation ("batch layout every 25 additions") had
never actually been implemented — `RunView.tsx` triggered a full graph refetch and full
`cy.layout().run()` on every single relevant event, with no batching at all. Fixed with a
graph-size-aware throttle: below 100 nodes, every relevant event refreshes immediately
(unchanged — this is what typical 6-15 paper runs need, and what CLAUDE.md invariant #6
"never batch the whole graph write to the end" requires); at or above 100 nodes, refreshes
are limited to once every 4 seconds except at terminal events (`run_finished` /
`pipeline_finished`), which always refresh immediately so the final view is never stale.
Not fully solved — this reduces *how often* an expensive full re-layout runs, it doesn't
make any individual re-layout faster (a true incremental layout, positioning only newly
added nodes while leaving existing ones fixed, is the deeper fix and remains future work)
— but it directly addresses the actual failure mode (relayout-on-every-event) rather than
just the symptom.

---

### R7 — GROBID is a heavy dependency
~1.5 GB image, slow cold start, 5–20 s per PDF, occasional hangs.

**Mitigation.** Run it as a long-lived container, cache TEI by PDF hash, 60 s timeout with PyMuPDF
fallback. Never make GROBID availability a hard requirement for the pipeline to run at all.

**Tripwire.** `make up && atlas ingest --pdf tests/fixtures/sample.pdf` must work on a teammate's
machine in week 2.

---

### R8 — Scope creep kills the deadline
The design is ambitious. Chat interface, four report types, six detectors, a live graph, three
depth modes. Any one of them can absorb three weeks.

**Mitigation.** `ROADMAP.md` labels every feature core / differentiator / stretch. Ship core end
to end **before** improving any single stage. A working thin pipeline in week 6 beats an excellent
claim extractor and no loop in week 12.

**Tripwire.** If by week 6 you cannot run `atlas run "<query>" --mode standard` and get *any*
report out, stop building features and connect what exists.

---

### R9 — Non-determinism makes results unreproducible
An examiner asks you to re-run it and you get a different graph.

**Mitigation.** `temperature=0`, LLM response cache, seeded clustering, fixed model versions
pinned in `models.yaml`, `config_hash` stored on every run.

**Tripwire.** Week 7: run the same query twice with a warm cache and diff the graphs. They should
be identical. If they are not, find the source of randomness immediately — it gets harder to find
every week.

---

### R10 — Ethical / licensing exposure
Bulk-downloading paywalled PDFs is a real problem, not a hypothetical one.

**Mitigation.** Only fetch OA PDFs via legitimate routes (arXiv, PMC OA, Unpaywall, publisher OA
links). Never scrape Sci-Hub or equivalents. Respect `robots.txt` and every API's terms. Store a
`license` field per paper and show it in the UI. Put a short paragraph on this in the report —
examiners notice when it is missing.
