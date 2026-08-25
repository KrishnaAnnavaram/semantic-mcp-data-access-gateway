"""Stable cache-contract versions, changed only for material behavior changes."""

DOMAIN_RETRIEVAL_PROMPT_VERSION = "retrieval-2026-08-25.1"
DOMAIN_DERIVE_PROMPT_VERSION = "derive-2026-08-25.1"
DOMAIN_REVISE_PROMPT_VERSION = "revise-2026-08-25.1"
DOMAIN_VALIDATE_PROMPT_VERSION = "validate-2026-08-25.1"
MCP_CATALOGUE_VERSION = "catalogue-2026-08-25.1"
MCP_ASSESS_PROMPT_VERSION = "assess-2026-08-25.1"
MCP_CHOICES_VERSION = "choices-2026-08-25.1"

DOMAIN_REQUIREMENT_SCHEMA_VERSION = "requirement-v2"
DOMAIN_RETRIEVAL_SCHEMA_VERSION = "knowledge-chunks-v2"
DOMAIN_VALIDATION_SCHEMA_VERSION = "result-validation-v1"
MCP_CATALOGUE_SCHEMA_VERSION = "tool-catalogue-v2"
MCP_ASSESS_SCHEMA_VERSION = "serve-response-v1"
MCP_CHOICES_SCHEMA_VERSION = "choices-v1"

# A catalogue is cached before its own content fingerprint is known. This
# version identifies the deterministic construction logic; the resulting
# catalogue fingerprint then invalidates every downstream assessment.
MCP_CAPABILITY_LOGIC_VERSION = "mcp-capabilities-2026-08-25.1"

# Changing the analytical-signature parser changes semantic-cache eligibility.
SEMANTIC_POLICY_VERSION = "semantic-safety-v1"
CACHE_ENVELOPE_SCHEMA_VERSION = "cache-envelope-v1"
