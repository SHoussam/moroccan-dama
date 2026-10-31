from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.realtime.websocket import ConnectionHub
from app.rooms.manager import RoomManager

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


class CreateRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_name: str = Field(..., min_length=1, max_length=40)


class JoinRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_name: str = Field(default="", max_length=40)
    player_token: str | None = Field(default=None, max_length=128)


def _get_services(request: Request) -> tuple[RoomManager, ConnectionHub]:
    return request.app.state.room_manager, request.app.state.connection_hub


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_room_endpoint(payload: CreateRoomRequest, request: Request) -> JSONResponse:
    room_manager, _ = _get_services(request)
    result = room_manager.create_room(payload.player_name)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=result.model_dump(mode="json", by_alias=True),
    )


@router.post("/{room_code}/join")
async def join_room_endpoint(
    room_code: str,
    payload: JoinRoomRequest,
    request: Request,
    x_player_token: str | None = Header(default=None),
) -> JSONResponse:
    room_manager, hub = _get_services(request)
    existing_token = payload.player_token or x_player_token
    result = room_manager.join_room(
        room_code,
        payload.player_name,
        existing_token=existing_token,
    )

    if not result.reconnected:
        await hub.broadcast_personalized(
            result.room_code,
            room_manager,
            lambda snap: {
                "type": "player_joined",
                "room": snap.model_dump(mode="json", by_alias=True),
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=result.model_dump(mode="json", by_alias=True),
    )


@router.get("/{room_code}")
async def get_room_public_endpoint(room_code: str, request: Request) -> JSONResponse:
    room_manager, _ = _get_services(request)
    snapshot = room_manager.get_public_snapshot(room_code)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=snapshot.model_dump(mode="json", by_alias=True),
    )
