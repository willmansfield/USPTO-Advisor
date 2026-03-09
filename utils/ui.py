"""Shared UI helpers used across multiple pages."""


def score_badge(score, band: str, color: str, size: str = "large") -> str:
    """Return an HTML difficulty badge. size='large' for full pages, 'small' for inline cards."""
    if size == "small":
        padding, font = "4px 14px", "1rem"
    else:
        padding, font = "6px 18px", "1.2rem"
    score_str = f"{score}/100" if score is not None else "—"
    return (
        f'<span style="background:{color};color:white;padding:{padding};'
        f'border-radius:24px;font-weight:700;font-size:{font};">'
        f"{band} &nbsp; {score_str}</span>"
    )
