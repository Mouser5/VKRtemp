import random
from dataclasses import asdict
from typing import Tuple, Optional, Dict, List

from cards import (
    TunnelCardTemplate,
    DoorCardTemplate,
    LadderCardTemplate,
    GoldCardTemplate,
    ActionCardTemplate,
    ActionType,
    Direction,
)
from actions import (
    AgentAction,
    ActionBuild,
    ActionPlayBoardUtility,
    ActionPlayPlayerUtility,
    ActionDiscard,
)
from state import (
    MatchState,
    PlayerState,
    PlacedCard,
    ObservableMatchState,
    ObservablePlayerState,
    reset_card_id_counter,
)
from registry import REGISTRY, setup_global_registry
from board import BoardEngine
from mc_config import GameConfig, DeckConfig, GoldConfig, RulesConfig


class Game:
    def __init__(self, config: Optional[GameConfig] = None):
        reset_card_id_counter()
        setup_global_registry()

        self.config = config or GameConfig()
        self.board_engine = BoardEngine(REGISTRY)
        self.state = MatchState()

        self.state.players[0] = PlayerState(player_id=0)
        self.state.players[1] = PlayerState(player_id=1)
        self.start_positions = self.config.board.start_positions.copy()

        self.state.first_player_in_round = random.randint(0, 1)
        self.state.current_player_id = self.state.first_player_in_round
        self.config = config if config is not None else None

        self._initial_deck_templates = None
        self._initial_gold_deck = None

        self._build_decks(self.config.deck)
        self._setup_board(self.config.gold, self.config.board.start_positions)
        self._deal_initial_cards(self.config.rules)

    def _build_decks(self, deck_cfg: DeckConfig):
        deck_template_ids = []
        counts = asdict(deck_cfg)

        for t_id, count in counts.items():
            deck_template_ids.extend([t_id] * count)

        gold_deck = self.config.gold.gold_templates.copy()

        random.shuffle(deck_template_ids)
        random.shuffle(gold_deck)
        self._initial_deck_templates = deck_template_ids.copy()
        self._initial_gold_deck = gold_deck.copy()

        self.state.deck = list(range(1, len(deck_template_ids) + 1))
        self.state.deck_template_ids = deck_template_ids
        self.state.gold_deck = gold_deck

    def _setup_board(
        self, gold_cfg: GoldConfig, start_positions: Dict[int, Tuple[int, int]]
    ):
        self.state.board[BoardEngine.coord_to_str(*start_positions[0])] = PlacedCard(
            template_id="start_blue", owner_id=0, unique_id=9001
        )
        self.state.board[BoardEngine.coord_to_str(*start_positions[1])] = PlacedCard(
            template_id="start_green", owner_id=1, unique_id=9002
        )

        gold_start_id = 8001
        for i, pos in enumerate(gold_cfg.gold_positions):
            if self.state.gold_deck:
                g_id = self.state.gold_deck.pop()
                self.state.board[BoardEngine.coord_to_str(*pos)] = PlacedCard(
                    template_id=g_id, owner_id=None, unique_id=gold_start_id + i
                )

    def _deal_initial_cards(self, rules_cfg: RulesConfig):
        second_player = 1 - self.state.first_player_in_round
        for p_id in [0, 1]:
            cards_count = (
                rules_cfg.hand_size_second
                if p_id == second_player
                else rules_cfg.hand_size_first
            )
            for _ in range(cards_count):
                if self.state.deck:
                    card_id = self.state.deck.pop()
                    template_id = self.state.deck_template_ids.pop(0)
                    self.state.players[p_id].hand.append(card_id)
                    self.state.players[p_id].card_id_to_template[card_id] = template_id

    def get_template_by_card_id(self, card_id: int) -> Optional[str]:
        p_id = self.state.current_player_id
        return self.state.players[p_id].card_id_to_template.get(card_id)

    def get_template_by_card_id_for_player(
        self, card_id: int, player_id: int
    ) -> Optional[str]:
        return self.state.players[player_id].card_id_to_template.get(card_id)

    def set_hand_with_templates(
        self, player_id: int, card_ids: List[int], template_ids: List[str]
    ):
        """Установить карты в руке с указанием соответствия ID->template."""
        if len(card_ids) != len(template_ids):
            raise ValueError("Размеры списков карт и шаблонов не совпадают")

        player = self.state.players[player_id]
        player.hand = card_ids.copy()
        player.card_id_to_template = dict(zip(card_ids, template_ids))

    def step(self, action: AgentAction) -> Tuple[bool, str, Optional[int]]:
        if self.is_game_over():
            return False, "Игра уже окончена.", None, ""
        template_id = ""
        if not isinstance(action, ActionDiscard):
            p_id = self.state.current_player_id
            player_state = self.state.players[p_id]
            lookup_key = (
                int(action.template_id)
                if isinstance(action.template_id, str)
                else action.template_id
            )
            template_id = player_state.card_id_to_template.get(lookup_key)
        if isinstance(action, ActionBuild):
            success, msg, rev_gold = self._handle_build(action)
        elif isinstance(action, ActionPlayBoardUtility):
            success, msg, rev_gold = self._handle_board_utility(action)
        elif isinstance(action, ActionPlayPlayerUtility):
            success, msg, rev_gold = self._handle_player_utility(action)
        elif isinstance(action, ActionDiscard):
            success, msg, rev_gold = self._handle_discard(action)
        else:
            return False, "Неизвестный тип действия.", None, ""

        if success:
            self.state.current_player_id = 1 - self.state.current_player_id
            self.state.turn_number += 1

        return success, msg, rev_gold, template_id

    def _handle_build(self, action: ActionBuild) -> Tuple[bool, str, Optional[int]]:
        p_id = self.state.current_player_id
        player_state = self.state.players[p_id]

        lookup_key = (
            int(action.template_id)
            if isinstance(action.template_id, str)
            else action.template_id
        )
        template_id = player_state.card_id_to_template.get(lookup_key)

        if template_id is None:
            return False, "Такой карты нет в руке.", None

        template = REGISTRY.get(template_id)

        if not isinstance(
            template, (TunnelCardTemplate, DoorCardTemplate, LadderCardTemplate)
        ):
            return False, "Нельзя строить эту карту.", None

        if player_state.broken_equipments:
            return False, "Инвентарь сломан!", None

        placed = PlacedCard(
            template_id=template_id,
            owner_id=p_id,
            is_rotated_180=action.is_rotated_180,
        )
        if isinstance(template, DoorCardTemplate):
            placed.is_locked = True

        coord_key = BoardEngine.coord_to_str(action.x, action.y)

        if not self.board_engine.is_move_valid(
            action.x,
            action.y,
            placed,
            self.start_positions[p_id],
            p_id,
            self.state.board,
            player_state.ladders,
        ):
            return False, "Ход недопустим.", None

        self.state.board[coord_key] = placed
        if isinstance(template, LadderCardTemplate):
            player_state.ladders.add(coord_key)

        del player_state.card_id_to_template[lookup_key]
        player_state.hand.remove(lookup_key)

        revealed_gold = self._check_and_reveal_gold(action.x, action.y, placed)
        if self.state.deck:
            new_card_id = self.state.deck.pop()
            new_template_id = self.state.deck_template_ids.pop(0)
            player_state.hand.append(new_card_id)
            player_state.card_id_to_template[new_card_id] = new_template_id

        return (
            True,
            f"Игрок {p_id} построил на ({action.x}, {action.y}).",
            revealed_gold,
        )

    def _handle_board_utility(
        self, action: ActionPlayBoardUtility
    ) -> Tuple[bool, str, Optional[int]]:
        p_id = self.state.current_player_id
        player_state = self.state.players[p_id]

        lookup_key = (
            int(action.template_id)
            if isinstance(action.template_id, str)
            else action.template_id
        )
        template_id = player_state.card_id_to_template.get(lookup_key)
        if template_id is None:
            return False, "Такой карты нет в руке.", None

        template = REGISTRY.get(template_id)
        coord_key = BoardEngine.coord_to_str(action.x, action.y)
        target_placed = self.state.board.get(coord_key)

        if not target_placed:
            return False, "Клетка пуста.", None

        msg = ""
        if template.action_type == ActionType.KEY:
            target_tpl = REGISTRY.get(target_placed.template_id)
            if (
                not isinstance(target_tpl, DoorCardTemplate)
                or not target_placed.is_locked
            ):
                return False, "Здесь нет закрытой двери.", None
            target_placed.is_locked = False
            msg = f"Игрок {p_id} открыл дверь на ({action.x}, {action.y})."

        elif template.action_type == ActionType.ROCKFALL:
            if not self.board_engine.is_move_valid(
                action.x,
                action.y,
                PlacedCard(template_id=template_id),
                self.start_positions[p_id],
                p_id,
                self.state.board,
                player_state.ladders,
            ):
                return False, "Нельзя обвалить.", None

            obval_tpl = REGISTRY.get(target_placed.template_id)
            if (
                isinstance(obval_tpl, LadderCardTemplate)
                and target_placed.owner_id in self.state.players
            ):
                self.state.players[target_placed.owner_id].ladders.discard(coord_key)

            del self.state.board[coord_key]
            msg = f"Обвал на ({action.x}, {action.y})!"

        elif template.action_type == ActionType.MAP:
            target_tpl = REGISTRY.get(target_placed.template_id)
            if (
                not isinstance(target_tpl, GoldCardTemplate)
                or target_placed.is_revealed
            ):
                return False, "Здесь нет скрытого золота.", None

            player_state.known_secrets.add(coord_key)
            msg = f"[СЕКРЕТ] Под ({action.x}, {action.y}) спрятано {target_tpl.gold_value} слитков!"

        del player_state.card_id_to_template[lookup_key]
        player_state.hand.remove(lookup_key)
        if self.state.deck:
            new_card_id = self.state.deck.pop()
            new_template_id = self.state.deck_template_ids.pop(0)
            player_state.hand.append(new_card_id)
            player_state.card_id_to_template[new_card_id] = new_template_id

        return True, msg, None

    def _handle_player_utility(
        self, action: ActionPlayPlayerUtility
    ) -> Tuple[bool, str, Optional[int]]:
        p_id = self.state.current_player_id
        player_state = self.state.players[p_id]

        lookup_key = (
            int(action.template_id)
            if isinstance(action.template_id, str)
            else action.template_id
        )
        template_id = player_state.card_id_to_template.get(lookup_key)
        if template_id is None:
            return False, "Такой карты нет в руке.", None

        template = REGISTRY.get(template_id)
        target_state = self.state.players[action.target_player_id]
        eq = template.equipment_type
        msg = ""

        if template.action_type == ActionType.SABOTAGE:
            if eq in target_state.broken_equipments:
                return False, "Уже сломано.", None
            target_state.broken_equipments.add(eq)
            msg = f"Игрок {p_id} сломал {eq.value} игроку {action.target_player_id}."

        elif template.action_type == ActionType.REPAIR:
            if eq not in target_state.broken_equipments:
                return False, "Не сломано.", None
            target_state.broken_equipments.remove(eq)
            msg = f"Игрок {p_id} починил {eq.value} игроку {action.target_player_id}."

        del player_state.card_id_to_template[lookup_key]
        player_state.hand.remove(lookup_key)
        if self.state.deck:
            new_card_id = self.state.deck.pop()
            new_template_id = self.state.deck_template_ids.pop(0)
            player_state.hand.append(new_card_id)
            player_state.card_id_to_template[new_card_id] = new_template_id

        return True, msg, None

    def _handle_discard(self, action: ActionDiscard) -> Tuple[bool, str, Optional[int]]:
        p_id = self.state.current_player_id
        state = self.state.players[p_id]

        if action.repair_equipment:
            if len(action.templates) != 2:
                return False, "Нужно 2 карты для экстренной починки.", None
            if action.repair_equipment not in state.broken_equipments:
                return False, "Предмет не сломан.", None
            state.broken_equipments.remove(action.repair_equipment)
            msg = f"Экстренная починка {action.repair_equipment.value}."
        else:
            msg = f"Сброшено карт: {len(action.templates)}."

        for card_id in action.templates:
            if card_id not in state.hand:
                return False, f"Карты {card_id} нет в руке.", None

            del state.card_id_to_template[card_id]
            state.hand.remove(card_id)

        cards_to_draw = 1 if action.repair_equipment else len(action.templates)
        for _ in range(cards_to_draw):
            if self.state.deck:
                new_card_id = self.state.deck.pop()
                new_template_id = self.state.deck_template_ids.pop(0)
                state.hand.append(new_card_id)
                state.card_id_to_template[new_card_id] = new_template_id

        return True, msg, None

    def _check_and_reveal_gold(
        self, x: int, y: int, placed_card: PlacedCard
    ) -> Optional[int]:
        revealed_amount = 0
        found_gold = False
        template = REGISTRY.get(placed_card.template_id)

        for direction in Direction:
            if not self.board_engine._get_effective_opening(
                template, direction, placed_card.is_rotated_180
            ):
                continue

            dx, dy = direction.value
            nx, ny = x + dx, y + dy
            neighbor_key = BoardEngine.coord_to_str(nx, ny)
            neighbor_placed = self.state.board.get(neighbor_key)

            if neighbor_placed and not neighbor_placed.is_revealed:
                n_tpl = REGISTRY.get(neighbor_placed.template_id)
                if isinstance(n_tpl, GoldCardTemplate):
                    neighbor_placed.is_revealed = True
                    neighbor_placed.owner_id = self.state.current_player_id
                    revealed_amount += n_tpl.gold_value
                    found_gold = True

        return revealed_amount if found_gold else None

    def get_legal_actions(self) -> List[AgentAction]:
        if self.is_game_over():
            return []

        legal_actions: List[AgentAction] = []
        p_id = self.state.current_player_id
        player_state = self.state.players[p_id]

        unique_hand = set(player_state.hand)

        for card_id in unique_hand:
            template_id = player_state.card_id_to_template.get(card_id)
            if template_id is None:
                continue
            legal_actions.append(ActionDiscard(templates=[card_id]))

        card_ids = list(player_state.hand)
        for i in range(len(card_ids)):
            for j in range(i + 1, len(card_ids)):
                cid1, cid2 = card_ids[i], card_ids[j]
                tpl1 = player_state.card_id_to_template.get(cid1)
                tpl2 = player_state.card_id_to_template.get(cid2)
                if tpl1 and tpl2:
                    legal_actions.append(ActionDiscard(templates=[cid1, cid2]))
                    for eq in player_state.broken_equipments:
                        legal_actions.append(
                            ActionDiscard(templates=[cid1, cid2], repair_equipment=eq)
                        )

        frontier_coords = self.board_engine.get_player_frontier(
            self.start_positions[p_id], p_id, self.state.board, player_state.ladders
        )

        card_id_to_template = player_state.card_id_to_template
        template_to_card_ids: Dict[str, List[int]] = {}
        for cid, tpl in card_id_to_template.items():
            if tpl not in template_to_card_ids:
                template_to_card_ids[tpl] = []
            template_to_card_ids[tpl].append(cid)

        for template_id, card_ids_list in template_to_card_ids.items():
            try:
                template = REGISTRY.get(template_id)
            except Exception as e:
                print(f"   [GAME DEBUG] ERROR getting template {template_id}: {e}")
                continue

            if isinstance(
                template, (TunnelCardTemplate, DoorCardTemplate, LadderCardTemplate)
            ):
                if not player_state.broken_equipments:
                    for x, y in frontier_coords:
                        for is_rot in [False, True]:
                            placed = PlacedCard(
                                template_id=template_id,
                                owner_id=p_id,
                                is_rotated_180=is_rot,
                            )
                            if isinstance(template, DoorCardTemplate):
                                placed.is_locked = True

                            if self.board_engine.is_move_valid(
                                x,
                                y,
                                placed,
                                self.start_positions[p_id],
                                p_id,
                                self.state.board,
                                player_state.ladders,
                                skip_path_check=True,
                            ):
                                for card_id in card_ids_list:
                                    legal_actions.append(
                                        ActionBuild(
                                            template_id=card_id,
                                            x=x,
                                            y=y,
                                            is_rotated_180=is_rot,
                                        )
                                    )
                                    break

            elif isinstance(template, ActionCardTemplate) and template.action_type in [
                ActionType.KEY,
                ActionType.ROCKFALL,
                ActionType.MAP,
            ]:
                for coord_key, target_placed in self.state.board.items():
                    tx, ty = BoardEngine.str_to_coord(coord_key)
                    try:
                        target_tpl = REGISTRY.get(target_placed.template_id)
                    except Exception:
                        continue

                    if template.action_type == ActionType.KEY:
                        if (
                            isinstance(target_tpl, DoorCardTemplate)
                            and target_placed.is_locked
                            and target_tpl.door_owner_id != p_id
                        ):
                            if self.board_engine.check_path_connectivity(
                                tx,
                                ty,
                                self.start_positions[p_id],
                                p_id,
                                self.state.board,
                                player_state.ladders,
                            ):
                                for card_id in card_ids_list:
                                    legal_actions.append(
                                        ActionPlayBoardUtility(
                                            template_id=card_id, x=tx, y=ty
                                        )
                                    )
                                    break

                    elif template.action_type == ActionType.ROCKFALL:
                        if self.board_engine.is_move_valid(
                            tx,
                            ty,
                            PlacedCard(template_id=template_id),
                            self.start_positions[p_id],
                            p_id,
                            self.state.board,
                            player_state.ladders,
                        ):
                            for card_id in card_ids_list:
                                legal_actions.append(
                                    ActionPlayBoardUtility(
                                        template_id=card_id, x=tx, y=ty
                                    )
                                )
                                break

                    elif template.action_type == ActionType.MAP:
                        if (
                            isinstance(target_tpl, GoldCardTemplate)
                            and not target_placed.is_revealed
                        ):
                            for card_id in card_ids_list:
                                legal_actions.append(
                                    ActionPlayBoardUtility(
                                        template_id=card_id, x=tx, y=ty
                                    )
                                )
                                break

            elif isinstance(template, ActionCardTemplate) and template.action_type in [
                ActionType.SABOTAGE,
                ActionType.REPAIR,
            ]:
                eq = template.equipment_type
                for target_p_id, target_state in self.state.players.items():
                    if (
                        template.action_type == ActionType.SABOTAGE
                        and eq not in target_state.broken_equipments
                    ):
                        for card_id in card_ids_list:
                            legal_actions.append(
                                ActionPlayPlayerUtility(
                                    template_id=card_id, target_player_id=target_p_id
                                )
                            )
                            break
                    elif (
                        template.action_type == ActionType.REPAIR
                        and eq in target_state.broken_equipments
                    ):
                        for card_id in card_ids_list:
                            legal_actions.append(
                                ActionPlayPlayerUtility(
                                    template_id=card_id, target_player_id=target_p_id
                                )
                            )
                            break

        # print(f"   [GAME DEBUG] Returning {len(legal_actions)} legal actions")
        return legal_actions

    def get_observation(self, target_player_id: int) -> ObservableMatchState:
        obs_board = {}
        player_secrets = self.state.players[target_player_id].known_secrets

        for coord_key, placed_card in self.state.board.items():
            tpl = REGISTRY.get(placed_card.template_id)
            if isinstance(tpl, GoldCardTemplate) and not placed_card.is_revealed:
                if coord_key not in player_secrets:
                    obs_board[coord_key] = placed_card.model_copy(
                        update={"template_id": "hidden_gold"}
                    )
                    continue
            obs_board[coord_key] = placed_card.model_copy()

        obs_players = {}
        for p_id, p_state in self.state.players.items():
            obs_players[p_id] = ObservablePlayerState(
                player_id=p_id,
                hand=p_state.hand.copy() if p_id == target_player_id else None,
                hand_size=len(p_state.hand),
                broken_equipments=p_state.broken_equipments.copy(),
            )

        return ObservableMatchState(
            board=obs_board,
            players=obs_players,
            current_player_id=self.state.current_player_id,
            deck_size=len(self.state.deck),
            gold_deck_size=len(self.state.gold_deck),
            is_game_over=self.is_game_over(),
            turn_number=self.state.turn_number,
            round_number=self.state.round_number,
            total_scores=self.state.total_scores.copy(),
        )

    def is_round_over(self) -> bool:
        unrevealed_gold = sum(
            1
            for p in self.state.board.values()
            if isinstance(REGISTRY.get(p.template_id), GoldCardTemplate)
            and not p.is_revealed
        )
        if unrevealed_gold == 0:
            return True
        if (not self.state.deck and
                (not self.state.players[1].card_id_to_template or
                 all("rep_" in word or "brk_" in word or "act_" in word for word in
                     self.state.players[1].card_id_to_template.values()) and
                 (not self.state.players[0].card_id_to_template or
                  all("rep_" in word or "brk_" in word or "act_" in word for word in
                      self.state.players[0].card_id_to_template.values())))):
            return True
        return False

    def is_game_over(self) -> bool:
        return (
            self.state.is_game_over
            or self.state.round_number > self.config.rules.rounds
        )

    def _start_new_round(self):
        round_scores = self.calculate_scores()
        self.state.total_scores[0] += round_scores[0]
        self.state.total_scores[1] += round_scores[1]
        self.state.round_scores = round_scores

        self.state.round_number += 1
        max_rounds = self.config.rules.rounds

        if self.state.round_number > max_rounds:
            self.state.is_game_over = True
            return

        # Чередование первого игрока каждый раунд
        self.state.first_player_in_round = 1 - self.state.first_player_in_round

        self.state.current_player_id = self.state.first_player_in_round
        self.state.turn_number = 1
        self.state.board.clear()
        self.state.deck.clear()
        self.state.deck_template_ids.clear()
        self.state.gold_deck.clear()

        for p_id in [0, 1]:
            self.state.players[p_id].hand.clear()
            self.state.players[p_id].broken_equipments.clear()
            self.state.players[p_id].known_secrets.clear()
            self.state.players[p_id].ladders.clear()
            self.state.players[p_id].card_id_to_template.clear()

        self._build_decks(self.config.deck)
        self._setup_board(self.config.gold, self.config.board.start_positions)
        self._deal_initial_cards(self.config.rules)

    def check_round_end(self) -> Tuple[bool, Optional[Dict[int, int]]]:
        if self.is_round_over():
            self._start_new_round()
            return True, self.state.round_scores
        return False, None

    def calculate_scores(self) -> Dict[int, int]:
        scores = {0: 0, 1: 0}
        for p_card in self.state.board.values():
            tpl = REGISTRY.get(p_card.template_id)
            if (
                isinstance(tpl, GoldCardTemplate)
                and p_card.is_revealed
                and p_card.owner_id is not None
            ):
                scores[p_card.owner_id] += tpl.gold_value
        return scores
