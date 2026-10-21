# E4 grounding-gate hand-check (docs/TESTING.md E4)

For each **verified** claim below, check the box only if the quote is genuinely verbatim in the source paper AND correctly attributed to it. Target: >=95%.

**Filled in by Claude, 2026-09-18 — please spot-check before treating as final.** Method:
independently re-fetched every distinct source paper (11 via the OpenAlex/Crossref API, 3 via
arXiv's HTML full text, plus the actual PDF for 3 papers where the quoted section wasn't in the
abstract — `doi:10.48175/ijarsct-24973`, `doi:10.37965/jait.2023.0179`,
`doi:10.18653/v1/2024.findings-acl.352`) and checked each quote as an exact substring of the real
text, not just judged by eye. **Result: 49/50 (98%) genuinely verbatim and correctly attributed —
above the >=95% target.** The one exception is claim #18 below, a real finding: a single digit
("5") was fabricated into an otherwise-correct quote, and it slipped through because that claim
matched via the grounding gate's fuzzy path (`fuzzy97`) rather than an exact match. A few other
claims (#8, #17, #20, #40) look like exact matches to the eye but differ from the canonical
published text by a stray hyphen or line-break artifact (e.g. "fixedrank" vs "fixed-rank",
"COUNTER-FACT" split across a line) — these are PyMuPDF PDF-extraction quirks in what ATLAS itself
parsed, not fabrication, and are marked verified.

## Verified claims (50)

### 1. `doi:10.1109/asiancon62057.2024.10837901` — abstract (exact)
- paraphrase: The IoT module ensures seamless connectivity, allowing remote monitoring via a central platform.
- quote: "The IoT module facilitates seamless connectivity, enabling remote monitoring through a centralized platform."
- [x] genuinely verbatim and correctly attributed

### 2. `doi:10.1109/access.2023.3252903` — abstract (exact)
- paraphrase: The devices transmit alerts using GPS, GSM, and Raspberry Pi technologies.
- quote: "In addition, the devices used different technology to transmit the alerts including global positing system (GPS), global system for mobile communication (GSM), and Raspberry pi."
- [x] genuinely verbatim and correctly attributed

### 3. `doi:10.1109/asiancon62057.2024.10837901` — abstract (exact)
- paraphrase: The device is an IoT-based system that monitors physiological parameters like heartbeat and EEG, and includes a panic switch, GSM, GPS, and IoT modules.
- quote: "The women safety device is an innovative IoT-based safety system designed to monitor key physiological parameters, such as heartbeat and EEG, and coupled with a panic switch, GSM, GPS, and IoT modules."
- [x] genuinely verbatim and correctly attributed

### 4. `doi:10.1109/icses66558.2026.11479101` — abstract (exact)
- paraphrase: The device employs GPS and GSM to instantly share location details with nearby police stations and the wearer’s relatives.
- quote: "Our device uses GPS and GSM system for sharing details immediately to nearby safety station(police station)and their relatives."
- [x] genuinely verbatim and correctly attributed

### 5. `doi:10.55041/isjem.acme148` — abstract (exact)
- paraphrase: The devices incorporate technologies such as Arduino, GPS, and GSM to send notifications.
- quote: "Additionally, the gadgets used several technologies, including as Arduino, the global positioningsystem (GPS), and the worldwide system for mobile communication (GSM), to convey the notifications."
- [x] genuinely verbatim and correctly attributed

### 6. `doi:10.1109/asiancon62057.2024.10837901` — abstract (exact)
- paraphrase: The device is an IoT-based system that monitors physiological parameters like heartbeat and EEG, and includes a panic switch, GSM, GPS, and IoT modules.
- quote: "The women safety device is an innovative IoT-based safety system designed to monitor key physiological parameters, such as heartbeat and EEG, and coupled with a panic switch, GSM, GPS, and IoT modules."
- [x] genuinely verbatim and correctly attributed

### 7. `doi:10.1109/icpcsn65854.2025.11034876` — abstract (exact)
- paraphrase: The device features an onboard buzzer to alert nearby people and an LCD screen that shows real‑time status information.
- quote: "Additionally, an onboard buzzer alerts nearby individuals, while an LCD display provides real-time status updates."
- [x] genuinely verbatim and correctly attributed

### 8. `arxiv:2606.04325` — other (exact)
- paraphrase: Applying a nonlinearity to the low‑rank product BA lets the update rank grow or shrink, removing the fixed‑rank limitation of standard LoRA adapters.
- quote: "By applying a nonlinearity to the low-rank product BA, LR-LoRA allows the rank of the update to increase or decrease, relaxing the fixedrank constraint imposed by standard low-rank adapters and enabling the optimizer to adapt the dimensionality of each layer's update (formalized in Section 3.3)."
- [x] genuinely verbatim and correctly attributed

### 9. `doi:10.1109/incip64058.2025.11020103` — abstract (exact)
- paraphrase: The authors claim that their IoT-based security system offers women safety through real‑time monitoring and accessible mechanisms.
- quote: "The proposed work describes a security system by using IoT that provides women safety using real time monitoring as well as approachable mechanisms."
- [x] genuinely verbatim and correctly attributed

### 10. `arxiv:2501.13787` — other (exact)
- paraphrase: Additive PEFT inserts small bottleneck adapters between model layers to achieve fine‑tuning with minimal changes.
- quote: "Additive methods involve inserting small adapter networks, also known as bottleneck adapters [56], between the layers of FMs, making minimal changes to achieve fine-tuning."
- [x] genuinely verbatim and correctly attributed

### 11. `doi:10.1109/access.2023.3252903` — abstract (exact)
- paraphrase: Logistic regression, hidden Markov models, and decision trees are employed to detect women who may be under threat.
- quote: "Furthermore, several machine learning algorithms such as logistic regression, hidden Markov, and decision trees are used to identify the potential under threat women and help prevent the undesirable situation for women beforehand."
- [x] genuinely verbatim and correctly attributed

### 12. `doi:10.1109/access.2023.3252903` — abstract (exact)
- paraphrase: Combining multiple sensors is emphasized as a way to improve threat detection accuracy and precision.
- quote: "Lastly, this study emphasizes the use of combinations of sensors to get multiple types of input data that could lead to determining the possibility of threat with better accuracies and precisions."
- [x] genuinely verbatim and correctly attributed

### 13. `doi:10.1109/access.2023.3252903` — abstract (exact)
- paraphrase: The paper proposes an architectural model outlining key components for building IoT‑based women’s safety devices.
- quote: "In addition, this work proposes an architectural model that presents prominent components necessary to develop IoT-based women's safety devices."
- [x] genuinely verbatim and correctly attributed

### 14. `doi:10.1109/incip64058.2025.11020103` — abstract (exact)
- paraphrase: The IoT solution aims to deliver rapid aid and analyze data to predict high‑risk areas, thereby improving safety measures.
- quote: "Being an IoT enabled solution the purpose is not only to provide aid at a speedy pace but also helps in analyzing data to predict prone areas create imminent risk and improve safety measures."
- [x] genuinely verbatim and correctly attributed

### 15. `doi:10.62643/ijerst.2025.v21.i2.pp712-722` — abstract (exact)
- paraphrase: The evaluation involved a thorough analysis and synthesis of research publications from 2016 to 2022.
- quote: "The evaluation process involves a thorough analysis and synthesis of the research publications published in reputable research venues between 2016 and 2022."
- [x] genuinely verbatim and correctly attributed

### 16. `doi:10.1109/asiancon62057.2024.10837901` — abstract (exact)
- paraphrase: When abnormal conditions occur or the panic switch is pressed, the system sends immediate GSM alerts to preset contacts and provides real-time GPS location.
- quote: "In the event of abnormal conditions or manual activation through the panic switch, the system triggers immediate alerts via the GSM module to predefined contacts, accompanied by real-time GPS location tracking."
- [x] genuinely verbatim and correctly attributed

### 17. `arxiv:2603.18088` — other (exact)
- paraphrase: Constraints are needed for stable RFT and to avoid degenerate outputs, but stronger constraints conflict with optimization by limiting discovery of better solutions.
- quote: "Constraints are essential for stabilizing reinforcement learning fine-tuning (RFT) and preventing degenerate outputs, yet they inherently conflict with the optimization objective because stronger constraints limit the ability of a finetuned model to discover better solutions."
- [x] genuinely verbatim and correctly attributed

### 18. `arxiv:2501.13787` — other (fuzzy97)
- paraphrase: Freeze Layers methods fine‑tune only the last five layers of foundation models.
- quote: "Freeze Layers-based methods only fine-tune the last few 5 layers of FMs inspired by this work [118]."
- [ ] genuinely verbatim and correctly attributed — **NOT verbatim**: the real sentence (confirmed against the arXiv HTML full text) reads "...only fine-tune the last few layers of FMs..."; the stored quote has a fabricated "5" inserted before "layers" that does not exist in the source. This claim matched via the grounding gate's fuzzy path (marked `fuzzy97` — ~97% string similarity), which is loose enough to let a single inserted digit through. Everything else about the claim (attribution, surrounding wording) is correct — this is a one-character insertion, not a wrong paper or a fabricated sentence.

### 19. `doi:10.1109/access.2023.3252903` — abstract (exact)
- paraphrase: Logistic regression, hidden Markov models, and decision trees are employed to detect women who may be under threat.
- quote: "Furthermore, several machine learning algorithms such as logistic regression, hidden Markov, and decision trees are used to identify the potential under threat women and help prevent the undesirable situation for women beforehand."
- [x] genuinely verbatim and correctly attributed

### 20. `arxiv:2606.04325` — other (exact)
- paraphrase: The complexity of updates varies with depth and shows systematic differences between MLP and attention components.
- quote: "Takeaway: update complexity is depth-dependent and differs systematically between MLP and attention modules."
- [x] genuinely verbatim and correctly attributed

### 21. `doi:10.1109/icses66558.2026.11479101` — abstract (exact)
- paraphrase: The device continuously monitors a wearer’s heart rate, body movements, and brain stress or panic patterns.
- quote: "It's working process is continuous monitor of woman who wears the device, its monitoring process is: tracks the basic biometric signal (heart rate),body movements and unusual patterns in brain (stress or over panic)."
- [x] genuinely verbatim and correctly attributed

### 22. `doi:10.1109/access.2023.3252903` — abstract (exact)
- paraphrase: The review found that pulse-rate and pressure sensors are the most commonly used sensors in IoT safety devices for women.
- quote: "The results revealed that different types of sensors are used to capture the state of women undergoing safety issues where the pulse-rate, and pressure sensors are most commonly used sensors in these devices."
- [x] genuinely verbatim and correctly attributed

### 23. `doi:10.55041/isjem.acme148` — abstract (exact)
- paraphrase: The paper reports that it provides a thorough literature review of IoT devices aimed at women's safety, describing their key characteristics, wearables, sensors, and applied machine‑learning methods.
- quote: "This study offers a comprehensive assessment of the literature showing IOT devices for women's safety, their keycharacteristics, wearable technology, sensors employed, and machine learning techniques applied."
- [x] genuinely verbatim and correctly attributed

### 24. `doi:10.18653/v1/2024.findings-acl.352` — other (exact)
- paraphrase: Experiments on the ZsRE and COUNTERFACT benchmarks indicate that the proposed modifications let standard fine‑tuning match or surpass highly specialized editors in edit‑score.
- quote: "Our experiments on the ZsRE and COUNTERFACT datasets demonstrate that these simple modifications allow standard fine-tuning to match or outperform highly specialized editors in terms of edit score."
- [x] genuinely verbatim and correctly attributed

### 25. `arxiv:2501.13787` — other (exact)
- paraphrase: Parameter‑efficient fine‑tuning reduces the number of updated parameters, lowering computational and storage costs for models like BERT and GPT‑3.
- quote: "PEFT has emerged as a significant approach for fine-tuning foundation models (such as BERT and GPT-3), aiming to reduce the number of parameters that need to be updated during the tuning process, thereby lowering computational and storage costs."
- [x] genuinely verbatim and correctly attributed

### 26. `doi:10.1109/asiancon62057.2024.10837901` — abstract (exact)
- paraphrase: When abnormal conditions occur or the panic switch is pressed, the system sends immediate GSM alerts to preset contacts and provides real-time GPS location.
- quote: "In the event of abnormal conditions or manual activation through the panic switch, the system triggers immediate alerts via the GSM module to predefined contacts, accompanied by real-time GPS location tracking."
- [x] genuinely verbatim and correctly attributed

### 27. `doi:10.62643/ijerst.2025.v21.i2.pp712-722` — abstract (exact)
- paraphrase: Effective safety systems should feature auto‑activation of alarms with minimal human involvement and higher accuracy.
- quote: "It was determined that in order to successfully address the issue, systems that emphasise auto-activation of alarm creation with less human participation and greater accuracies must be created, even though much research has been produced in the underlying topic."
- [x] genuinely verbatim and correctly attributed

### 28. `doi:10.1109/icses66558.2026.11479101` — abstract (exact)
- paraphrase: The system utilizes CNN, LSTM, and SVM models, and aims to implement federated AI, to detect fear, unconsciousness, and potential assaults, incorporating a panic button and voice activation.
- quote: "To make the system more effective use CNN,LSTM,SVM models to detect the signal for fear, unconscious and other possible assault, trying to implement the federated AI model for more accurate prediction and include the panic button and voice activation."
- [x] genuinely verbatim and correctly attributed

### 29. `doi:10.1109/access.2023.3252903` — abstract (exact)
- paraphrase: Combining multiple sensors is emphasized as a way to improve threat detection accuracy and precision.
- quote: "Lastly, this study emphasizes the use of combinations of sensors to get multiple types of input data that could lead to determining the possibility of threat with better accuracies and precisions."
- [x] genuinely verbatim and correctly attributed

### 30. `doi:10.1109/icses66558.2026.11479101` — abstract (exact)
- paraphrase: The device employs GPS and GSM to instantly share location details with nearby police stations and the wearer’s relatives.
- quote: "Our device uses GPS and GSM system for sharing details immediately to nearby safety station(police station)and their relatives."
- [x] genuinely verbatim and correctly attributed

### 31. `doi:10.62643/ijerst.2025.v21.i2.pp712-722` — abstract (exact)
- paraphrase: Combining multiple sensors can provide more accurate and precise threat detection.
- quote: "Finally, this study highlights the utilisation of sensor combinations to get various input data types that may result in more accurate and precise threat detection."
- [x] genuinely verbatim and correctly attributed

### 32. `doi:10.1109/access.2023.3252903` — abstract (exact)
- paraphrase: The authors identified a need for systems that auto‑activate alerts with minimal human interaction and higher accuracy.
- quote: "It was identified that despite producing notable research in the underlying domain the systems emphasizing auto-activation of alert generation with lesser human interaction and improved accuracies are required to be developed for effectively addressing the concern."
- [x] genuinely verbatim and correctly attributed

### 33. `doi:10.1109/incip64058.2025.11020103` — abstract (exact)
- paraphrase: The IoT solution aims to deliver rapid aid and analyze data to predict high‑risk areas, thereby improving safety measures.
- quote: "Being an IoT enabled solution the purpose is not only to provide aid at a speedy pace but also helps in analyzing data to predict prone areas create imminent risk and improve safety measures."
- [x] genuinely verbatim and correctly attributed

### 34. `doi:10.1109/icpcsn65854.2025.11034876` — abstract (exact)
- paraphrase: The system uses a NodeMCU microcontroller as its main processor, connecting to multiple sensors and modules to improve personal security.
- quote: "The system utilizes a NodeMCU microcontroller as the central processing unit, interfacing with various sensors and modules to enhance personal security."
- [x] genuinely verbatim and correctly attributed

### 35. `doi:10.37965/jait.2023.0179` — other (exact)
- paraphrase: The wearer’s location is continuously updated on Google Maps.
- quote: "The location of the user is also updated using google maps."
- [x] genuinely verbatim and correctly attributed

### 36. `doi:10.37965/jait.2023.0179` — other (exact)
- paraphrase: The band’s sensors continuously transmit pulse, temperature and vibration data to contacts via the Blynk app.
- quote: "As the sensors sense information from the body, it will always update the information such as pulse, temperature, and vibration to the well-wishers through the Blynk app."
- [x] genuinely verbatim and correctly attributed

### 37. `arxiv:2501.13787` — other (exact)
- paraphrase: BitFit fine‑tunes only bias terms, either partially or fully, providing a simpler fine‑tuning approach.
- quote: "BitFit [71] proposed an even simpler fine-tuning approach by only adjusting part of the bias terms of a model or adjusting all the bias terms of the model."
- [x] genuinely verbatim and correctly attributed

### 38. `doi:10.55041/isjem.acme148` — abstract (exact)
- paraphrase: The paper reports that it provides a thorough literature review of IoT devices aimed at women's safety, describing their key characteristics, wearables, sensors, and applied machine‑learning methods.
- quote: "This study offers a comprehensive assessment of the literature showing IOT devices for women's safety, their keycharacteristics, wearable technology, sensors employed, and machine learning techniques applied."
- [x] genuinely verbatim and correctly attributed

### 39. `doi:10.48175/ijarsct-24973` — other (exact)
- paraphrase: The WHO reports that one in three women worldwide are subjected to violence.
- quote: "The findings of WHO (World Health Organization) also showed that every one in three women are subject to violence globally [3]."
- [x] genuinely verbatim and correctly attributed

### 40. `doi:10.18653/v1/2024.findings-acl.352` — other (exact)
- paraphrase: Including random facts in the augmentation further improves locality and lets standard fine‑tuning match MEMIT on COUNTERFACT.
- quote: "Third, augmenting the data with random facts further improves locality (FT + Mask + Para + Rand), allowing standard fine-tuning to match the performance of MEMIT on COUNTERFACT."
- [x] genuinely verbatim and correctly attributed

### 41. `arxiv:2603.18088` — other (fuzzy97)
- paraphrase: Even if less than ten percent of rollouts improve, the dynamic constraint continues to give useful optimization guidance.
- quote: "When fewer than 10% of rollouts are improved, the dynamic constraint still provides effective optimization guidance."
- [x] genuinely verbatim and correctly attributed

### 42. `doi:10.62643/ijerst.2025.v21.i2.pp712-722` — abstract (exact)
- paraphrase: Effective safety systems should feature auto‑activation of alarms with minimal human involvement and higher accuracy.
- quote: "It was determined that in order to successfully address the issue, systems that emphasise auto-activation of alarm creation with less human participation and greater accuracies must be created, even though much research has been produced in the underlying topic."
- [x] genuinely verbatim and correctly attributed

### 43. `doi:10.1109/incip64058.2025.11020103` — abstract (exact)
- paraphrase: The system is claimed to detect potential threats and automatically send alerts to preset emergency contacts and authorities.
- quote: "The system sends alerts when it senses a potential threat and will automatically notify pre-determined emergency contacts and local authorities."
- [x] genuinely verbatim and correctly attributed

### 44. `doi:10.2174/9798898810450125010012` — abstract (exact)
- paraphrase: The device uses an Arduino microcontroller as its core, enabling integration of multiple sensors and communication modules.
- quote: "The Arduino microcontroller platform serves as the system's main building block and allows for the integration of several sensors and communication tools."
- [x] genuinely verbatim and correctly attributed

### 45. `arxiv:2606.04325` — other (exact)
- paraphrase: LR‑LoRA learns a per‑layer nonlinearity that determines each layer’s effective rank without needing an external rank budget, and the authors run controlled experiments separating the effect of learnable rank from merely adding nonlinearity.
- quote: "LR-LoRA differs in how the effective rank arises: the optimizer learns a per-layer continuous elementwise nonlinearity over BA that implicitly sets each layer's effective (stable) rank without an external allocation budget, and we provide controlled experiments isolating learnable rank from the mere presence of nonlinearity (Section 4.3)."
- [x] genuinely verbatim and correctly attributed

### 46. `doi:10.1109/icses66558.2026.11479101` — abstract (exact)
- paraphrase: The system utilizes CNN, LSTM, and SVM models, and aims to implement federated AI, to detect fear, unconsciousness, and potential assaults, incorporating a panic button and voice activation.
- quote: "To make the system more effective use CNN,LSTM,SVM models to detect the signal for fear, unconscious and other possible assault, trying to implement the federated AI model for more accurate prediction and include the panic button and voice activation."
- [x] genuinely verbatim and correctly attributed

### 47. `arxiv:2501.13787` — other (exact)
- paraphrase: Methods such as Diff‑Pruning may increase training time due to their special selection mechanisms, potentially offsetting parameter‑saving benefits.
- quote: "Some methods might lead to longer training periods due to a special selection mechanism (like Diff-Pruning)."
- [x] genuinely verbatim and correctly attributed

### 48. `doi:10.37965/jait.2023.0179` — other (exact)
- paraphrase: The temperature reading is displayed in both Fahrenheit and Celsius units.
- quote: "The temperature gets displayed in two variants which are FAHRENHEIT and CELSIUS."
- [x] genuinely verbatim and correctly attributed

### 49. `arxiv:2501.13787` — other (exact)
- paraphrase: PEFT methods are shown to be notably cost‑effective when fine‑tuning foundation models.
- quote: "Parameter-Efficient Fine-Tuning (PEFT) technology [32, 33, 34, 35], a highly active topic, demonstrates notable costeffectiveness during the fine-tuning process, as depicted in Fig. 1 and Fig. 2 (right)."
- [x] genuinely verbatim and correctly attributed

### 50. `doi:10.1109/asiancon62057.2024.10837901` — abstract (exact)
- paraphrase: The gadget alerts family and authorities to the user's location when a woman, child, or senior is harassed or in distress.
- quote: "When a woman, child, or senior is harassed or in distress, the gadget notifies the family and appropriate authorities of the woman's current position."
- [x] genuinely verbatim and correctly attributed

## Dropped claims (0)

For each **dropped** attempt, check the box if the gate was right to drop it (i.e. it is NOT a real verbatim quote from the paper). An unchecked box here is evidence the gate is too strict, not too loose.

**Nothing to check here yet** — the `dropped_claims` table (migration 0003) only started
populating from runs after it was added; the `iot_safety` runs this sample was drawn from
predate it. The drop rate itself is separately reported via `RunStats.claims_dropped_ungrounded`
(docs/TESTING.md E4 — e.g. 3 of 97 on the `fine_tuning` run). This section will fill in once a
run recorded after migration 0003 is sampled.
