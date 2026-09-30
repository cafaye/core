# tenancy_test.rb — the negative assertions. Every one of them asks account A
# for account B's row and expects NOTHING BACK, not an error: a 403 would tell
# an attacker the id exists, which is an enumeration oracle. See D33.
#
# The two account fixtures are the whole idiom: a second account, and the same
# question asked of both. For a write, "nothing" is the other account's row
# coming back unchanged — the refusal is an absent row, never a raised error.

require "test/unit"

class AssetsTenancyTest < Test::Unit::TestCase
  ACCOUNT = "6f5d4c3b-2a19-4e8f-9c07-1b2d3e4f5061"
  OTHER_ACCOUNT = "7a6e5d4c-3b20-4f90-8d18-2c3e4f506172"

  def setup
    Assets.insert(id: "a1", account_id: ACCOUNT, checksum: "sha256:mine")
    Assets.insert(id: "b1", account_id: OTHER_ACCOUNT, checksum: "sha256:theirs")
  end

  # account A asks for account B's row: nothing, and the same nothing an id
  # that does not exist would give
  def test_fetch_is_absent_for_another_account
    assert Assets.fetch("a1", account(OTHER_ACCOUNT)).nil?
  end

  # the list, which is the one a join usually loses the scope on
  def test_list_is_empty_for_another_account
    assert Assets.list(account(OTHER_ACCOUNT)).empty?
  end

  # the settlement window
  def test_pending_is_empty_for_another_account
    assert Assets.pending(account(OTHER_ACCOUNT)).empty?
  end

  # the variant
  def test_variant_is_absent_for_another_account
    assert AssetVariants.fetch("v1", account(OTHER_ACCOUNT)).nil?
  end

  # the update: another account's row is not even touched
  def test_settle_changes_nothing_for_another_account
    assert_unchanged("a1") { Assets.settle("a1", account(OTHER_ACCOUNT)) }
  end

  # the delete, which is the one that would end a customer's data
  def test_delete_changes_nothing_for_another_account
    assert_unchanged("a1") { Assets.delete("a1", account(OTHER_ACCOUNT)) }
  end

  # the repository method, with the account bound rather than interpolated
  def test_find_by_checksum_is_absent_for_another_account
    assert Assets.find_by_checksum("sha256:mine", account(OTHER_ACCOUNT)).nil?
  end
end
