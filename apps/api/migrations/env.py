from alembic import context

from app.core import models  # noqa: F401
from app.core.config import Settings
from app.core.db import Base, make_engine
from app.modules.assessment import models as assessment_models  # noqa: F401
from app.modules.fsp import models as fsp_models  # noqa: F401
from app.modules.invitations import models as invitation_models  # noqa: F401
from app.modules.matching import models as matching_models  # noqa: F401
from app.modules.profiles import models as profile_models  # noqa: F401

config = context.config
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url=Settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(Settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
