// Package storage is the shared-database base for the latent case: one DSN for
// the whole suite, no per-test schema, and no `t.Parallel()` anywhere.
//
// Both absences matter and they are different absences. No `t.Parallel()` is why
// the suite is not ALREADY broken — go test runs a package's tests in sequence
// unless a test asks otherwise. No per-test schema is why one `t.Parallel()`
// would be enough to make it broken, because the pool is shared and unqualified
// names resolve against the same tables.
//
// The file itself contains no cleanup, so it is NOT a finding on its own. The
// case that uses this fixture adds the cleanup; that is what makes the pair
// latent rather than safe.

package storage

import (
	"context"
	"os"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Pool is every test's pool. TEST_DATABASE_URL names one database and every
// test in this package uses it.
func Pool(ctx context.Context) *pgxpool.Pool {
	dsn := os.Getenv("TEST_DATABASE_URL")
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		panic(err)
	}
	return pool
}