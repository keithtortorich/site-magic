# Open-source replacement matrix

The VRE demo does not need a paid provider stack. These are the approved
private-demo substitutions, with the important boundary that an open-source
tool is not automatically an equivalent evidence source.

| Paid or hosted dependency | Private-demo replacement | Status and boundary |
| --- | --- | --- |
| OpenAI/OpenRouter text generation | [Ollama](https://github.com/ollama/ollama), [llama.cpp](https://github.com/ggml-org/llama.cpp), or [vLLM](https://github.com/vllm-project/vllm) through the existing OpenAI-compatible adapter | Supported. The adapter already accepts a loopback endpoint. Model quality and model licenses remain separate checks. |
| Hosted image generation | The repository's deterministic `SyntheticImageGenerator`; optionally [ComfyUI](https://github.com/Comfy-Org/ComfyUI) for a later local image-model experiment | Supported now without an image API. Synthetic assets are visibly illustrative and never customer proof. ComfyUI is not silently treated as an OpenAI Images API. |
| DataForSEO search discovery | [SearXNG](https://github.com/searxng/searxng) | Discovery-only. SearXNG results do not satisfy the fixed geo-qualified ranking contract, so they cannot enter `corpus.json` or replace the authoritative provider for this study. |
| Hosted browser and accessibility checks | [Playwright](https://github.com/microsoft/playwright), [axe-core](https://github.com/dequelabs/axe-core), and local Lighthouse already in the repository | Supported locally. These remain deterministic quality gates. |
| Hosted object storage | `LocalArtifactStore` under `artifacts/runtime/<tenant>/<job>/<build>.tar` | Supported locally. Archives are tenant-scoped and immutable; no public URL is created. |
| Hosted database/auth/publishing | Existing local control-plane test app, synthetic API key, and null publisher | Supported for the demo only. Production migrations, credentials, release, and customer traffic remain deferred. |

## Rules

SearXNG may help discover candidate domains, but the raw candidate artifact is
unclassified. `scripts/select_corpus.py` requires an explicit manifest before
anything can be labeled training, holdout, franchise control, or excluded.
The authoritative corpus validator remains the final gate.

The local model path is opt-in:

```text
SITE_MAGIC_USE_AI_COMPATIBLE=true
SITE_MAGIC_USE_SYNTHETIC_ASSETS=true
SITE_MAGIC_USE_LOCAL_ARTIFACTS=true
```

No production endpoint, hosted credential, customer account, or public release
is configured by this matrix.
