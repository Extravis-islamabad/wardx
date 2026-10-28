# WardX roadmap

Scope (decided 2026-10-28): the full CyberArk Identity Security feature set, built as one
product on the MonetX architecture, sellable standalone or integrated with MonetX.

Status: ✅ built · 🟡 partial · ⬜ not started · ⏸ deferred

## Release plan

| Release | Phases | Contents |
|---|---|---|
| **MVP: first sellable release** | **0–3** | Foundation and tenancy, vault and rotation (CPM), MonetX credential provider, session manager (PSM), discovery and JIT |
| Later | 4–8 | Secrets management, threat analytics, cloud and vendor access and certificates, endpoint agents, workforce identity and IGA |

Gate before Phase 1 starts: the security test suite (route permission coverage, crypto
round-trip and tamper, audit append-only) is in CI and green. ✅ met 2026-10-28, except
cross-tenant isolation, which is deferred with tenancy (below).

## Phase 0: Foundation and re-architecture (MVP, in progress)

| Item | Status |
|---|---|
| Vault: AES-256-GCM envelope encryption, KEK keyring and rotation, owner-bound AAD | ✅ |
| Identity: local users, argon2id, JWT, lockout, TOTP MFA, LDAP/AD sign-in, directory sync | ✅ |
| Access: request → approve (never your own) → check-out → reveal → check-in, expiry | ✅ |
| SSH session gateway: injection, deny rules, recording, kill, host-key pinning | ✅ |
| Hash-chained append-only audit with verification; keyed (HMAC) since the tenancy seams | ✅ |
| Re-layer backend and frontend onto exact MonetX layering | ✅ |
| Permission codenames instead of role checks | ✅ |
| Tenant key management design (`Backend/TENANCY_KEYS.md`, revision 3, decisions in §10) | ✅ approved |
| Tenancy core (Part A): parent and tenant DBs, file and SoftHSM2 providers, key hierarchy, re-wrap job, recording encryption, cross-tenant tests on | ⏸ |
| Tenancy hardening (Part B): audit sink and checkpoints, backup/restore, ceremony tooling, TPM provider, cloud KMS, compromise tooling | ⏸ |
| Tenancy seams so Phase 1 needs no rewrite: key-provider interface (file provider only), keyed HMAC audit chain, single default-tenant context | ✅ |
| MonetX envelope and pagination shape; MonetX integration contract (SSO, device sync, credential provider for NCM) | ⬜ |

> **Tenancy deferred (2026-10-28).** Parts A and B are on hold. `Backend/TENANCY_KEYS.md`
> (revision 3) is the approved design to build from when it resumes. Until then WardX runs as a
> single default tenant behind the tenancy seams above. `tests/security/test_cross_tenant.py`
> stays skipped; **when tenancy resumes, those tests passing (none skipped) is the gate for
> shipping it.**

## Phase 1: Digital Vault and Central Policy Manager (MVP)

### Phase 1 plan (2026-10-28)

Built one module at a time, in this order. Each module ships backend, frontend and tests on the
targets/accounts template (`Backend/ARCHITECTURE.md`), in small commits with tests and the
frontend build passing at every commit. Effort is engineer-days.

| # | Module | Scope | Effort |
|---|---|---|---|
| 0 | Tenancy seams | Key-provider interface (file provider), keyed HMAC audit chain, default-tenant context | 2–3 |
| a | Safes | Safes, members, per-safe permissions on top of the codenames; accounts move into safes; existing accounts kept in a default safe | 5–7 |
| b | Approval workflow | Approval policies per safe: dual control, multi-level approver chains, ticket number field (validated against SupportX later) | 5–7 |
| c | Rotation engine and platforms | Scheduled, after check-in and on-demand rotation; verify and reconcile; Linux/Unix over SSH, then Windows, then Cisco, Huawei and MikroTik | 12–15 |
| d | MonetX credential provider API | App identities and authentication, credential fetch at poll time, full audit trail, API document for the MonetX team | 5–7 |
| e | HA/DR | Active/passive API and gateway, DB replication guidance, vault behaviour on failover, DR runbook | 5–8 |

Review points: after (a) and (b).

- **Safes:** containers of accounts with per-safe members and permissions (list, use, retrieve,
  manage, approve).
- **Approvals:** dual control and multi-level approval chains, plus a ticket number checked
  against ITSM.
- **Rotation engine:** on a schedule, after check-in (exclusive check-out with forced rotation),
  or on demand. Verify and reconcile out-of-sync passwords. Complexity and age policies per
  platform.
- **Platform drivers:** Linux/Unix (SSH, passwd/chpasswd, SSH keys), Windows (WinRM/SMB), AD
  (LDAPS), Cisco IOS/NX-OS, Juniper, Fortinet, Palo Alto, Huawei, H3C, MikroTik, Oracle,
  MSSQL, PostgreSQL, MySQL, DB2, VMware ESXi/vCenter, AWS/Azure/GCP console users. A plugin
  SDK covers anything with a CLI or web login (the TPC/PMTerminal equivalent).
- **Dependent usages:** Windows services, scheduled tasks, IIS app pools and config files
  updated on rotation.
- **MonetX credential provider API:** MonetX fetches device credentials (SSH, SNMP v2c
  community and v3 auth/priv, API tokens) from WardX at poll time instead of storing them.
  - App authentication: each MonetX instance or collector gets its own app identity (mTLS
    client certificate or a signed short-lived token), bound to a tenant and limited to the
    safes and targets it is allowed to read. No user accounts are used.
  - Every fetch is audited: app identity, target, account, purpose (poll, NCM backup,
    onboarding) and outcome.
  - Short client-side cache with TTL, so a WardX outage doesn't stop polling at once. Values
    are never written to MonetX's database.
  - Rotation is coordinated: MonetX picks up the new credential on its next fetch.
- **High availability:** active/passive vault, a DR replica, distributed vaults for
  multi-site, HSM/KMS behind `Keyring`.

## Phase 2: Privileged Session Manager (MVP)

- **Protocols:** RDP, VNC and web apps through a guacd-based HTML5 gateway (clientless), and
  database proxies (PostgreSQL, MySQL, MSSQL, Oracle).
- **Recording:** full video for RDP and GUI sessions, keystroke and command logs for SSH, a
  searchable index of commands and window titles.
- **Live control:** live monitoring (shadowing), suspend and resume, terminate.
- **Native clients:** SSH with your own client (✅ today), and RDP with your own client via an
  RDP proxy.
- **Command policy:** allow and deny lists (✅ deny today), per platform, safe and role.

## Phase 3: Discovery, onboarding, JIT and Zero Standing Privilege (MVP)

- **Discovery scans:** AD, Windows, Unix, network devices and clouds, for privileged and local
  admin accounts, SSH keys, service accounts and their dependencies.
- **Onboarding:** rule-based automatic onboarding into safes. MonetX device sync
  (`targets.external_ref`).
- **JIT:** time-boxed group membership, with temporary elevation to admin groups.
- **ZSP:** ephemeral SSH certificates and short-lived DB and K8s credentials, with no
  persistent accounts.

## Phase 4: Secrets management (machine identities) (later)

- **Secrets Manager:** a Conjur-style policy-as-code API for apps, CI/CD, containers and
  Kubernetes. Workloads authenticate by identity attributes (K8s service account, AWS IAM role,
  Azure MI, GCP SA, GitHub OIDC).
- **Credential providers:** CP and CCP equivalents, so apps fetch credentials at runtime with
  no hard-coded passwords. SDKs for Python, Java, .NET and Go.
- **Secrets Hub:** governs AWS Secrets Manager, Azure Key Vault and GCP Secret Manager.
- **Integrations:** Jenkins, Ansible, Terraform, Kubernetes (CSI and injector), OpenShift,
  GitHub Actions, Spring.

## Phase 5: Privileged Threat Analytics (later)

- **Behavioural baselining** per privileged user: time, source, target and command patterns.
- **AD attack detection** from DC event logs and traffic: Pass-the-Hash, Golden Ticket,
  Kerberoasting, suspicious DCSync, credential theft.
- **Bypass detection:** unmanaged privileged access that skips the vault (sign-ins to managed
  accounts with no check-out).
- **Risk scoring** per session, with automatic responses: rotate the credential, suspend the
  session, require re-approval.

## Phase 6: Cloud privilege, vendor access and certificates (later)

- **Cloud privilege:** JIT role elevation in AWS, Azure and GCP consoles and CLIs.
- **CIEM:** finds excessive cloud permissions and recommends right-sizing.
- **ZSP for clouds:** cloud VMs, Kubernetes and databases with ephemeral certificates.
- **Vendor privileged access:** VPN-less, agentless portal and time-bound invitations, with
  mobile-app biometric MFA, full recording, and no vendor accounts stored in AD.
- **Machine identity and certificates:**
  - Discovery and inventory of TLS certificates and keys.
  - Issuance, renewal and revocation across CAs (ACME, MS CA, public CAs).
  - Code-signing protection.
  - Readiness for short-lived certificates.

## Phase 7: Endpoint Privilege Manager (native agents) (later)

> **Evaluate first:** reuse AgentX components (agent runtime, enrolment, update channel,
> transport) before building a new endpoint agent. Decide build vs reuse before this phase starts.

- **Agents** for Windows, Linux and macOS, managed from WardX policies.
- **Local admin removal** and least privilege. Application control (allow, deny, restrict) and
  controlled elevation of specific apps. JIT elevation requests with justification.
- **Credential theft protection:** LSASS, browsers and the credential store.
- **Ransomware protection:** blocks unknown processes from encrypting files.
- **Offline devices:** offline-capable policy for loosely connected devices.
- **Account onboarding:** discovered local admin accounts are onboarded automatically.

## Phase 8: Workforce and customer identity, and governance (later)

> **Evaluate first:** integrate with Entra ID and Okta (WardX as a relying party and
> provisioning target, with step-up for privileged actions) instead of building our own SSO
> identity provider. Build only what those platforms don't cover for privileged access.

- **Single sign-on:** WardX as the identity provider (SAML 2.0 and OIDC) to apps.
- **Adaptive MFA:** risk-based step-up, and passwordless (FIDO2/WebAuthn, push).
- **Workforce password management:** business app credentials.
- **Secure web sessions:** records and audits sensitive web app sessions.
- **Customer and B2B identity:** external user portals.
- **Directory and lifecycle:** directory services and joiner/mover/leaver provisioning (SCIM).
- **IGA:**
  - Access certification campaigns and user access reviews.
  - Role and policy management, including SoD rules.
  - Automated provisioning and deprovisioning.
  - Compliance reports: SOX, PCI DSS, ISO 27001, HIPAA, SBP and other central-bank frameworks.

## Platform-wide (built alongside every phase)

- **Admin:** single admin portal and unified audit across modules. Identity security
  intelligence dashboards.
- **SIEM:** syslog (CEF/LEEF), plus Splunk, QRadar, Sentinel and Cortex XSIAM connectors.
- **ITSM:** ServiceNow, Remedy and Jira, so access requires a valid ticket.
- **Automation:** REST API, PowerShell module, Python SDK, Terraform provider.
- **AI layer:** natural-language audit queries and policy recommendations.
- **AI agent identities:** controls for LLM agents that use privileged access.
- **MonetX:**
  - SSO.
  - Device inventory sync.
  - NCM and onboarding fetch device credentials from WardX.
  - PAM alerts into MonetX.
  - Sessions launched from a MonetX device page.
