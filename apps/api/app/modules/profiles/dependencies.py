from app.modules.profiles.privacy import PublicProfileRead
from app.modules.profiles.service import ProfileService


def port(app, name, db):
    factory = getattr(app.state, f"{name}_factory", None)
    return factory(db) if factory else None


def make_profile_service(app, db):
    return ProfileService(db, port(app, "assessment_read", db), port(app, "fsp_read", db))


def make_public_read(app, db):
    return PublicProfileRead(db, port(app, "assessment_read", db))


def configure_d(app):
    from app.modules.invitations.service import ContactService

    app.state.profile_read_factory = lambda db: make_public_read(app, db)
    app.state.contact_access_factory = lambda db: ContactService(db)
