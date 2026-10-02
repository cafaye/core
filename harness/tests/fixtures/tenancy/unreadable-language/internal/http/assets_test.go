// assets_test.go — the three-way denial shape, absent rather than forbidden.
package http

import "testing"

// no identity at all: nothing is acting, so nothing comes back.
func TestGetAssetIsAbsentWithoutAnAccount(t *testing.T) {
	srv := newServer(t, noAccount, "a1")
	resp := srv.Get("/v1/assets/a1")
	assertBody(t, resp, not_found)
}

// account A asks for account B's row and gets nothing back, which is the same
// answer an id that does not exist gives. This is the arm with all the
// information in it, and the one a naive suite leaves out.
func TestGetAssetIsAbsentForAnotherAccount(t *testing.T) {
	srv := newServer(t, otherAccount, "b1")
	resp := srv.Get("/v1/assets/a1")
	assertBody(t, resp, not_found)
}

// And its own: the same call, made with this account's credential, returns the
// row. Without this arm the two above are satisfied by a service that returns
// nothing to anybody, which is a broken service rather than an isolated one.
func TestGetAssetSeesItsOwnRow(t *testing.T) {
	srv := newServer(t, myAccount, "a1")
	resp := srv.Get("/v1/assets/a1")
	assertBody(t, resp, object_key)
}