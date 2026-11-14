-- 核心表结构参考（PostgreSQL 语法，运行时不执行；建表由 SQLAlchemy create_all 完成）

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(160) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    display_name    VARCHAR(80)  NOT NULL,
    role            VARCHAR(20)  NOT NULL,
    org             VARCHAR(120),
    created_at      TIMESTAMP    NOT NULL
);

CREATE TABLE channels (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(40)  NOT NULL UNIQUE,
    name            VARCHAR(120) NOT NULL,
    kind            VARCHAR(20)  NOT NULL,
    crawl_cron      VARCHAR(40)  NOT NULL,
    endpoint        VARCHAR(255),
    owner           VARCHAR(80),
    note            TEXT,
    enabled         BOOLEAN      NOT NULL DEFAULT TRUE,
    last_crawled_at TIMESTAMP,
    created_at      TIMESTAMP    NOT NULL,
    updated_at      TIMESTAMP    NOT NULL
);

CREATE TABLE posts (
    id                SERIAL PRIMARY KEY,
    external_id       VARCHAR(60)  NOT NULL,
    channel_id        INTEGER      NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    company_raw       VARCHAR(160) NOT NULL,
    company_norm      VARCHAR(120) NOT NULL,
    title_raw         VARCHAR(200) NOT NULL,
    title_stem        VARCHAR(160) NOT NULL,
    city              VARCHAR(40)  NOT NULL,
    salary_raw        VARCHAR(80)  NOT NULL,
    salary_status     VARCHAR(16)  NOT NULL,
    salary_low        INTEGER,
    salary_high       INTEGER,
    months            INTEGER      NOT NULL DEFAULT 12,
    monthly_low       INTEGER,
    monthly_high      INTEGER,
    monthly_median    INTEGER,
    salary_basis      TEXT,
    salary_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    degree            VARCHAR(16)  NOT NULL DEFAULT 'any',
    experience        VARCHAR(16)  NOT NULL DEFAULT 'any',
    published_at      TIMESTAMP    NOT NULL,
    expire_at         TIMESTAMP,
    raw_text          TEXT,
    seed_key          VARCHAR(120),
    created_at        TIMESTAMP    NOT NULL,
    updated_at        TIMESTAMP    NOT NULL,
    CONSTRAINT uq_posts_channel_external UNIQUE (channel_id, external_id)
);

CREATE TABLE runs (
    id              SERIAL PRIMARY KEY,
    run_no          VARCHAR(40)  NOT NULL UNIQUE,
    trigger         VARCHAR(20)  NOT NULL,
    status          VARCHAR(20)  NOT NULL,
    operator_email  VARCHAR(160) NOT NULL,
    threshold       DOUBLE PRECISION NOT NULL DEFAULT 0.82,
    posts_in        INTEGER      NOT NULL DEFAULT 0,
    clusters_out    INTEGER      NOT NULL DEFAULT 0,
    dupes_removed   INTEGER      NOT NULL DEFAULT 0,
    metrics         JSON,
    log_text        TEXT,
    seed_key        VARCHAR(120) UNIQUE,
    started_at      TIMESTAMP    NOT NULL,
    finished_at     TIMESTAMP
);

CREATE TABLE clusters (
    id              SERIAL PRIMARY KEY,
    run_id          INTEGER      NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    fingerprint     VARCHAR(32)  NOT NULL,
    blocking_key    VARCHAR(220) NOT NULL,
    company_norm    VARCHAR(120) NOT NULL,
    company_display VARCHAR(160) NOT NULL,
    title_stem      VARCHAR(160) NOT NULL,
    title_display   VARCHAR(200) NOT NULL,
    city            VARCHAR(40)  NOT NULL,
    salary_low      INTEGER,
    salary_high     INTEGER,
    monthly_median  INTEGER,
    salary_basis    TEXT,
    member_ids      JSON,
    channels        JSON,
    channel_count   INTEGER      NOT NULL DEFAULT 1,
    member_count    INTEGER      NOT NULL DEFAULT 1,
    dup_removed     INTEGER      NOT NULL DEFAULT 0,
    degree          VARCHAR(16)  NOT NULL DEFAULT 'any',
    experience      VARCHAR(16)  NOT NULL DEFAULT 'any',
    published_at    TIMESTAMP,
    expire_at       TIMESTAMP,
    status          VARCHAR(16)  NOT NULL DEFAULT 'active',
    confidence      DOUBLE PRECISION NOT NULL DEFAULT 1,
    needs_review    BOOLEAN      NOT NULL DEFAULT FALSE,
    review_reason   VARCHAR(200),
    golden_post_id  INTEGER      REFERENCES posts(id) ON DELETE SET NULL,
    created_at      TIMESTAMP    NOT NULL,
    updated_at      TIMESTAMP    NOT NULL,
    CONSTRAINT uq_clusters_run_fingerprint UNIQUE (run_id, fingerprint)
);

CREATE TABLE reviews (
    id              SERIAL PRIMARY KEY,
    cluster_id      INTEGER      NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    run_id          INTEGER      REFERENCES runs(id) ON DELETE SET NULL,
    decision        VARCHAR(12)  NOT NULL,
    reviewer        VARCHAR(160) NOT NULL,
    note            TEXT,
    seed_key        VARCHAR(120) UNIQUE,
    created_at      TIMESTAMP    NOT NULL,
    updated_at      TIMESTAMP    NOT NULL,
    CONSTRAINT uq_reviews_cluster UNIQUE (cluster_id)
);

CREATE TABLE audit_logs (
    id              SERIAL PRIMARY KEY,
    actor_email     VARCHAR(160) NOT NULL,
    actor_role      VARCHAR(20)  NOT NULL,
    action          VARCHAR(64)  NOT NULL,
    entity          VARCHAR(40)  NOT NULL,
    entity_id       VARCHAR(64),
    detail          JSON,
    layer           VARCHAR(16)  NOT NULL DEFAULT 'domain',
    ip              VARCHAR(64),
    seed_key        VARCHAR(120) UNIQUE,
    created_at      TIMESTAMP    NOT NULL
);
