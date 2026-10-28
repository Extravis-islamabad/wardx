# Onboarding a MikroTik (RouterOS) device for password rotation

WardX changes MikroTik passwords **only over API-SSL** (TLS, port 8729) with a pinned
certificate. SSH is used only to verify a login. A device without API-SSL can still be
vaulted, but rotation stops as "needs attention" with the reason "API-SSL not enabled on
device", and WardX never falls back to changing it over SSH. The plain API (8728) and Telnet
are cleartext, so rotation over them is always refused. Background: `ROTATION.md`.

Run the RouterOS steps on the device console or over an existing trusted session, not over the
network path you are about to trust. Commands are for RouterOS 7; check them on your version in
a lab first.

## 1. Certificate for API-SSL

**Option A: a certificate issued by your CA** (preferred where you have one):

```
/certificate import file-name=router1.crt passphrase=""
/certificate import file-name=router1.key passphrase="<key passphrase>"
```

**Option B: self-signed on the device** (trust comes from the fingerprint you pin in WardX):

```
/certificate add name=wardx-api common-name=router1.example.net key-size=2048 \
    days-valid=825 key-usage=digital-signature,key-encipherment,tls-server
/certificate sign wardx-api
```

Read the certificate's SHA-256 fingerprint on the device; you compare it in step 4:

```
/certificate print detail where name=wardx-api
```

## 2. Enable API-SSL; disable cleartext services

```
/ip service set api-ssl certificate=wardx-api disabled=no address=<WardX address>/32
/ip service set api disabled=yes
/ip service set telnet disabled=yes
```

Restricting `address` to the WardX hosts is strongly recommended.

## 3. Accounts

- **Accounts WardX rotates themselves** need the `api` policy (to log in over API-SSL) and the
  `password` policy (to change their own password), plus `ssh` for verify logins.
- **A reconcile account** (to reset another account's password) needs `api`, `read`, `write`
  and `policy`. Keep it in a separate WardX safe.
- Never leave an account with an **empty password**. RouterOS accepts any SSH password for
  such an account, and WardX flags it as high risk when it detects one over the API.

## 4. In WardX

1. Add the target: platform **MikroTik RouterOS**, protocol SSH, port 22.
2. On the target, open **Host key**. Compare the SSH host-key fingerprint shown with the device,
   and accept it only if it matches.
3. Pin the **API-SSL certificate** fingerprint the same way, comparing it with step 1. This
   step arrives with the MikroTik driver; until both identities are pinned, rotation is
   refused with "learn the device identity first".
4. Allow rotation on the target, add the accounts, and set the safe's rotation policy.
5. Start with **Verify** (or a dry run) before the first real rotation.

If either identity changes later, rotation and verify stop with a high alert until an
administrator compares and accepts the new fingerprint. WardX never accepts it automatically.
