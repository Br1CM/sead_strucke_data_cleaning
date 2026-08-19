"""Helpers shared by every notebook that talks to sead_staging or writes versioned outputs."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine


def get_db_engine(env_path='.env'):
    """Loads DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD from `env_path` and returns a
    sqlalchemy engine for sead_staging. `env_path` is resolved relative to the caller's cwd
    (notebooks run from within their own `notebooks/` folder, so pass the right number of `../`)."""
    load_dotenv(env_path)
    db_host = os.environ['DB_HOST']
    db_port = os.environ['DB_PORT']
    db_name = os.environ['DB_NAME']
    db_user = os.environ['DB_USER']
    db_password = os.environ['DB_PASSWORD']
    return create_engine(f'postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}')


def next_available_path(filename, dir_path, version=None):
    """Never silently overwrite a previous run's output - if the (optionally versioned) filename
    is already taken, keep bumping a numeric suffix (_2, _3, ...) until a free one is found."""
    dir_path = Path(dir_path)
    dir_path.mkdir(parents=True, exist_ok=True)
    if version:
        stem, suffix = filename.rsplit('.', 1)
        filename = f'{stem}_{version}.{suffix}'
    candidate = dir_path / filename
    if not candidate.exists():
        return candidate
    stem, suffix = filename.rsplit('.', 1)
    n = 2
    while (dir_path / f'{stem}_{n}.{suffix}').exists():
        n += 1
    return dir_path / f'{stem}_{n}.{suffix}'
