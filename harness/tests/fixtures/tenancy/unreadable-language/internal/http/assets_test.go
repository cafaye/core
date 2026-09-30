// assets_test.go — the negative assertion, absent rather than forbidden.
package http

import "testing"

// account A asks for account B's row and gets nothing back, which is the same
// answer an id that does not exist gives.
func TestGetAssetIsAbsentForAnotherAccount(t *testing.T) {
	srv := newServer(t, otherAccount, "b1")
	resp := srv.Get("/v1/assets/a1")
	assertBody(t, resp, not_found)
}
