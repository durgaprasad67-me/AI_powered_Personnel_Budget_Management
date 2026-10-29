"""
Constants for file imports in FinSight AI.
"""

# Maximum uploaded file size: 5 MB
MAX_FILE_SIZE = 5 * 1024 * 1024

# Maximum number of transactions allowed per import
MAX_ROWS = 500

# Supported file extensions
ALLOWED_EXTENSIONS = frozenset({
    ".pdf",
    ".docx",
    ".txt",
    ".csv",
    ".xlsx",
    ".xls",
})

# Human-readable list of supported formats
SUPPORTED_FORMATS = "PDF, DOCX, TXT, CSV, XLSX, XLS"

# Maximum number of validation errors returned to the client
MAX_VALIDATION_ERRORS = 100