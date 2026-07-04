"""Regresión: to_camel de Pydantic rompe los campos que empiezan con 'n8n'
(genera 'n8N…'); los aliases explícitos deben aceptar el camelCase real que
manda el frontend."""

from app.modules.config.router import AccountIn, AccountPatch, PlatformIn


def test_platform_accepts_camelcase_n8n_fields():
    body = PlatformIn.model_validate({
        "n8nWebhookUrl": "https://n8n.example.com/webhook/in",
        "n8nWebhookSecret": "secreto",
    })
    assert body.n8n_webhook_url == "https://n8n.example.com/webhook/in"
    assert body.n8n_webhook_secret == "secreto"


def test_account_in_accepts_camelcase_n8n_fields():
    body = AccountIn.model_validate({
        "name": "Ventas",
        "wabaId": "W1",
        "phoneNumberId": "123",
        "displayPhoneNumber": "+54911",
        "accessToken": "token-largo-x",
        "n8nInboundWebhookUrl": "https://n8n.example.com/webhook/in",
    })
    assert body.n8n_inbound_webhook_url is not None


def test_account_patch_accepts_camelcase_n8n_fields():
    body = AccountPatch.model_validate({"n8nWebhookSecret": "s1", "clearWebhookUrl": True})
    assert body.n8n_webhook_secret == "s1"
    assert body.clear_webhook_url is True


def test_snake_case_also_accepted():
    # populate_by_name permite snake_case (útil para scripts)
    body = PlatformIn.model_validate({"n8n_webhook_url": "https://x"})
    assert body.n8n_webhook_url == "https://x"
