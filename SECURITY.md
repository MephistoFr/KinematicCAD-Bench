# Security boundaries

Generated CAD scripts are executable untrusted Python. The default runner requires Docker and
does not silently fall back to local execution. `--unsafe-local` is a deliberate development
escape hatch for code you trust; its results are excluded from official ranking.

Candidate and judge run in separate containers. Both have no network, no Linux capabilities,
read-only roots, limited memory/CPU/PIDs, bounded writable tmpfs and timeouts. Only bounded STEP
files and JSON cross the boundary. The host rejects archive traversal, links, compression,
duplicate names, special files and unexpected candidate output types.

Native CAD parsing itself processes adversarial inputs and therefore runs in the judge container.
A hostile public deployment should put worker containers inside disposable VMs and use a
reviewed host patching and image-pinning policy. Docker isolation is not a mathematical security
proof. The host-side inference command adapter is trusted executable configuration.

Do not put API keys in provider JSON or source files. Use the named environment variable option.
Do not publish credentials, private tasks or sensitive model responses with evaluation artifacts.

Report security problems privately to the repository maintainers through the hosting platform's
private vulnerability reporting facility when this repository is published. Include a minimal
reproducer and affected protocol/image versions. This initial source distribution does not
claim an existing disclosure email, public repository URL or completed penetration audit.

