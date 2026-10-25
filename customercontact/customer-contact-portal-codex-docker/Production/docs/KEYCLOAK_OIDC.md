# Keycloak OIDC integration

The portal supports `AUTH_MODE=local` (the default) and `AUTH_MODE=oidc`. OIDC is
an opt-in deployment change. The implementation uses `mozilla-django-oidc` 5.0.2
for authorization code flow, PKCE, state/nonce, callback and Django sessions;
its DRF bearer parser is combined with PyJWT signature, issuer, audience,
expiry and access-token-type validation. No Keycloak container is added.

## Realm and portal client

1. Create a Keycloak realm reachable by **the browser and app container at the
   same HTTPS issuer URL**. Use a certificate trusted by both. The issuer must
   exactly match the token `iss` and discovery metadata. The app reads
   `<issuer>/.well-known/openid-configuration`; authorization, token, userinfo,
   JWKS and logout endpoints must share the issuer's HTTPS host.
2. Create a confidential OIDC client, e.g. `customer-portal`. Enable Standard
   Flow (authorization code), client authentication and S256 PKCE. Disable
   Direct Access Grants and public registration unless managed separately by
   your organization. The client secret belongs only in private `.env`.
3. Register `https://<PORTAL_DOMAIN>/oidc/callback/` as an exact valid redirect
   URI and `https://<PORTAL_DOMAIN>/accounts/logged-out/` as a valid
   post-logout redirect URI. The portal uses Caddy's `X-Forwarded-Proto` to
   construct HTTPS redirects. If `OIDC_REDIRECT_URI` is set, it must exactly
   equal the constructed callback URL.
4. Create **client roles on this portal client** named `portal-viewer`,
   `portal-editor`, `portal-admin`. Assign one or more directly to users or
   through Keycloak groups. The highest of the three applies. Generic realm
   administrator roles have no portal effect. A user with none receives 403.
5. Ensure the Keycloak **client roles** protocol mapper places these roles in
   the access token at `resource_access.<OIDC_CLIENT_ID>.roles`. Configure an
   Audience mapper so access tokens contain `OIDC_API_AUDIENCE` in `aud`.
   Browser login access tokens need that audience too. The ID token must have
   the portal client ID in `aud`, and Keycloak must emit `typ=Bearer` in access
   token claims. Verify these claims using a nonproduction account before
   enabling OIDC. Do not put portal roles solely in realm roles.
6. Set access-token lifetime to at most five minutes. The portal expires its
   interactive authorization after five minutes and rejects access tokens
   older than five minutes, even if Keycloak gave them a longer expiry; users
   must reauthenticate.
   Role removal, deactivation and service-account changes take effect at the
   next login or token expiry, within this configured interval. Keycloak SSO
   can make a fresh login seamless while applying current roles.

## Configuration and Docker

Copy these examples into the **private** `.env` on an authorized test stack.
Keep its permissions at `0600`. No values below are real secrets:

```dotenv
AUTH_MODE=local
OIDC_ISSUER_URL=https://keycloak.example.internal/realms/customer-portal
OIDC_CLIENT_ID=customer-portal
OIDC_CLIENT_SECRET=REPLACE_WITH_PRIVATE_VALUE
OIDC_API_AUDIENCE=customer-portal
OIDC_REDIRECT_URI=https://portal.example.internal/oidc/callback/
```

`OIDC_REDIRECT_URI` is optional and serves as an exact mismatch check. The
library derives the callback from the incoming HTTPS request. `AUTH_MODE=oidc`
requires issuer, client ID and secret; local mode does not contact Keycloak.
No password or token belongs in Git. `OIDC_ROLE_CLAIM_CONFIGURATION` is not
needed: client roles use the fixed standard Keycloak claim above.

The app container has outbound access through the existing `edge` network;
its port remains private. Ensure container DNS and routing can reach Keycloak.
For a private CA, add the trusted CA to the app image/OS trust store and set
`REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE` to its in-container path if needed.
Never disable TLS verification. Browser devices must independently trust the
Keycloak and portal CAs. Do not use a loopback-only issuer unless the app
container can reach the same hostname. SSH tunnel development is possible
when the portal's external hostname, TLS certificate, issuer and container
routing all agree; do not mix internal and external issuer URLs.

On an authorized nonproduction stack, apply the additive `accounts.0003`
migration and run `setup_roles`, configure Keycloak, verify discovery and a
browser login, then set `AUTH_MODE=oidc` and recreate **only** the app container
through the normal backup-first update process. Keep `AUTH_MODE=local` until
these checks succeed. Do not change a running production deployment as part
of development. No containers, volumes, database rows or local credentials
are removed by the migration.

## Browser sessions and logout

Unauthenticated browser requests go through `/accounts/login/` to Keycloak.
Keycloak handles MFA. The portal stores neither access nor ID tokens in the
session, and never renders them in HTML. The session stores only its OIDC
verification time and library state/nonce during login. Once the verification
is older than five minutes, the portal drops the session so fresh Keycloak
roles and account state are evaluated. Session-authenticated writes keep
Django CSRF protection.

Sign out with the portal's POST form. The library ends the Django session and
redirects to Keycloak's discovered end-session endpoint, then to
`/accounts/logged-out/`. Without an ID-token hint, Keycloak may show a logout
confirmation; this depends on realm settings. If Keycloak is unavailable,
the Django session still ends, but the upstream SSO session may remain. Close
the browser or sign out of Keycloak separately in that case.

## Existing account migration

The stable identity is `(iss, sub)`, never email or username. A first-time
Keycloak user with a portal role gets a new local account with an unusable
password. Existing customers, contacts and audit attributions remain attached
to their current users. To reuse a particular local account and its audit
identity, an operator must review the local username and Keycloak immutable
subject, then run inside Docker:

```bash
docker compose run --rm --no-deps app python manage.py link_oidc_user \
  LOCAL_USERNAME https://keycloak.example.internal/realms/customer-portal \
  REVIEWED_KEYCLOAK_SUBJECT
# After checking the dry-run result and taking a database backup:
docker compose run --rm --no-deps app python manage.py link_oidc_user \
  LOCAL_USERNAME https://keycloak.example.internal/realms/customer-portal \
  REVIEWED_KEYCLOAK_SUBJECT --apply
```

The command rejects inactive users, superusers and duplicate links. Do not
link by email alone. During OIDC login, that account's groups become exactly
its verified portal role and direct permissions are cleared. Review custom
permissions before linking. Existing local password login is disabled in
OIDC mode, including Django Administration. The legacy `ccp_` API credential
authenticator and issuance endpoints are disabled in OIDC mode; stored
credentials remain intact for a controlled revert.

OIDC-managed users' portal groups are not editable through Django
Administration in OIDC mode; assign roles in Keycloak. The portal can still
deactivate a linked local account to deny it immediately. Adding local
password accounts is disabled in OIDC-mode Administration.

## REST API and n8n service accounts

Use the issuer's token endpoint shown in discovery. Give an automation client
Client Authentication and Service Accounts, disable interactive flows when
unneeded, and assign only the portal client roles needed (normally
`portal-viewer`). Add the portal API audience to its access token. A generic
Keycloak admin role does not grant portal administrator access. Never place
bearer tokens in URLs, logs, workflow output or source control.

```bash
TOKEN="$(curl --fail --silent --show-error \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode 'client_id=portal-automation' \
  --data-urlencode 'client_secret=YOUR_PRIVATE_SECRET' \
  'https://keycloak.example.internal/realms/customer-portal/protocol/openid-connect/token' \
  | jq -r '.access_token')"
curl --fail --silent --show-error \
  --header "Authorization: Bearer ${TOKEN}" \
  'https://portal.example.internal/api/v1/customers/?page_size=25'
unset TOKEN
```

The API accepts only signed, unexpired RS256 **access** tokens with the exact
issuer, required audience, `typ=Bearer`, subject and a recognized portal
client role. ID tokens, wrong-issuer/audience tokens, malformed tokens and
expired tokens return 401. Valid tokens without a portal role return 403.
Roles then flow through the existing Viewer, Editor and Administrator checks
for every endpoint. Session API calls still require CSRF on writes. There is
no unrestricted CORS. See [REST API](REST_API.md) for endpoint details.

## Troubleshooting and controlled revert

- `503` at login initiation: verify container DNS/routing, discovery URL,
  HTTPS certificate trust, issuer equality and endpoint host consistency.
- Redirect URI error in Keycloak: compare the exact HTTPS callback above,
  Caddy's forwarded scheme, `PORTAL_DOMAIN` and optional `OIDC_REDIRECT_URI`.
- `401` API: check that the token is an access token, not an ID token; inspect
  `iss`, `aud`, `typ`, `exp`, signature key and trusted CA. Never log the token.
- `403` API/browser: assign the three client roles on the portal client and
  ensure the client-role mapper includes them in the access token. Realm admin
  roles and `is_staff` do not substitute.
- SSO logout may need Keycloak confirmation; local session expiry still works.

To revert during a controlled migration, take/verify a database backup,
set `AUTH_MODE=local`, and recreate only the app through the approved update
procedure. Previously linked local users retain their records; their local
passwords and groups should be reviewed before local access is restored.
Stored `ccp_` credentials become usable again in local mode, so review/revoke
them before reverting. Do not delete OIDC identity rows or Docker volumes.
