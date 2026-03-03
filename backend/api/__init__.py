"""backend.api — Split from the monolithic dashboard.py.

Re-exports all public functions so existing `from dashboard import X` patterns
continue to work via the thin shim at backend/dashboard.py.
"""

# __all__ needed because `from api import *` skips underscore-prefixed names
__all__ = [
    # _common
    "PROJECT_ROOT", "DB_PATH", "VECTOR_PATH", "OUT_PATH", "MOSAIC_DIR",
    "RENDERED_DIR", "JOURNAL_PATH", "GENERATED_DIR", "human_bytes", "pct",
    # stats
    "get_stats",
    # vectors
    "_get_lance", "similarity_search", "drift_search",
    # content
    "get_journal_html", "get_instructions_html", "get_mosaics_data",
    # cartoons
    "get_cartoon_data", "get_gemma_cartoon_data", "get_all_cartoon_data", "review_cartoon",
    # gemma
    "get_gemma_data", "get_gemma_progress",
    # qwen
    "get_qwen_data",
    # inspectors
    "generate_signal_inspector_data", "get_signal_inspector_picks_data",
    "generate_embedding_audit_data", "generate_collection_coverage_data", "generate_schema_data",
    # generated
    "get_generated_data", "review_generated", "get_variant_review_data", "batch_reject_variants",
    "get_unpicked_data", "get_location_tagger_data",
    "do_pick", "tag_location", "untag_location", "register_location",
    "get_show_photography", "get_show_variants",
    # pages
    "PAGE_HTML", "page_shell", "serve", "generate_static", "_static_links",
    "render_readme", "render_instructions", "render_mosaics", "render_journal",
    "render_drift", "render_creative_drift", "render_blind_test", "Handler",
]

from .stats import get_stats  # noqa: F401
from .vectors import _get_lance, similarity_search, drift_search  # noqa: F401
from .content import get_journal_html, get_instructions_html, get_mosaics_data  # noqa: F401
from .cartoons import (  # noqa: F401
    get_cartoon_data, get_gemma_cartoon_data,
    get_all_cartoon_data, review_cartoon,
)
from .gemma import get_gemma_data, get_gemma_progress  # noqa: F401
from .qwen import get_qwen_data  # noqa: F401
from .inspectors import (  # noqa: F401
    generate_signal_inspector_data,
    get_signal_inspector_picks_data,
    generate_embedding_audit_data,
    generate_collection_coverage_data,
    generate_schema_data,
)
from .generated import (  # noqa: F401
    get_generated_data, review_generated, get_variant_review_data, batch_reject_variants,
    get_unpicked_data, get_location_tagger_data,
    do_pick, tag_location, untag_location, register_location,
    get_show_photography, get_show_variants,
)
from .pages import (  # noqa: F401
    PAGE_HTML, page_shell, serve, generate_static, _static_links,
    render_readme, render_instructions, render_mosaics, render_journal,
    render_drift, render_creative_drift, render_blind_test,
    Handler,
)
from ._common import (  # noqa: F401
    PROJECT_ROOT, DB_PATH, VECTOR_PATH, OUT_PATH, MOSAIC_DIR,
    RENDERED_DIR, JOURNAL_PATH, GENERATED_DIR,
    human_bytes, pct,
)
