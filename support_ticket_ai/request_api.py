"""HTTP operations for explicitly saved local requests."""

import logging
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .need_review import SaveNeedReview
from .request_store import CATEGORIES, RequestMissing, StoreConflict, payload_hash

logger = logging.getLogger(__name__)


class SaveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    text: Annotated[str, Field(strict=True, min_length=1, max_length=2000)]
    client_request_id: UUID
    include_prediction: Annotated[bool, Field(strict=True)] = True
    mode: Literal['word', 'semantic'] = 'word'
    check_multiple_requests: Annotated[bool, Field(strict=True)] = False

    @model_validator(mode='after')
    def check_mode(self):
        if self.check_multiple_requests and self.mode != 'semantic':
            raise ValueError('Separate-request checks require semantic mode.')
        return self


class RequestAction(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    version: Annotated[int, Field(strict=True, ge=1)]
    action: Literal['review', 'clarify', 'start', 'resolve', 'reopen', 'note']
    actor: Annotated[str, Field(strict=True, min_length=1, max_length=80)]
    note: Annotated[str, Field(strict=True, max_length=2000)] = ''
    category: str | None = None

    @model_validator(mode='after')
    def check_action(self):
        if self.action == 'review' and self.category not in CATEGORIES:
            raise ValueError('Choose a supported category for review.')
        if self.action != 'review' and self.category is not None:
            raise ValueError('Category is accepted only for review actions.')
        if self.action in {'clarify', 'resolve', 'reopen', 'note'} and not self.note:
            raise ValueError('A note is required for this action.')
        return self


def register_request_routes(application, predict, prediction_request_type, prediction_response_type):
    def store():
        result = application.state.request_store
        if result is None:
            raise HTTPException(status_code=503, detail='Local request storage is unavailable. Check the server configuration.')
        return result

    def call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except RequestMissing as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except StoreConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (sqlite3.Error, OSError) as error:
            logger.error('Request storage operation failed (%s)', type(error).__name__)
            raise HTTPException(status_code=503, detail='Local request storage could not complete the operation. Retry after checking the server.') from error

    @application.get('/workspace/config')
    def configuration():
        return {'storage_available': application.state.request_store is not None,
                'categories': list(CATEGORIES), 'local_single_user': True,
                'category_notes': 'CANCEL covers cancellation-fee questions; actual order cancellation is ORDER. SUBSCRIPTION covers newsletter preferences; SHIPPING covers destination addresses.'}

    @application.get('/requests/overview')
    def overview():
        return call(store().overview)

    @application.get('/requests')
    def list_requests(q: Annotated[str, Query(max_length=200)] = '',
                      status: Literal['open', 'needs_clarification', 'in_progress', 'resolved'] | None = None,
                      category: str | None = None, review_state: Literal['pending', 'reviewed'] | None = None,
                      queue: Literal['review'] | None = None,
                      limit: Annotated[int, Query(ge=1, le=100)] = 20,
                      offset: Annotated[int, Query(ge=0, le=1000000)] = 0):
        if category is not None and category not in CATEGORIES:
            raise HTTPException(status_code=422, detail='Unknown confirmed category filter.')
        return call(store().list, q=q.strip(), status=status, category=category,
                    review_state=review_state, queue=queue, limit=limit, offset=offset)

    @application.post('/requests', status_code=201)
    def save_request(body: SaveRequest):
        repository = store()
        digest = payload_hash(body.model_dump(mode='json', exclude={'client_request_id'}))
        key = str(body.client_request_id)
        existing = call(repository.existing, key, digest)
        if existing:
            return existing
        snapshot = None
        if body.include_prediction:
            request = prediction_request_type(text=body.text, mode=body.mode,
                                               check_multiple_requests=body.check_multiple_requests)
            snapshot = prediction_response_type.model_validate(predict(request)).model_dump(mode='json')
        return call(repository.create, key, digest, body.text, snapshot)

    @application.get('/requests/{request_id}')
    def get_request(request_id: UUID):
        return call(store().get, str(request_id))

    @application.post('/requests/{request_id}/actions')
    def change_request(request_id: UUID, body: RequestAction):
        return call(store().change, str(request_id), **body.model_dump())

    @application.post('/requests/{request_id}/needs-review')
    def save_need_review(request_id: UUID, body: SaveNeedReview):
        return call(store().save_need_review, str(request_id), version=body.version,
                    actor=body.actor, review=body.review.model_dump(mode='json'))
