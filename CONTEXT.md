# Kenyon Model UN Recaps

A content system where the Kenyon Model UN club's officers publish recaps of the club's conference trips for the Kenyon community.

## Content

**Trip**:
One conference journey the club made, such as the Chicago conference. A Trip carries its own required Summary of what the trip was, and groups the Recaps written about it. A Trip appears on the Public site only once it has at least one Published Recap, and it can be deleted only while it has no Recaps.
_Avoid_: Event, conference (as the record's name)

**Summary**:
An Admin-written overview on a Trip: the conference, where it was, and what happened overall. Readers see it at the top of the Trip's page.
_Avoid_: Description, intro

**Recap**:
One club member's personal account of exactly one Trip. A Recap has a title, a Slug, a Markdown body with optional Images, a Byline, an Owner, and records of when it was created, last edited, and Published. It is written by an Editor, or entered by an Admin for a Contributor. Recaps are individual anecdotes, while the Trip's Summary says what the trip was. A Trip can have several Recaps.
_Avoid_: Post, blog, article

**Slug**:
The short, URL-safe name that identifies a Trip, Recap, or Page in the public site's addresses, such as `2026-chicago` or `chicago-food-crawl`. A Trip's Slug is unique among Trips, a Recap's within its Trip, and a Page's among Pages. A Page cannot take a Slug the site already uses, such as `trips` or `images`.
_Avoid_: Permalink, path, handle

**Byline**:
The writer's name and class year shown on a Recap, such as "by Jane Doe '27". Both parts are required. An Editor's or Admin's Byline comes from their Account, and an Admin types a Contributor's Byline by hand. The Byline is separate from the Recap's Owner.
_Avoid_: Author (an Admin who typed a Recap in is not its writer)

**Owner**:
The Account a Recap or Page belongs to: the Editor who wrote it, or the Admin who created it or entered it for a Contributor. "Their own Recap" means a Recap they Own.
_Avoid_: Author, creator

**Image**:
A photo uploaded to a Recap and placed inline in its body, always with alt text. Images belong to Recaps only. Recaps show only uploaded Images, never ones hosted elsewhere.
_Avoid_: Media, attachment, embed

**Page**:
Standing content about the club that is not tied to a Trip, such as "About the club" or "Officers and contact". A Page has a title, a Slug, a text-only Markdown body, a Draft or Published status, an Owner, and records of when it was created and last edited. Only Admins create, edit, or delete Pages.
_Avoid_: Static page, post

**Body**:
The Markdown text of a Recap or Page. A Body never links to outside sites or shows images hosted elsewhere.
_Avoid_: Content, text (for this field)

**Navigation bar**:
The list of links across the top of the public site: a Home link first, then the Published Pages in the order Admins set.
_Avoid_: Menu, header links

## Publishing

**Public site**:
The static website the Kenyon community reads: Trips that have a Published Recap, their Published Recaps, the Published Pages, and the Navigation bar. Deploy produces it. Nothing else reaches it.
_Avoid_: Blog, front end, live site

**Draft**:
A Recap's or Page's status while it is still being written. Every Recap and Page starts as a Draft, and Drafts never leave the database.

**Submitted**:
A Recap's status once its Editor says it is finished and ready for an Admin to review. Nobody but an Admin can change it from here.
_Avoid_: Pending, in review

**Published**:
A Recap's or Page's status once an Admin has approved it for the public site. It is not visible to readers until the next Deploy.

**Submit**:
An Editor moving their own Recap from Draft to Submitted.

**Send back**:
An Admin returning a Submitted Recap to Draft so its Editor can revise it.
_Avoid_: Reject

**Publish / Unpublish**:
Moving a Recap or Page to Published, or from Published back to Draft. Only Admins Publish or Unpublish.
_Avoid_: using "publish" for rebuilding the site

**Deploy**:
Rebuilding the Public site from the Trips, Published Recaps, and Published Pages, and pushing it live. Only Admins deploy. A Deploy is two commands: `cms publish` renders the Public site into `site/`, and `cms deploy` pushes it live. Despite its name, `cms publish` does not Publish anything.
_Avoid_: Publish (for this action), build, push

**Site state**:
The single record of when `cms publish` last rendered the Public site. Changes made after that moment are not yet live, which is what the dashboard's "changes not yet live" notice reports.
Counted as changes: creating, editing or deleting a Trip, Recap or Page; adding or deleting a Recap's Image; and Publish, Unpublish, Submit and Send back. A Recap's or Page's "last edited" time therefore also moves on Publish and Unpublish, and Draft changes can also turn the notice on. Both are deliberate: the notice errs toward telling an Admin to Deploy. Stamps have one-second precision, so a change in the same second as the render counts as already rendered.
_Avoid_: Publish timestamp (Published is a Recap's or Page's status)

**Backup**:
A dated archive of the database and uploaded Images, kept somewhere private outside the repository. It is the only copy of Drafts and Recap sources if the Console laptop is lost. Only Admins make Backups.

## Operations

**Console laptop**:
The single machine (the President's) that runs the admin console and holds the one real database. Admins work on it, and Editors log in on it during the Sunday club meetings.

**Handover**:
The yearly transfer to new officers: outgoing Admins create the incoming Admins' Accounts, incoming Admins Deactivate the outgoing ones, and the Console laptop or latest Backup moves with them.

## People

**Account**:
One person's login to the admin console, carrying their name, class year, and role (Admin or Editor). An Account is either active or Deactivated.
_Avoid_: User (in prose), profile, login

**Deactivate**:
An Admin switching off an Account so it can no longer log in. Its Recaps, Pages, and Bylines stay as they are. The last active Admin can never be Deactivated.
_Avoid_: Delete, remove, ban

**Admin**:
The club's President or Vice President. Admins can do everything an Editor can, and also Publish and Unpublish, Send back, create, edit, and delete Trips, create, edit, and delete Pages, create Accounts, change an Account's role, Deactivate Accounts, Deploy, and make Backups. They can edit or delete any Recap and enter one on a Contributor's behalf.
_Avoid_: Officer (in the system), superuser

**Editor**:
A club member with their own Account who writes their own Recaps as Drafts, adds Images with alt text to them, and Submits them. An Editor can edit or delete their own Recap only while it is a Draft. The President and VP decide which members become Editors, and an Admin creates the Account. An Editor cannot Publish or Unpublish, create Trips, create or edit Pages, manage Accounts, Deploy, make Backups, or edit another person's Recap.
_Avoid_: Author, writer, contributor (for this role)

**Contributor**:
A member whose writing an Admin enters for them, for example because they missed a Sunday meeting and emailed it in. A Contributor has no Account of their own.
_Avoid_: Editor (for this role), author, writer
