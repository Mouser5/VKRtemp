from pydantic import BaseModel, Field
from typing import Literal, List, Optional, Union
from cards import EquipmentType


class ActionBuild(BaseModel):
    """Действие: Построить туннель, лестницу или дверь."""

    type: Literal["build"] = "build"
    template_id: int
    x: int
    y: int
    is_rotated_180: bool = False


class ActionPlayBoardUtility(BaseModel):
    """Действие: Сыграть карту на поле (Обвал, Ключ, Карта сокровищ)."""

    type: Literal["play_board_utility"] = "play_board_utility"
    template_id: int
    x: int
    y: int


class ActionPlayPlayerUtility(BaseModel):
    """Действие: Сыграть карту на игрока (Поломка, Починка)."""

    type: Literal["play_player_utility"] = "play_player_utility"
    template_id: int
    target_player_id: int


class ActionDiscard(BaseModel):
    """Действие: Сбросить карты (обычный сброс 1-2 карт ИЛИ экстренная починка за 2 карты)."""

    type: Literal["discard"] = "discard"
    templates: List[int] = Field(..., min_length=1, max_length=2)
    repair_equipment: Optional[EquipmentType] = None


class ActionMulligan(BaseModel):
    """Действие: Пересдача стартовой руки (mulligan)."""

    type: Literal["mulligan"] = "mulligan"


AgentAction = Union[
    ActionBuild,
    ActionPlayBoardUtility,
    ActionPlayPlayerUtility,
    ActionDiscard,
    ActionMulligan,
]
