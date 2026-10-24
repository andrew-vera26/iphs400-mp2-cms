# Ticket to test map

Acceptance criteria are copied verbatim from GitHub issues #2 to #10 (`gh issue view`). Each test is cited as `tests/<file>.py::<function>`. Parametrized tests are cited by function name. Where a criterion has no test aimed at it, the row says "no direct test" and names what covers it indirectly.

## #2 T01: Log in, sign out, CSRF and the permission policy

| # | Acceptance criterion | Test(s) |
|---|---|---|
| 1 | The Account schema has email (unique), name, class year, role (`admin` or `editor`), argon2 password hash, an active flag and a created timestamp. | `tests/test_traceability.py::test_account_schema_has_every_listed_field` It checks the `account` database table: every listed column, email unique, seeded hashes are argon2, `created_at` filled in on insert, and a role other than `admin` or `editor` refused. The `Account` Python class deliberately has no `password_hash`, so the hash is never carried around after login. |
| 2 | Logging in with the right email and password works for both seeded Accounts, and `client_as("admin")` and `client_as("editor")` no longer skip. | `tests/test_t01.py::test_seeded_accounts_can_log_in` `client_as` use across the suite also proves it no longer skips. |
| 3 | A wrong password and an unknown email both fail with the same generic message. | `tests/test_t01.py::test_wrong_password_and_unknown_email_look_identical` |
| 4 | The stored password is an argon2 hash and never the plain text. No password is logged. | `tests/test_t01.py::test_password_is_stored_as_argon2_and_never_logged` |
| 5 | Signing out ends the session, and console pages redirect to login afterwards. | `tests/test_t01.py::test_sign_out_ends_the_session` |
| 6 | Anonymous requests to `/admin` routes redirect to `/login`. | `tests/test_t01.py::test_anonymous_console_requests_redirect_to_login`, `tests/test_t01.py::test_anonymous_requests_are_redirected_on_every_guarded_route` |
| 7 | Every state-changing form, including login and logout, renders a hidden CSRF token. A POST with a missing or wrong token gets a 403. | `tests/test_t01.py::test_login_and_logout_forms_carry_a_token`, `tests/test_t01.py::test_post_without_or_with_wrong_token_is_403`, `tests/test_t01.py::test_anonymous_post_without_a_token_is_refused` |
| 8 | Routes ask the one permission-policy module, with no ad-hoc role checks in the routes, and the policy rereads the Account on every request. | `tests/test_traceability.py::test_no_role_comparison_outside_the_policy_module`, `tests/test_t01.py::test_deactivation_takes_effect_at_once` The scan parses every file in `app/` except `app/policy.py`. Five functions are allowlisted because their role comparisons are not permission checks: `app/db.py` (the role CHECK constraint), `_is_last_active_admin` and `set_role` in `app/accounts.py` (the last-active-Admin rule), and `create_account` and `change_role` in `app/routes/accounts.py` (validating the submitted role field). Templates are outside the scan. The rereading is covered by `test_deactivation_takes_effect_at_once`. |
| 9 | The table-driven Editor-on-Admin-only-routes test exists and is ready for later tickets to add rows. | `tests/test_t01.py::test_editor_on_admin_only_routes` The table is `ADMIN_ONLY_ROUTES` in `tests/test_t01.py`; later tickets added rows. |
| 10 | The seed script creates the demo Admin and Editor from environment passwords, and is idempotent on a fresh database. | `tests/test_t01.py::test_seeding_twice_does_not_duplicate_accounts`, `tests/test_t01.py::test_seeded_accounts_can_log_in`, `tests/test_t09.py::test_passwords_come_from_the_environment_only` |
| 11 | The tests in `tests/test_t00.py` still pass. They may be updated only where `/admin` now requires login. | `tests/test_t00.py::test_admin_console_answers`, `tests/test_t00.py::test_public_home_answers`, `tests/test_t00.py::test_publish_writes_a_site`, `tests/test_t00.py::test_published_html_uses_relative_paths` |

## #3 T02: Account management

| # | Acceptance criterion | Test(s) |
|---|---|---|
| 1 | An Admin can list Accounts and create an Account with email, name, class year, role and initial password, which is stored as an argon2 hash. | `tests/test_t02.py::test_admin_lists_accounts`, `tests/test_t02.py::test_admin_creates_an_account_that_can_log_in` The argon2 check on the stored hash is in `tests/test_t02.py::test_admin_creates_an_account_that_can_log_in`. |
| 2 | Creating an Account with an email that is already in use is refused with a clear error. | `tests/test_t02.py::test_duplicate_email_is_refused_with_a_clear_error` |
| 3 | An Admin can change an Account's role, and the Account's permissions follow the new role on its next request. | `tests/test_t02.py::test_promotion_takes_effect_on_the_next_request`, `tests/test_t02.py::test_demotion_takes_effect_on_the_next_request` |
| 4 | An Admin can Deactivate an Account. The Account can't log in afterwards, and its existing session stops working. | `tests/test_t02.py::test_deactivated_account_cannot_log_in`, `tests/test_t02.py::test_deactivated_accounts_existing_session_stops_working` |
| 5 | Deactivating or demoting the last active Admin is refused, and that Account stays an active Admin. | `tests/test_t02.py::test_last_active_admin_cannot_be_deactivated`, `tests/test_t02.py::test_last_active_admin_cannot_be_demoted` |
| 6 | An Admin can set a new password for an Account. | `tests/test_t02.py::test_admin_sets_a_new_password` |
| 7 | There is no Reactivate action. | `tests/test_t02.py::test_there_is_no_reactivate_action`, `tests/test_t02.py::test_changing_role_or_password_does_not_reactivate` |
| 8 | Every Account route is added to the table-driven Editor test, and Editors get a 403 or a redirect on each one. | `tests/test_t01.py::test_editor_on_admin_only_routes` Account rows are in `ADMIN_ONLY_ROUTES`. |
| 9 | Every Account form carries a CSRF token. | `tests/test_t02.py::test_every_account_form_carries_a_token`, `tests/test_t02.py::test_account_posts_without_a_valid_token_are_403` |

## #4 T03: Trips and Recap Drafts with ownership

| # | Acceptance criterion | Test(s) |
|---|---|---|
| 1 | An Admin can create, edit, list and delete Trips. All five fields and the Slug are required. | `tests/test_t03.py::test_admin_creates_a_trip_and_it_is_listed`, `tests/test_t03.py::test_admin_edits_a_trip`, `tests/test_t03.py::test_admin_deletes_a_trip_without_recaps`, `tests/test_t03.py::test_every_trip_field_and_the_slug_are_required` |
| 2 | The Trip Slug is suggested from the year and city, can be edited, and a duplicate is refused with a clear error. | `tests/test_t03.py::test_trip_slug_is_suggested_from_year_and_city`, `tests/test_t03.py::test_duplicate_trip_slug_is_refused_with_a_clear_error` |
| 3 | Deleting a Trip that has any Recap is refused, and the Trip remains. | `tests/test_t03.py::test_deleting_a_trip_that_has_a_recap_is_refused` |
| 4 | An Editor can create a Recap on an existing Trip, chosen from a list, and the Recap starts as a Draft. | `tests/test_t03.py::test_editor_creates_a_draft_with_byline_and_owner_from_their_account`, `tests/test_t03.py::test_editor_picks_the_trip_from_a_list` |
| 5 | The Recap Slug is suggested from the title. A Slug that clashes within the same Trip is refused with a clear error, and the same Slug on a different Trip is allowed. | `tests/test_t03.py::test_recap_slug_is_suggested_from_the_title`, `tests/test_t03.py::test_recap_slug_clash_within_a_trip_is_refused`, `tests/test_t03.py::test_same_recap_slug_on_a_different_trip_is_allowed` |
| 6 | Saving a Recap with an empty or whitespace-only Body is refused. | `tests/test_t03.py::test_empty_or_whitespace_body_is_refused` |
| 7 | An Editor's Byline is filled in from their Account. An Admin can create a Recap with a typed Contributor Byline, and Owner is still set to the Admin. | `tests/test_t03.py::test_editor_creates_a_draft_with_byline_and_owner_from_their_account`, `tests/test_t03.py::test_admin_enters_a_recap_for_a_contributor` |
| 8 | Renaming the Owner's Account later doesn't change existing Bylines. | `tests/test_t03.py::test_renaming_the_owner_later_does_not_change_the_byline` |
| 9 | Owner, created and edited timestamps are recorded and shown in the editor. | `tests/test_t03.py::test_editor_shows_owner_and_timestamps` |
| 10 | An Editor can edit and delete their own Draft. | `tests/test_t03.py::test_editor_edits_their_own_draft`, `tests/test_t03.py::test_editor_deletes_their_own_draft` |
| 11 | An Editor's requests to view, edit or delete another person's Recap are refused, and that Recap is unchanged. | `tests/test_t03.py::test_editor_is_refused_on_another_persons_recap`, `tests/test_t03.py::test_one_editor_cannot_touch_another_editors_recap` |
| 12 | An Admin can edit or delete any Recap, including its Byline. | `tests/test_t03.py::test_admin_edits_any_recap_including_the_byline`, `tests/test_t03.py::test_admin_deletes_any_recap` |
| 13 | The Trip write routes are added to the table-driven Editor test. | `tests/test_t01.py::test_editor_on_admin_only_routes`, `tests/test_t03.py::test_editor_cannot_write_trips` Trip rows are in `ADMIN_ONLY_ROUTES`. |
| 14 | Every form carries a CSRF token. | `tests/test_t03.py::test_new_forms_carry_a_csrf_token`, `tests/test_t03.py::test_state_changing_requests_without_a_token_are_refused` |

## #5 T04: Recap status machine, sanitized Markdown and Preview

| # | Acceptance criterion | Test(s) |
|---|---|---|
| 1 | An Editor can Submit their own Draft, and it becomes Submitted. | `tests/test_t04.py::test_allowed_transitions_move_the_status` Submit is one of the parametrized transitions. |
| 2 | An Admin can Send back a Submitted Recap to Draft, Publish a Draft or Submitted Recap, and Unpublish a Published Recap to Draft. | `tests/test_t04.py::test_allowed_transitions_move_the_status` Send back, Publish (from Draft and from Submitted) and Unpublish are parametrized cases. |
| 3 | Transitions that aren't in the table are refused, for example Submitting a Published Recap. | `tests/test_t04.py::test_transitions_not_in_the_table_are_refused` |
| 4 | An Editor's Publish and Unpublish requests are refused, and the status is unchanged. | `tests/test_t04.py::test_an_editor_cannot_publish_unpublish_or_send_back` |
| 5 | An Editor's Submit request on another person's Recap is refused, and the Recap is unchanged. | `tests/test_t04.py::test_an_editor_cannot_submit_another_persons_recap` |
| 6 | An Editor can't edit or delete their own Recap once it is Submitted or Published. | `tests/test_t04.py::test_an_editor_cannot_edit_or_delete_their_recap_once_it_is_locked`, `tests/test_t04.py::test_an_editor_save_landing_after_the_recap_locked_is_refused`, `tests/test_t04.py::test_an_editor_delete_landing_after_the_recap_locked_is_refused` |
| 7 | Submitting a Recap with an empty Body is refused. | `tests/test_t04.py::test_submitting_with_an_empty_body_is_refused` |
| 8 | Publishing sets the Published timestamp. | `tests/test_t04.py::test_publishing_records_the_published_timestamp` |
| 9 | Editing or Unpublishing a Published Recap shows the "still live until you Deploy" notice. | `tests/test_t04.py::test_editing_a_published_recap_shows_the_still_live_notice`, `tests/test_t04.py::test_unpublishing_shows_the_still_live_notice` |
| 10 | Preview, given a Body containing `<script>`, an external link and an external image, shows sanitized HTML with all three removed and the ordinary Markdown formatting intact. | `tests/test_t04.py::test_preview_removes_script_external_link_and_external_image`, `tests/test_t04.py::test_preview_keeps_ordinary_markdown_formatting` |
| 11 | A `mailto:` link in a Body is removed, and its text remains as plain text. | `tests/test_t04.py::test_mailto_links_are_removed_but_their_text_stays`, `tests/test_t04.py::test_mailto_becomes_plain_text_not_an_anchor` |
| 12 | Publish, Unpublish and Send back are added to the table-driven Editor test. | `tests/test_t01.py::test_editor_on_admin_only_routes` Publish, Unpublish and Send back rows are in `ADMIN_ONLY_ROUTES`. |
| 13 | Every action form carries a CSRF token. | `tests/test_t04.py::test_every_action_form_carries_a_csrf_token`, `tests/test_t04.py::test_an_action_without_a_csrf_token_is_refused` |

## #6 T05: Public site for Trips and Recaps

| # | Acceptance criterion | Test(s) |
|---|---|---|
| 1 | `render_site(out)` writes the home page, one page per Trip that has a Published Recap, and one page per Published Recap, at the addresses above. | `tests/test_t05.py::test_writes_home_trip_and_recap_pages_at_index_addresses` |
| 2 | Draft and Submitted Recaps are absent from the output, and so are Trips with no Published Recap. | `tests/test_t05.py::test_draft_and_submitted_recaps_and_empty_trips_are_absent` |
| 3 | The home page orders Trips by newest start date first. | `tests/test_t05.py::test_home_lists_trips_newest_start_date_first` |
| 4 | A Trip page shows its Summary, then its Published Recaps in Published order, each with its Byline. | `tests/test_t05.py::test_trip_page_shows_summary_then_recaps_in_published_order_with_bylines` |
| 5 | A Body containing `<script>`, an external link and an external image is sanitized in the output. | `tests/test_t05.py::test_hostile_body_is_sanitized_in_the_output` |
| 6 | No `href="/` or `src="/` appears in any file in the output, and links from nested pages resolve correctly. | `tests/test_t05.py::test_no_root_absolute_paths_and_nested_links_resolve`, `tests/test_t05.py::test_stylesheet_reference_is_computed_from_page_depth` |
| 7 | Every page has the Instagram footer link, taken from the committed constant. | `tests/test_t05.py::test_every_page_has_the_instagram_footer_from_the_constant`, `tests/test_t05.py::test_placeholder_instagram_constant_is_committed_in_settings` |
| 8 | Running `cms publish` updates the Site state record of when it last ran. | `tests/test_t05.py::test_cms_publish_writes_site_and_records_when_it_rendered`, `tests/test_t05.py::test_each_publish_run_updates_the_one_site_state_record` |
| 9 | The tests in `tests/test_t00.py` still pass. | `tests/test_t00.py::test_admin_console_answers`, `tests/test_t00.py::test_public_home_answers`, `tests/test_t00.py::test_publish_writes_a_site`, `tests/test_t00.py::test_published_html_uses_relative_paths` |

## #7 T06: Images

| # | Acceptance criterion | Test(s) |
|---|---|---|
| 1 | Uploading a valid JPEG, PNG or WebP with alt text to a Recap succeeds and shows a Markdown snippet with that alt text and a relative `images/<file>` path. | `tests/test_t06.py::test_valid_image_is_stored_and_a_markdown_snippet_is_shown` |
| 2 | A file of the wrong type is refused with a clear message. This includes a non-image renamed to `.jpg`. | `tests/test_t06.py::test_a_file_of_the_wrong_type_is_refused_with_a_message`, `tests/test_t06.py::test_the_real_type_decides_not_the_extension_or_header` |
| 3 | A file over the size limit is refused with a clear message. | `tests/test_t06.py::test_a_file_over_the_size_limit_is_refused_with_a_message` |
| 4 | An upload with missing alt text is refused. | `tests/test_t06.py::test_missing_alt_text_is_refused` |
| 5 | An Editor can't upload to another person's Recap, or to their own Recap once it is Submitted or Published. | `tests/test_t06.py::test_an_editor_cannot_upload_to_another_persons_recap`, `tests/test_t06.py::test_an_editor_cannot_upload_after_submitting` |
| 6 | Publish is refused while the Body contains an image with empty alt text. | `tests/test_t06.py::test_publish_is_refused_while_the_body_has_an_image_without_alt` |
| 7 | Preview shows the Recap's own uploaded Images, and still strips external images. | `tests/test_t06.py::test_preview_shows_the_recaps_own_uploaded_images`, `tests/test_t06.py::test_preview_still_strips_external_and_unknown_images` |
| 8 | Deleting a Recap removes its Images from storage. | `tests/test_t06.py::test_deleting_a_recap_removes_its_images_from_storage` |
| 9 | `render_site` copies only the Images of Published Recaps, and an Image from a Draft Recap is absent from the output. | `tests/test_t06.py::test_only_the_published_recaps_images_are_copied`, `tests/test_t06.py::test_images_of_recaps_that_are_not_published_are_not_copied` |
| 10 | Image references in the output are relative and resolve. | `tests/test_t06.py::test_image_references_in_the_output_are_relative_and_resolve` |
| 11 | The upload form carries a CSRF token. | `tests/test_t06.py::test_the_upload_and_delete_forms_carry_a_csrf_token`, `tests/test_t06.py::test_an_upload_without_a_csrf_token_is_refused` |

## #8 T07: Pages and the Navigation bar

| # | Acceptance criterion | Test(s) |
|---|---|---|
| 1 | An Admin can create, edit, delete, Publish and Unpublish a Page. Every Page starts as a Draft. | `tests/test_t07.py::test_admin_creates_a_page_and_it_starts_as_a_draft`, `tests/test_t07.py::test_admin_edits_a_page`, `tests/test_t07.py::test_admin_deletes_a_page`, `tests/test_t07.py::test_publish_and_unpublish_move_the_status` |
| 2 | Owner, created and edited timestamps are recorded. | `tests/test_t07.py::test_the_editor_records_owner_and_both_timestamps` |
| 3 | A reserved Slug (`trips`, `images`, `admin`, `login`) and a duplicate Page Slug are each refused with a clear error. | `tests/test_t07.py::test_a_reserved_slug_is_refused_with_a_clear_error`, `tests/test_t07.py::test_a_duplicate_page_slug_is_refused_with_a_clear_error` |
| 4 | The Pages list filters by status. | `tests/test_t07.py::test_the_pages_list_filters_by_status` |
| 5 | Page Preview shows the sanitized Body, with external links, `mailto:` links, images and raw HTML removed. | `tests/test_t07.py::test_new_page_preview_shows_the_sanitized_body`, `tests/test_t07.py::test_existing_page_preview_shows_the_sanitized_body` |
| 6 | Editing or Unpublishing a Published Page shows the "still live until you Deploy" notice. | `tests/test_t07.py::test_editing_a_published_page_shows_the_still_live_notice`, `tests/test_t07.py::test_unpublishing_a_page_shows_the_still_live_notice` |
| 7 | Every Page route is added to the table-driven Editor test, and Editors get a 403 or a redirect on each one. | `tests/test_t01.py::test_editor_on_admin_only_routes`, `tests/test_t07.py::test_an_editor_cannot_create_edit_publish_or_delete_a_page` Page rows are in `ADMIN_ONLY_ROUTES`. |
| 8 | `render_site` writes Published Pages and omits Draft Pages. | `tests/test_t07.py::test_published_pages_are_written_and_drafts_are_not` |
| 9 | Every page in the output has a Navigation bar listing Home, then the Published Pages in nav order, with relative links that resolve from every depth. | `tests/test_t07.py::test_navigation_bar_is_home_then_published_pages_in_nav_order`, `tests/test_t07.py::test_navigation_links_resolve_from_every_depth` |
| 10 | No `href="/` or `src="/` appears anywhere in the output. | `tests/test_t07.py::test_no_root_absolute_paths_with_pages_in_the_output` |
| 11 | Every Page form carries a CSRF token. | `tests/test_t07.py::test_every_page_form_carries_a_csrf_token`, `tests/test_t07.py::test_page_posts_without_a_valid_token_are_403` |

## #9 T08: Dashboard and content list

| # | Acceptance criterion | Test(s) |
|---|---|---|
| 1 | The Admin dashboard counts match the test data: Recaps by status, Trips, Pages by status, and active Accounts, with Deactivated Accounts excluded. | `tests/test_t08.py::test_admin_dashboard_counts_match_the_data`, `tests/test_t08.py::test_deactivating_an_account_lowers_the_active_count` |
| 2 | The Editor dashboard shows only counts of that Editor's own Recaps. | `tests/test_t08.py::test_editor_dashboard_counts_only_their_own_recaps` |
| 3 | The "changes not yet live" notice appears after a content change, disappears after `cms publish`, and appears again after the next change. | `tests/test_t08.py::test_notice_cycle_with_the_real_cms_publish`, `tests/test_t08.py::test_notice_appears_after_any_content_change`, `tests/test_t08.py::test_notice_is_absent_right_after_a_render` |
| 4 | The Admin Recaps list filters correctly by status, Trip and Owner, alone and combined. | `tests/test_t08.py::test_admin_filters_by_status`, `tests/test_t08.py::test_admin_filters_by_trip`, `tests/test_t08.py::test_admin_filters_by_owner`, `tests/test_t08.py::test_admin_filters_combine` |
| 5 | Submitted Recaps appear first in the Admin list. | `tests/test_t08.py::test_submitted_recaps_come_first_for_an_admin` |
| 6 | An Editor's list contains only their own Recaps, the status and Trip filters work, and an Owner filter can't reveal anyone else's Recaps. | `tests/test_t08.py::test_editor_list_contains_only_their_own_recaps`, `tests/test_t08.py::test_editor_filters_by_status_and_trip`, `tests/test_t08.py::test_editor_owner_filter_cannot_reveal_anyone_elses_recaps` |
| 7 | Anonymous requests to the dashboard and list redirect to login. | `tests/test_t08.py::test_anonymous_requests_redirect_to_login` |

## #10 T09: Seed data, cms backup and the final route audit

| # | Acceptance criterion | Test(s) |
|---|---|---|
| 1 | The seed script on a fresh database creates the Admin, the Editor, a Trip, at least one Recap in each status, a Draft Page and a Published Page, and exits 0. | `tests/test_t09.py::test_seed_on_a_fresh_database_creates_one_of_everything` |
| 2 | The seed script exits non-zero with a clear message when either password variable is missing. No password is hard-coded. | `tests/test_t09.py::test_seed_without_a_password_exits_nonzero_and_says_which`, `tests/test_t09.py::test_passwords_come_from_the_environment_only` |
| 3 | Running `cms publish` after seeding produces a site with the Published content only. | `tests/test_t09.py::test_cms_publish_after_seeding_writes_published_content_only` |
| 4 | `main(["backup", <folder>])` writes one dated archive containing the database and the uploaded Images. | `tests/test_t09.py::test_backup_writes_one_dated_archive_with_the_database_and_images` |
| 5 | `cms backup` with an output folder inside the repository is refused with a non-zero exit, and no archive is written. | `tests/test_t09.py::test_backup_inside_the_repository_is_refused` |
| 6 | `.gitignore` excludes backup archives. | `tests/test_t09.py::test_backup_archives_are_gitignored` |
| 7 | A test requests every console route anonymously and gets a redirect to login for each one. | `tests/test_t09.py::test_every_console_route_sends_an_anonymous_visitor_to_login` |
| 8 | The Editor table covers Trip writes, all Page routes, all Account routes, Publish, Unpublish, Send back, and edit, Submit and delete on a Recap the Editor doesn't Own. | `tests/test_traceability.py::test_every_admin_only_or_state_changing_route_is_in_a_table`, `tests/test_t01.py::test_editor_on_admin_only_routes` The first checks that every admin-only or state-changing /admin route is in `ADMIN_ONLY_ROUTES` or in the documented `EDITOR_ALLOWED_ROUTES` (an Editor's own Draft); the second runs each row of `ADMIN_ONLY_ROUTES` as an Editor. |
| 9 | The full test suite passes, including `tests/test_t00.py`. | no direct test. The criterion is the suite itself: `uv run pytest -q`. The `tests/test_t00.py` tests are in the suite. |

## Summary

- Criteria: 94
- Rows marked "no direct test": 1
