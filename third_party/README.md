# third_party

Vendored external dependencies.

We pin specific snapshots of dependencies here when (a) we need to ensure
reproducible builds across machines, (b) the upstream API is unstable, or
(c) we need to apply local patches.

Anything in this directory is excluded from .gitignore patterns; everything
else under third_party is ignored. Add a subdirectory per dependency with
a README explaining the source URL, version, and any local modifications.

Currently empty.
