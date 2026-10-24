# ADR-003: Editors write at the Sunday meetings; only Admins Publish

**Status:** accepted
**Date:** 2026-10-24

## Context

The assignment requires two roles, Admin and Editor, with different
permissions. ADR-001 keeps the admin console on one local machine, the
President's laptop, which never goes on the internet. So an Editor account is
only useful if members can get to that laptop. The officers also want to
review and edit every Recap before readers see it.

## Decision

- **Editors exist.** Members the President and VP choose get an Editor
  account, created by an Admin. An Editor writes and edits their own Recaps
  as Drafts and adds Images with alt text. They cannot Publish or Unpublish,
  create Trips, manage accounts, Deploy, make Backups, or edit another
  person's Recap.
- **Publish is Admin-only.** Admins (President and VP) can do everything an
  Editor can, plus all of the above, and can edit any Recap.
- **Editors write at the Sunday club meetings.** The President brings the
  Console laptop, so members don't have to track an officer down across
  campus. A member who misses a meeting can email their writing to an Admin,
  who enters it for them as a Contributor.

## Why Publish stays Admin-only

Nothing is public until an Admin Deploys, so letting Editors Publish would
not make anything go live sooner. It would only blur which Recaps an Admin has
actually checked. With Publish kept for Admins, Published means exactly one
thing: an Admin approved this Recap.

## Considered and rejected

- **No Editor accounts, with Admins entering everything.** Simpler, but it
  fails the assignment's two-role requirement.
- **Remote editing, so Editors log in from their own laptops.** This needs the
  console hosted on the internet, with the security work ADR-001 avoids. Out
  of scope.

## Consequences

- This departs from the brief's "editors can publish their own posts". The
  Editor role here matches WordPress's Contributor role more than its Editor
  role.
- Writing happens on a weekly rhythm. A Recap written between meetings waits
  for Sunday, or goes through an Admin.
