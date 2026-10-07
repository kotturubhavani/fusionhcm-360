"""Hosted provider contracts use synthetic credentials and mocked HTTP only."""
import json
import math
import pytest
import httpx
from pydantic import SecretStr
from app.core.config import settings
from app.services.ai import providers, vectors


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-provider-test')
    monkeypatch.setattr(settings, 'ai_provider', 'gemini')
    monkeypatch.setattr(settings, 'ai_embedding_dimensions', 768)
    calls = []
    replies = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs == dict(timeout=settings.ai_timeout_seconds, follow_redirects=False, trust_env=False)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            assert url.startswith('https://generativelanguage.googleapis.com/v1beta/models/gemini-')
            assert '?' not in url
            assert kwargs['headers'] == {'x-goog-api-key': 'synthetic-provider-test'}
            assert 'synthetic-provider-test' not in json.dumps(kwargs['json'])
            calls.append((url, kwargs['json']))
            reply = replies.pop(0)
            if isinstance(reply, Exception): raise reply
            status, content = reply
            return httpx.Response(status, json=content, request=httpx.Request('POST', url))

    monkeypatch.setattr(providers.httpx, 'Client', Client)
    return calls, replies


def response(text, finish='STOP'):
    return {'candidates': [{'finishReason': finish, 'content': {'parts': [{'text': text}]}}]}


def test_generation_and_embedding_contract(transport):
    calls, replies = transport
    p = providers.provider()
    assert isinstance(p, providers.GeminiProvider)
    replies.extend([(200, {'embeddings': [{'values': [0.1]*768}]}),
                    (200, response('{"selected_ids":["known"]}'))])
    vector = p.embed(['policy'])[0]
    assert len(vector) == 768 and math.isclose(sum(x*x for x in vector), 1)
    assert p.select('question', [{'id': 'known', 'text': 'Synthetic policy'}], {'net': '61108.33'}).selected_ids == ['known']
    embedding = calls[0][1]['requests'][0]
    assert embedding['taskType'] == 'RETRIEVAL_DOCUMENT' and embedding['outputDimensionality'] == 768
    generation = calls[1][1]
    assert generation['generationConfig']['temperature'] == settings.ai_temperature
    assert generation['generationConfig']['maxOutputTokens'] == settings.ai_max_tokens
    assert generation['generationConfig']['responseMimeType'] == 'application/json'
    assert 'tools' not in generation and '61108.33' in generation['contents'][0]['parts'][0]['text']
    replies.append((200, {'embeddings': [{'values': [0.1]*768}]}))
    p.embed(['query'], query=True)
    assert calls[-1][1]['requests'][0]['taskType'] == 'RETRIEVAL_QUERY'


@pytest.mark.parametrize('reply', [
    (429, {'error': {'message': 'private key or quota details'}}),
    (403, {'error': {'message': 'private details'}}),
    (500, {'error': {'message': 'private details'}}),
    httpx.ReadTimeout('private details'),
    (200, response('partial', 'MAX_TOKENS')),
    (200, {'promptFeedback': {'blockReason': 'SAFETY'}}),
    (200, {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'functionCall': {'name': 'unsafe'}}]}}]}),
])
def test_errors_are_safe_and_never_fall_back(transport, reply):
    transport[1].append(reply)
    with pytest.raises(providers.ProviderError) as caught:
        providers.provider().generate('Tiny verification prompt')
    assert 'private' not in str(caught.value) and 'synthetic-provider-test' not in str(caught.value)


@pytest.mark.parametrize('output', ['{"selected_ids":["invented"]}', '{"selected_ids":["ok","ok"]}',
                                    '{"selected_ids":[],"answer":"invented salary"}', 'not JSON'])
def test_selection_rejects_untrusted_output(transport, output):
    transport[1].append((200, response(output)))
    with pytest.raises(providers.ProviderError):
        providers.provider().select('q', [{'id': 'ok', 'text': 'Synthetic'}], {})


@pytest.mark.parametrize('values', [[0.1]*256, [0.0]*768, [True]*768, ['bad']*768])
def test_invalid_embedding_vectors(transport, values):
    transport[1].append((200, {'embeddings': [{'values': values}]}))
    with pytest.raises(providers.ProviderError): providers.provider().embed(['policy'])


def test_input_bounds_and_secret_settings(transport, monkeypatch):
    p = providers.provider()
    with pytest.raises(providers.ProviderError): p.generate('x'*40001)
    with pytest.raises(providers.ProviderError): p.embed(['x']*101)
    with pytest.raises(providers.ProviderError): p.request('https://example.com', 'generateContent', {})
    monkeypatch.delenv('GEMINI_API_KEY')
    monkeypatch.setattr(settings, 'gemini_api_key', None)
    with pytest.raises(providers.ProviderError, match='unavailable'): p.generate('q')
    assert not transport[0]
    monkeypatch.setattr(settings, 'gemini_api_key', SecretStr('synthetic-provider-test'))
    assert 'synthetic-provider-test' not in repr(settings)
    assert 'gemini_api_key' not in settings.model_dump()
    transport[1].append((200, response('FUSIONHCM_GEMINI_OK')))
    assert p.generate('Reply with exactly: FUSIONHCM_GEMINI_OK') == 'FUSIONHCM_GEMINI_OK'


def test_vector_spaces_and_dimensions(monkeypatch):
    p = providers.GeminiProvider()
    before = p.signature
    monkeypatch.setattr(settings, 'ai_embedding_dimensions', 1536)
    assert p.signature != before and p.signature != providers.MockProvider.signature
    calls = []
    def fake(method, path, body=None, **kwargs):
        calls.append((method, path, body))
        return None
    monkeypatch.setattr(vectors, 'request', fake)
    from types import SimpleNamespace
    vectors.upsert(before, [SimpleNamespace(id='id')], [[0.1]*768])
    assert calls[1][2]['vectors']['size'] == 768
    monkeypatch.setattr(vectors, 'request', lambda *a, **k: {'result': {'config': {'params': {'vectors': {'size': 256}}}}})
    with pytest.raises(providers.ProviderError, match='dimensions'):
        vectors.upsert(before, [SimpleNamespace(id='id')], [[0.1]*768])
