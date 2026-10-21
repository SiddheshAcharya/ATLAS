# ATLAS — demo script and Q&A notes

For the guide meeting (30 Sep) and the board review (3 Oct). Every number here is measured and
matches the updated paper, the Blue Book and the slides. If a number isn't here, don't quote it.

---

## Part 1 — Before you start (5 minutes)

1. Close heavy apps (browser tabs, other programs). The laptop has 5.9 GB of RAM.
2. Open the VS Code terminal and run:
   ```
   cd "C:\Users\Sidhesh Acharya\Downloads\ATLAS-main\ATLAS-main"
   .venv\Scripts\atlas serve
   ```
   Wait for `Uvicorn running on http://127.0.0.1:8000` (10–30 s).
3. Open **http://127.0.0.1:8000** in the browser. Press **F11** for full screen.
4. If the room is bright, click **☀ Light** at the top right. Light mode reads better on projectors.
5. **The wifi can be off.** The five saved demo runs and every chat question listed below work
   offline. Only a *new* run, or a chat question not listed here, needs the internet.

To stop at the end: click in the terminal and press **Ctrl + C**.

---

## Part 2 — The demo (about 8 minutes)

### Step 1 — Home page (30 s)
Point at the three steps: **Forage → Ground → Report**.
> "You give ATLAS a research question. It reads the literature the way a researcher does, one
> paper at a time, and what it reads decides what it reads next. Every claim it reports carries
> a quote that is checked, character by character, against the paper."

Point at **Demo runs**: *"Five saved runs on three research questions."*

### Step 2 — The graph (1.5 min)
Click **IoT devices for women safety — a0e32253** (15 papers).
- Point at the header: 15 papers read, 73 claims kept, 0 quotes rejected, 132 relations judged.
- Point at the graph:
> "The ringed nodes are the 15 papers ATLAS read. The faded ones are papers they cite, which
> ATLAS knows about but didn't read. Size is PageRank; colour is citation cluster. The graph was
> built live, paper by paper, while it read."
- Point at **What ATLAS did** on the right: *"Its reading order, and how many claims each paper gave."*
- **Click one ringed node.** A preview card appears. Click **Open paper — claims and quotes →**.

### Step 3 — The trust moment (1.5 min) ★ the most important step
You're now on the paper page.
- **Click a claim on the left.** Its quote lights up in orange inside the paper text on the right.
> "This is the grounding gate. The model must copy an exact sentence, and code checks that the
> sentence really is in the paper. If it isn't, the claim is deleted, never repaired. In our
> audit, 49 of 50 quotes were verbatim, against a 95 % target. The one miss was a page number
> the PDF reader left inside a sentence, and we fixed that at the source."
- Point at the green **"quote found verbatim in source"** label.

### Step 4 — The report (1 min)
Click the **Report** tab.
- Numbered citations **[1] [2]**, with the reference list at the bottom.
- Point at the amber **"Auto-detected — verify before relying on it"** box above the disagreements:
> "Honestly: this contradiction, a NodeMCU device against a Raspberry Pi Pico device, is false.
> It's two different devices, not a disagreement. Relating papers to each other is ATLAS's
> weakest part, and the dashboard says so."

### Step 5 — The chat (1.5 min)
Click the **Chat** tab. Ask **exactly** these (type them, or click the button where noted):
1. Click **Summarise**. It gets a cited answer.
2. Type: **`Which sensors do these devices use to detect danger?`** It gets a cited answer.
3. Click **Test the refusal** ("Who won the 2018 FIFA World Cup?").
   It shows an amber **"Refused — nothing ATLAS read addresses this"**.
> "It only answers from what it read. The refusal is decided before any AI model is even called."

Other questions that work on this run: `How do these systems send an alert when a woman is in
danger?` and `Do any of these devices use machine learning?`

⚠ **Don't click "Disagreements" or "Limitations" on the IoT run.** General questions like those
don't match a specific claim closely enough, so they get refused. That's safe behaviour, but it
looks bad in a demo.

### Step 6 — The GROBID run (1 min, optional)
Go back to the home page (**← ATLAS** at the top left). Open **gut microbiome and depression — 4c1f35f3**.
> "This run parsed full-text PDFs with GROBID. A third of its papers were read in full, and a
> full-text paper gave 30 to 65 claims against about 5 from an abstract."
- Open a big node and show the claims with section labels.
- Chat questions that work here: **Summarise**, `Do probiotics improve symptoms of depression?`,
  `How can gut bacteria affect the brain?`, `Why are the clinical results on the gut microbiome
  and depression mixed?`. **Limitations** also works on this run.
- Its one contradiction ("repeatedly associated with depression" vs "clinical results are mixed")
  is a *plausible* tension about the same topic, but it still needs a human to judge it.

### If something goes wrong
- **Page blank or error:** refresh (F5). If that fails, stop the server (Ctrl + C) and start it again.
- **Chat says "error":** you asked something not cached while offline. Use a listed question.
- **Laptop frozen:** close the browser, wait 30 s, and reopen it. The server keeps running.
- **Nothing works:** show the slides. Slide 4 has screenshots of exactly this demo.

---

## Part 3 — Likely questions, with honest answers

**Q1. How is this different from ChatGPT or a normal RAG chatbot?**
Those retrieve once and answer once. ATLAS reads one paper at a time, and each paper changes what
it reads next (a closed loop). It also *proves* its quotes: every claim's quote must be found
verbatim in the source, or the claim is deleted. And its chat refuses anything it didn't read.

**Q2. How do you know it doesn't hallucinate?**
For claims: 49 of 50 audited quotes were found verbatim in the re-fetched source (98 %, against a
95 % target). A quote that fails is dropped, never fixed by the AI. The gate rejected 0–5 claims
per run. For relations and gaps we *don't* claim that; see Q5 and Q6.

**Q3. Did the foraging loop actually beat plain search?**
Partly. We compared it with the same number of top papers from plain similarity search, in one
citation graph. ATLAS read a substantially different set (only 36–56 % overlap) and reached 4–60 %
more of the reference network. But at 9–15 papers it was **not** broader in citation clusters
(−1, 0, +2, +2, −1). We expect that to change at larger budgets, which we haven't tested yet.

**Q4. Your Review-I design said Qwen, vLLM, SPECTER2, Temporal. Why is it different?**
The development laptop has no GPU and 5.9 GB of RAM, so a local 7B model and a local GROBID were
impossible (GROBID literally ran out of memory). We moved to open-weight models on Groq's free
tier, and GROBID on a hosted container. We replaced Temporal with caching every AI call, which
gives the same "resume after crash" property: a 15-paper run replayed exactly, with zero new AI
calls, in 6.7 minutes. The paper states every difference openly.

**Q5. How accurate is the relation judge (supports / contradicts / …)?**
We couldn't establish it, and that's a real finding. A human annotator and an AI annotator agreed
on only 2 of 12 pairs (Cohen's κ = −0.17), so the labels themselves are ambiguous. The main
confusion is whether two similar claims about *different devices* "support" each other or are
"different scope". The IoT runs' only contradiction was false. The next step is written label
rules plus several human annotators.

**Q6. Are the research gaps any good?**
Mostly not yet. Of 10 gaps, 2 were plausible; of 6, none were (AI-rated). The main problem is
wording: two ideas that the corpus does connect, under different words, get reported as
"unlinked". The fix is better concept normalisation. What does work is the rule that every gap
must name the papers that bound it, so each one can be checked in minutes.

**Q7. What does κ = −0.17 mean?**
Cohen's kappa measures agreement beyond chance. 1 is perfect, 0 is chance, and below 0 is worse
than chance. So the two annotators effectively didn't agree. That's why we don't quote a judge
"accuracy" figure.

**Q8. Why only 9–15 papers per run?**
Free-tier AI limits: 8,000 tokens a minute and 200,000 a day per model. A 15-paper run takes 1–4
hours. The gut-microbiome run hit the daily limit at 9 papers, so we stopped it cleanly rather than
record papers with no claims. Deep (75) and Extra Deep (200) modes are built but not yet run.

**Q9. What would a paid AI tier change? What does it cost?**
Speed, not results (every call is cached and deterministic). The measured cost is at most about
US$0.05 per 15-paper run at paid rates. It's in future work.

**Q10. Is it reproducible?**
Yes, measured. A 15-paper run replayed from its cache read the same papers in the same order and
produced identical claims (65) and relations (132), compared field by field.

**Q11. What is GROBID and did it help?**
A tool that turns a PDF into labelled sections. On federated learning it raised the full-text share
from 14 % to 23 % and roughly doubled the claims (97 → 195). On gut microbiome, 3 of 9 papers were
full text, giving 30 and 65 claims against about 5 from an abstract. The limit is that few papers
have a free, open PDF.

**Q12. Why did you use an AI annotator instead of people?**
Time. One team member hand-labelled 15 claim pairs, and the rest were AI-labelled. We say that
clearly, and it's the first thing we'd fix with more time.

**Q13. What happens if the internet or an API fails during the demo?**
Completed runs are saved as offline snapshots and open with the wifi off, as you just saw.

**Q14. Is it legal / ethical to process these papers?**
It only uses terms-of-service-compliant APIs and legally open-access PDFs, and it stores extracted
claims and short quotes, not redistributed full texts.

**Q15. What's original in this project?**
Three things: the reading loop, where what's read changes what's read next (Novelty computed from
the reading history); the mechanical grounding gate with no AI repair; and the hard rule that no
gap is shown without the papers that bound it. Contest, the fourth idea, is only built in a
reduced form, and we say so.

**Q16. What would you do with more time?**
In order: (1) written relation-label rules plus 2–3 human annotators; (2) better concept
normalisation for gaps; (3) Deep and Extra Deep runs on a paid tier; (4) the unbuilt parts
(link-prediction detector D2, full Contest signal, SPECTER2, Leiden).

**If you don't know an answer:** *"We didn't measure that. Here's what we did measure: …"* is
always better than guessing. Examiners respect it.
