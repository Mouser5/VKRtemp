from typing import Dict
from cards import (
    CardTemplate,
    TunnelCardTemplate,
    CardOpenings,
    Direction,
    StartCardTemplate,
    DoorCardTemplate,
    LadderCardTemplate,
    ActionCardTemplate,
    ActionType,
    EquipmentType,
    GoldCardTemplate,
)


class TemplateRegistry:
    """Глобальный справочник всех карт игры."""

    def __init__(self):
        self.templates: Dict[str, CardTemplate] = {}

    def register(self, template: CardTemplate):
        self.templates[template.id] = template

    def get(self, template_id: str) -> CardTemplate:
        if template_id not in self.templates:
            raise ValueError(f"Шаблон {template_id} не найден в реестре!")
        return self.templates[template_id]


REGISTRY = TemplateRegistry()


def setup_global_registry():
    """Вызывается один раз за всё время работы программы."""
    if REGISTRY.templates:
        return  # Защита от повторной инициализации при MCTS rollouts

    # 1. Обычные туннели
    tunnel_configs = [
        ("tunnel_cross", "Crossroad", (True, True, True, True)),
        ("tunnel_t", "T-Junction", (True, True, True, False)),
        ("tunnel_straight", "Straight", (True, True, False, False)),
        ("tunnel_horizontal", "Horizontal", (False, False, True, True)),
        ("tunnel_corner_dl", "Corner down", (False, True, True, False)),
        ("tunnel_corner_ul", "Corner up", (True, False, True, False)),
        ("tunnel_deadend", "Dead End", (True, False, False, False)),
    ]
    for t_id, name, ops in tunnel_configs:
        REGISTRY.register(
            TunnelCardTemplate(
                id=t_id,
                name=name,
                openings=CardOpenings(
                    up=ops[0], down=ops[1], left=ops[2], right=ops[3]
                ),
            )
        )

    # 2. Сложные туннели
    subnetwork_configs = [
        (
            "tunnel_bridge",
            "Bridge",
            (True, True, True, True),
            [
                frozenset({Direction.UP, Direction.DOWN}),
                frozenset({Direction.LEFT, Direction.RIGHT}),
            ],
        ),
        (
            "tunnel_double_corner",
            "Double Corner",
            (True, True, True, True),
            [
                frozenset({Direction.UP, Direction.LEFT}),
                frozenset({Direction.DOWN, Direction.RIGHT}),
            ],
        ),
        (
            "tunnel_split_t_up",
            "Split T Vertical",
            (True, True, True, True),
            [
                frozenset({Direction.UP}),
                frozenset({Direction.DOWN, Direction.LEFT, Direction.RIGHT}),
            ],
        ),
        (
            "tunnel_split_t_l",
            "Split T Left",
            (True, True, True, True),
            [
                frozenset({Direction.LEFT}),
                frozenset({Direction.DOWN, Direction.UP, Direction.RIGHT}),
            ],
        ),
    ]

    for t_id, name, ops, subs in subnetwork_configs:
        REGISTRY.register(
            TunnelCardTemplate(
                id=t_id,
                name=name,
                openings=CardOpenings(
                    up=ops[0], down=ops[1], left=ops[2], right=ops[3]
                ),
                subnetworks=subs,
            )
        )

    # 3. Старты, Двери, Лестницы
    REGISTRY.register(
        StartCardTemplate(
            id="start_blue",
            name="Start Blue",
            openings=CardOpenings(up=True, down=True, left=True, right=True),
        )
    )
    REGISTRY.register(
        StartCardTemplate(
            id="start_green",
            name="Start Green",
            openings=CardOpenings(up=True, down=True, left=True, right=True),
        )
    )
    REGISTRY.register(
        DoorCardTemplate(
            id="door_blue",
            name="Blue Door",
            openings=CardOpenings(up=True, down=True, left=False, right=False),
            door_owner_id=0,
        )
    )
    REGISTRY.register(
        DoorCardTemplate(
            id="door_green",
            name="Green Door",
            openings=CardOpenings(up=True, down=True, left=False, right=False),
            door_owner_id=1,
        )
    )
    REGISTRY.register(
        LadderCardTemplate(
            id="ladder",
            name="Ladder",
            openings=CardOpenings(up=False, down=True, left=True, right=False),
        )
    )

    # 4. Действия
    REGISTRY.register(
        ActionCardTemplate(id="act_boom", name="Boom", action_type=ActionType.ROCKFALL)
    )
    REGISTRY.register(
        ActionCardTemplate(id="act_key", name="Key", action_type=ActionType.KEY)
    )
    REGISTRY.register(
        ActionCardTemplate(id="act_map", name="Map", action_type=ActionType.MAP)
    )

    for eq in EquipmentType:
        REGISTRY.register(
            ActionCardTemplate(
                id=f"brk_{eq.name}",
                name=f"Break {eq.value}",
                action_type=ActionType.SABOTAGE,
                equipment_type=eq,
            )
        )
        REGISTRY.register(
            ActionCardTemplate(
                id=f"rep_{eq.name}",
                name=f"Repair {eq.value}",
                action_type=ActionType.REPAIR,
                equipment_type=eq,
            )
        )

    # 5. Золото с разными конфигурациями выходов
    # Каждый номинал имеет несколько вариантов направления
    gold_configs = [
        # Номинал 1 - 2 карты
        ("gold_1_ud", "Gold 1 Up-Down", (True, True, False, False), 1),
        ("gold_1_lr", "Gold 1 Left-Right", (False, False, True, True), 1),
        # Номинал 2 - 2 карты
        ("gold_2_corner", "Gold 2 Corner", (False, True, True, False), 2),
        ("gold_2_t", "Gold 2 T-Junction", (True, True, True, False), 2),
        # Номинал 3 - 2 карты
        ("gold_3_cross", "Gold 3 Cross", (True, True, True, True), 3),
        ("gold_3_t", "Gold 3 T-Junction", (True, True, False, True), 3),
    ]

    for g_id, name, ops, val in gold_configs:
        REGISTRY.register(
            GoldCardTemplate(
                id=g_id,
                name=name,
                openings=CardOpenings(
                    up=ops[0], down=ops[1], left=ops[2], right=ops[3]
                ),
                gold_value=val,
            )
        )

    REGISTRY.register(
        GoldCardTemplate(
            id="hidden_gold",
            name="Hidden Gold",
            openings=CardOpenings(up=True, down=True, left=True, right=True),
            gold_value=0,
        )
    )
