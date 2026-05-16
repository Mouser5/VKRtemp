import sys
import os
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import streamlit as st  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from web.database import SessionLocal, init_db  # noqa: E402
from web.schemas import UserCreate, UserLogin  # noqa: E402
from web.auth import register_user, authenticate_user, create_access_token  # noqa: E402
from web.bot_crud import (  # noqa: E402
    create_bot,
    get_user_bots,
    get_bot_by_id,
    delete_bot,
    save_game_result,
    get_user_game_history,
    get_bot_stats,
    get_latest_bots_from_all_users,
    get_all_bots_grouped_by_user,
    get_all_game_history,
    get_all_users,
    update_user_role,
    create_user_by_admin,
    create_bot_for_user,
    get_all_bots_with_users,
    delete_bot_by_admin,
)
from web.agent_validator import AgentValidator  # noqa: E402
from web.game_runner import (  # noqa: E402
    save_game_log_to_db,
    GameLog,
    BUILTIN_AGENTS,
    SingleGameResult,
    BenchmarkResult,
    run_tournament,
    run_hyperparam_benchmark,
)
from mc_config import GameConfig, RulesConfig  # noqa: E402

st.set_page_config(
    page_title="Гномы-вредители: Дуэль",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def display_scrollable_code(code: str, height: int = 300):
    st.code(code, language="python")


st.markdown(
    """
<style>
.stApp {
    max-width: 1400px;
}
.code-container {
    background-color: #1e1e1e;
    border-radius: 10px;
    padding: 15px;
    color: #d4d4d4;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
}
div[data-testid="stCodeBlock"] {
    max-height: 300px;
    overflow-y: auto;
}
div[data-testid="stCodeBlock"] pre {
    max-height: 300px;
    overflow-y: auto;
}
.success-box {
    background-color: #d4edda;
    border: 1px solid #c3e6cb;
    border-radius: 5px;
    padding: 10px;
    color: #155724;
}
.error-box {
    background-color: #f8d7da;
    border: 1px solid #f5c6cb;
    border-radius: 5px;
    padding: 10px;
    color: #721c24;
}
.uml-container {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 10px;
    padding: 20px;
    text-align: center;
}
.log-container {
    background-color: #f5f5f5;
    border: 1px solid #ddd;
    border-radius: 5px;
    padding: 10px;
    font-family: monospace;
    font-size: 12px;
    max-height: 400px;
    overflow-y: auto;
}
.stCodeBlock {
    max-height: 400px;
    overflow-y: auto;
}
.code-block-wrapper {
    background-color: #1e1e1e;
    border-radius: 10px;
    padding: 15px;
    max-height: 400px;
    overflow-y: auto;
}
.code-block-wrapper pre {
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
}
</style>
""",
    unsafe_allow_html=True,
)


def init_database():
    try:
        init_db()
    except Exception as e:
        st.warning(f"БД недоступна: {e}")


def get_db_session():
    if "db_session" not in st.session_state:
        st.session_state.db_session = SessionLocal()
    return st.session_state.db_session


def init_auth_state():
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "role" not in st.session_state:
        st.session_state.role = "admin"
    if "access_token" not in st.session_state:
        st.session_state.access_token = None


def login_user(db: Session, username: str, password: str):
    user, error = authenticate_user(db, UserLogin(username=username, password=password))
    if error:
        return False, error
    token = create_access_token(data={"sub": str(user.id), "username": user.username})
    st.session_state.user_id = user.id
    st.session_state.username = user.username
    st.session_state.role = (
        user.role.value if hasattr(user.role, "value") else str(user.role)
    )
    st.session_state.access_token = token
    return True, ""


def logout_user():
    st.session_state.user_id = None
    st.session_state.username = None
    st.session_state.role = "admin"
    st.session_state.access_token = None
    if "db_session" in st.session_state:
        st.session_state.db_session.close()
        del st.session_state.db_session


def show_login(db: Session):
    st.markdown("### 🔐 Вход в систему")

    with st.form("login_form"):
        username = st.text_input("Имя пользователя")
        password = st.text_input("Пароль", type="password")
        submit = st.form_submit_button("Войти", type="primary")

        if submit:
            if not username or not password:
                st.error("Заполните все поля")
            else:
                success, error = login_user(db, username, password)
                if success:
                    st.success("Вход выполнен!")
                    st.rerun()
                else:
                    st.error(error)

    st.markdown("---")
    st.markdown("### 📝 Регистрация")

    with st.form("register_form"):
        new_username = st.text_input("Новое имя пользователя")
        new_email = st.text_input("Email")
        new_password = st.text_input("Пароль", type="password")
        confirm_password = st.text_input("Подтвердите пароль", type="password")
        new_role = st.selectbox("Роль", ["admin", "player"])
        submit_reg = st.form_submit_button("Зарегистрироваться", type="primary")

        if submit_reg:
            if not new_username or not new_email or not new_password:
                st.error("Заполните все поля")
            elif new_password != confirm_password:
                st.error("Пароли не совпадают")
            else:
                user, error = register_user(
                    db,
                    UserCreate(
                        username=new_username,
                        email=new_email,
                        password=new_password,
                        role=new_role,
                    ),
                )
                if error:
                    st.error(error)
                else:
                    st.success("Регистрация успешна! Теперь войдите.")

    st.markdown("---")
    st.markdown("### 📋 Требования к роботу")
    st.markdown(AgentValidator.get_agent_requirements_text())


def show_dashboard(db: Session):
    user_id = st.session_state.user_id
    user_role = st.session_state.get("role", "admin")

    st.sidebar.markdown(f"### 👤 {st.session_state.username} ({user_role})")
    if st.sidebar.button("🚪 Выйти", width="stretch"):
        logout_user()
        st.rerun()

    st.sidebar.markdown("---")

    if user_role == "admin":
        tabs = st.tabs(
            [
                "🎮 Игра",
                "🤖 Мои боты",
                "🏆 Турнир",
                "🤖 Все боты",
                "📊 История",
                "⚙️ Администрирование",
                "🔧 Гиперпараметры",
                "❓ Правила",
            ]
        )

        with tabs[0]:
            show_game_tab(db, user_id)

        with tabs[1]:
            show_bots_tab(db, user_id)

        with tabs[2]:
            show_tournament_tab(db, user_id)

        with tabs[3]:
            show_all_bots_tab(db, user_id)

        with tabs[4]:
            show_all_history_tab(db, user_id)

        with tabs[5]:
            show_admin_panel(db)

        with tabs[6]:
            show_hyperparam_tuning_tab(db, user_id)

        with tabs[7]:
            show_requirements()
    else:
        tabs = st.tabs(["🎮 Игра", "🤖 Мои боты", "📊 История", "❓ Правила"])

        with tabs[0]:
            show_game_tab(db, user_id)

        with tabs[1]:
            show_bots_tab(db, user_id)

        with tabs[2]:
            show_history_tab(db, user_id)

        with tabs[3]:
            show_requirements()


def show_game_tab(db: Session, user_id: int):
    from web.logger import (
        log_game_start,
        log_game_end,
        log_game_error,
        log_bot_load_for_game,
        log_bot_loaded,
    )
    import uuid

    st.markdown("### 🎮 Запуск игры")

    user_bots = get_user_bots(db, user_id)
    bot_options = {bot.id: bot.name for bot in user_bots}
    bot_options[-1] = "Нет бота (человек)"

    col1, col2 = st.columns(2)

    with col1:
        opponent = st.selectbox(
            "Противник:",
            options=list(BUILTIN_AGENTS.keys()),
            format_func=lambda x: {
                "random": "🎲 RandomAgent",
                "heuristic": "🧠 HeuristicAgent",
                "smart": "🤖 SmartAgent",
            }.get(x, x),
        )

    if user_bots:
        with col2:
            selected_bot = st.selectbox(
                "Ваш бот:",
                options=list(bot_options.keys()),
                format_func=lambda x: bot_options.get(x, "Выбрать бота"),
            )
    else:
        st.info("У вас нет ботов. Создайте бота на вкладке 'Мои боты'")
        return

    st.info(
        "⚠️ Бот запускается в изолированном Docker-контейнере. "
        "Убедитесь, что образ gnomes-bot:latest собран: "
        "`docker build -t gnomes-bot -f src/bot-container/Dockerfile .`"
    )

    if st.button("🚀 Запустить игру", type="primary", width="stretch"):
        if selected_bot == -1:
            st.warning("Выберите бота для игры")
            return

        bot = get_bot_by_id(db, selected_bot)
        if not bot:
            st.error("Бот не найден")
            return

        log_bot_load_for_game(bot.id, bot.name)

        import random
        import math

        module_name = f"bot_{bot.id}"
        try:
            exec_globals = {
                "__name__": module_name,
                "random": random,
                "math": math,
            }
            exec(compile(bot.code, f"<bot_{bot.id}>", "exec"), exec_globals)

            has_agent = any(
                isinstance(obj, type) and hasattr(obj, "choose_action")
                for obj in exec_globals.values()
            )
            if not has_agent:
                log_bot_loaded(bot.id, bot.name, False)
                st.error("Не найден класс агента с методом choose_action")
                return

            log_bot_loaded(bot.id, bot.name, True)
        except SyntaxError as e:
            log_bot_loaded(bot.id, bot.name, False)
            st.error(f"Синтаксическая ошибка (строка {e.lineno}): {e.msg}")
            return
        except Exception as e:
            log_bot_loaded(bot.id, bot.name, False)
            st.error(f"Ошибка при загрузке: {str(e)}")
            return

        progress_bar = st.progress(0, text="Подготовка...")
        progress_bar.progress(25, text="Запуск игры...")

        game_id = str(uuid.uuid4())[:8]
        log_game_start(game_id, bot.name, opponent.capitalize())

        try:
            opponent_class = BUILTIN_AGENTS[opponent]

            from web.redis_game_bridge import RedisGameBridge

            bridge = RedisGameBridge()
            result_data_raw = bridge.run_with_container(
                container_player_id=0,
                bot_code=bot.code,
                opponent_class=opponent_class,
                opponent_name=opponent.capitalize(),
                bot_name=bot.name,
            )

            class ContainerGameResult:
                def __init__(self, data):
                    self.winner = data.get("winner")
                    self.winner_name = (
                        bot.name
                        if data.get("winner") == 0
                        else (
                            opponent.capitalize()
                            if data.get("winner") == 1
                            else "Ничья"
                        )
                    )
                    self.total_scores = data.get("scores", {0: 0, 1: 0})
                    self.turns = data.get("turns", 0)
                    self.errors = data.get("errors", [])
                    self.logs = [GameLog(**log) for log in data.get("logs", [])]

            result = ContainerGameResult(result_data_raw)

            if result_data_raw.get("error"):
                st.error(f"Ошибка контейнера: {result_data_raw['error']}")
                return

            winner_name = result.winner_name if result.winner is not None else "Ничья"
            log_game_end(game_id, winner_name, result.total_scores, result.turns)
            progress_bar.progress(100, text="Готово!")

        except Exception as e:
            log_game_error(game_id, str(e))
            progress_bar.progress(100, text="Ошибка!")
            raise

        from web.schemas import GameResultCreate

        result_data = GameResultCreate(
            bot_id=bot.id,
            opponent_type=opponent,
            opponent_id=None,
            result="win"
            if result.winner == 0
            else ("loss" if result.winner == 1 else "draw"),
            user_score=result.total_scores.get(0, 0),
            opponent_score=result.total_scores.get(1, 0),
            turns=result.turns,
        )
        save_game_result(db, user_id, result_data)

        dsl_log = result_data_raw.get("dsl_log", "")
        save_game_log_to_db(
            db_session=db,
            game_id=game_id,
            dsl_log=dsl_log,
            scores_p0=result.total_scores.get(0, 0),
            scores_p1=result.total_scores.get(1, 0),
            winner=result.winner,
            turns=result.turns,
            bot1_code=bot.code,
            bot2_code=None,
        )

        show_single_game_result(result)


def show_tournament_tab(db: Session, user_id: int):
    from web.models import Tournament, TournamentResult as TR
    from sqlalchemy import desc

    st.markdown("### 🏆 Турнир")

    all_bots = get_latest_bots_from_all_users(db)
    if not all_bots:
        st.info("Нет ботов для участия в турнире")
        return

    with st.expander("➕ Создать турнир", expanded=True):
        with st.form("tournament_form"):
            tournament_name = st.text_input(
                "Название турнира", placeholder="Мой турнир"
            )
            selected_bots = st.multiselect(
                "Выберите ботов (минимум 2)",
                options=[
                    (bot.id, f"{bot.name} (user_id={bot.user_id})") for bot in all_bots
                ],
                format_func=lambda x: x[1],
            )
            submit = st.form_submit_button("Запустить турнир", type="primary")

            if submit:
                if len(selected_bots) < 2:
                    st.error("Выберите минимум 2 бота")
                elif not tournament_name:
                    st.error("Введите название турнира")
                else:
                    import random
                    import math

                    bots_list = []
                    for bot_id, bot_name in selected_bots:
                        bot = get_bot_by_id(db, bot_id)
                        if not bot:
                            continue

                        module_name = f"bot_{bot.id}"
                        try:
                            exec_globals = {
                                "__name__": module_name,
                                "random": random,
                                "math": math,
                            }
                            exec(
                                compile(bot.code, f"<bot_{bot.id}>", "exec"),
                                exec_globals,
                            )

                            agent_class = None
                            for name in exec_globals:
                                obj = exec_globals[name]
                                if isinstance(obj, type) and hasattr(
                                    obj, "choose_action"
                                ):
                                    agent_class = obj
                                    break

                            if agent_class:
                                bots_list.append((bot.code, agent_class, bot_name))
                        except Exception:
                            continue

                    if len(bots_list) < 2:
                        st.error("Не удалось загрузить хотя бы 2 бота")
                    else:
                        progress_bar = st.progress(0, text="Подготовка...")
                        progress_bar.progress(10, text="Запуск турнира...")

                        try:
                            result = run_tournament(
                                bots_list,
                                db,
                                user_id,
                                tournament_name,
                            )

                            progress_bar.progress(100, text="Готово!")

                            st.success(
                                f"Турнир завершён! Всего игр: {result.total_games}"
                            )

                        except Exception as e:
                            progress_bar.progress(100, text="Ошибка!")
                            st.error(f"Ошибка турнира: {str(e)}")

    st.markdown("---")
    st.markdown("#### 📂 История турниров")

    tournaments = (
        db.query(Tournament).order_by(desc(Tournament.created_at)).limit(10).all()
    )

    if not tournaments:
        st.info("Пока нет турниров")
        return

    for tournament in tournaments:
        with st.expander(
            f"🏆 {tournament.name} ({tournament.created_at.strftime('%d.%m.%Y %H:%M')})"
        ):
            results = db.query(TR).filter(TR.tournament_id == tournament.id).all()

            col1, col2, col3 = st.columns(3)
            with col1:
                total_games = (
                    sum(r.games_played for r in results) // 2 if results else 0
                )
                st.metric("Всего игр", total_games)
            with col2:
                st.metric("Статус", tournament.status.value)
            with col3:
                st.metric("Время", f"{tournament.created_at.strftime('%H:%M')}")

            if results:
                st.markdown("##### Результаты:")
                sorted_results = sorted(
                    results, key=lambda x: (-x.wins, -x.total_score)
                )
                for i, tr in enumerate(sorted_results, 1):
                    st.write(
                        f"{i}. **{tr.bot_name}**: {tr.wins} побед, {tr.losses} поражений, {tr.draws} ничьих, {tr.total_score} очков"
                    )


def show_bots_tab(db: Session, user_id: int):
    from web.logger import log_bot_upload

    st.markdown("### 🤖 Мои боты")

    with st.expander("➕ Загрузить нового бота", expanded=False):
        with st.form("upload_bot"):
            bot_name = st.text_input("Название бота", placeholder="MySuperBot")

            code_tabs = st.tabs(["✏️ Ввести код", "📁 Загрузить файл"])
            bot_code = ""

            with code_tabs[0]:
                bot_code = st.text_area(
                    "Код бота (Python)", height=300, key="user_bot_code"
                )

            with code_tabs[1]:
                uploaded_file = st.file_uploader(
                    "Выберите .py файл",
                    type=["py"],
                    key="user_file_upload",
                )
                if uploaded_file:
                    bot_code = uploaded_file.getvalue().decode("utf-8")
                    st.success(
                        f"Загружено: {uploaded_file.name} ({len(bot_code)} символов)"
                    )

            submit = st.form_submit_button("Загрузить", type="primary")

            if submit:
                if not bot_name or not bot_code:
                    st.error("Заполните все поля")
                else:
                    validation = AgentValidator.validate_agent_class_from_code(bot_code)
                    if validation.is_valid:
                        from web.schemas import BotCreate

                        bot_data = BotCreate(name=bot_name, code=bot_code)
                        bot = create_bot(db, user_id, bot_data)
                        log_bot_upload(user_id, bot.name, bot.id)
                        st.success(f"Бот '{bot.name}' загружен!")
                        st.rerun()
                    else:
                        for error in validation.errors:
                            st.error(error)

    st.markdown("---")
    st.markdown("#### 📂 Загруженные боты")

    bots = get_user_bots(db, user_id)

    if not bots:
        st.info("У вас пока нет ботов. Загрузите первого бота!")
        return

    for bot in bots:
        with st.expander(f"🤖 {bot.name} (ID: {bot.id})"):
            stats = get_bot_stats(db, bot.id)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Всего игр", stats["total"])
            with col2:
                st.metric("Побед", stats["wins"])
            with col3:
                st.metric("Поражений", stats["losses"])
            with col4:
                st.metric("Win Rate", f"{stats['win_rate']:.1f}%")

            st.markdown("**Код:**")
            display_scrollable_code(bot.code)

            if st.button("🗑️ Удалить", key=f"delete_{bot.id}"):
                if delete_bot(db, bot.id, user_id):
                    st.success("Бот удалён")
                    st.rerun()


def show_history_tab(db: Session, user_id: int):
    st.markdown("### 📊 История игр")

    history = get_user_game_history(db, user_id)

    if not history:
        st.info("У вас пока нет сыгранных игр")
        return

    for idx, game in enumerate(history, start=1):
        result_icon = (
            "✅" if game.result == "win" else ("❌" if game.result == "loss" else "🤝")
        )
        with st.expander(f"Игра #{idx} — {result_icon} vs {game.opponent_type}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Ваш счёт", game.user_score)
            with col2:
                st.metric("Счёт противника", game.opponent_score)
            with col3:
                st.metric("Ходов", game.turns)
            st.caption(f"Дата: {game.played_at} | ID в БД: {game.id}")


def show_all_bots_tab(db: Session, user_id: int):
    from web.models import User

    st.markdown("### 🤖 Все боты (по пользователям)")

    bots_by_user = get_all_bots_grouped_by_user(db)

    if not bots_by_user:
        st.info("Нет загруженных ботов")
        return

    for uid, bots in bots_by_user.items():
        user = db.query(User).filter(User.id == uid).first()
        username = user.username if user else f"user_{uid}"

        with st.expander(f"👤 {username} ({len(bots)} ботов)"):
            for bot in bots:
                stats = get_bot_stats(db, bot.id)

                with st.expander(f"🤖 {bot.name} (ID: {bot.id})"):
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Всего игр", stats["total"])
                    with col2:
                        st.metric("Побед", stats["wins"])
                    with col3:
                        st.metric("Поражений", stats["losses"])
                    with col4:
                        st.metric("Win Rate", f"{stats['win_rate']:.1f}%")

                    st.markdown("**Код:**")
                    display_scrollable_code(bot.code)
                    st.markdown("---")


def show_all_history_tab(db: Session, user_id: int):
    st.markdown("### 📊 Все игры")

    history = get_all_game_history(db)

    if not history:
        st.info("Нет сыгранных игр")
        return

    for game in history:
        result_icon = (
            "✅" if game.result == "win" else ("❌" if game.result == "loss" else "🤝")
        )
        with st.expander(
            f"Игра #{game.id} — {result_icon} | user_id={game.user_id} | vs {game.opponent_type}"
        ):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("user_id", game.user_id)
            with col2:
                st.metric("Счёт", f"{game.user_score} : {game.opponent_score}")
            with col3:
                st.metric("Результат", game.result)
            with col4:
                st.metric("Ходов", game.turns)
            st.caption(f"Дата: {game.played_at}")


def show_admin_panel(db: Session):
    st.markdown("### ⚙️ Панель администратора")

    sub_tabs = st.tabs(["👥 Пользователи", "🤖 Код всех ботов", "📁 Загрузить бота"])

    with sub_tabs[0]:
        st.markdown("#### 👥 Управление пользователями")

        users = get_all_users(db)
        if not users:
            st.info("Нет пользователей")
        else:
            for user in users:
                col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                with col1:
                    st.write(f"**{user.username}**")
                with col2:
                    st.write(user.email)
                with col3:
                    st.write(f"Роль: {user.role}")
                with col4:
                    new_role = "player" if user.role == "admin" else "admin"
                    if st.button(f"→ {new_role}", key=f"role_{user.id}"):
                        if update_user_role(db, user.id, new_role):
                            st.success("Роль изменена")
                            st.rerun()
                        else:
                            st.error("Ошибка")

        st.markdown("---")
        st.markdown("#### ➕ Создать пользователя")

        with st.form("create_user_admin"):
            new_username = st.text_input("Имя пользователя")
            new_email = st.text_input("Email")
            new_password = st.text_input("Пароль", type="password")
            submit = st.form_submit_button("Создать", type="primary")

            if submit:
                if not new_username or not new_email or not new_password:
                    st.error("Заполните все поля")
                else:
                    user, error = create_user_by_admin(
                        db, new_username, new_email, new_password
                    )
                    if error:
                        st.error(error)
                    else:
                        st.success(f"Создан пользователь: {user.username}")
                        st.rerun()

    with sub_tabs[1]:
        st.markdown("#### 🤖 Боты по пользователям")

        all_bots = get_all_bots_with_users(db)
        if not all_bots:
            st.info("Нет загруженных ботов")
        else:
            from collections import defaultdict

            bots_by_user = defaultdict(list)
            for bot in all_bots:
                bots_by_user[bot["username"]].append(bot)

            for username, bots in bots_by_user.items():
                with st.expander(f"👤 {username} ({len(bots)} ботов)"):
                    for bot in bots:
                        with st.expander(f"🤖 {bot['bot_name']} (ID: {bot['bot_id']})"):
                            col1, col2 = st.columns([1, 1])
                            with col1:
                                st.write(
                                    f"**Создан:** {bot['created_at'].strftime('%d.%m.%Y %H:%M')}"
                                )
                            with col2:
                                if st.button(
                                    "🗑️ Удалить бота",
                                    key=f"admin_delete_bot_{bot['bot_id']}",
                                ):
                                    if delete_bot_by_admin(db, bot["bot_id"]):
                                        st.success("Бот удалён")
                                        st.rerun()
                                    else:
                                        st.error("Ошибка при удалении")
                            st.markdown("**Код:**")
                            display_scrollable_code(bot["code"])

    with sub_tabs[2]:
        st.markdown("#### 📁 Загрузить бота для пользователя")

        users = get_all_users(db)
        if not users:
            st.info("Нет пользователей")
        else:
            user_options = {u.id: u.username for u in users}
            selected_user_id = st.selectbox(
                "Выберите пользователя",
                options=list(user_options.keys()),
                format_func=lambda x: user_options[x],
            )

            with st.form("upload_bot_admin"):
                bot_name = st.text_input("Название бота", placeholder="MySuperBot")

                code_input_tabs = st.tabs(["✏️ Ввести код", "📁 Загрузить файл"])

                bot_code = ""

                with code_input_tabs[0]:
                    bot_code = st.text_area(
                        "Код бота (Python)", height=300, key="admin_bot_code"
                    )

                with code_input_tabs[1]:
                    uploaded_file = st.file_uploader(
                        "Выберите .py файл",
                        type=["py"],
                        key="admin_file_upload",
                    )
                    if uploaded_file:
                        bot_code = uploaded_file.getvalue().decode("utf-8")
                        st.success(
                            f"Загружено: {uploaded_file.name} ({len(bot_code)} символов)"
                        )

                submit = st.form_submit_button("Загрузить", type="primary")

                if submit:
                    if not bot_name or not bot_code:
                        st.error("Заполните все поля")
                    else:
                        validation = AgentValidator.validate_agent_class_from_code(
                            bot_code
                        )
                        if validation.is_valid:
                            bot = create_bot_for_user(
                                db, selected_user_id, bot_name, bot_code
                            )
                            st.success(
                                f"Бот '{bot.name}' создан для {user_options[selected_user_id]}"
                            )
                            st.rerun()
                        else:
                            for error in validation.errors:
                                st.error(error)


def show_requirements():
    st.markdown(AgentValidator.get_agent_requirements_text())

    st.markdown("### 📊 UML-диаграмма интерфейса агента")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    svg_path = os.path.join(base_dir, "docs", "rules.svg")
    if os.path.exists(svg_path):
        st.image(svg_path, caption="Диаграмма интерфейса агента", width="stretch")
    else:
        st.warning("Диаграмма не найдена")


def show_single_game_result(result: SingleGameResult):
    if result.errors:
        st.error("❌ Игра завершена с ошибкой!")
        for error in result.errors:
            with st.expander("🔴 Показать ошибку"):
                st.code(error, language="text")
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        if result.winner == 0:
            st.success(f"🏆 Победитель: **{result.winner_name}**")
        elif result.winner == 1:
            st.error(f"Победитель: **{result.winner_name}**")
        else:
            st.info("🤝 Ничья!")

    with col2:
        st.metric("Ваш робот", f"{result.total_scores[0]} очков")

    with col3:
        st.metric("Противник", f"{result.total_scores[1]} очков")

    st.metric("Всего ходов", result.turns)

    st.markdown("#### 📜 Лог игры")

    log_text = ""
    for log in result.logs:
        player_marker = "👤 ВЫ" if log.player_id == 0 else "🤖 ОПП"
        gold_str = f" ✨ ЗОЛОТО: {log.gold_found}!" if log.gold_found else ""
        log_text += f"Ход {log.turn_number} (Раунд {log.round_number}) [{player_marker}]: {log.action_description}{gold_str}\n"

    with st.expander("Показать полный лог"):
        st.code(log_text, language="text")


def show_benchmark_result(result: BenchmarkResult):
    st.markdown("#### 📊 Статистика бенчмарка")

    col1, col2, col3 = st.columns(3)

    with col1:
        wins_user = sum(v for k, v in result.wins.items() if k != "draw")
        pct = 100 * wins_user / result.total_games if result.total_games > 0 else 0
        st.metric("Побед", f"{wins_user} ({pct:.1f}%)")

    with col2:
        draws = result.wins.get("draw", 0)
        pct_draw = 100 * draws / result.total_games if result.total_games > 0 else 0
        st.metric("Ничьих", f"{draws} ({pct_draw:.1f}%)")

    with col3:
        st.metric("Всего игр", result.total_games)

    col4, col5 = st.columns(2)

    with col4:
        st.metric("Всего ходов", result.total_turns)

    with col5:
        st.metric("Время", f"{result.elapsed_time:.2f} сек")

    if result.total_errors > 0:
        st.warning(f"⚠️ Ошибок: {result.total_errors}")


def show_hyperparam_tuning_tab(db: Session, user_id: int):
    st.markdown("### 🔧 Гиперпараметры")

    st.markdown(
        "Тестирование влияния гиперпараметров на баланс игры. "
        "Система считается сбалансированной, если у ботов с одинаковой логикой "
        "винрейт ≈ 50%. Чем сложнее логика бота, тем выше его винрейт."
    )

    if st.session_state.pop("hp_reset_trigger", False):
        for k, v in {
            "hp_h1": 5,
            "hp_h2": 5,
            "hp_cpt": 1,
            "hp_rounds": 3,
            "hp_guar": False,
            "hp_extra": False,
            "hp_rest": False,
            "hp_mull": False,
            "hp_gold": 0,
            "hp_hand": 0,
            "hp_ngames": 100,
        }.items():
            st.session_state[k] = v

    bot_names = list(BUILTIN_AGENTS.keys())

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        agent1_choice = st.selectbox("Первый бот", bot_names, index=0, key="hp_agent1")
    with col_b2:
        agent2_choice = st.selectbox(
            "Второй бот",
            bot_names,
            index=2 if len(bot_names) > 2 else 1,
            key="hp_agent2",
        )

    st.markdown("---")

    with st.expander("⚙️ Параметры игры", expanded=True):
        col_r1, col_r2, col_r3 = st.columns(3)

        with col_r1:
            hand_size_first = st.slider("Рука первого игрока", 2, 10, 5, key="hp_h1")
            hand_size_second = st.slider("Рука второго игрока", 2, 10, 5, key="hp_h2")
            cards_drawn_per_turn = st.slider("Карт за ход", 1, 5, 1, key="hp_cpt")
            rounds = st.slider("Раундов", 1, 5, 3, key="hp_rounds")

        with col_r2:
            guarantee_card_types = st.checkbox(
                "Гарантия типов карт (тоннель/починка/поломка)",
                value=False,
                key="hp_guar",
            )
            second_extra_draw_t1 = st.checkbox(
                "Дополнительная карта второму игроку на T1", value=False, key="hp_extra"
            )
            first_turn_pass_restriction = st.checkbox(
                "Запрет поломки/починки первому игроку на T1",
                value=False,
                key="hp_rest",
            )
            mulligan_enabled = st.checkbox(
                "Пересдача руки (mulligan)", value=False, key="hp_mull"
            )

        with col_r3:
            second_player_bonus_gold = st.slider(
                "Бонусное золото второму игроку", 0, 10, 0, key="hp_gold"
            )
            hand_limit = st.slider(
                "Лимит карт в руке (0 = без лимита)", 0, 10, 0, key="hp_hand"
            )

        st.markdown("---")

        if st.button(
            "🔄 Сбросить к стандартному состоянию (равные карты)",
            use_container_width=True,
        ):
            st.session_state.hp_reset_trigger = True
            st.rerun()

    st.markdown("---")

    num_games = st.number_input(
        "Количество игр в бенчмарке",
        min_value=10,
        max_value=10000,
        value=100,
        step=10,
        key="hp_ngames",
    )

    if st.button("▶️ Запустить бенчмарк", type="primary", use_container_width=True):
        rules = RulesConfig(
            hand_size_first=hand_size_first,
            hand_size_second=hand_size_second,
            cards_drawn_per_turn=cards_drawn_per_turn,
            rounds=rounds,
            guarantee_card_types=guarantee_card_types,
            second_extra_draw_t1=second_extra_draw_t1,
            first_turn_pass_restriction=first_turn_pass_restriction,
            mulligan_enabled=mulligan_enabled,
            second_player_bonus_gold=second_player_bonus_gold,
            hand_limit=hand_limit,
        )
        config = GameConfig(rules=rules)

        agent1_class = BUILTIN_AGENTS[agent1_choice]
        agent2_class = BUILTIN_AGENTS[agent2_choice]
        agent1_name = agent1_choice.capitalize()
        agent2_name = agent2_choice.capitalize()
        if agent1_name == agent2_name:
            agent1_name = f"{agent1_name} (P0)"
            agent2_name = f"{agent2_name} (P1)"

        progress_bar = st.progress(0, text="Запуск игр...")
        status_text = st.empty()

        result = run_hyperparam_benchmark(
            agent1_class=agent1_class,
            agent2_class=agent2_class,
            num_games=num_games,
            config=config,
            agent1_name=agent1_name,
            agent2_name=agent2_name,
        )

        progress_bar.empty()
        status_text.empty()

        st.markdown("#### 📊 Результаты")

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            pct1 = (
                100 * result.wins[agent1_name] / result.total_games
                if result.total_games > 0
                else 0
            )
            st.metric(
                f"🏆 Побед ({agent1_name})", f"{result.wins[agent1_name]} ({pct1:.1f}%)"
            )
        with col_s2:
            pct_d = (
                100 * result.wins["draw"] / result.total_games
                if result.total_games > 0
                else 0
            )
            st.metric("🤝 Ничьих", f"{result.wins['draw']} ({pct_d:.1f}%)")
        with col_s3:
            pct2 = (
                100 * result.wins[agent2_name] / result.total_games
                if result.total_games > 0
                else 0
            )
            st.metric(
                f"🏆 Побед ({agent2_name})", f"{result.wins[agent2_name]} ({pct2:.1f}%)"
            )

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("Всего игр", result.total_games)
        with col_m2:
            st.metric("Всего ходов", result.total_turns)
        with col_m3:
            st.metric("Время", f"{result.elapsed_time:.2f} сек")
        with col_m4:
            st.metric("Игр/сек", f"{result.games_per_second:.1f}")

        if result.total_errors > 0:
            st.warning(f"⚠️ Ошибок: {result.total_errors}")

        st.markdown("#### 📈 Динамика винрейта")
        st.markdown(
            "График показывает, как меняется процент побед каждого бота "
            "по мере увеличения количества сыгранных игр."
        )

        chart_data = []
        for i in range(result.total_games):
            chart_data.append(
                {
                    "Игра": i + 1,
                    agent1_name: result.winrate_history[agent1_name][i],
                    agent2_name: result.winrate_history[agent2_name][i],
                }
            )

        if chart_data:
            import pandas as pd

            df = pd.DataFrame(chart_data)
            df = df.set_index("Игра")
            st.line_chart(df)

        st.markdown("---")
        st.markdown(
            "💡 **Вывод**: если винрейты обоих ботов близки к 50%, "
            "систему можно считать сбалансированной для данных гиперпараметров."
        )


def main():
    init_database()
    init_auth_state()

    st.title("⛏️ Гномы-вредители: Дуэль")
    st.markdown("##### Карточная игра для обучения ИИ-агентов")

    db = get_db_session()

    if st.session_state.user_id is None:
        show_login(db)
    else:
        show_dashboard(db)


if __name__ == "__main__":
    main()
