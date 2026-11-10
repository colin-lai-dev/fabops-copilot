-- Agent proposals and audit log (ADR-0006). Created on demand with IF NOT EXISTS, so
-- `make seed` (which drops and reloads the MES tables) never wipes the audit history.

CREATE TABLE IF NOT EXISTS agent_proposals (
    proposal_id     text PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    thread_id       text NOT NULL,
    requester       text NOT NULL,
    action          text NOT NULL CHECK (action IN ('hold_lot', 'inhibit_chamber', 'request_pm')),
    target_id       text NOT NULL,
    reason          text NOT NULL,
    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'executed')),
    approver        text,
    note            text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    decided_at      timestamptz,
    executed_at     timestamptz
);

CREATE TABLE IF NOT EXISTS agent_audit_log (
    audit_id    bigserial PRIMARY KEY,
    ts          timestamptz NOT NULL DEFAULT now(),
    proposal_id text NOT NULL REFERENCES agent_proposals,
    event       text NOT NULL CHECK (event IN ('proposed', 'approved', 'rejected', 'executed')),
    actor       text NOT NULL,
    detail      jsonb NOT NULL DEFAULT '{}'
);
