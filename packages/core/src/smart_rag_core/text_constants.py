"""Import-free text constants shared by the parser sandbox and answers.

The no-network parser image does not install answer-generation
dependencies such as ``tiktoken``. Importing ``query_answer`` from the
parser loads that package and fails the sandbox before a file is read.
Keep the paragraph separator here so PDF reflow and citation binding use
the same bytes.
"""

from __future__ import annotations

PARAGRAPH_DELIMITER = "\n\n"
