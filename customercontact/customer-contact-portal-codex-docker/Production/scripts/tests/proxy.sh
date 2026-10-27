#!/usr/bin/env bash
# Read-only end-to-end proxy checks; all TLS requests verify the internal CA.
source "$(dirname "$0")/../common.sh"
require_health
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
compose cp proxy:/data/caddy/pki/authorities/local/root.crt "$work/ca.crt" >/dev/null
bind="$(jq -r '.services.proxy.ports[] | select(.target == 443) | .host_ip // "0.0.0.0"' <<< "$configuration")"
[[ "$bind" != 0.0.0.0 ]] || bind=127.0.0.1
curl_args=(--noproxy '*' --silent --show-error --connect-timeout 5 --max-time 15 --cacert "$work/ca.crt" --resolve "$domain:443:$bind")
count=0
check_request() {
  local expected="$1" path="$2"; shift 2
  status="$(curl "${curl_args[@]}" "$@" -D "$work/headers" -o "$work/body" -w '%{http_code}' "https://$domain$path")"
  [[ "$status" == "$expected" ]] || fail "Unexpected response for $path: $status (expected $expected)."
  count=$((count + 1))
}
status="$(curl --noproxy '*' --silent --show-error --max-time 15 --resolve "$domain:80:$bind" -D "$work/headers" -o /dev/null -w '%{http_code}' "http://$domain/health/")"
[[ "$status" == 308 ]] || fail 'HTTP did not redirect to HTTPS.'
grep -qi "^location: https://$domain/health/" "$work/headers" || fail 'Incorrect HTTPS redirect.'
count=$((count + 1))
check_request 200 /health/ --http1.1
grep -q '"status": "ok"' "$work/body" || fail 'Database readiness failed.'
grep -qi '^strict-transport-security:' "$work/headers" || fail 'HSTS header missing.'
protocol="$(curl "${curl_args[@]}" --http2 -o "$work/body" -w '%{http_version}' "https://$domain/health/")"
[[ "$protocol" == 2 ]] || fail 'HTTP/2 was not negotiated; ensure curl has HTTP2 support.'
count=$((count + 1))
check_request 401 /api/v1/customers/ --http2
check_request 302 /customers/ --http2
check_request 200 /accounts/login/ --http2
check_request 200 /static/css/portal.css --http2
# Exercise Range handling in the patched HTTP stack without large requests.
check_request 206 /static/css/portal.css --http2 -H 'Range: bytes=0-15'
[[ "$(wc -c < "$work/body")" == 16 ]] || fail 'Range response length is wrong.'
check_request 416 /static/css/portal.css --http2 -H 'Range: bytes=999999999-'
# Oversize normal login input must be rejected, without accepting or saving it.
curl "${curl_args[@]}" --fail -c "$work/cookies" -o /dev/null "https://$domain/accounts/login/"
csrf="$(awk '$6 == "csrftoken" {print $7}' "$work/cookies")"
[[ -n "$csrf" ]] || fail 'Login did not issue its CSRF cookie.'
head -c 6100000 /dev/zero | tr '\0' x > "$work/oversize"
status="$(curl "${curl_args[@]}" --http2 -b "$work/cookies" -H "Referer: https://$domain/accounts/login/" -H "X-CSRFToken: $csrf" -H 'Content-Type: application/x-www-form-urlencoded' --data-binary "@$work/oversize" -o /dev/null -w '%{http_code}' "https://$domain/accounts/login/")"
[[ "$status" == 400 || "$status" == 413 ]] || fail "Oversize form not rejected: $status."
count=$((count + 1))
echo "Proxy HTTPS/HTTP2 checks: $count passed, 0 failed."
