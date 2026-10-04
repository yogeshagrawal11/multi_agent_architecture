-- Author: Yogesh Agrawal
-- Mock Bank schema (SQLite). All data is fictional/seeded for the demo.

CREATE TABLE IF NOT EXISTS customers (
    customer_id         TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    role                TEXT NOT NULL,          -- privileged | premium | standard
    registered_address  TEXT NOT NULL,
    phone               TEXT NOT NULL,
    email               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id   TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL,
    type         TEXT NOT NULL,                 -- savings | current
    balance      REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    txn_id              TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL,
    date                TEXT NOT NULL,
    amount              REAL NOT NULL,
    direction           TEXT NOT NULL,          -- debit | credit
    merchant            TEXT NOT NULL,
    category            TEXT NOT NULL DEFAULT 'purchase',  -- purchase | interest_charge | salary | ...
    flagged_suspicious  INTEGER NOT NULL DEFAULT 0,
    waived              INTEGER NOT NULL DEFAULT 0,         -- 1 if an interest charge was waived
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

CREATE TABLE IF NOT EXISTS credit_cards (
    card_id        TEXT PRIMARY KEY,
    customer_id    TEXT NOT NULL,
    number_masked  TEXT NOT NULL,
    "limit"        REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS service_requests (
    req_id       TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL,
    type         TEXT NOT NULL,                 -- checkbook | address_change | credit_limit
    status       TEXT NOT NULL,                 -- open | completed | denied
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
