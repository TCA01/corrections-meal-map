from __future__ import annotations

from collector.catalog import CatalogStore
from collector.models import Post
from institutions.master import InstitutionMaster

from .document_roles import classify_document_role


def migrate_current_catalog(store: CatalogStore, master: InstitutionMaster) -> tuple[int, list[str]]:
    posts = store.load()
    changed, unresolved = enrich_posts(posts, master)
    if changed:
        store.commit(posts, existing_posts=[])
    return changed, unresolved


def enrich_posts(posts: list[Post], master: InstitutionMaster) -> tuple[int, list[str]]:
    changed = 0
    unresolved: list[str] = []
    for post in posts:
        resolution = master.resolve_post(post.institution_name, post.title)
        if resolution.institution_id:
            if post.institution_id != resolution.institution_id:
                post.institution_id = resolution.institution_id
                changed += 1
        else:
            unresolved.append(post.institution_name)
        sibling_filenames = [item.original_filename for item in post.attachments]
        for item in post.attachments:
            role = classify_document_role(item.original_filename, post.title, sibling_filenames)
            if (item.document_role, item.role_confidence, item.role_rule) != (role.role, role.confidence, role.rule):
                item.document_role = role.role
                item.role_confidence = role.confidence
                item.role_rule = role.rule
                changed += 1
    return changed, sorted(set(unresolved))

