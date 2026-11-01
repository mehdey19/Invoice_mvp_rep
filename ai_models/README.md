# LangChain vision models

This directory contains model access (`registry.py`), extraction (`extraction.py`), versioned prompts, and a `weights/` directory for local model files. Weights are excluded from git and Docker build context. No model is downloaded automatically.

The installed client integration is LangChain ChatOllama. Configure an already installed, vision-capable model supported by your Ollama runtime:

```dotenv
AI_VISION_MODEL=your-installed-vision-model-tag
AI_VISION_BASE_URL=http://host.docker.internal:11434
```

For host execution, the base URL is typically `http://127.0.0.1:11434`. Compose adds the host gateway alias for the app. Recreate the app after changing environment values. The selected model must support image input and the structured-output method used by the adapter.

Ollama manages its own installed model weights. Files placed in `ai_models/weights/` are a storage location for custom local assets; they are not automatically loaded into Ollama. Import/install them through your runtime, then reference its model tag in AI_VISION_MODEL. See the official [LangChain ChatOllama documentation](https://docs.langchain.com/oss/python/integrations/chat/ollama).

Open Week 2 → Image Extraction, select an acquired PNG/JPEG artifact, and choose Extract image fields. Calls use only an artifact resolved through its registered company/ID/checksum. Prompts instruct the model to return visible fields and leave missing information unknown. Provider, model, prompt version, result and failures are recorded in integration_pipeline.extraction_result.

Extracted data is not written directly to invoice/payment tables. Run normalization to validate dates, decimals, currency, identifiers, parties and totals first. Existing OCR output or manually reviewed extraction JSON can also be stored through the UI/API. A synthetic fixture extraction in tests is explicitly a mocked model response, not a claim of real OCR accuracy.

No vision model was configured or downloaded during implementation. Adapter behavior was tested with a controlled model stub and the real LangChain message interface. Real inference depends on your configured runtime/model. PDF rendering is not implemented; provide an existing/reviewed extraction result for PDF normalization.
