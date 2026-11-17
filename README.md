# UB Skeleton

This repository contains the shared Python runner, module loader, and worker image. Module source is maintained separately in the sibling `modules` repository.

`default-modules.json` pins the default packages that the Termux bootstrap installs from the modules repository. The server has its own allowlist and installs modules per tenant.

The runner loads installed module packages from `ub/modules`. Termux installations keep that directory under the user's local UB checkout. Server workers mount a per-user module directory at the same path.

Runtime data and locally installed modules are ignored by Git. They may contain Telegram sessions, module tokens, settings, and databases; do not commit them.

For a local Python run, place this repository in a directory named `ub` and run `python -m ub` from its parent after installing the required modules. The Dockerfile packages the core runtime and dependencies only; tenant modules are supplied by mounts.
