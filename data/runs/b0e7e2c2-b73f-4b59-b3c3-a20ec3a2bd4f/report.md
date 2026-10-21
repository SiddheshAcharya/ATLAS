# Literature review: federated learning for medical imaging

_run `b0e7e2c2-b73f-4b59-b3c3-a20ec3a2bd4f`_

## What the field agrees on

The field generally agrees that AI shows significant potential for applications in medical imaging [doi:10.48550/arxiv.2508.20414]. Federated learning (FL) is considered valuable for medical imaging, primarily because it addresses privacy concerns associated with medical data [doi:10.1016/j.jacr.2022.03.016]. Imaging data is well-suited for FL, as it enables hospitals and devices to jointly train AI/ML models on diverse ultrasound data without exchanging raw scans [doi:10.1007/s11831-026-10629-0]. While many prior works have used simple neural networks like MLPs or shallow CNNs, which may be insufficient for the complexity of medical image classification, researchers are actively performing comprehensive evaluations of state-of-the-art FL algorithms and introducing new optimization approaches to improve performance and applicability in medical imaging [arxiv:2504.05238]. Despite these advancements, identified challenges include performance bottlenecks, heterogeneity risks, and a lack of clinical deployment benchmarks in FL for medical imaging [doi:10.1007/s10462-025-11489-z].

**Sources:** [arxiv:2504.05238] Federated Learning for Medical Image Classification: A Comprehensive Benchmark; [doi:10.1007/s10462-025-11489-z] Advancements and challenges of federated learning in medical imaging: a systematic literature review; [doi:10.1007/s11831-026-10629-0] Federated Learning in Multimodal Healthcare Diagnostics: Privacy-Preserving AI for Biomedical Imaging, Electronic Health Records, Wearables, and Clinical Decision Support; [doi:10.1016/j.jacr.2022.03.016] Federated Learning in Medical Imaging: Part II: Methods, Challenges, and Considerations; [doi:10.48550/arxiv.2508.20414] Federated Learning for Large Models in Medical Imaging: A Comprehensive Review

## Where the field disagrees

There are no contradictions found in the provided material.

## Methods and datasets over time

In 2025, the papers [arxiv:2504.05238] and [doi:10.1109/jbhi.2025.3631706] commonly utilized several methods and datasets. Both papers employed "global aggregation" and "federated learning" as key methodologies, alongside the use of a "global classification model" and scenarios involving a "limited local training dataset". Regarding datasets, both works focused on "federated learning" environments, specifically incorporating "unique image datasets", "heterogeneous datasets", and "client local dataset" configurations.

**Sources:** [arxiv:2504.05238] Federated Learning for Medical Image Classification: A Comprehensive Benchmark; [doi:10.1109/jbhi.2025.3631706] Federated Learning for Medical Image Classification: A Comprehensive Benchmark

## Gaps

(no gaps survived the citation-rule filter for this run.)
## Run stats

- papers discovered / read: 728 / 13
- full-text ratio: 23%
- claims extracted (kept / dropped ungrounded): 195 / 3
- relations judged: 28 (contradictions: 0)
- bridge promotions: 0
- clusters covered: 13
- stop reason: saturation: EMA 2.61 < 0.15·45.05 for 3 papers
- cost: $0.0046, wall clock: 40s
