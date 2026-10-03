//! The conforming fixture's one test. It writes, reads back, and cleans up — and
//! the cleanup is a `truncate` that is SAFE ONLY BECAUSE of the search_path
//! `tests/common/mod.rs` stamps onto every connection.
//!
//! That is the shape this whole check exists to recognise, and it is why the
//! `truncate` below is not a finding: an unqualified truncate under a per-test
//! search_path empties one schema. The same line under a shared schema empties
//! the whole table, which is darkroom's defect and what the self-test plants.

mod common;

#[tokio::test]
async fn an_asset_round_trips() {
    let pool = common::test_pool().await;
    common::truncate(&pool).await;

    sqlx::query("insert into assets (name) values ($1)")
        .bind("a")
        .execute(&pool)
        .await
        .expect("inserting");

    let count: (i64,) = sqlx::query_as("select count(*) from assets")
        .fetch_one(&pool)
        .await
        .expect("counting");

    assert_eq!(count.0, 1, "the asset this test created is the only one it sees");
}