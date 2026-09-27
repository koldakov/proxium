from fastapi.security import HTTPBearer

# `Authorization: Bearer <access token>`. Swagger's Authorize button takes the token as is.
bearer_scheme: HTTPBearer = HTTPBearer()
