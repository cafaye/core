// The conforming fixture's harness, and the shape `db_isolation_check.py` is
// looking for when it decides a service has per-test isolation.
//
// Two things here are load-bearing and both were measured against darkroom's
// real harness before they were written:
//
//   * the schema is minted PER CALL (`fresh_schema()`), so two tests never share
//     one — this is the difference between the fix and the defect;
//   * `set search_path` is applied in `after_connect`, on EVERY connection. A
//     pool hands any of its connections to any statement, so a search_path set
//     on one connection would isolate whichever query happened to get it. That
//     is the shape of bug that passes in a small suite and fails under load.

use std::sync::Arc;

use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

pub const SCHEMA_PREFIX: &str = "t_";
pub const SCHEMA_HEX_CHARS: usize = 8;

/// A schema name no other test in this run will use.
pub fn fresh_schema() -> String {
    let hex = Uuid::new_v4().simple().to_string();
    format!("{SCHEMA_PREFIX}{}", &hex[..SCHEMA_HEX_CHARS])
}

pub fn quoted(name: &str) -> String {
    format!("\"{name}\"")
}

/// Connect, migrate into a schema of this test's own, and hand back a pool
/// whose unqualified names resolve inside it.
pub async fn test_pool() -> Arc<sqlx::PgPool> {
    let schema = fresh_schema();
    let search_path = format!("set search_path to {}", quoted(&schema));

    let pool = PgPoolOptions::new()
        .max_connections(5)
        .after_connect(move |conn, _meta| {
            let search_path = search_path.clone();
            Box::pin(async move {
                sqlx::query(&search_path).execute(&mut *conn).await?;
                Ok(())
            })
        })
        .connect(&test_database_url())
        .await
        .expect("TEST_DATABASE_URL");

    let name = quoted(&schema);
    sqlx::query(&format!("create schema {name}"))
        .execute(&pool)
        .await
        .expect("creating the test schema");
    pool
}

/// Empty every table this service owns — in THIS test's schema, because the
/// names are unqualified and the pool's `search_path` points at it.
pub async fn truncate(pool: &sqlx::PgPool) {
    sqlx::query("truncate assets, asset_variants cascade")
        .execute(pool)
        .await
        .expect("truncate");
}

fn test_database_url() -> String {
    std::env::var("TEST_DATABASE_URL").expect("TEST_DATABASE_URL is not set")
}