"""Client-requested answer-source preference for one query run.

Requested scope is a source preference, not authorization. It cannot select
document IDs, ACL predicates, route families, budgets, or tools.
"""

from __future__ import annotations

from enum import StrEnum


class RequestedSearchScope(StrEnum):
    """Client source preference fixed at admission.

    Values:
        AUTO: Existing server classifier decides company versus general.
        COMPANY_DOCUMENTS: Force company retrieval for substantive prompts.
        GENERAL_KNOWLEDGE: Forbid company retrieval and company claims.
    """

    AUTO = "auto"
    COMPANY_DOCUMENTS = "company_documents"
    GENERAL_KNOWLEDGE = "general_knowledge"
