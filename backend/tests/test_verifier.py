"""OllamaVerifier: disponibilità, richiesta, classificazione degli errori. Nessuna rete reale."""
import base64
import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest
from PIL import Image

from backend.services import verifier as module
from backend.services.verifier import ModelUnavailable, OllamaVerifier, TransientModelError, VerificationItem


GOOD = {"esito_suggerito": "pubblica", "violazioni": [], "confidenza": 0.9, "note_moderatore": "ok"}


class Fake:
    def __init__(self):
        self.requests, self.tags, self.chat, self.error = [], {"models": [{"name": "qwen2.5vl:7b"}]}, GOOD, None

    def __call__(self, request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        if url.endswith("/api/tags"):
            return BytesIO(json.dumps(self.tags).encode())
        content = self.chat if isinstance(self.chat, str) else json.dumps(self.chat)
        return BytesIO(json.dumps({"message": {"content": content}}).encode())


@pytest.fixture()
def fake(monkeypatch):
    stub = Fake()
    monkeypatch.setattr(module, "urlopen", stub)
    return stub


def item(**changes):
    image = BytesIO()
    Image.new("RGB", (2400, 1600), "gray").save(image, format="JPEG")
    data = dict(id=1, tipo="segnalazione", titolo="Buca", descrizione="Buca profonda in via Roma",
                indirizzo="Via Roma", categorie_catalogo=[{"id": 2, "nome": "Mobilità urbana"}],
                immagini=[image.getvalue()], video_allegati=1)
    data.update(changes)
    return VerificationItem(**data)


def verifier():
    return OllamaVerifier("http://localhost:11434", "qwen2.5vl:7b", timeout=99)


def test_availability_requires_the_model_to_be_pulled(fake):
    assert verifier().available() is True
    fake.tags = {"models": [{"name": "llama3:8b"}]}
    assert verifier().available() is False
    fake.tags = {"models": [{"name": "qwen2.5vl:latest"}]}
    assert OllamaVerifier("http://localhost:11434", "qwen2.5vl").available() is True
    fake.error = URLError(ConnectionRefusedError())
    assert verifier().available() is False


def test_request_is_multimodal_structured_and_deterministic(fake):
    result = verifier().verify(item())
    assert result.esito_suggerito == "pubblica"
    request, timeout = fake.requests[-1]
    payload = json.loads(request.data)
    assert request.full_url == "http://localhost:11434/api/chat" and timeout == 99
    assert payload["model"] == "qwen2.5vl:7b" and payload["stream"] is False and payload["options"]["temperature"] == 0
    assert set(payload["format"]["required"]) == {"esito_suggerito", "violazioni", "confidenza", "note_moderatore"}
    system, user = payload["messages"][0]["content"], payload["messages"][1]
    for criterion in ("Coerenza", "Scopo", "Linguaggio", "Plausibilità", "asterischi", "generazione artificiale"):
        assert criterion in system
    assert "<testo_utente>" in user["content"] and "id 2: Mobilità urbana" in user["content"]
    assert "Video allegati non analizzabili: 1" in user["content"]
    sent = Image.open(BytesIO(base64.b64decode(user["images"][0])))
    assert sent.format == "JPEG" and max(sent.size) == 1024


def test_unreadable_images_are_skipped(fake):
    verifier().verify(item(immagini=[b"rotto"]))
    assert "images" not in json.loads(fake.requests[-1][0].data)["messages"][1]


@pytest.mark.parametrize("error,expected", [
    (URLError(ConnectionRefusedError()), ModelUnavailable),
    (ConnectionResetError(), ModelUnavailable),
    (HTTPError("http://x", 404, "model not found", {}, None), ModelUnavailable),
    (HTTPError("http://x", 500, "errore", {}, None), TransientModelError),
    (TimeoutError(), TransientModelError),
    (URLError(TimeoutError()), TransientModelError),
])
def test_errors_are_classified(fake, error, expected):
    fake.error = error
    with pytest.raises(expected):
        verifier().verify(item())


@pytest.mark.parametrize("content", ["non json", {"esito_suggerito": "forse"}, {**GOOD, "confidenza": 3}])
def test_non_conforming_answers_are_transient_errors(fake, content):
    fake.chat = content
    with pytest.raises(TransientModelError):
        verifier().verify(item())


def test_invalid_base_url_is_refused():
    with pytest.raises(ValueError):
        OllamaVerifier("file:///etc", "qwen2.5vl:7b")


def test_get_verifier_uses_configuration_and_can_be_replaced(app):
    from backend.services.verifier import get_verifier
    with app.app_context():
        configured = get_verifier()
        assert configured.model == app.config["VERIFICA_MODELLO"] and configured.timeout == app.config["VERIFICA_TIMEOUT"]
        app.extensions["verifier"] = "finto"
        assert get_verifier() == "finto"
