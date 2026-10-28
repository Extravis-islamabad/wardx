# Phase 1 (a) Safes and (b) Approval workflow: spec

Decisions agreed in review on 2026-10-28; this is the build spec. Layering follows
`Backend/ARCHITECTURE.md` (copy the inventory module). Never delete or rewrite existing dev
data: migrations only add, backfill and move.

## (a) Safes

### Model

- **Safe:** name (unique, case-insensitive), description, active flag. Every account belongs
  to **exactly one** safe (`inventory.accounts.safe_id NOT NULL`). Targets stay global; a
  target's accounts may sit in different safes.
- **Member:** `(safe, principal, permissions)`. A principal is one of:
  - `user`: a WardX user, by id;
  - `group`: a directory group, by normalised DN;
  - `role`: a WardX role. **Roles are for the migration only.** The UI offers users and groups;
    the API accepts roles so the Default safe can keep today's access.
- **Safe permissions (7):**

  | Permission | Allows |
  |---|---|
  | `list` | See the safe and its accounts |
  | `use` | Connect through the gateway without seeing the password |
  | `retrieve` | Check out and reveal |
  | `manage_accounts` | Add, edit and delete accounts; set secrets |
  | `manage_members` | Add, change and remove members |
  | `view_audit` | Read audit events for the safe's accounts |
  | `approve` | Approve requests (used by (b)) |

- **Effective permissions** for a user on a safe are the union over their direct
  membership, their role's membership, and the membership of every directory group they
  belong to.

### Global codenames (src/core/permissions.py)

- `safes.manage`: create and edit safes, and manage members of any safe. Held by admin.
  **It doesn't grant list, use or retrieve.** That needs membership, so admins don't get
  into secrets by default (separation of duties).
- `access.emergency`: break-glass, described below. **No role holds it.**
- Today's `inventory.view` and `inventory.manage` keep gating targets and the routes
  themselves. Account visibility and account actions are then filtered and checked
  against safe permissions.

### Rules

- **Account list and get:** only accounts in safes where the caller has `list`. Any other
  account reads as 404.
- **Account create, edit, set secret, delete:** need `manage_accounts` on the account's safe
  (and on the destination safe when moving an account).
- **Check-out** needs `retrieve`, and so does **reveal**. **Gateway sessions** need `use` or
  `retrieve`.
- **No self-grant.**
  - Nobody can add or change a membership whose principal is themselves, a group they
    belong to, or their own role. That includes widening an existing self-membership.
  - Refused with 403 `self_grant_forbidden` and audited as a failure. Another admin must do it.
- **Every** safe and membership change is audited with before and after values.

### Directory groups

- At directory sign-in, the user's groups (normalised DNs) are stored in
  `iam.user_group_cache` with `fetched_at`.
- When permissions are evaluated and the cache is older than
  `WARDX_GROUP_CACHE_MINUTES` (default 15), the groups are re-read through the
  directory service-account lookup.
- **If the directory is unreachable at that point, group memberships count as none (fail
  closed)** and a warning is logged. Direct and role memberships still work.
- Directory sync also refreshes the cache, and clears it for users it disables.
- **Nested groups:**
  - Active Directory: resolved with the `LDAP_MATCHING_RULE_IN_CHAIN` filter
    (`1.2.840.113556.1.4.1941`), **on by default for AD**. The directory config's
    `nested_groups` flag is an off-switch for very large directories where the in-chain
    query is slow. Defaults: on for the AD preset (`attr_username` `sAMAccountName`), off
    for OpenLDAP. Migration 013 turns it on for an existing AD config.
  - WardX searches `(&(objectClass=group)(member:1.2.840.113556.1.4.1941:=<user DN>))` under
    the group base DN, or the domain root (the user base DN's `dc=` suffix), and adds the
    results to the user's direct `memberOf` groups.
  - Other directories: direct groups only, a documented limitation.
  - **Test limitation:** ldap3's mock (`MOCK_SYNC`) rejects extensible-match filters, so the
    in-chain query can't run against it. Unit tests check the filter and base WardX sends,
    and that its results are added to `memberOf`. Integration tests run with
    `nested_groups` off. Verify against a real AD before release.
- **Implementation:**
  - Cache refreshes are written on their own short session, so a read-only or failing
    request still keeps them.
  - After a failed contact, WardX doesn't retry the directory for
    `WARDX_DIRECTORY_RETRY_SECONDS` (default 60). During that time, groups fail closed at
    once, without a connect timeout on every request. Any successful contact ends the wait:
    a sign-in, a sync, or the admin's test lookup.

### Break-glass (`access.emergency`)

- **Break-glass must not depend on the directory.** Only **local** users (`auth_source`
  `local`) who are **enrolled in MFA** can hold it. Granting it to a directory user, or to
  a local user without MFA, is refused (409 `not_eligible`). Directory groups and roles can
  never hold it: it is a per-user direct grant only.
- **Granting it:**
  - A per-user grant in `iam.user_permissions` (direct user grants, the MonetX "UBAC" idea).
    Only a holder of `users.manage` can grant it, never to themselves (403
    `self_grant_forbidden`, audited as a failure). That includes re-granting after an
    automatic revoke: another admin must do it.
  - API: `PUT` / `DELETE /users/{id}/permissions/access.emergency`. A revoke stamps
    `revoked_at`; grant rows are kept as history.
  - The grant and the revoke are each audited and each raise a high-severity alert.
  - `/auth/me` returns the caller's effective global permissions (role bundle plus direct
    grants), and the frontend gates on that list.
- **Safeguards:**
  - At the time of use, an emergency reveal also requires the holder to still be local,
    active and enrolled in MFA. A refusal is audited as a failure.
  - A holder can't turn their own MFA off while holding the grant (409 with a clear
    message).
  - An admin MFA reset on a holder revokes the grant automatically, in the same
    transaction. The revocation is audited (`user.revoke`, reason `mfa_reset`) and raises a
    high alert.
- **Eligible holder** (used by the health check and coverage warning below): local, active,
  enrolled in MFA, and holding the grant.
- **Using it:**
  - `POST /accounts/{id}/emergency-reveal {reason}`, with a reason of at least 20 characters.
  - It reveals from any safe, regardless of membership, and records an emergency check-out.
  - Audited as `secret.emergency_reveal`, and creates a **high-severity alert**.
- **Security alerts:**
  - Stored in `security.alerts` (severity, kind, message, object refs, acknowledged by/at).
  - Unacknowledged high alerts show as a banner on the dashboard for holders of
    `audit.view`. An admin acknowledges them, which is audited.
  - Alerts are never deleted.
  - API:
    - `GET /alerts`, filtered by `severity` and `acknowledged`, needs `audit.view`.
    - `POST /alerts/{id}/acknowledge` needs `alerts.acknowledge`, a new admin codename.
  - A database trigger refuses any delete, and any update other than acknowledging an
    unacknowledged alert.

### Migration (no data loss)

- Create a **Default** safe with a fixed id. Every existing account moves into it.
- Members keep today's access:
  - roles `user`, `approver`, `auditor`: `list`, `use`, `retrieve`;
  - role `admin`: all of the above plus `manage_accounts`, `manage_members` and `view_audit`;
  - `approve` for `approver` and `admin`, because that is how approvals work today.

### Build decisions (where the spec was silent; the more restrictive choice was taken)

- **Routes:** safes and members live under `/safes` and `/safes/{id}/members`. Reading
  safes and changing members is gated by `inventory.view` at the route; the service then
  requires `safes.manage` or `manage_members` on that safe. Creating and editing safes
  needs `safes.manage`. Safes are deactivated, never deleted.
- **Inactive safe:** its members keep only `list`, `view_audit` and `manage_members`, so
  nobody uses, retrieves or edits its accounts until it is reactivated.
- **New accounts** without a `safe_id` go into the Default safe, which still needs
  `manage_accounts` there. Account routes keep their `inventory.manage` gate, so account
  administration needs both the route codename and `manage_accounts`.
- **Self-grant:** any add or change of your own membership is refused, narrowing included.
  Removing a membership (yours too) is allowed, since it only narrows access. While your
  directory groups can't be verified, every group membership change is refused with
  `self_grant_forbidden`, because the group might be yours.
- **Requests** (today's approval flow) need `retrieve` or `use` on the account's safe,
  and 404 for unlisted accounts.
- **Deleting a target** deletes its accounts, so it needs `manage_accounts` on every safe
  those accounts sit in.
- **Emergency check-out:** it lasts min(60 min, the account's limit). It ignores
  exclusivity, which is the point of break-glass. It is refused while the holder already
  holds an active check-out of the account.
- **Reveal** re-checks `retrieve` on every call, so removing a member stops their next reveal
  even mid check-out. A check-out the gateway took for a `use`-only member can't be revealed.

## (b) Approval workflow

### Safe policy (set per safe)

| Setting | Default |
|---|---|
| `approval_required` | off |
| approval levels | none (see below) |
| `ticket_mode` | off / optional / **required** (default off) |
| `ticket_pattern` | regex, optional |
| `approval_window_minutes` | 120 |
| `approval_multi_use` | false (single use) |
| `level_timeout_hours` | 24 |

- **Levels** are ordered. Each level has approvers and `required_approvals` (at least 1).
- A level's approvers are either "safe members with `approve`", or a named user or directory
  group (which must also hold `approve` on the safe).
- Dual control is one level needing 2 approvals.
- The per-account `requires_approval` flag is retired: no longer read, and the column is
  kept, not dropped. Its meaning moves into the safe policy, with the migration below.

### Request flow

1. **Create:**
   - The account's safe must require approval.
   - The ticket is validated per `ticket_mode` and `ticket_pattern`.
   - The duration must be within the account's maximum.
   - The request starts at level 1.
2. **Decide (approve or deny at the current level):**
   - The approver must be eligible for that level.
   - The requester can never approve.
   - The same person can never approve at two levels: one decision per person per request.
   - Any deny ends the request as `denied`.
   - When a level reaches `required_approvals`, the request moves to the next level. After
     the last level it becomes `approved`, with `valid_until = approved_at + window`.
3. **Timeouts:** a level left undecided for `level_timeout_hours` expires the request. An
   approved request that is unused at `valid_until` expires. The expiry sweeper handles both,
   and there's no escalation yet.
4. **Use:**
   - Check-out (and the gateway's check-out for a session) consumes an approved request
     within its window.
   - Single-use requests become `used` after one use. Multi-use requests count uses until
     `valid_until`.
5. **Notifications:**
   - In-app only (`notify.notifications`, per user, with read and unread state).
   - Created when a request is made (the level-1 approvers), when it advances (the next
     approvers and the requester), and when it is approved, denied or expires (the requester).
   - The console shows a bell with an unread count. No email.
6. **Audit:** every decision is audited, with its level.

### Migration (no data loss)

- Existing accounts with `requires_approval = true` move to a new safe,
  **"Default (approval required)"**. It has the same members and policy
  `approval_required = on`, with one level of 1 approval from safe members with `approve`.
- Existing open requests continue at level 1 of their safe's policy.
