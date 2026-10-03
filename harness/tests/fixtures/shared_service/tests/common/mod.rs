//! The shared-database harness: one pool, one set of tables, no `search_path`.
//!
//! This is darkroom's PRE-fix shape in miniature, and it is deliberately shaped
//! so that adding any cleanup to it produces a hazard. Every case in
//! `db_isolation_self_test.sh` that is not a negative control starts here.
//!
//! Note what is ABSENT, because each absence is one of the three conditions the
//! checker reports:
//!
//!   * no `search_path` — a truncate resolves against the shared `public`
//!     tables, so it empties rows another test owns;
//!   * no sandbox or transaction — nothing rolls back at the end of a test;
//!   * one pool for the whole suite, so every test really does share it.
//!
//! cargo's parallelism is the DEFAULT and needs no line here, which is the
//! reason this shape was a live defect in a Rust service and not only in a Go
//! one that had opted in.

use sqlx::postgres::PgPoolOptions;

/// One database for the whole suite, exactly as `TEST_DATABASE_URL` names one.
pub async fn shared_pool() -> sqlx::PgPool {
    PgPoolOptions::new()
        .max_connections(5)
        .connect(&test_database_url())
        .await
        .expect("TEST_DATABASE_URL")
}

fn test_database_url() -> String {
    std::env::var("TEST_DATABASE_URL").expect("TEST_DATABASE_URL is not set")
}