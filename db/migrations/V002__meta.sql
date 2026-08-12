-- V002 - Lineage and audit
--
-- The question this schema has to answer, months later, in front of a reviewer:
-- "where did this number come from?" Answer: a load run, a source file, a
-- SHA-256, a Treasury URL and a download timestamp.

CREATE TABLE IF NOT EXISTS meta.load_run (
    load_run_id         bigint      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    started_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    status              text        NOT NULL DEFAULT 'running'
                                    CHECK (status IN ('running', 'succeeded', 'failed')),
    loader_version      text        NOT NULL,
    manifest_generated_at timestamptz,
    datasets_requested  text[]      NOT NULL,
    rows_staged         bigint      NOT NULL DEFAULT 0,
    rows_loaded         bigint      NOT NULL DEFAULT 0,
    error               text,
    notes               text
);

COMMENT ON TABLE meta.load_run IS
    'One row per invocation of the loader. A run that fails is still recorded - '
    'silence about a failure is worse than the failure.';

CREATE TABLE IF NOT EXISTS meta.source_file (
    source_file_id      bigint      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    data_key            text        NOT NULL,
    requested_year      integer     NOT NULL,
    file_name           text        NOT NULL,
    source_url          text        NOT NULL,
    sha256              char(64)    NOT NULL,
    bytes               bigint,
    records             integer     NOT NULL,
    downloaded_at_utc   timestamptz,
    earliest_observation date,
    latest_observation  date,
    http_status         integer,
    content_type        text,
    first_seen_run_id   bigint      NOT NULL REFERENCES meta.load_run (load_run_id),
    last_seen_run_id    bigint      NOT NULL REFERENCES meta.load_run (load_run_id),
    checksum_verified   boolean     NOT NULL DEFAULT false,
    UNIQUE (data_key, requested_year, sha256)
);

COMMENT ON TABLE meta.source_file IS
    'One row per raw Treasury XML file, mirrored from download_manifest.json. '
    'The SHA-256 is re-computed from the file on disk at load time; a mismatch '
    'fails the run rather than loading unverified bytes.';
COMMENT ON COLUMN meta.source_file.sha256 IS
    'Checksum of the raw XML as downloaded. Uniqueness is on (data_key, year, '
    'sha256) so a re-download that changes content is a new row, not an update - '
    'Treasury revisions stay visible.';

CREATE INDEX IF NOT EXISTS source_file_data_key_year_idx
    ON meta.source_file (data_key, requested_year);

CREATE TABLE IF NOT EXISTS meta.load_step (
    load_step_id        bigint      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    load_run_id         bigint      NOT NULL REFERENCES meta.load_run (load_run_id),
    step                text        NOT NULL,
    data_key            text,
    started_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    rows_in             bigint,
    rows_out            bigint,
    status              text        NOT NULL DEFAULT 'running'
                                    CHECK (status IN ('running', 'succeeded', 'failed', 'skipped')),
    detail              jsonb
);

COMMENT ON TABLE meta.load_step IS
    'Per-dataset, per-phase timing and row counts. rows_in vs rows_out is the '
    'first thing to read when a count looks wrong.';

CREATE INDEX IF NOT EXISTS load_step_run_idx ON meta.load_step (load_run_id);

CREATE TABLE IF NOT EXISTS meta.reconciliation (
    reconciliation_id   bigint      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    load_run_id         bigint      NOT NULL REFERENCES meta.load_run (load_run_id),
    checked_at          timestamptz NOT NULL DEFAULT now(),
    check_name          text        NOT NULL,
    data_key            text,
    expected            text,
    actual              text,
    passed              boolean     NOT NULL,
    detail              text
);

COMMENT ON TABLE meta.reconciliation IS
    'Result of every verification check, stored rather than printed. A load is '
    'trustworthy because the checks are on record, not because someone watched '
    'them scroll past.';

CREATE INDEX IF NOT EXISTS reconciliation_run_idx
    ON meta.reconciliation (load_run_id, passed);
