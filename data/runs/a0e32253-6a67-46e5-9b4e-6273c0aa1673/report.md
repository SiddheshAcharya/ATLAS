# Literature review: IoT devices for women safety

_run `a0e32253-6a67-46e5-9b4e-6273c0aa1673`_

## What the field agrees on

The field agrees that IoT-based systems for women's safety commonly incorporate physiological monitoring. These systems monitor parameters such as heartbeat and EEG [doi:10.1109/asiancon62057.2024.10837901], utilizing sensors like pressure and pulse-rate sensors to detect safety concerns and provide real-time vital sign monitoring for distress detection [doi:10.62643/ijerst.2025.v21.i2.pp712-722, doi:10.55041/isjem.acme148]. There is also consensus that current safety measures are often insufficient, particularly in regions like India where violence is increasing, and existing solutions face challenges such as network connectivity [doi:10.1109/icears64219.2025.10941429]. IoT solutions are designed to address these gaps by delivering rapid aid, analyzing data for high-risk area prediction, and providing real-time emergency response with minimal latency through user-centric, sensor-integrated wearable devices [doi:10.1109/incip64058.2025.11020103, doi:10.1109/icoecit68303.2026.11497989].

**Sources:** [doi:10.1109/access.2023.3252903] The Role of IoT in Woman’s Safety: A Systematic Literature Review; [doi:10.1109/asiancon62057.2024.10837901] Development of Women's Safety System Using Iot and Taser Technology; [doi:10.1109/icears64219.2025.10941429] Intelligent Voice and Emotion Recognition for Women's Safety: An IoT-Enabled Wearable Emergency System; [doi:10.1109/icisc65841.2025.11187989] Smart Hi-Tech Emergency Rescuer Using IoT; [doi:10.1109/icoecit68303.2026.11497989] Smart Wearable Device for Enhanced Women Safety: A Multinodal Approach; [doi:10.1109/icpcsn65854.2025.11034876] Implementation of IoT based Women Safety System; [doi:10.1109/icses66558.2026.11479101] SheGUARD: Real-Time Defence Device for Women's Protection Using ML, IoT & Federated AI; [doi:10.1109/incip64058.2025.11020103] IoT Based Smart Safety System for Women's Protection; [doi:10.37965/jait.2023.0179] IOT Based Wrist Band for Women Safety; [doi:10.47392/irjaem.2025.0288] IoT Based Women Safety Devices with Screaming Detection and Photo Capturing; [doi:10.55041/isjem.acme148] Smart IOT-Based Women Safety System:A Robust Real-Time Approach; [doi:10.62643/ijerst.2025.v21.i2.pp712-722] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY

## Where the field disagrees

A contradiction exists regarding the primary microcontroller used in IoT-based women's safety systems. One paper states that its system uses a NodeMCU microcontroller as the main processor [doi:10.1109/icpcsn65854.2025.11034876]. In contrast, another paper describes a system that integrates a Raspberry Pi Pico and ESP32-CAM, alongside other modules, for its core functionality [doi:10.1109/icoecit68303.2026.11497989]. This contradiction has not been resolved within the provided corpus.

**Sources:** [doi:10.1109/icoecit68303.2026.11497989] Smart Wearable Device for Enhanced Women Safety: A Multinodal Approach; [doi:10.1109/icpcsn65854.2025.11034876] Implementation of IoT based Women Safety System

## Methods and datasets over time

The corpus contains no extracted methods or datasets. This is likely due to the nature of the papers, which may be abstract-only, as concept extraction for methods and datasets is typically scoped to real GROBID sections.

## Gaps

### 1. unresolved_conflict — score 0.020

"Implementation of IoT based Women Safety System" (2025) reports 'The system uses a NodeMCU microcontroller as its main processor, connecting to multiple sensors and modules to improve personal security.'; "Smart Wearable Device for Enhanced Women Safety: A Multinodal Approach" (2026) reports 'The system combines GPS, GSM, Raspberry Pi Pico, ESP32-CAM, LCD, buzzer, push button, and a shock circuit to deliver reliable communication, generate evidence, and offer self‑defense features during critical incidents.'. No subsequent paper in this corpus cites both or resolves the disagreement.

- [a_side] Implementation of IoT based Women Safety System (2025) — `doi:10.1109/icpcsn65854.2025.11034876`
- [b_side] Smart Wearable Device for Enhanced Women Safety: A Multinodal Approach (2026) — `doi:10.1109/icoecit68303.2026.11497989`

### 2. unlinked_concepts — score 0.016

"iot device" and "multiple safety measures" are both linked to "sensors" (4 and 2 papers respectively) but no paper in this corpus connects "iot device" to "multiple safety measures" directly.

- [evidence] The Role of IoT in Woman’s Safety: A Systematic Literature Review (2023) — `doi:10.1109/access.2023.3252903`
- [evidence] Implementation of IoT based Women Safety System (2025) — `doi:10.1109/icpcsn65854.2025.11034876`
- [evidence] IoT Based Smart Safety System for Women's Protection (2025) — `doi:10.1109/incip64058.2025.11020103`
- [evidence] IOT Based Wrist Band for Women Safety (2023) — `doi:10.37965/jait.2023.0179`
- [evidence] Smart IOT-Based Women Safety System:A Robust Real-Time Approach (2026) — `doi:10.55041/isjem.acme148`
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025) — `doi:10.62643/ijerst.2025.v21.i2.pp712-722`
- [evidence] SheGUARD: Real-Time Defence Device for Women's Protection Using ML, IoT & Federated AI (2026) — `doi:10.1109/icses66558.2026.11479101`
- [evidence] IoT Based Women Safety Devices with Screaming Detection and Photo Capturing (2025) — `doi:10.47392/irjaem.2025.0288`
- _(+3 more — see the graph)_

### 3. unlinked_concepts — score 0.015

"gps" and "alarm creation" are both linked to "safety" (2 and 2 papers respectively) but no paper in this corpus connects "gps" to "alarm creation" directly.

- [evidence] Development of Women's Safety System Using Iot and Taser Technology (2024) — `doi:10.1109/asiancon62057.2024.10837901`
- [evidence] Smart Wearable Device for Enhanced Women Safety: A Multinodal Approach (2026) — `doi:10.1109/icoecit68303.2026.11497989`
- [evidence] IOT Based Wrist Band for Women Safety (2023) — `doi:10.37965/jait.2023.0179`
- [evidence] IoT Based Women Safety Devices with Screaming Detection and Photo Capturing (2025) — `doi:10.47392/irjaem.2025.0288`

### 4. unlinked_concepts — score 0.014

"possible safety risks" and "accurate detection" are both linked to "device" (3 and 2 papers respectively) but no paper in this corpus connects "possible safety risks" to "accurate detection" directly.

- [evidence] The Role of IoT in Woman’s Safety: A Systematic Literature Review (2023) — `doi:10.1109/access.2023.3252903`
- [evidence] SheGUARD: Real-Time Defence Device for Women's Protection Using ML, IoT & Federated AI (2026) — `doi:10.1109/icses66558.2026.11479101`
- [evidence] IoT Based Women Safety Devices with Screaming Detection and Photo Capturing (2025) — `doi:10.47392/irjaem.2025.0288`
- [evidence] Smart IOT-Based Women Safety System:A Robust Real-Time Approach (2026) — `doi:10.55041/isjem.acme148`
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025) — `doi:10.62643/ijerst.2025.v21.i2.pp712-722`
- [evidence] Intelligent Voice and Emotion Recognition for Women's Safety: An IoT-Enabled Wearable Emergency System (2025) — `doi:10.1109/icears64219.2025.10941429`
- [evidence] Smart Hi-Tech Emergency Rescuer Using IoT (2025) — `doi:10.1109/icisc65841.2025.11187989`
- [evidence] IOT Based Wrist Band for Women Safety (2023) — `doi:10.37965/jait.2023.0179`
- _(+1 more — see the graph)_

### 5. unlinked_concepts — score 0.014

"machine learning" and "incidents" are both linked to "device" (2 and 2 papers respectively) but no paper in this corpus connects "machine learning" to "incidents" directly.

- [evidence] Intelligent Voice and Emotion Recognition for Women's Safety: An IoT-Enabled Wearable Emergency System (2025) — `doi:10.1109/icears64219.2025.10941429`
- [evidence] Smart Hi-Tech Emergency Rescuer Using IoT (2025) — `doi:10.1109/icisc65841.2025.11187989`
- [evidence] IoT Based Women Safety Devices with Screaming Detection and Photo Capturing (2025) — `doi:10.47392/irjaem.2025.0288`
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025) — `doi:10.62643/ijerst.2025.v21.i2.pp712-722`
- [evidence] IoT Based Smart Safety System for Women's Protection (2025) — `doi:10.1109/incip64058.2025.11020103`
- [evidence] IOT Based Wrist Band for Women Safety (2023) — `doi:10.37965/jait.2023.0179`

### 6. unlinked_concepts — score 0.013

"wearable device" and "harassment" are both linked to "sensors" (4 and 2 papers respectively) but no paper in this corpus connects "wearable device" to "harassment" directly.

- [evidence] The Role of IoT in Woman’s Safety: A Systematic Literature Review (2023) — `doi:10.1109/access.2023.3252903`
- [evidence] Smart Hi-Tech Emergency Rescuer Using IoT (2025) — `doi:10.1109/icisc65841.2025.11187989`
- [evidence] Implementation of IoT based Women Safety System (2025) — `doi:10.1109/icpcsn65854.2025.11034876`
- [evidence] IOT Based Wrist Band for Women Safety (2023) — `doi:10.37965/jait.2023.0179`
- [evidence] Smart IOT-Based Women Safety System:A Robust Real-Time Approach (2026) — `doi:10.55041/isjem.acme148`
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025) — `doi:10.62643/ijerst.2025.v21.i2.pp712-722`
- [evidence] IoT Based Smart Safety System for Women's Protection (2025) — `doi:10.1109/incip64058.2025.11020103`

### 7. unlinked_concepts — score 0.010

"potential technology" and "personal security" are both linked to "iot" (2 and 2 papers respectively) but no paper in this corpus connects "potential technology" to "personal security" directly.

- [evidence] The Role of IoT in Woman’s Safety: A Systematic Literature Review (2023) — `doi:10.1109/access.2023.3252903`
- [evidence] Implementation of IoT based Women Safety System (2025) — `doi:10.1109/icpcsn65854.2025.11034876`
- [evidence] IoT Based Smart Safety System for Women's Protection (2025) — `doi:10.1109/incip64058.2025.11020103`
- [evidence] A SYSTEMATIC SURVEY ON IOT-BASED DEVICES FOR ENHANCING WOMEN’S SAFETY (2025) — `doi:10.62643/ijerst.2025.v21.i2.pp712-722`
- [evidence] SheGUARD: Real-Time Defence Device for Women's Protection Using ML, IoT & Federated AI (2026) — `doi:10.1109/icses66558.2026.11479101`
- [evidence] IOT Based Wrist Band for Women Safety (2023) — `doi:10.37965/jait.2023.0179`

## Run stats

- papers discovered / read: 226 / 15
- full-text ratio: 7%
- claims extracted (kept / dropped ungrounded): 73 / 1
- relations judged: 132 (contradictions: 1)
- bridge promotions: 0
- clusters covered: 14
- stop reason: budget: 46 minutes elapsed
- cost: $0.0055, wall clock: 27s
