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
    days-valid=825 key-usage=digital-signature,key-encipherment,key-cert-sign,tls-server
/certificate sign wardx-api
```

RouterOS 7.25 refuses to self-sign (`CA not found`) unless `key-usage` includes
`key-cert-sign`.

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

1. Add the target: platform **MikroTik RouterOS**, protocol SSH, port 22. Set **API-SSL
   port** if it is not 8729. Leave **API is TLS** on; switch it off only for a device that
   offers nothing but the cleartext API, which WardX then vaults but never rotates
   ("non-rotatable (cleartext API)").
2. On the target, open **Host key**. Compare the SSH host-key fingerprint shown with the device,
   and accept it only if it matches.
3. In the same dialog, the **API-SSL certificate** section shows the SHA-256 fingerprint the
   device presents on API-SSL (read during the TLS handshake; nothing is sent), with its
   subject and expiry. Compare it with the `fingerprint` from step 1 (RouterOS prints it in
   lower case without colons; WardX shows `AA:BB:…`, the same value), tick that it matches and
   accept. WardX pins it only if the device still presents exactly that certificate. Until
   both identities are pinned, rotation and verify are refused with "learn the device
   identity first". (API: `POST /targets/{id}/tls-cert/probe`, then `/tls-cert/accept` with
   the fingerprint.)
4. Allow rotation on the target, add the accounts, and set the safe's rotation policy.
5. Start with **Verify** (or a dry run) before the first real rotation.

If either identity changes later, rotation and verify stop with a high alert until an
administrator compares and accepts the new fingerprint. WardX never accepts it automatically,
and clearing a pin (**reset**) does not clear a recorded mismatch. If API-SSL is switched off
on the device, rotation stops as "needs attention" with "API-SSL not enabled on device";
verify then falls back to one SSH login. Each job step shows the channel it used.
