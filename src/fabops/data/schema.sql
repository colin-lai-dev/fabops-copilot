-- FabOps Copilot schema. All data is synthetic (fictional fab "Fab-X").
-- Permission attributes (ADR-0002): fab, department, clearance.
-- clearance: 0 public < 1 internal < 2 confidential < 3 restricted.
-- department 'shared' is visible to every department.

CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS chunks, documents, maintenance, alarms, dispatch_log, lots,
    chambers, equipment, users CASCADE;

CREATE TABLE users (
    user_id       text PRIMARY KEY,
    display_name  text NOT NULL,
    fabs          text[] NOT NULL,
    departments   text[] NOT NULL,
    clearance     smallint NOT NULL CHECK (clearance BETWEEN 0 AND 3)
);

-- Named "equipment" (not "tools") to avoid confusion with agent tools.
CREATE TABLE equipment (
    equipment_id  text PRIMARY KEY,
    fab           text NOT NULL,
    department    text NOT NULL,
    equipment_type text NOT NULL,
    vendor_model  text NOT NULL,
    status        text NOT NULL CHECK (status IN ('up', 'down', 'pm', 'idle'))
);

CREATE TABLE chambers (
    chamber_id    text PRIMARY KEY,
    equipment_id  text NOT NULL REFERENCES equipment,
    status        text NOT NULL CHECK (status IN ('up', 'down', 'pm', 'idle'))
);

CREATE TABLE lots (
    lot_id        text PRIMARY KEY,
    fab           text NOT NULL,
    product       text NOT NULL,
    route_step    text NOT NULL,
    priority      smallint NOT NULL,
    status        text NOT NULL CHECK (status IN ('wait', 'run', 'hold', 'done'))
);

CREATE TABLE dispatch_log (
    dispatch_id   bigint PRIMARY KEY,
    fab           text NOT NULL,
    lot_id        text NOT NULL REFERENCES lots,
    equipment_id  text NOT NULL REFERENCES equipment,
    chamber_id    text NOT NULL REFERENCES chambers,
    dispatched_at timestamptz NOT NULL,
    result        text NOT NULL CHECK (result IN ('ok', 'rejected', 'aborted'))
);

CREATE TABLE alarms (
    alarm_id      bigint PRIMARY KEY,
    fab           text NOT NULL,
    equipment_id  text NOT NULL REFERENCES equipment,
    chamber_id    text REFERENCES chambers,
    alarm_code    text NOT NULL,
    severity      text NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    message       text NOT NULL,
    occurred_at   timestamptz NOT NULL,
    lot_id        text REFERENCES lots
);

CREATE TABLE maintenance (
    maintenance_id bigint PRIMARY KEY,
    fab           text NOT NULL,
    equipment_id  text NOT NULL REFERENCES equipment,
    chamber_id    text REFERENCES chambers,
    pm_type       text NOT NULL,
    start_at      timestamptz NOT NULL,
    end_at        timestamptz NOT NULL
);

CREATE TABLE documents (
    doc_id        text PRIMARY KEY,
    doc_type      text NOT NULL CHECK (doc_type IN ('sop', 'incident')),
    title         text NOT NULL,
    fab           text NOT NULL,
    department    text NOT NULL,
    clearance     smallint NOT NULL CHECK (clearance BETWEEN 0 AND 3),
    sop_key       text,             -- groups versions of the same SOP
    version       int NOT NULL DEFAULT 1,
    effective_date date NOT NULL,
    superseded_by text REFERENCES documents,
    source        text NOT NULL CHECK (source IN ('template', 'polished')),
    body_md       text NOT NULL
);

CREATE TABLE chunks (
    chunk_id      text PRIMARY KEY,
    doc_id        text NOT NULL REFERENCES documents ON DELETE CASCADE,
    seq           int NOT NULL,
    section       text,
    text          text NOT NULL,
    -- Denormalized permission attributes for filtering (ADR-0003: filter, then exact search).
    fab           text NOT NULL,
    department    text NOT NULL,
    clearance     smallint NOT NULL,
    embedding     vector(1024),      -- bge-m3 dense (fabops.rag.index)
    sparse        jsonb,             -- bge-m3 lexical weights {token_id: weight}
    tokens        text[]             -- jieba tokens for BM25
);

CREATE INDEX ON chunks (fab, department, clearance);
CREATE INDEX ON alarms (equipment_id, occurred_at);
CREATE INDEX ON dispatch_log (equipment_id, dispatched_at);
CREATE INDEX ON maintenance (equipment_id, start_at);
