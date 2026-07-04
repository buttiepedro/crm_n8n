"""Esquema inicial (DDL congelado desde app/db/models — 2026-07-03).

Revision ID: 0001_init
Revises:
Create Date: 2026-07-03

Generado con scripts one-off desde los modelos SQLAlchemy y verificado con
`alembic upgrade head --sql`. Los cambios de esquema posteriores van en
migraciones autogeneradas (`alembic revision --autogenerate`).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE_DDL = [
    """CREATE TYPE user_role AS ENUM ('admin', 'supervisor', 'agent')""",
    """CREATE TYPE wa_account_status AS ENUM ('active', 'paused', 'error')""",
    """CREATE TYPE conversation_status AS ENUM ('open', 'pending', 'closed')""",
    """CREATE TYPE lead_source AS ENUM ('manual', 'n8n_webhook')""",
    """CREATE TYPE message_direction AS ENUM ('inbound', 'outbound')""",
    """CREATE TYPE message_origin AS ENUM ('whatsapp', 'crm_user', 'n8n')""",
    """CREATE TYPE message_type AS ENUM ('text', 'image', 'audio', 'video', 'document', 'sticker', 'location', 'contacts', 'template', 'interactive', 'reaction', 'unknown')""",
    """CREATE TYPE message_status AS ENUM ('queued', 'sent', 'delivered', 'read', 'failed', 'received')""",
    """CREATE TYPE attachment_download_status AS ENUM ('pending', 'done', 'failed')""",
    """CREATE TYPE note_author_source AS ENUM ('user', 'n8n_webhook')""",
    """CREATE TABLE contacts (
	wa_id TEXT NOT NULL, 
	profile_name TEXT, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (wa_id)
)""",
    """CREATE TABLE event_logs (
	actor_type TEXT NOT NULL, 
	actor_id UUID, 
	action TEXT NOT NULL, 
	entity_type TEXT, 
	entity_id UUID, 
	metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
	trace_id TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
)""",
    """CREATE INDEX idx_event_logs_created ON event_logs (created_at)""",
    """CREATE INDEX idx_event_logs_entity ON event_logs (entity_type, entity_id, created_at)""",
    """CREATE TABLE pipelines (
	name TEXT NOT NULL, 
	is_default BOOLEAN NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
)""",
    """CREATE TABLE users (
	email TEXT NOT NULL, 
	name TEXT NOT NULL, 
	password_hash TEXT NOT NULL, 
	role user_role NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	last_login_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email)
)""",
    """CREATE TABLE whatsapp_accounts (
	name TEXT NOT NULL, 
	waba_id TEXT NOT NULL, 
	phone_number_id TEXT NOT NULL, 
	display_phone_number TEXT NOT NULL, 
	access_token_ciphertext BYTEA NOT NULL, 
	token_key_version SMALLINT NOT NULL, 
	status wa_account_status NOT NULL, 
	n8n_inbound_webhook_url TEXT, 
	n8n_webhook_secret_ciphertext BYTEA, 
	settings JSONB DEFAULT '{}'::jsonb NOT NULL, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (phone_number_id)
)""",
    """CREATE TABLE api_keys (
	name TEXT NOT NULL, 
	key_hash TEXT NOT NULL, 
	key_prefix TEXT NOT NULL, 
	scopes TEXT[] NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	last_used_at TIMESTAMP WITH TIME ZONE, 
	created_by UUID, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (key_hash), 
	FOREIGN KEY(created_by) REFERENCES users (id)
)""",
    """CREATE TABLE conversations (
	whatsapp_account_id UUID NOT NULL, 
	contact_id UUID NOT NULL, 
	status conversation_status NOT NULL, 
	assigned_user_id UUID, 
	last_message_at TIMESTAMP WITH TIME ZONE, 
	last_inbound_at TIMESTAMP WITH TIME ZONE, 
	unread_count INTEGER NOT NULL, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_conversation_account_contact UNIQUE (whatsapp_account_id, contact_id), 
	FOREIGN KEY(whatsapp_account_id) REFERENCES whatsapp_accounts (id), 
	FOREIGN KEY(contact_id) REFERENCES contacts (id), 
	FOREIGN KEY(assigned_user_id) REFERENCES users (id)
)""",
    """CREATE INDEX idx_conversations_assigned ON conversations (assigned_user_id) WHERE status <> 'closed'""",
    """CREATE INDEX idx_conversations_inbox ON conversations (whatsapp_account_id, status, last_message_at)""",
    """CREATE TABLE pipeline_stages (
	pipeline_id UUID NOT NULL, 
	name TEXT NOT NULL, 
	position INTEGER NOT NULL, 
	color TEXT, 
	is_terminal BOOLEAN NOT NULL, 
	outcome TEXT, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_stage_position UNIQUE (pipeline_id, position) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT ck_stage_outcome CHECK (outcome IN ('won', 'lost')), 
	FOREIGN KEY(pipeline_id) REFERENCES pipelines (id) ON DELETE CASCADE
)""",
    """CREATE TABLE sessions (
	user_id UUID NOT NULL, 
	token_hash TEXT NOT NULL, 
	config_panel_until TIMESTAMP WITH TIME ZONE, 
	ip INET, 
	user_agent TEXT, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	UNIQUE (token_hash)
)""",
    """CREATE TABLE settings (
	key TEXT NOT NULL, 
	value JSONB NOT NULL, 
	updated_by UUID, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (key), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
)""",
    """CREATE TABLE user_permissions (
	user_id UUID NOT NULL, 
	permission TEXT NOT NULL, 
	PRIMARY KEY (user_id, permission), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)""",
    """CREATE TABLE webhook_deliveries (
	whatsapp_account_id UUID NOT NULL, 
	target_url TEXT NOT NULL, 
	event_type TEXT NOT NULL, 
	payload JSONB NOT NULL, 
	attempt INTEGER NOT NULL, 
	response_status INTEGER, 
	response_body TEXT, 
	succeeded BOOLEAN NOT NULL, 
	next_retry_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(whatsapp_account_id) REFERENCES whatsapp_accounts (id)
)""",
    """CREATE INDEX idx_webhook_deliveries_pending ON webhook_deliveries (next_retry_at) WHERE succeeded = false""",
    """CREATE TABLE leads (
	contact_id UUID NOT NULL, 
	conversation_id UUID, 
	pipeline_id UUID NOT NULL, 
	stage_id UUID NOT NULL, 
	external_key TEXT, 
	title TEXT NOT NULL, 
	value NUMERIC(14, 2), 
	currency CHAR(3), 
	source lead_source NOT NULL, 
	owner_user_id UUID, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(contact_id) REFERENCES contacts (id), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id), 
	FOREIGN KEY(pipeline_id) REFERENCES pipelines (id), 
	FOREIGN KEY(stage_id) REFERENCES pipeline_stages (id), 
	UNIQUE (external_key), 
	FOREIGN KEY(owner_user_id) REFERENCES users (id)
)""",
    """CREATE INDEX idx_leads_stage ON leads (pipeline_id, stage_id) WHERE deleted_at IS NULL""",
    """CREATE TABLE messages (
	conversation_id UUID NOT NULL, 
	whatsapp_account_id UUID NOT NULL, 
	wamid TEXT, 
	direction message_direction NOT NULL, 
	origin message_origin NOT NULL, 
	sent_by_user_id UUID, 
	type message_type NOT NULL, 
	body TEXT, 
	status message_status NOT NULL, 
	error_detail JSONB, 
	raw_payload JSONB, 
	reply_to_message_id UUID, 
	wa_timestamp TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id), 
	FOREIGN KEY(whatsapp_account_id) REFERENCES whatsapp_accounts (id), 
	UNIQUE (wamid), 
	FOREIGN KEY(sent_by_user_id) REFERENCES users (id), 
	FOREIGN KEY(reply_to_message_id) REFERENCES messages (id)
)""",
    """CREATE INDEX idx_messages_account_created ON messages (whatsapp_account_id, created_at)""",
    """CREATE INDEX idx_messages_conversation ON messages (conversation_id, created_at)""",
    """CREATE TABLE attachments (
	message_id UUID NOT NULL, 
	media_id TEXT, 
	gcs_path TEXT, 
	mime_type TEXT NOT NULL, 
	file_name TEXT, 
	size_bytes BIGINT, 
	sha256 TEXT, 
	download_status attachment_download_status NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(message_id) REFERENCES messages (id) ON DELETE CASCADE
)""",
    """CREATE TABLE lead_stage_events (
	lead_id UUID NOT NULL, 
	from_stage_id UUID, 
	to_stage_id UUID NOT NULL, 
	moved_by TEXT NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE, 
	FOREIGN KEY(from_stage_id) REFERENCES pipeline_stages (id), 
	FOREIGN KEY(to_stage_id) REFERENCES pipeline_stages (id)
)""",
    """CREATE TABLE message_status_events (
	message_id UUID NOT NULL, 
	status message_status NOT NULL, 
	raw_payload JSONB, 
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(message_id) REFERENCES messages (id) ON DELETE CASCADE
)""",
    """CREATE TABLE notes (
	lead_id UUID, 
	conversation_id UUID, 
	external_key TEXT, 
	body TEXT NOT NULL, 
	author_user_id UUID, 
	author_source note_author_source NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_note_lead_external_key UNIQUE (lead_id, external_key), 
	CONSTRAINT ck_note_lead_or_conversation CHECK (lead_id IS NOT NULL OR conversation_id IS NOT NULL), 
	FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE, 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id), 
	FOREIGN KEY(author_user_id) REFERENCES users (id)
)""",
    """CREATE INDEX idx_notes_lead ON notes (lead_id) WHERE deleted_at IS NULL""",
]

DOWNGRADE_DDL = [
    """DROP TABLE IF EXISTS notes CASCADE""",
    """DROP TABLE IF EXISTS message_status_events CASCADE""",
    """DROP TABLE IF EXISTS lead_stage_events CASCADE""",
    """DROP TABLE IF EXISTS attachments CASCADE""",
    """DROP TABLE IF EXISTS messages CASCADE""",
    """DROP TABLE IF EXISTS leads CASCADE""",
    """DROP TABLE IF EXISTS webhook_deliveries CASCADE""",
    """DROP TABLE IF EXISTS user_permissions CASCADE""",
    """DROP TABLE IF EXISTS settings CASCADE""",
    """DROP TABLE IF EXISTS sessions CASCADE""",
    """DROP TABLE IF EXISTS pipeline_stages CASCADE""",
    """DROP TABLE IF EXISTS conversations CASCADE""",
    """DROP TABLE IF EXISTS api_keys CASCADE""",
    """DROP TABLE IF EXISTS whatsapp_accounts CASCADE""",
    """DROP TABLE IF EXISTS users CASCADE""",
    """DROP TABLE IF EXISTS pipelines CASCADE""",
    """DROP TABLE IF EXISTS event_logs CASCADE""",
    """DROP TABLE IF EXISTS contacts CASCADE""",
    """DROP TYPE IF EXISTS user_role""",
    """DROP TYPE IF EXISTS wa_account_status""",
    """DROP TYPE IF EXISTS conversation_status""",
    """DROP TYPE IF EXISTS lead_source""",
    """DROP TYPE IF EXISTS message_direction""",
    """DROP TYPE IF EXISTS message_origin""",
    """DROP TYPE IF EXISTS message_type""",
    """DROP TYPE IF EXISTS message_status""",
    """DROP TYPE IF EXISTS attachment_download_status""",
    """DROP TYPE IF EXISTS note_author_source""",
]


def upgrade() -> None:
    for statement in UPGRADE_DDL:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_DDL:
        op.execute(statement)
