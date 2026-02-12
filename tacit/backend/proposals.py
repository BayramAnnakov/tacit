"""Proposal CRUD and approval logic."""

import database as db


async def create_proposal(
    rule_text: str,
    category: str = "general",
    confidence: float = 0.8,
    source_excerpt: str = "",
    proposed_by: str = "",
) -> dict:
    """Create a new knowledge rule proposal."""
    return await db.create_proposal(
        rule_text=rule_text,
        category=category,
        confidence=confidence,
        source_excerpt=source_excerpt,
        proposed_by=proposed_by,
    )


async def list_proposals(status: str | None = None) -> list[dict]:
    """List proposals, optionally filtered by status."""
    return await db.list_proposals(status=status)


async def approve_proposal(proposal_id: int, reviewed_by: str = "", feedback: str = "") -> dict | None:
    """Approve a proposal and optionally promote it to a knowledge rule."""
    proposal = await db.get_proposal(proposal_id)
    if not proposal:
        return None

    updated = await db.update_proposal(
        proposal_id=proposal_id,
        status="approved",
        feedback=feedback,
        reviewed_by=reviewed_by,
    )

    # Promote to knowledge rule
    if updated:
        # Get contributor info for consensus trail
        contributions = await db.list_proposal_contributions(proposal_id)
        contributor_names = sorted({c["contributor_name"] for c in contributions})
        contributor_count = len(contributor_names)

        rule = await db.insert_rule(
            rule_text=proposal["rule_text"],
            category=proposal["category"],
            confidence=proposal["confidence"],
            source_type="conversation",
            source_ref=f"proposal:{proposal_id}",
            repo_id=proposal.get("repo_id"),
        )
        if rule.get("id"):
            desc = f"Promoted from proposal #{proposal_id} by {reviewed_by}"
            if contributor_count > 1:
                desc += f" (consensus: {contributor_count} contributors — {', '.join(contributor_names)})"
            await db.add_trail_entry(
                rule_id=rule["id"],
                event_type="approved",
                description=desc,
                source_ref=f"proposal:{proposal_id}",
            )

    return updated


async def reject_proposal(proposal_id: int, reviewed_by: str = "", feedback: str = "") -> dict | None:
    """Reject a proposal with optional feedback."""
    return await db.update_proposal(
        proposal_id=proposal_id,
        status="rejected",
        feedback=feedback,
        reviewed_by=reviewed_by,
    )
