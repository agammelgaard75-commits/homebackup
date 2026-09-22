# The Four Software Flows

All four flows participate in the same change. They share global health gates, the ignore policy, the action journal, and final verification. Discovery never enables updates. Each target registration is root-owned, rejects unknown fields, and is included in the plan's policy fingerprint.

## Common registration

A registration contains a stable target ID, one owner flow, a code-owned handler ID, enabled/held state with reason, approved artifact origin and installation root, version-comparison rule, exact existing service name if applicable, restart permission, readiness check ID and parameters, backup scope, size limit, and explicitly excluded migration behavior. Paths must be absolute, confined to the target's registered roots, and checked for unexpected symlinks/ownership. Service checks use fixed handlers, never arbitrary configured shell commands.

Manual and pip registration includes a separately reviewed one-time conversion to versioned releases and a stable `current` link if the application does not already use that layout. It does not silently rewrite existing service units. Registration can authorize rebuilding the same existing distribution set in a new venv, but does not authorize installing new products or dependencies onto the host. An empty registration set is valid and yields `NO_TARGET`.

Each routine update must stay within a recognized release series and must not downgrade. APT retains its existing conservative Debian-version classifier. Manual/Docker use the existing strict numeric release rules. pip uses PEP 440 parsing via a pinned `packaging` dependency, permits stable releases only, and rejects epoch or major changes, development/prerelease versions, unknown versions, and changed interpreter requirements that the registered interpreter cannot satisfy. Unclassifiable transitions are deferred.

## APT

**Scope:** Existing dpkg-managed packages, including normal security updates, under the inherited refusal rules. APT owns dpkg-managed copies of products even when another collector can identify their vendor metadata.

Preparation inventories installed versions, runs a read-only upgrade simulation against the available local metadata, captures metadata age, applies ignore and version policy, and creates an indicative candidate summary. Its approval authorizes a bounded safe transaction, not an immutable list of preparation-time versions. This preserves the monolith's behavior and permits newly available safe updates after metadata refresh.

The APT flow selects refresh plus bounded upgrade evaluation even when its indicative package list is empty. Its preparation assessment is therefore still required: an empty old package index is not permission to skip AI and install newly discovered updates later. A no-update maintenance result records the successful refresh and skipped installation separately.

At maintenance:

1. Validate the prepared authorization, current policy fingerprint, host health, and absence of an interrupted framework change.
2. Commit RUNNING before the executor's `apt.refresh` action. Refresh is a mutation of the package metadata cache and is never performed by a read-only collector.
3. Run the existing refreshed simulation and exact-version simulation. Reject removals, new installations/dependencies, downgrades, ignored-package changes, major/epoch/unclassified upgrades, package/vendor version conflicts, or any difference between the exact simulated and intended transaction.
4. Commit the exact package names, before/after versions, simulation evidence, and execution digest to the execution manifest. Do not modify the preparation plan.
5. Execute the exact pinned upgrade using the existing `--no-remove` and `--only-upgrade` protections. An empty transaction is a recorded no-op.
6. Verify installed versions, unexpected package additions/removals/changes, `dpkg --audit`, failed services, storage, and reboot-required state.

If refreshed candidates violate policy, fail the combined change without installing packages. The metadata refresh is still recorded as an executed action. No autonomous package removal, new package install, release upgrade, reboot, or forced dpkg-lock removal is permitted. Normal package maintainer-script restarts remain subject to the existing restart policy.

Other package managers and administrators do not honor the controller's private lifecycle lock. Respect APT/dpkg locks, fail on contention, and revalidate the exact transaction. Report any observed external change; do not claim the controller serializes unrelated host activity.

**Reuse:** `upgrade_candidates`, `Controller.approved_upgrade`, APT inventory and direction checks, plus existing package tests. Extend verification to reject every unexplained package delta, not merely missing expected versions.

## Docker / Compose

**Scope:** Existing explicitly registered, single-replica Compose services. Preserve hold rules, version labels, pinned image digests, platform matching, backup limits, and configured health/readiness checks.

Preparation reads the current container/image identity, runtime and Compose fingerprints, writable mounts, platform, version labels, and candidate registry metadata. Pin the exact approved image digest and version evidence. No image pull into the live daemon occurs during preparation or shadowing.

Execution reuses the existing single-service handler:

1. Validate the prepared policy, current container identity, Compose configuration, mounts, and version rules.
2. Pull the pinned image through the executor; verify its digest, platform and labels.
3. Revalidate drift and check the original service is healthy.
4. Stop the configured service, create its stopped-data backup, read back/checksum the backup, and preserve the old image/configuration references.
5. Replace only that service, preserving its approved mounts and configuration.
6. Require the expected image plus readiness/health and stability checks before another action starts.

Reject shared writable data, unsupported replicas/builds, unclassified version jumps, configuration drift, absent readiness checks, or insufficient backup space. If backup fails before replacement, retain the existing deterministic attempt to restart and verify the original service. Once replacement has occurred, preserve evidence and backups for operator recovery; do not automatically downgrade an image or database.

**Activation:** Import currently configured services as held registrations. The dedicated Docker canary enables only verified eligible entries. Do not infer deployed services from commented examples in repository configuration.

## Manually installed software

**Scope:** Discover `/opt`, `/usr/local`, configured vendor locations, Snap and system Flatpak metadata, and registered manual products. Snap/Flatpak and unregistered products remain report-only. Splunk, LiteLLM, the model runtime, the sysadmin controller, arbitrary installation scripts, and products requiring database/license/configuration migrations remain report-only in this migration.

Implement the `manual.versioned_release` handler for registered relocatable vendor archives or binaries. Supported applications must keep mutable data outside the release directory and provide a deterministic version/readiness check. For a service application, its existing approved service unit must already invoke the registered `current` path and have restart permission.

Preparation obtains vendor release metadata from the registered source, applies its strict version rule, and records the exact version, artifact URL, platform, size and SHA-256. Authenticity requires either a verified vendor signature under a registered key or an operator-reviewed checksum manifest provisioned independently of the artifact download. A checksum downloaded beside an untrusted artifact is insufficient. Where trusted metadata is unavailable, report `DEFERRED`.

Execution downloads the exact artifact into executor-owned scratch space, verifies it, and stages it under `<registered-root>/releases/<version>-<digest-prefix>`. Archive extraction rejects path traversal, absolute paths, device files, hardlinks, unsafe symlinks, setuid/setgid bits, excessive file count, and expansion beyond the registered quota. Never execute a vendor installer or archive hook. Validate the staged release as an unprivileged worker before root finalizes approved ownership/modes.

After durable action intent and pre-switch evidence, atomically replace the registered `current` link on the same filesystem and restart only the registered service when applicable. Verify resolved release identity, exact version, readiness and unchanged mutable data/configuration expectations. Retain the prior release. An installation without the registered layout is deferred until a separate onboarding change establishes it.

Failures stop later mutations. Reactivating a prior release is an explicit operator recovery action, not an automatic downgrade; verify data compatibility first. An application with possible schema migrations is ineligible for this handler.

## Python pip applications

**Scope:** Registered application virtual environments. Inventory unregistered environments and system Python metadata for reporting only. Never use global `pip install`, `--user`, `--break-system-packages`, editable/VCS installs, source distributions, source builds, or arbitrary setup hooks.

Use the registered absolute interpreter and environment paths. Metadata inspection does not import installed application modules. Candidate resolution runs in restricted scratch space with wheels only and a single registered index/origin; do not mix public and private indexes implicitly. Capture a complete exact lock manifest with wheel SHA-256 hashes, names, versions, platform/interpreter compatibility, and provenance. Bootstrap tooling is a separately pinned part of the environment recipe and cannot float to latest.

The selected distribution-name set, including transitive dependencies, must equal the current registered set. Any new or removed distribution, unsafe version transition, unsupported wheel, or unsatisfied dependency is deferred before action selection. A registered application may upgrade the same set into a new environment; package additions need a separate reviewed application change.

Create the environment at its final versioned path, such as `<registered-root>/releases/<manifest-digest>/venv`, using the same registered interpreter. Do not create it elsewhere and move it: virtual environments contain location-dependent paths, as explained by the [Python venv documentation](https://docs.python.org/3/library/venv.html).

Install only the prepared wheel set from an offline wheelhouse with `--no-index`, `--require-hashes`, `--only-binary=:all:`, and `--no-deps`; all dependencies are explicitly present in the complete manifest. Validate exact metadata and `pip check`, then run a code-owned application smoke check as the existing application user with restricted filesystem/network access. [pip's secure-install guidance](https://pip.pypa.io/en/stable/topics/secure-installs/) documents hash checking, complete pinning, and excluding source distributions.

Atomically activate the prepared release through the pre-registered `current` link and restart only its approved service. Verify exact environment identity, distribution set, dependency consistency, interpreter identity and service readiness. Retain the old environment without modifying it. APT's earlier interpreter patch update is rechecked before staging; a changed interpreter major/minor or incompatible ABI blocks the action.

Respect the [externally managed environment specification](https://packaging.python.org/en/latest/specifications/externally-managed-environments/): the pip flow never overrides the distribution-managed Python environment. The controller's own environment and the gateway are held outside routine pip maintenance.

## Combined closure

The record has a section for each flow: observed state, selected actions, executed actions, verified deltas, deferrals, and remaining attention. If APT succeeds and Docker fails, the combined change is FAILED; manual and pip actions are recorded as not executed due to the earlier failure. Successfully applied APT work remains in history and is not blindly repeated in a successor.

A subsequent approved retry re-inspects actual state and builds a new plan with a parent change reference. It cannot reopen the old change or replay its action list. No rollback is represented as complete until its actual state has been verified.
