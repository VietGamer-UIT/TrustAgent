# Training Methodology

TrustAgent utilizes reusable training components designed for high-performance ML workloads, particularly Supervised Fine-Tuning (SFT) and PEFT.

## Dataset Abstraction
- Datasets are abstracted to feed efficiently into trainer modules.
- We support positive/negative sampling schemas, combining exact matches with mined hard negatives to improve model discernment.

## Resource Management
- **LoRA/PEFT:** We employ Low-Rank Adaptation to train multi-billion parameter models on limited consumer hardware without full parameter updates.
- **Batching & Accumulation:** Features gradient accumulation and micro-batching to simulate large batch sizes on small VRAM constraints.
- **FP16 / Mixed Precision:** Uses Half-Precision (FP16) or Bfloat16 where supported to accelerate tensor operations and reduce memory footprint.
- **Gradient Checkpointing:** Re-computes activations during the backward pass to drastically reduce VRAM usage at the cost of training speed.

## CPU/GPU Orchestration
- Data loaders and tokenization pipelines are mapped intelligently to CPU to prevent GPU bottlenecks, streaming tensors asynchronously where possible.
