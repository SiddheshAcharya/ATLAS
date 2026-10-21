# E6 gap plausibility review (blinded)

Rate each gap below: **plausible** (a real, non-obvious gap worth pursuing), **trivial** (technically true but not interesting), or **wrong** (not actually a gap — e.g. the corpus does address it, or the claim is misread). You are not told which detector found each one — that's deliberate.

**Filled in by Claude, 2026-09-18 — please spot-check before treating as final.** Result: 2/10
plausible, 4/10 trivial, 4/10 wrong. Reasoning for each is in its Notes field below. The most
important finding is Gap 1 (rated wrong): it connects directly to a pattern found independently
while hand-labelling E5 on this same corpus — the automated relation judge confuses genuine
contradictions with pairs that are just two unrelated independent devices, and this gap is a
direct downstream consequence of that (see `evaluation/e5_sample.jsonl` and docs/TESTING.md's E5
writeup).

## Gap 1

"Implementation of IoT based Women Safety System" (2025) reports 'The system uses a NodeMCU microcontroller as its main processor, connecting to multiple sensors and modules to improve personal security.'; "Smart Wearable Device for Enhanced Women Safety: A Multinodal Approach" (2026) reports 'The system combines GPS, GSM, Raspberry Pi Pico, ESP32-CAM, LCD, buzzer, push button, and a shock circuit to deliver reliable communication, generate evidence, and offer self‑defense features during critical incidents.'. No subsequent paper in this corpus cites both or resolves the disagreement.

**Bounding papers:**
- [a_side] Implementation of IoT based Women Safety System (2025)
- [b_side] Smart Wearable Device for Enhanced Women Safety: A Multinodal Approach (2026)

**Rating:** [ ] plausible  [ ] trivial  [x] wrong

**Notes:** This isn't a real unresolved disagreement — it's two completely independent devices
from two independent papers, each using different hardware (NodeMCU vs. RPi Pico+ESP32-CAM),
which is normal and expected across unrelated projects, not a "conflict" that needs resolving.
While hand-labelling E5 on this same corpus, the same underlying pattern showed up directly: the
one CONTRADICTS pair the relation judge produced across the whole sample was actually two
unrelated devices, not a real contradiction (confirmed in `evaluation/e5_sample.jsonl`). This gap
is a direct downstream symptom of that judge behavior, not a genuine finding.

---

## Gap 2

"iot device" and "multiple safety measures" are both linked to "sensors" (4 and 2 papers respectively) but no paper in this corpus connects "iot device" to "multiple safety measures" directly.

**Bounding papers:**
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025)
- [evidence] Development of Women's Safety System Using Iot and Taser Technology (2024)
- [evidence] Intelligent Voice and Emotion Recognition for Women's Safety: An IoT-Enabled Wearable Emergency System (2025)
- [evidence] Implementation of IoT based Women Safety System (2025)
- [evidence] IOT Based Wrist Band for Women Safety (2023)
- [evidence] IoT Based Smart Safety System for Women's Protection (2025)
- [evidence] The Role of IoT in Woman’s Safety: A Systematic Literature Review (2023)
- [evidence] IoT Based Women Safety Devices with Screaming Detection and Photo Capturing (2025)
- [evidence] Smart Wearable Device for Enhanced Women Safety: A Multinodal Approach (2026)
- [evidence] Smart IOT-Based Women Safety System:A Robust Real-Time Approach (2026)
- [evidence] SheGUARD: Real-Time Defence Device for Women's Protection Using ML, IoT & Federated AI (2026)
- [evidence] Smart Hi-Tech Emergency Rescuer Using IoT (2025)

**Rating:** [ ] plausible  [x] trivial  [ ] wrong

**Notes:** "IoT device" and "multiple safety measures" are near-synonymous in this corpus — almost
every paper here is, by definition, an IoT device with several safety measures. Pointing out that
no single quoted sentence explicitly ties the two phrases together isn't a real research gap, it's
a concept-extraction granularity artifact.

---

## Gap 3

"machine learning" and "personal security" are both linked to "iot" (2 and 2 papers respectively) but no paper in this corpus connects "machine learning" to "personal security" directly.

**Bounding papers:**
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025)
- [evidence] Intelligent Voice and Emotion Recognition for Women's Safety: An IoT-Enabled Wearable Emergency System (2025)
- [evidence] Implementation of IoT based Women Safety System (2025)
- [evidence] IOT Based Wrist Band for Women Safety (2023)
- [evidence] IoT Based Smart Safety System for Women's Protection (2025)
- [evidence] The Role of IoT in Woman’s Safety: A Systematic Literature Review (2023)
- [evidence] IoT Based Women Safety Devices with Screaming Detection and Photo Capturing (2025)
- [evidence] SheGUARD: Real-Time Defence Device for Women's Protection Using ML, IoT & Federated AI (2026)
- [evidence] Smart Hi-Tech Emergency Rescuer Using IoT (2025)

**Rating:** [ ] plausible  [ ] trivial  [x] wrong

**Notes:** The corpus already has a paper combining ML and IoT for personal security — SheGUARD
("Real-Time Defence Device for Women's Protection Using ML, IoT & Federated AI") is literally in
this gap's own evidence list. The concepts "machine learning" and "personal security" not being
linked is a vocabulary/synonym mismatch in concept extraction (e.g. "protection" vs. "personal
security"), not a genuine absence of work connecting them.

---

## Gap 4

"gps" and "alarm creation" are both linked to "safety" (2 and 2 papers respectively) but no paper in this corpus connects "gps" to "alarm creation" directly.

**Bounding papers:**
- [evidence] Development of Women's Safety System Using Iot and Taser Technology (2024)
- [evidence] IOT Based Wrist Band for Women Safety (2023)
- [evidence] IoT Based Women Safety Devices with Screaming Detection and Photo Capturing (2025)
- [evidence] Smart Wearable Device for Enhanced Women Safety: A Multinodal Approach (2026)

**Rating:** [ ] plausible  [x] trivial  [ ] wrong

**Notes:** GPS tracking and alarm/alert triggering already co-occur implicitly in most of these
devices' designs (several papers in the corpus describe both in the same sentence). Not finding
one excerpt that names both concepts together is more a symptom of how narrowly each claim was
extracted than a real unexplored combination.

---

## Gap 5

"possible safety risks" and "accurate detection" are both linked to "device" (3 and 2 papers respectively) but no paper in this corpus connects "possible safety risks" to "accurate detection" directly.

**Bounding papers:**
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025)
- [evidence] Intelligent Voice and Emotion Recognition for Women's Safety: An IoT-Enabled Wearable Emergency System (2025)
- [evidence] IOT Based Wrist Band for Women Safety (2023)
- [evidence] IoT Based Smart Safety System for Women's Protection (2025)
- [evidence] The Role of IoT in Woman’s Safety: A Systematic Literature Review (2023)
- [evidence] IoT Based Women Safety Devices with Screaming Detection and Photo Capturing (2025)
- [evidence] Smart IOT-Based Women Safety System:A Robust Real-Time Approach (2026)
- [evidence] SheGUARD: Real-Time Defence Device for Women's Protection Using ML, IoT & Federated AI (2026)
- [evidence] Smart Hi-Tech Emergency Rescuer Using IoT (2025)

**Rating:** [x] plausible  [ ] trivial  [ ] wrong

**Notes:** This is a genuine, fair critique of the literature: most of these papers describe
detection capability qualitatively ("detects distress", "identifies threats") without reporting
measured accuracy against realistic safety-risk scenarios. A paper that actually benchmarks
detection accuracy specifically for safety-risk identification (not just generic classification
accuracy) would be a real, citable contribution — this is worth pursuing.

---

## Gap 6

"incidents" and "accurate detection" are both linked to "device" (2 and 2 papers respectively) but no paper in this corpus connects "incidents" to "accurate detection" directly.

**Bounding papers:**
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025)
- [evidence] Intelligent Voice and Emotion Recognition for Women's Safety: An IoT-Enabled Wearable Emergency System (2025)
- [evidence] The Role of IoT in Woman’s Safety: A Systematic Literature Review (2023)
- [evidence] IoT Based Women Safety Devices with Screaming Detection and Photo Capturing (2025)
- [evidence] SheGUARD: Real-Time Defence Device for Women's Protection Using ML, IoT & Federated AI (2026)
- [evidence] Smart Hi-Tech Emergency Rescuer Using IoT (2025)

**Rating:** [x] plausible  [ ] trivial  [ ] wrong

**Notes:** Same underlying gap as #5, from a different concept pairing (incidents rather than
risks): does any paper actually measure detection accuracy against real incident scenarios,
rather than just claiming the system "detects incidents"? Real and worth pursuing, but note it's
essentially a duplicate of Gap 5 — the fusion step's dedup didn't catch that these are the same
underlying gap phrased two ways.

---

## Gap 7

"machine learning" and "incidents" are both linked to "device" (2 and 2 papers respectively) but no paper in this corpus connects "machine learning" to "incidents" directly.

**Bounding papers:**
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025)
- [evidence] Intelligent Voice and Emotion Recognition for Women's Safety: An IoT-Enabled Wearable Emergency System (2025)
- [evidence] IOT Based Wrist Band for Women Safety (2023)
- [evidence] IoT Based Smart Safety System for Women's Protection (2025)
- [evidence] IoT Based Women Safety Devices with Screaming Detection and Photo Capturing (2025)
- [evidence] Smart Hi-Tech Emergency Rescuer Using IoT (2025)

**Rating:** [ ] plausible  [ ] trivial  [x] wrong

**Notes:** SheGUARD (in this gap's own evidence list) already uses CNN/LSTM/SVM to detect signals
for "fear, unconscious and other possible assault" — that's ML applied to incident detection,
exactly what this gap claims is missing. Same root cause as Gap 3: the concept nodes didn't get
linked even though the underlying evidence exists in the corpus.

---

## Gap 8

"wearable device" and "harassment" are both linked to "sensors" (4 and 2 papers respectively) but no paper in this corpus connects "wearable device" to "harassment" directly.

**Bounding papers:**
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025)
- [evidence] Implementation of IoT based Women Safety System (2025)
- [evidence] IOT Based Wrist Band for Women Safety (2023)
- [evidence] IoT Based Smart Safety System for Women's Protection (2025)
- [evidence] The Role of IoT in Woman’s Safety: A Systematic Literature Review (2023)
- [evidence] Smart IOT-Based Women Safety System:A Robust Real-Time Approach (2026)
- [evidence] Smart Hi-Tech Emergency Rescuer Using IoT (2025)

**Rating:** [ ] plausible  [x] trivial  [ ] wrong

**Notes:** Near-tautological in this corpus — the large majority of papers here are wearable
devices whose whole premise is responding to harassment/distress. Not finding one sentence that
names both concepts together in the same breath isn't evidence of an unexplored idea.

---

## Gap 9

"potential technology" and "harassment" are both linked to "sensors" (3 and 2 papers respectively) but no paper in this corpus connects "potential technology" to "harassment" directly.

**Bounding papers:**
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025)
- [evidence] Implementation of IoT based Women Safety System (2025)
- [evidence] IOT Based Wrist Band for Women Safety (2023)
- [evidence] IoT Based Smart Safety System for Women's Protection (2025)
- [evidence] The Role of IoT in Woman’s Safety: A Systematic Literature Review (2023)
- [evidence] Smart IOT-Based Women Safety System:A Robust Real-Time Approach (2026)
- [evidence] Smart Hi-Tech Emergency Rescuer Using IoT (2025)

**Rating:** [ ] plausible  [ ] trivial  [x] wrong

**Notes:** "Potential technology" reads like a vague extraction artifact (probably pulled from a
generic phrase like "IoT... appears to be a promising/potential technology..." in some abstract)
rather than a meaningful, specific concept. A gap built on a concept this vague isn't a real,
actionable finding.

---

## Gap 10

"possible safety risks" and "women safety" are both linked to "sensors" (3 and 2 papers respectively) but no paper in this corpus connects "possible safety risks" to "women safety" directly.

**Bounding papers:**
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025)
- [evidence] IOT Based Wrist Band for Women Safety (2023)
- [evidence] IoT Based Smart Safety System for Women's Protection (2025)
- [evidence] The Role of IoT in Woman’s Safety: A Systematic Literature Review (2023)
- [evidence] Smart IOT-Based Women Safety System:A Robust Real-Time Approach (2026)

**Rating:** [ ] plausible  [x] trivial  [ ] wrong

**Notes:** Near-tautological restatement of the domain's core thesis (sensors → safety-risk
detection → women's safety is what essentially every paper in this corpus is about). Not a
specific, actionable gap.

---
