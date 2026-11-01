"""Explicit server-side model configuration; credentials never enter source metadata."""
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PROMPT_VERSION='invoice-v1'


def configuration():
    model=os.environ.get('AI_VISION_MODEL','').strip()
    return {'provider':'ollama','model':model,'base_url':os.environ.get('AI_VISION_BASE_URL','http://host.docker.internal:11434'),
            'enabled':bool(model),'prompt_version':PROMPT_VERSION,'weights_directory':str(ROOT/'weights')}


def get_vision_model():
    config=configuration()
    if not config['enabled']: raise ValueError('Set AI_VISION_MODEL to an installed vision-capable Ollama model before extraction')
    try: from langchain_ollama import ChatOllama
    except ImportError as exc: raise ValueError('Install requirements-ai.txt to enable the LangChain vision integration') from exc
    return ChatOllama(model=config['model'],base_url=config['base_url'],temperature=0,client_kwargs={'timeout':120})
