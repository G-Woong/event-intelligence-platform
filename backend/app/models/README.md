# models/

SQLAlchemy 2.x ORM 모델 (STEP 004 추가).

| 모듈 | 클래스 | 테이블 |
|---|---|---|
| `event.py` | `EventCardORM` | `event_cards` |
| `comment.py` | `CommentORM` | `comments` |
| `base.py` | `Base` | — (`DeclarativeBase`) |

`__init__.py` 에서 모든 모델을 import하여 `Base.metadata`에 등록 보장.
Alembic `env.py`는 `from backend.app import models` 로 모델을 로드한다.
