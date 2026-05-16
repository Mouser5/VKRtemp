import inspect
from typing import Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    class_name: Optional[str] = None
    has_choose_action: bool = False
    has_player_id_param: bool = False


class AgentValidator:
    REQUIRED_METHOD = "choose_action"
    ALLOWED_PARAMS = ("game", "play", "state", "g", "gs", "game_state", "player")

    @classmethod
    def validate_agent_class(cls, agent_class: type) -> ValidationResult:
        errors = []
        warnings = []

        class_name = agent_class.__name__

        if not hasattr(agent_class, cls.REQUIRED_METHOD):
            errors.append(
                f"Класс '{class_name}' не имеет метода '{cls.REQUIRED_METHOD}'"
            )
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                class_name=class_name,
                has_choose_action=False,
            )

        choose_action = getattr(agent_class, cls.REQUIRED_METHOD)

        if not callable(choose_action):
            errors.append(
                f"'{cls.REQUIRED_METHOD}' должен быть методом, а не атрибутом"
            )
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                class_name=class_name,
                has_choose_action=False,
            )

        try:
            sig = inspect.signature(choose_action)
            params = list(sig.parameters.keys())

            has_valid_param = any(p in cls.ALLOWED_PARAMS for p in params)
            if not has_valid_param and len(params) < 2:
                errors.append(
                    f"Метод '{cls.REQUIRED_METHOD}' должен принимать один из параметров: {', '.join(cls.ALLOWED_PARAMS)}"
                )
                return ValidationResult(
                    is_valid=False,
                    errors=errors,
                    warnings=warnings,
                    class_name=class_name,
                    has_choose_action=True,
                    has_player_id_param=False,
                )

        except (ValueError, TypeError) as e:
            errors.append(f"Не удалось проверить сигнатуру метода: {e}")
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                class_name=class_name,
                has_choose_action=True,
            )

        try:
            sig_init = inspect.signature(agent_class.__init__)
            init_params = list(sig_init.parameters.keys())

            if "player_id" not in init_params and "self" in init_params:
                if len(init_params) < 2:
                    warnings.append(
                        "Рекомендуется, чтобы __init__ принимал player_id: int"
                    )
        except Exception:
            pass

        return ValidationResult(
            is_valid=True,
            errors=errors,
            warnings=warnings,
            class_name=class_name,
            has_choose_action=True,
            has_player_id_param=True,
        )

    @classmethod
    def validate_code_string(cls, code: str) -> Tuple[bool, List[str]]:
        errors = []

        try:
            compile(code, "<validation>", "exec")
        except SyntaxError as e:
            errors.append(f"Синтаксическая ошибка (строка {e.lineno}): {e.msg}")
            return False, errors

        if "def choose_action" not in code and "choose_action" not in code:
            errors.append("Код не содержит метод 'choose_action'")
            return False, errors

        if "class " not in code:
            errors.append("Код не содержит определения класса")
            return False, errors

        return True, errors

    @classmethod
    def validate_agent_class_from_code(cls, code: str) -> ValidationResult:
        import types
        import random
        import math
        import sys

        module_name = "temp_validation_module"
        try:
            if module_name in sys.modules:
                del sys.modules[module_name]

            module = types.ModuleType(module_name)
            sys.modules[module_name] = module

            exec_globals = {
                "__name__": module_name,
                "random": random,
                "math": math,
            }
            exec(compile(code, "<bot_code>", "exec"), exec_globals)

            agent_class = None
            for name in exec_globals:
                obj = exec_globals[name]
                if isinstance(obj, type) and hasattr(obj, "choose_action"):
                    agent_class = obj
                    break

            if agent_class is None:
                return ValidationResult(
                    is_valid=False,
                    errors=["Не найден класс агента с методом choose_action"],
                    warnings=[],
                )

            result = cls.validate_agent_class(agent_class)
            return result

        except SyntaxError as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Синтаксическая ошибка (строка {e.lineno}): {e.msg}"],
                warnings=[],
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Ошибка при загрузке кода: {str(e)}"],
                warnings=[],
            )
        finally:
            if module_name in sys.modules:
                del sys.modules[module_name]

    @classmethod
    def get_agent_requirements_text(cls) -> str:
        return """
## Требования к классу агента

Ваш робот должен быть реализован как Python-класс со следующими характеристиками:

### Обязательные элементы:

1. **Конструктор** — должен принимать `player_id: int`:
```python
def __init__(self, player_id: int):
    self.player_id = player_id
```

2. **Метод `choose_action`** — принимает объект игры и возвращает действие:
Имя параметра может быть любым: `game`, `play`, `state`, `g`, `gs`, `game_state`, `player`
```python
def choose_action(self, game):
    # Ваш код здесь
    pass
```

### Доступные методы объекта игры:

| Метод | Описание | Возвращает |
|-------|----------|------------|
| `get_legal_actions()` | Получить список легальных ходов | List[AgentAction] |
| `get_hand()` | Получить свои карты (ID карт) | List[int] |
| `get_scores()` | Получить текущий счёт | Dict[int, int] |
| `get_current_player()` | Узнать чей ход | int |
| `is_game_over()` | Проверить окончена ли игра | bool |
| `state` | Объект состояния игры | MatchState |

### Доступ к состоянию игрока:

```python
player_state = game.state.players[self.player_id]
hand = player_state.hand  # Список ID карт в руке
card_id_to_template = player_state.card_id_to_template  # Dict[int, str] - маппинг ID -> template_id
broken = player_state.broken_equipments  # Set[EquipmentType] - сломанное оборудование
```

### Доступные типы действий:

| Класс | Описание | Параметры |
|-------|----------|-----------|
| `ActionBuild` | Построить туннель/дверь/лестницу | `template_id, x, y, is_rotated_180` |
| `ActionPlayBoardUtility` | Сыграть карту на поле (ключ/обвал/карта) | `template_id, x, y` |
| `ActionPlayPlayerUtility` | Сыграть карту на игрока (поломка/починка) | `template_id, target_player_id` |
| `ActionDiscard` | Сбросить карты | `templates, repair_equipment` |

### Статические ID карт (101 карта):

**Колода (ID 1-96):**
| Шаблон | Диапазон ID |
|--------|-------------|
| tunnel_cross | 1-10 |
| tunnel_t | 11-20 |
| tunnel_straight | 21-28 |
| tunnel_corner | 29-38 |
| tunnel_deadend | 39-42 |
| tunnel_bridge | 43-46 |
| tunnel_double_corner | 47-50 |
| tunnel_split_t_up | 51-54 |
| tunnel_split_t_l | 55-58 |
| door_blue | 59-61 |
| door_green | 62-64 |
| ladder | 65-68 |
| act_boom | 69-71 |
| act_key | 72-74 |
| act_map | 75-78 |
| brk_LAMP | 79-81 |
| brk_CART | 82-84 |
| brk_PICKAXE | 85-87 |
| rep_LAMP | 88-90 |
| rep_CART | 91-93 |
| rep_PICKAXE | 94-96 |

**Золото (ID 8001-8012):**
| Шаблон | ID |
|--------|-----|
| gold_1_ud | 8001-8002 |
| gold_1_lr | 8003-8004 |
| gold_2_corner | 8005-8006 |
| gold_2_t | 8007-8008 |
| gold_3_cross | 8009-8010 |
| gold_3_t | 8011-8012 |

**Стартовые карты:**
| Шаблон | ID |
|--------|-----|
| start_blue | 9001 |
| start_green | 9002 |

### Примеры роботов:

```python
# Вариант 1: с параметром game
class MyAgent1:
    def __init__(self, player_id: int):
        self.player_id = player_id
    
    def choose_action(self, game):
        return game.get_legal_actions()[0] if game.get_legal_actions() else None

# Вариант 2: с параметром play
class MyAgent2:
    def __init__(self, player_id: int):
        self.player_id = player_id
    
    def choose_action(self, play):
        return play.get_legal_actions()[0] if play.get_legal_actions() else None

# Вариант 3: с параметром state
class MyAgent3:
    def __init__(self, player_id: int):
        self.player_id = player_id
    
    def choose_action(self, state):
        return state.get_legal_actions()[0] if state.get_legal_actions() else None
```

### Важно:
- Используйте `game.get_legal_actions()` для получения списка легальных ходов
- Возвращайте `None` если нет доступных ходов
- Не изменяйте состояние игры напрямую!
- ID карт в hand — это статические ID из таблицы выше
"""


validator = AgentValidator()
