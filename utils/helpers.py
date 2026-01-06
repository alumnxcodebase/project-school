def serialize(doc):
    """Converts MongoDB _id to string 'id'."""
    if not doc: return None
    doc["id"] = str(doc.pop("_id"))
    return doc