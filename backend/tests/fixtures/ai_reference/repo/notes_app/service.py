"""Application service tying authentication, storage and caching together."""

from notes_app import auth, cache
from notes_app.storage import NoteStore


class NotesService:
    """Use cases the HTTP layer calls."""

    def __init__(self, store=None):
        self.store = store or NoteStore()

    def login(self, password, stored_hash, user_id):
        if not auth.verify_password(password, stored_hash):
            return None
        return auth.start_session(user_id)

    def add_note(self, token, body):
        user = auth.current_user(token)
        if user is None:
            raise PermissionError("not signed in")
        note_id = self.store.add(user, body)
        cache.purge()
        return note_id

    def render_notes(self, token):
        user = auth.current_user(token)
        if user is None:
            raise PermissionError("not signed in")
        cached = cache.recall(user)
        if cached is not None:
            return cached
        text = "\n".join(self.store.list_for(user))
        cache.remember(user, text)
        return text
