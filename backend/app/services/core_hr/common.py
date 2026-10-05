"""Domain errors and transaction boundaries. Callers commit successful operations."""
from functools import wraps
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


class HRError(Exception):
    pass


class NotFound(HRError):
    pass


class Conflict(HRError):
    pass


class InvalidOperation(HRError):
    pass


class StorageError(HRError):
    pass


def atomic(function):
    @wraps(function)
    def execute(db, *args, **kwargs):
        # Every HR writer takes the same lock BEFORE reading business state.
        try:
            db.execute(text('SELECT pg_advisory_xact_lock(360, 1)'))
            with db.begin_nested():
                result = function(db, *args, **kwargs)
                db.flush()
                return result
        except ValidationError as exc:
            raise InvalidOperation('Invalid fields or date range.') from exc
        except IntegrityError as exc:
            raise Conflict('The change conflicts with an existing record or reference.') from exc
        except SQLAlchemyError as exc:
            raise StorageError('The change could not be saved.') from exc
    return execute


def get(db, model, identifier, lock=False):
    query = select(model).where(model.id == identifier).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    record = db.scalar(query)
    if record is None:
        raise NotFound(f'{model.__name__} not found.')
    return record


def active(db, model, identifier):
    record = get(db, model, identifier)
    if not record.is_active:
        raise InvalidOperation(f'{model.__name__} is inactive.')
    return record
