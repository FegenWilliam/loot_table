import random
import json
import os
import signal
import sys


class LootItem:
    def __init__(self, name, weight, gold_value, item_type="misc", quantity=1, rarity=None):
        self.name = name
        self.weight = weight
        self.gold_value = gold_value
        self.item_type = item_type
        self.quantity = quantity
        self.rarity = rarity  # For Equipment items: Normal, Rare, Epic, Legendary
        self.enchantments = []
        self.effects = []  # For Equipment and Upgrade items

    def add_enchantment(self, enchantment):
        self.enchantments.append(enchantment)
        self.gold_value += enchantment.gold_value

    def add_effect(self, effect):
        self.effects.append(effect)

    def get_display_name(self):
        base_name = f"{self.quantity}x {self.name}" if self.quantity > 1 else self.name

        # Add rarity prefix for Equipment items
        if self.rarity:
            base_name = f"[{self.rarity}] {base_name}"

        if self.enchantments:
            enchant_names = ", ".join([e.name for e in self.enchantments])
            return f"{base_name} [{enchant_names}]"
        return base_name

    def get_effects_display(self):
        if not self.effects:
            return ""
        effect_strs = []
        for effect in self.effects:
            if effect.is_percentage:
                effect_strs.append(f"-{effect.value}%")
            else:
                effect_strs.append(f"-{effect.value}")
        return f" (Effects: {', '.join(effect_strs)})"

    def __str__(self):
        return f"{self.get_display_name()} ({self.gold_value}g)"

    def to_string(self, currency_symbol="g"):
        return f"{self.get_display_name()} ({self.gold_value}{currency_symbol})"

    def __repr__(self):
        return self.__str__()


class Enchantment:
    def __init__(self, name, enchant_type, gold_value, weight=1000):
        self.name = name
        self.enchant_type = enchant_type
        self.gold_value = gold_value
        self.weight = weight

    def __str__(self):
        return f"{self.name} ({self.enchant_type}, +{self.gold_value}g)"

    def __repr__(self):
        return self.__str__()


class Effect:
    def __init__(self, effect_type, value, is_percentage=False):
        self.effect_type = effect_type  # e.g., "draw_cost_reduction"
        self.value = value  # numeric value
        self.is_percentage = is_percentage  # True for %, False for flat

    def __str__(self):
        if self.is_percentage:
            return f"{self.effect_type}: -{self.value}%"
        else:
            return f"{self.effect_type}: -{self.value}"

    def __repr__(self):
        return self.__str__()


class EffectTemplate:
    """Template for effects that can be rolled when crafting Equipment/Upgrades."""
    def __init__(self, name, effect_type, value, is_percentage=False, weight=1000):
        self.name = name
        self.effect_type = effect_type
        self.value = value
        self.is_percentage = is_percentage
        self.weight = weight

    def create_effect(self):
        """Create an Effect instance from this template."""
        return Effect(self.effect_type, self.value, self.is_percentage)

    def __str__(self):
        if self.is_percentage:
            return f"{self.name}: {self.effect_type} -{self.value}% (weight: {self.weight})"
        else:
            return f"{self.name}: {self.effect_type} -{self.value} (weight: {self.weight})"

    def __repr__(self):
        return self.__str__()


class RaritySystem:
    def __init__(self):
        # Define rarities with their weights and effect slots
        self.rarities = {
            "Normal": {"weight": 500, "max_effects": 1},
            "Rare": {"weight": 300, "max_effects": 2},
            "Epic": {"weight": 150, "max_effects": 3},
            "Legendary": {"weight": 50, "max_effects": 5}
        }

    def roll_rarity(self):
        """Roll a random rarity based on weights."""
        rarity_names = list(self.rarities.keys())
        weights = [self.rarities[r]["weight"] for r in rarity_names]
        return random.choices(rarity_names, weights=weights, k=1)[0]

    def get_max_effects(self, rarity):
        """Get the maximum number of effects for a given rarity."""
        return self.rarities.get(rarity, {}).get("max_effects", 1)

    def set_weight(self, rarity, weight):
        """Set the weight for a specific rarity."""
        if rarity in self.rarities:
            self.rarities[rarity]["weight"] = weight
            return True
        return False


class CraftingRecipe:
    def __init__(self, output_name, output_type, output_gold_value):
        self.output_name = output_name
        self.output_type = output_type
        self.output_gold_value = output_gold_value
        self.ingredients = []
        self.effects = []  # Effects for Equipment/Upgrade items

    def add_ingredient(self, item_name):
        self.ingredients.append(item_name)

    def add_effect(self, effect):
        self.effects.append(effect)

    def __str__(self):
        ingredient_list = ", ".join(self.ingredients) if self.ingredients else "No ingredients"
        effects_str = f" [Effects: {len(self.effects)}]" if self.effects else ""
        return f"{self.output_name} ({self.output_type}, {self.output_gold_value}g){effects_str} = [{ingredient_list}]"

    def __repr__(self):
        return self.__str__()


class Player:
    def __init__(self, name):
        self.name = name
        self.gold = 0
        self.inventory = []
        self.equipped_items = []  # Items currently equipped
        self.consumed_upgrades = []  # Upgrades that have been consumed

    def add_item(self, item):
        self.inventory.append(item)

    def remove_item(self, index):
        if 0 <= index < len(self.inventory):
            return self.inventory.pop(index)
        return None

    def equip_item(self, item):
        """Equip an equipment item."""
        self.equipped_items.append(item)

    def unequip_item(self, index):
        """Unequip an equipment item and return it."""
        if 0 <= index < len(self.equipped_items):
            return self.equipped_items.pop(index)
        return None

    def consume_upgrade(self, item):
        """Consume an upgrade item permanently."""
        self.consumed_upgrades.append(item)

    def get_total_draw_cost_reduction(self):
        """Calculate total draw cost reduction from equipment and upgrades."""
        flat_reduction = 0
        percentage_reduction = 0

        # Add effects from equipped items
        for item in self.equipped_items:
            for effect in item.effects:
                if effect.effect_type == "draw_cost_reduction":
                    if effect.is_percentage:
                        percentage_reduction += effect.value
                    else:
                        flat_reduction += effect.value

        # Add effects from consumed upgrades
        for item in self.consumed_upgrades:
            for effect in item.effects:
                if effect.effect_type == "draw_cost_reduction":
                    if effect.is_percentage:
                        percentage_reduction += effect.value
                    else:
                        flat_reduction += effect.value

        return flat_reduction, percentage_reduction

    def calculate_draw_cost(self, base_cost):
        """Calculate the actual draw cost after reductions."""
        flat, percent = self.get_total_draw_cost_reduction()

        # Apply percentage reduction first
        cost = base_cost * (1 - percent / 100)

        # Then apply flat reduction
        cost = max(0, cost - flat)  # Don't go below 0

        return int(cost)

    def get_double_quantity_chance(self):
        """Calculate total chance to double item quantity from equipment and upgrades."""
        total_chance = 0

        # Add effects from equipped items
        for item in self.equipped_items:
            for effect in item.effects:
                if effect.effect_type == "double_quantity_chance":
                    total_chance += effect.value

        # Add effects from consumed upgrades
        for item in self.consumed_upgrades:
            for effect in item.effects:
                if effect.effect_type == "double_quantity_chance":
                    total_chance += effect.value

        return min(100, total_chance)  # Cap at 100%

    def add_gold(self, amount):
        self.gold += amount

    def remove_gold(self, amount):
        if self.gold >= amount:
            self.gold -= amount
            return True
        return False


class LootTable:
    def __init__(self, name="Default", draw_cost=100):
        self.name = name
        self.draw_cost = draw_cost
        self.items = []

    def add_item(self, name, weight, gold_value, item_type="misc", quantity=1):
        self.items.append(LootItem(name, weight, gold_value, item_type, quantity))

    def remove_item(self, index):
        if 0 <= index < len(self.items):
            self.items.pop(index)
            return True
        return False

    def edit_item(self, index, new_name=None, new_weight=None, new_gold=None, new_type=None, new_quantity=None):
        if 0 <= index < len(self.items):
            if new_name is not None:
                self.items[index].name = new_name
            if new_weight is not None:
                self.items[index].weight = new_weight
            if new_gold is not None:
                self.items[index].gold_value = new_gold
            if new_type is not None:
                self.items[index].item_type = new_type
            if new_quantity is not None:
                self.items[index].quantity = new_quantity
            return True
        return False

    def draw(self):
        if not self.items:
            return None
        weights = [item.weight for item in self.items]
        return random.choices(self.items, weights=weights, k=1)[0]

    def draw_multiple(self, count):
        if not self.items:
            return []
        weights = [item.weight for item in self.items]
        return random.choices(self.items, weights=weights, k=count)


class GameSystem:
    def __init__(self):
        self.loot_tables = []  # List of LootTable objects
        self.current_table_index = 0  # Currently selected table
        self.players = {}
        self.crafting_recipes = []
        self.enchantments = []
        self.enchant_cost_item = None
        self.enchant_cost_amount = 1
        self.effect_templates = []  # Pool of effects that can be rolled
        self.effect_cost = 100  # Currency cost to roll for an effect
        self.currency_name = "gold"  # Configurable currency name
        self.currency_symbol = "g"  # Configurable currency symbol
        self.rarity_system = RaritySystem()  # Rarity system for equipment
        self.save_file = "loot_system_save_new.json"

    def get_current_table(self):
        if self.loot_tables:
            return self.loot_tables[self.current_table_index]
        return None

    def add_loot_table(self, name, draw_cost=100):
        table = LootTable(name, draw_cost)
        self.loot_tables.append(table)
        return table

    def add_player(self, name):
        if name not in self.players:
            self.players[name] = Player(name)
            return True
        return False

    def get_player(self, name):
        return self.players.get(name)

    def remove_player(self, name):
        if name in self.players:
            del self.players[name]
            return True
        return False

    def save_game(self):
        """Save the game state to a JSON file."""
        try:
            data = {
                'loot_tables': [
                    {
                        'name': table.name,
                        'draw_cost': table.draw_cost,
                        'items': [
                            {
                                'name': item.name,
                                'weight': item.weight,
                                'gold_value': item.gold_value,
                                'item_type': item.item_type,
                                'quantity': item.quantity,
                                'rarity': item.rarity
                            }
                            for item in table.items
                        ]
                    }
                    for table in self.loot_tables
                ],
                'current_table_index': self.current_table_index,
                'players': {
                    name: {
                        'gold': player.gold,
                        'inventory': [
                            {
                                'name': item.name,
                                'weight': item.weight,
                                'gold_value': item.gold_value,
                                'item_type': item.item_type,
                                'quantity': item.quantity,
                                'rarity': item.rarity,
                                'enchantments': [
                                    {
                                        'name': ench.name,
                                        'enchant_type': ench.enchant_type,
                                        'gold_value': ench.gold_value,
                                        'weight': ench.weight
                                    }
                                    for ench in item.enchantments
                                ],
                                'effects': [
                                    {
                                        'effect_type': eff.effect_type,
                                        'value': eff.value,
                                        'is_percentage': eff.is_percentage
                                    }
                                    for eff in item.effects
                                ]
                            }
                            for item in player.inventory
                        ],
                        'equipped_items': [
                            {
                                'name': item.name,
                                'weight': item.weight,
                                'gold_value': item.gold_value,
                                'item_type': item.item_type,
                                'quantity': item.quantity,
                                'rarity': item.rarity,
                                'effects': [
                                    {
                                        'effect_type': eff.effect_type,
                                        'value': eff.value,
                                        'is_percentage': eff.is_percentage
                                    }
                                    for eff in item.effects
                                ]
                            }
                            for item in player.equipped_items
                        ],
                        'consumed_upgrades': [
                            {
                                'name': item.name,
                                'weight': item.weight,
                                'gold_value': item.gold_value,
                                'item_type': item.item_type,
                                'quantity': item.quantity,
                                'rarity': item.rarity,
                                'effects': [
                                    {
                                        'effect_type': eff.effect_type,
                                        'value': eff.value,
                                        'is_percentage': eff.is_percentage
                                    }
                                    for eff in item.effects
                                ]
                            }
                            for item in player.consumed_upgrades
                        ]
                    }
                    for name, player in self.players.items()
                },
                'crafting_recipes': [
                    {
                        'output_name': recipe.output_name,
                        'output_type': recipe.output_type,
                        'output_gold_value': recipe.output_gold_value,
                        'ingredients': recipe.ingredients,
                        'effects': [
                            {
                                'effect_type': eff.effect_type,
                                'value': eff.value,
                                'is_percentage': eff.is_percentage
                            }
                            for eff in recipe.effects
                        ]
                    }
                    for recipe in self.crafting_recipes
                ],
                'enchantments': [
                    {
                        'name': ench.name,
                        'enchant_type': ench.enchant_type,
                        'gold_value': ench.gold_value,
                        'weight': ench.weight
                    }
                    for ench in self.enchantments
                ],
                'enchant_cost_item': self.enchant_cost_item,
                'enchant_cost_amount': self.enchant_cost_amount,
                'effect_templates': [
                    {
                        'name': eff_tmpl.name,
                        'effect_type': eff_tmpl.effect_type,
                        'value': eff_tmpl.value,
                        'is_percentage': eff_tmpl.is_percentage,
                        'weight': eff_tmpl.weight
                    }
                    for eff_tmpl in self.effect_templates
                ],
                'effect_cost': self.effect_cost,
                'currency_name': self.currency_name,
                'currency_symbol': self.currency_symbol,
                'rarity_weights': {
                    rarity: data['weight']
                    for rarity, data in self.rarity_system.rarities.items()
                }
            }

            with open(self.save_file, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_game(self):
        """Load the game state from a JSON file."""
        if not os.path.exists(self.save_file):
            return False

        try:
            with open(self.save_file, 'r') as f:
                data = json.load(f)

            # Load loot tables (with backward compatibility)
            self.loot_tables = []
            if 'loot_tables' in data:
                # New format: multiple tables
                for table_data in data['loot_tables']:
                    table = LootTable(table_data.get('name', 'Default'), table_data.get('draw_cost', 100))
                    for item_data in table_data.get('items', []):
                        item = LootItem(
                            item_data['name'],
                            item_data['weight'],
                            item_data['gold_value'],
                            item_data.get('item_type', 'misc'),
                            item_data.get('quantity', 1),
                            item_data.get('rarity')
                        )
                        table.items.append(item)
                    self.loot_tables.append(table)
                self.current_table_index = data.get('current_table_index', 0)
            elif 'loot_table' in data:
                # Old format: single table - convert it
                table = LootTable("Default", 100)
                for item_data in data.get('loot_table', []):
                    item = LootItem(
                        item_data['name'],
                        item_data['weight'],
                        item_data['gold_value'],
                        item_data.get('item_type', 'misc'),
                        item_data.get('quantity', 1),
                        item_data.get('rarity')
                    )
                    table.items.append(item)
                self.loot_tables.append(table)
                self.current_table_index = 0

            # If no tables exist, create a default one
            if not self.loot_tables:
                self.loot_tables.append(LootTable("Default", 100))
                self.current_table_index = 0

            # Load players
            self.players = {}
            for name, player_data in data.get('players', {}).items():
                player = Player(name)
                player.gold = player_data['gold']

                # Load inventory
                for item_data in player_data.get('inventory', []):
                    item = LootItem(
                        item_data['name'],
                        item_data['weight'],
                        item_data['gold_value'],
                        item_data.get('item_type', 'misc'),
                        item_data.get('quantity', 1),
                        item_data.get('rarity')
                    )
                    # Load enchantments
                    for ench_data in item_data.get('enchantments', []):
                        ench = Enchantment(
                            ench_data['name'],
                            ench_data['enchant_type'],
                            ench_data['gold_value'],
                            ench_data.get('weight', 1000)
                        )
                        item.enchantments.append(ench)
                    # Load effects
                    for eff_data in item_data.get('effects', []):
                        eff = Effect(
                            eff_data['effect_type'],
                            eff_data['value'],
                            eff_data.get('is_percentage', False)
                        )
                        item.add_effect(eff)
                    player.add_item(item)

                # Load equipped items
                for item_data in player_data.get('equipped_items', []):
                    item = LootItem(
                        item_data['name'],
                        item_data['weight'],
                        item_data['gold_value'],
                        item_data.get('item_type', 'misc'),
                        item_data.get('quantity', 1),
                        item_data.get('rarity')
                    )
                    # Load effects
                    for eff_data in item_data.get('effects', []):
                        eff = Effect(
                            eff_data['effect_type'],
                            eff_data['value'],
                            eff_data.get('is_percentage', False)
                        )
                        item.add_effect(eff)
                    player.equip_item(item)

                # Load consumed upgrades
                for item_data in player_data.get('consumed_upgrades', []):
                    item = LootItem(
                        item_data['name'],
                        item_data['weight'],
                        item_data['gold_value'],
                        item_data.get('item_type', 'misc'),
                        item_data.get('quantity', 1),
                        item_data.get('rarity')
                    )
                    # Load effects
                    for eff_data in item_data.get('effects', []):
                        eff = Effect(
                            eff_data['effect_type'],
                            eff_data['value'],
                            eff_data.get('is_percentage', False)
                        )
                        item.add_effect(eff)
                    player.consume_upgrade(item)

                self.players[name] = player

            # Load crafting recipes
            self.crafting_recipes = []
            for recipe_data in data.get('crafting_recipes', []):
                recipe = CraftingRecipe(
                    recipe_data['output_name'],
                    recipe_data['output_type'],
                    recipe_data['output_gold_value']
                )
                recipe.ingredients = recipe_data['ingredients']
                # Load effects
                for eff_data in recipe_data.get('effects', []):
                    eff = Effect(
                        eff_data['effect_type'],
                        eff_data['value'],
                        eff_data.get('is_percentage', False)
                    )
                    recipe.add_effect(eff)
                self.crafting_recipes.append(recipe)

            # Load enchantments
            self.enchantments = []
            for ench_data in data.get('enchantments', []):
                ench = Enchantment(
                    ench_data['name'],
                    ench_data['enchant_type'],
                    ench_data['gold_value'],
                    ench_data.get('weight', 1000)
                )
                self.enchantments.append(ench)

            # Load global enchantment cost
            self.enchant_cost_item = data.get('enchant_cost_item')
            self.enchant_cost_amount = data.get('enchant_cost_amount', 1)

            # Load effect templates
            self.effect_templates = []
            for eff_tmpl_data in data.get('effect_templates', []):
                eff_tmpl = EffectTemplate(
                    eff_tmpl_data['name'],
                    eff_tmpl_data['effect_type'],
                    eff_tmpl_data['value'],
                    eff_tmpl_data.get('is_percentage', False),
                    eff_tmpl_data.get('weight', 1000)
                )
                self.effect_templates.append(eff_tmpl)

            # Load effect cost
            self.effect_cost = data.get('effect_cost', 100)

            # Load currency settings
            self.currency_name = data.get('currency_name', 'gold')
            self.currency_symbol = data.get('currency_symbol', 'g')

            # Load rarity weights
            if 'rarity_weights' in data:
                for rarity, weight in data['rarity_weights'].items():
                    self.rarity_system.set_weight(rarity, weight)

            return True
        except Exception as e:
            print(f"Error loading: {e}")
            import traceback
            traceback.print_exc()
            return False


def show_main_menu():
    print("\n" + "=" * 40)
    print("LOOT TABLE SYSTEM")
    print("=" * 40)
    print("1. Manage Loot Table")
    print("2. Manage Players")
    print("3. Draw Items")
    print("4. Sell Items")
    print("5. Crafting Menu")
    print("6. Equipment & Upgrades")
    print("7. Admin Menu")
    print("8. Save Game")
    print("9. Exit")
    print("=" * 40)


def show_loot_menu():
    print("\n--- LOOT TABLE MENU ---")
    print("1. Select/Create loot table")
    print("2. Add item to current table")
    print("3. Edit item in current table")
    print("4. Delete item from current table")
    print("5. Edit table settings (name, draw cost)")
    print("6. Delete current table")
    print("7. View all items in current table (with weights)")
    print("8. View rates for players (percentages only)")
    print("9. View all tables")
    print("10. Back to main menu")


def show_player_menu():
    print("\n--- PLAYER MENU ---")
    print("1. Add player")
    print("2. Remove player")
    print("3. View player info")
    print("4. View all players")
    print("5. Back to main menu")


def show_admin_menu(currency_name="gold"):
    print("\n--- ADMIN MENU ---")
    print(f"1. Give {currency_name} to player")
    print(f"2. Take {currency_name} from player")
    print("3. Gift item to player")
    print("4. Take item from player")
    print("5. Change currency settings")
    print("6. Configure rarity weights")
    print("7. Manage effect pool")
    print("8. Back to main menu")


def show_crafting_menu():
    print("\n--- CRAFTING MENU ---")
    print("1. Add crafting recipe")
    print("2. Delete crafting recipe")
    print("3. View all recipes")
    print("4. Craft item (player)")
    print("5. Enchantment Menu")
    print("6. Back to main menu")


def show_effect_pool_menu():
    print("\n--- EFFECT POOL MENU ---")
    print("1. Add effect template")
    print("2. Edit effect template")
    print("3. Delete effect template")
    print("4. View all effect templates")
    print("5. Set effect roll cost")
    print("6. Back to admin menu")


def show_enchantment_menu():
    print("\n--- ENCHANTMENT MENU ---")
    print("1. Add enchantment")
    print("2. Edit enchantment")
    print("3. Delete enchantment")
    print("4. Set global enchantment cost")
    print("5. View all enchantments")
    print("6. Enchant item (player)")
    print("7. Back to crafting menu")


def show_equipment_menu():
    print("\n--- EQUIPMENT & UPGRADES MENU ---")
    print("1. View player equipment & upgrades")
    print("2. Equip item")
    print("3. Unequip item")
    print("4. Consume upgrade")
    print("5. Back to main menu")


def manage_effect_pool(game):
    """Manage the pool of effect templates that can be rolled when crafting."""
    while True:
        show_effect_pool_menu()
        choice = input("Enter choice: ").strip()

        if choice == "1":
            # Add effect template
            name = input("Enter effect template name: ").strip()
            if not name:
                print("Name cannot be empty!")
                continue

            print("\nAvailable effect types:")
            print("  1. draw_cost_reduction")
            print("  2. double_quantity_chance")
            effect_type_choice = input("Choose effect type (1-2): ").strip()

            if effect_type_choice == '1':
                effect_type = "draw_cost_reduction"
            elif effect_type_choice == '2':
                effect_type = "double_quantity_chance"
            else:
                print("Invalid effect type!")
                continue

            try:
                value = float(input("Enter effect value: ").strip())
                if value <= 0:
                    print("Value must be greater than 0!")
                    continue

                is_percentage_input = input("Is this a percentage value? (y/n): ").strip().lower()
                is_percentage = is_percentage_input == 'y'

                weight = float(input("Enter weight (default 1000): ").strip() or "1000")
                if weight <= 0:
                    print("Weight must be greater than 0!")
                    continue

                effect_tmpl = EffectTemplate(name, effect_type, value, is_percentage, weight)
                game.effect_templates.append(effect_tmpl)
                print(f"✓ Added effect template: {effect_tmpl}")
            except ValueError:
                print("Invalid input!")

        elif choice == "2":
            # Edit effect template
            if not game.effect_templates:
                print("No effect templates exist!")
                continue

            print("\nCurrent effect templates:")
            for i, tmpl in enumerate(game.effect_templates):
                print(f"  {i}. {tmpl}")

            try:
                index = int(input("\nEnter effect template number to edit: ").strip())
                if index < 0 or index >= len(game.effect_templates):
                    print("Invalid template number!")
                    continue

                tmpl = game.effect_templates[index]
                print(f"\nEditing: {tmpl.name}")
                print("Leave blank to keep current value")

                new_name = input(f"New name [{tmpl.name}]: ").strip()
                weight_input = input(f"New weight [{tmpl.weight}]: ").strip()
                value_input = input(f"New value [{tmpl.value}]: ").strip()

                if new_name:
                    tmpl.name = new_name
                if weight_input:
                    tmpl.weight = float(weight_input)
                if value_input:
                    tmpl.value = float(value_input)

                print(f"✓ Updated effect template!")
            except ValueError:
                print("Invalid input!")

        elif choice == "3":
            # Delete effect template
            if not game.effect_templates:
                print("No effect templates exist!")
                continue

            print("\nCurrent effect templates:")
            for i, tmpl in enumerate(game.effect_templates):
                print(f"  {i}. {tmpl}")

            try:
                index = int(input("\nEnter effect template number to delete: ").strip())
                if 0 <= index < len(game.effect_templates):
                    deleted = game.effect_templates.pop(index)
                    print(f"✓ Deleted effect template: {deleted.name}")
                else:
                    print("Invalid template number!")
            except ValueError:
                print("Invalid input!")

        elif choice == "4":
            # View all effect templates
            if not game.effect_templates:
                print("No effect templates exist!")
                continue

            print(f"\n{'=' * 60}")
            print(f"Effect Roll Cost: {game.effect_cost}{game.currency_symbol}")
            print(f"{'=' * 60}")
            print("\nAll Effect Templates:")
            total_weight = sum(t.weight for t in game.effect_templates)
            for i, tmpl in enumerate(game.effect_templates):
                percentage = (tmpl.weight / total_weight) * 100
                print(f"  {i}. {tmpl.name}: {tmpl.effect_type}")
                if tmpl.is_percentage:
                    print(f"      Value: {tmpl.value}%")
                else:
                    print(f"      Value: {tmpl.value}")
                print(f"      Weight: {tmpl.weight} ({percentage:.2f}%)")
                print()

        elif choice == "5":
            # Set effect roll cost
            print(f"\nCurrent effect roll cost: {game.effect_cost}{game.currency_symbol}")
            try:
                new_cost = int(input(f"Enter new cost (in {game.currency_name}): ").strip())
                if new_cost < 0:
                    print("Cost cannot be negative!")
                    continue
                game.effect_cost = new_cost
                print(f"✓ Effect roll cost set to {game.effect_cost}{game.currency_symbol}")
            except ValueError:
                print("Invalid input!")

        elif choice == "6":
            break


def manage_equipment_upgrades(game):
    while True:
        show_equipment_menu()
        choice = input("Enter choice: ").strip()

        if choice == "1":
            # View player equipment & upgrades
            if not game.players:
                print("No players exist!")
                continue

            name = input("Enter player name: ").strip()
            player = game.get_player(name)
            if not player:
                print(f"Player '{name}' not found!")
                continue

            print(f"\n--- {player.name}'s Equipment & Upgrades ---")

            flat, percent = player.get_total_draw_cost_reduction()
            print(f"Total Draw Cost Reduction: -{flat} flat, -{percent}%")

            print(f"\nEquipped Items ({len(player.equipped_items)}):")
            if player.equipped_items:
                for i, item in enumerate(player.equipped_items):
                    effects_str = ", ".join([str(e) for e in item.effects])
                    print(f"  {i}. {item.name} [{effects_str}]")
            else:
                print("  (none)")

            print(f"\nConsumed Upgrades ({len(player.consumed_upgrades)}):")
            if player.consumed_upgrades:
                for item in player.consumed_upgrades:
                    effects_str = ", ".join([str(e) for e in item.effects])
                    print(f"  - {item.name} [{effects_str}]")
            else:
                print("  (none)")

        elif choice == "2":
            # Equip item
            if not game.players:
                print("No players exist!")
                continue

            name = input("Enter player name: ").strip()
            player = game.get_player(name)
            if not player:
                print(f"Player '{name}' not found!")
                continue

            # Filter for Equipment items in inventory
            equipment_items = [(i, item) for i, item in enumerate(player.inventory) if item.item_type.lower() == "equipment"]

            if not equipment_items:
                print(f"{player.name} has no equipment items to equip!")
                continue

            print(f"\n{player.name}'s Equipment Items:")
            for idx, (inv_idx, item) in enumerate(equipment_items):
                effects_str = ", ".join([str(e) for e in item.effects]) if item.effects else "No effects"
                print(f"  {idx}. {item.name} [{effects_str}]")

            try:
                choice_idx = int(input("\nEnter item number to equip: ").strip())
                if 0 <= choice_idx < len(equipment_items):
                    inv_idx, item = equipment_items[choice_idx]
                    player.remove_item(inv_idx)
                    player.equip_item(item)
                    print(f"✓ Equipped {item.name}!")
                else:
                    print("Invalid item number!")
            except ValueError:
                print("Invalid input!")

        elif choice == "3":
            # Unequip item
            if not game.players:
                print("No players exist!")
                continue

            name = input("Enter player name: ").strip()
            player = game.get_player(name)
            if not player:
                print(f"Player '{name}' not found!")
                continue

            if not player.equipped_items:
                print(f"{player.name} has no equipped items!")
                continue

            print(f"\n{player.name}'s Equipped Items:")
            for i, item in enumerate(player.equipped_items):
                effects_str = ", ".join([str(e) for e in item.effects])
                print(f"  {i}. {item.name} [{effects_str}]")

            try:
                index = int(input("\nEnter item number to unequip: ").strip())
                item = player.unequip_item(index)
                if item:
                    player.add_item(item)
                    print(f"✓ Unequipped {item.name}!")
                else:
                    print("Invalid item number!")
            except ValueError:
                print("Invalid input!")

        elif choice == "4":
            # Consume upgrade
            if not game.players:
                print("No players exist!")
                continue

            name = input("Enter player name: ").strip()
            player = game.get_player(name)
            if not player:
                print(f"Player '{name}' not found!")
                continue

            # Filter for Upgrade items in inventory
            upgrade_items = [(i, item) for i, item in enumerate(player.inventory) if item.item_type.lower() == "upgrade"]

            if not upgrade_items:
                print(f"{player.name} has no upgrade items to consume!")
                continue

            print(f"\n{player.name}'s Upgrade Items:")
            for idx, (inv_idx, item) in enumerate(upgrade_items):
                effects_str = ", ".join([str(e) for e in item.effects]) if item.effects else "No effects"
                print(f"  {idx}. {item.name} [{effects_str}]")

            try:
                choice_idx = int(input("\nEnter item number to consume: ").strip())
                if 0 <= choice_idx < len(upgrade_items):
                    inv_idx, item = upgrade_items[choice_idx]
                    player.remove_item(inv_idx)
                    player.consume_upgrade(item)
                    print(f"✓ Consumed {item.name}! Effects are now permanently applied.")
                else:
                    print("Invalid item number!")
            except ValueError:
                print("Invalid input!")

        elif choice == "5":
            break


def manage_loot_table(game):
    while True:
        current_table = game.get_current_table()
        if current_table:
            print(
                f"\n[Current Table: {current_table.name} (Draw Cost: {current_table.draw_cost}g, Items: {len(current_table.items)})]")
        else:
            print("\n[No tables exist! Please create one]")

        show_loot_menu()
        choice = input("Enter choice: ").strip()

        if choice == "1":
            # Select/Create loot table
            if game.loot_tables:
                print("\nExisting tables:")
                for i, table in enumerate(game.loot_tables):
                    marker = " <--" if i == game.current_table_index else ""
                    print(f"  {i}. {table.name} (Draw Cost: {table.draw_cost}g, Items: {len(table.items)}){marker}")

                print("\nEnter table number to select, or 'new' to create new table")
                selection = input("Choice: ").strip().lower()

                if selection == 'new':
                    name = input("Enter new table name: ").strip() or "Unnamed Table"
                    try:
                        cost = int(input("Enter draw cost (default 100): ").strip() or "100")
                        game.add_loot_table(name, cost)
                        game.current_table_index = len(game.loot_tables) - 1
                        print(f"✓ Created and selected table '{name}'")
                    except ValueError:
                        print("Invalid cost!")
                else:
                    try:
                        index = int(selection)
                        if 0 <= index < len(game.loot_tables):
                            game.current_table_index = index
                            print(f"✓ Selected table '{game.loot_tables[index].name}'")
                        else:
                            print("Invalid table number!")
                    except ValueError:
                        print("Invalid input!")
            else:
                # No tables exist, create first one
                name = input("Enter table name (default 'Default'): ").strip() or "Default"
                try:
                    cost = int(input("Enter draw cost (default 100): ").strip() or "100")
                    game.add_loot_table(name, cost)
                    game.current_table_index = 0
                    print(f"✓ Created table '{name}'")
                except ValueError:
                    print("Invalid cost!")

        elif choice == "2":
            # Add item
            if not current_table:
                print("No table selected!")
                continue

            name = input("Enter item name: ").strip()
            if not name:
                print("Item name cannot be empty!")
                continue

            try:
                quantity = int(input("Enter quantity (default 1): ").strip() or "1")
                weight = float(input("Enter weight: ").strip())
                gold = int(input(f"Enter {game.currency_name} value: ").strip())
                if weight <= 0 or gold < 0 or quantity < 1:
                    print("Invalid values!")
                    continue

                item_type = input("Enter item type (e.g., weapon, armor, misc): ").strip() or "misc"

                current_table.add_item(name, weight, gold, item_type, quantity)
                display_name = f"{quantity}x {name}" if quantity > 1 else name
                print(f"✓ Added '{display_name}' to {current_table.name}")
            except ValueError:
                print("Invalid input!")

        elif choice == "3":
            # Edit item
            if not current_table or not current_table.items:
                print("No items in current table!")
                continue

            print("\nCurrent items:")
            for i, item in enumerate(current_table.items):
                print(f"  {i}. {item.get_display_name()} (weight: {item.weight}, value: {item.gold_value}{game.currency_symbol}, type: {item.item_type})")

            try:
                index = int(input("\nEnter item number to edit: ").strip())
                if index < 0 or index >= len(current_table.items):
                    print("Invalid item number!")
                    continue

                item = current_table.items[index]
                print(f"\nEditing: {item.get_display_name()}")
                print("Leave blank to keep current value")

                new_name = input(f"New name [{item.name}]: ").strip()
                quantity_input = input(f"New quantity [{item.quantity}]: ").strip()
                weight_input = input(f"New weight [{item.weight}]: ").strip()
                gold_input = input(f"New {game.currency_name} value [{item.gold_value}]: ").strip()
                type_input = input(f"New type [{item.item_type}]: ").strip()

                new_quantity = int(quantity_input) if quantity_input else None
                new_weight = float(weight_input) if weight_input else None
                new_gold = int(gold_input) if gold_input else None
                new_type = type_input if type_input else None

                current_table.edit_item(index, new_name if new_name else None, new_weight, new_gold, new_type, new_quantity)
                print(f"✓ Updated item!")
            except ValueError:
                print("Invalid input!")

        elif choice == "4":
            # Delete item
            if not current_table or not current_table.items:
                print("No items in current table!")
                continue

            print("\nCurrent items:")
            for i, item in enumerate(current_table.items):
                print(f"  {i}. {item.get_display_name()} (weight: {item.weight}, value: {item.gold_value}{game.currency_symbol}, type: {item.item_type})")

            try:
                index = int(input("\nEnter item number to delete: ").strip())
                if index < 0 or index >= len(current_table.items):
                    print("Invalid item number!")
                    continue

                item_display_name = current_table.items[index].get_display_name()
                current_table.remove_item(index)
                print(f"✓ Deleted '{item_display_name}'")
            except ValueError:
                print("Invalid input!")

        elif choice == "5":
            # Edit table settings
            if not current_table:
                print("No table selected!")
                continue

            print(f"\nEditing table: {current_table.name}")
            print("Leave blank to keep current value")

            new_name = input(f"New name [{current_table.name}]: ").strip()
            cost_input = input(f"New draw cost [{current_table.draw_cost}]: ").strip()

            if new_name:
                current_table.name = new_name
            if cost_input:
                try:
                    current_table.draw_cost = int(cost_input)
                except ValueError:
                    print("Invalid cost, keeping old value")

            print(f"✓ Updated table settings!")

        elif choice == "6":
            # Delete table
            if not current_table:
                print("No table to delete!")
                continue

            if len(game.loot_tables) == 1:
                print("Cannot delete the last table!")
                continue

            confirm = input(f"Delete table '{current_table.name}'? (y/n): ").strip().lower()
            if confirm == 'y':
                deleted_name = current_table.name
                game.loot_tables.pop(game.current_table_index)
                game.current_table_index = min(game.current_table_index, len(game.loot_tables) - 1)
                print(f"✓ Deleted table '{deleted_name}'")

        elif choice == "7":
            # View all items
            if not current_table or not current_table.items:
                print("No items in current table!")
                continue

            print(f"\n{current_table.name} (Admin View):")
            total_weight = sum(item.weight for item in current_table.items)
            for item in current_table.items:
                percentage = (item.weight / total_weight) * 100
                print(f"  - {item.get_display_name()}: weight {item.weight} ({percentage:.2f}%), value {item.gold_value}{game.currency_symbol}")

        elif choice == "8":
            # View rates for players
            if not current_table or not current_table.items:
                print("No items in current table!")
                continue

            print("\n" + "=" * 50)
            print(f"{current_table.name.upper()} - RATES")
            print(f"Draw Cost: {current_table.draw_cost}{game.currency_symbol}")
            print("=" * 50)
            total_weight = sum(item.weight for item in current_table.items)

            sorted_items = sorted(current_table.items, key=lambda x: x.weight)

            for item in sorted_items:
                percentage = (item.weight / total_weight) * 100
                print(f"  {item.get_display_name()}")
                print(f"    Type: {item.item_type}")
                print(f"    Drop Rate: {percentage:.2f}%")
                print(f"    Value: {item.gold_value}{game.currency_symbol}")
                print()

        elif choice == "9":
            # View all tables
            if not game.loot_tables:
                print("No tables exist!")
                continue

            print("\nAll Loot Tables:")
            for i, table in enumerate(game.loot_tables):
                marker = " <-- CURRENT" if i == game.current_table_index else ""
                print(f"  {i}. {table.name} (Draw Cost: {table.draw_cost}g, Items: {len(table.items)}){marker}")

        elif choice == "10":
            break


def manage_players(game):
    while True:
        show_player_menu()
        choice = input("Enter choice: ").strip()

        if choice == "1":
            name = input("Enter player name: ").strip()
            if not name:
                print("Name cannot be empty!")
                continue

            if game.add_player(name):
                print(f"✓ Added player '{name}'")
            else:
                print(f"Player '{name}' already exists!")

        elif choice == "2":
            if not game.players:
                print("No players exist!")
                continue

            name = input("Enter player name to remove: ").strip()
            if game.remove_player(name):
                print(f"✓ Removed player '{name}'")
            else:
                print(f"Player '{name}' not found!")

        elif choice == "3":
            if not game.players:
                print("No players exist!")
                continue

            name = input("Enter player name: ").strip()
            player = game.get_player(name)
            if player:
                print(f"\n--- {player.name} ---")
                print(f"{game.currency_name.capitalize()}: {player.gold}{game.currency_symbol}")
                print(f"Inventory ({len(player.inventory)} items):")
                for i, item in enumerate(player.inventory):
                    print(f"  {i}. {item}")
            else:
                print(f"Player '{name}' not found!")

        elif choice == "4":
            if not game.players:
                print("No players exist!")
                continue

            print("\nAll Players:")
            for name, player in game.players.items():
                print(f"  - {name}: {player.gold}{game.currency_symbol}, {len(player.inventory)} items")

        elif choice == "5":
            break


def draw_items_menu(game):
    if not game.loot_tables:
        print("No loot tables exist! Create one first.")
        return

    if not game.players:
        print("No players exist! Add players first.")
        return

    # Select table
    print("\nAvailable loot tables:")
    for i, table in enumerate(game.loot_tables):
        print(f"  {i}. {table.name} (Cost: {table.draw_cost}g per draw, Items: {len(table.items)})")

    try:
        table_index = int(input("\nSelect table number: ").strip())
        if table_index < 0 or table_index >= len(game.loot_tables):
            print("Invalid table number!")
            return

        selected_table = game.loot_tables[table_index]

        if not selected_table.items:
            print(f"Table '{selected_table.name}' has no items!")
            return

        print("\nAvailable players:")
        for name, player in game.players.items():
            print(f"  - {name} ({player.gold}{game.currency_symbol})")

        player_name = input("\nEnter player name: ").strip()
        player = game.get_player(player_name)

        if not player:
            print(f"Player '{player_name}' not found!")
            return

        # Calculate actual draw cost with reductions
        base_cost = selected_table.draw_cost
        actual_cost = player.calculate_draw_cost(base_cost)

        flat, percent = player.get_total_draw_cost_reduction()
        reduction_info = ""
        if flat > 0 or percent > 0:
            reduction_info = f" (Base: {base_cost}{game.currency_symbol}, -{flat} flat, -{percent}%)"

        count = int(input(f"How many items to draw? (Cost: {actual_cost}{game.currency_symbol} per draw{reduction_info}): ").strip())
        if count <= 0:
            print("Count must be greater than 0!")
            return

        total_cost = count * actual_cost

        if player.gold < total_cost:
            print(f"❌ Not enough {game.currency_name}! Need {total_cost}{game.currency_symbol} but {player.name} only has {player.gold}{game.currency_symbol}")
            return

        player.remove_gold(total_cost)

        items = selected_table.draw_multiple(count)
        print(f"\n💰 Paid {total_cost}{game.currency_symbol} ({count} x {actual_cost}{game.currency_symbol}) to {selected_table.name}")
        print(f"🎲 {player.name} drew {count} items:")

        # Get double quantity chance
        double_chance = player.get_double_quantity_chance()

        total_value = 0
        doubled_count = 0

        for i, item in enumerate(items, 1):
            # Check if we should double the quantity
            if double_chance > 0 and random.random() * 100 < double_chance:
                item.quantity *= 2
                doubled_count += 1
                print(f"  {i}. {item} ✨ DOUBLED!")
            else:
                print(f"  {i}. {item}")

            player.add_item(item)
            total_value += item.gold_value

        if doubled_count > 0:
            print(f"\n✨ {doubled_count} item(s) had their quantity doubled! (Chance: {double_chance}%)")

        net_value = total_value - total_cost
        print(f"\nTotal value: {total_value}{game.currency_symbol}")
        print(f"Net gain/loss: {net_value:+d}{game.currency_symbol}")
        print(f"{player.name}'s {game.currency_name}: {player.gold}{game.currency_symbol} | Inventory: {len(player.inventory)} items")
    except ValueError:
        print("Invalid input!")


def sell_items_menu(game):
    if not game.players:
        print("No players exist! Add players first.")
        return

    print("\nAvailable players:")
    for name, player in game.players.items():
        print(f"  - {name} ({player.gold}{game.currency_symbol}, {len(player.inventory)} items)")

    player_name = input("\nEnter player name: ").strip()
    player = game.get_player(player_name)

    if not player:
        print(f"Player '{player_name}' not found!")
        return

    if not player.inventory:
        print(f"{player.name} has no items to sell!")
        return

    while True:
        print(f"\n--- {player.name}'s Inventory ---")
        print(f"{game.currency_name.capitalize()}: {player.gold}{game.currency_symbol}")
        print("\nItems:")
        for i, item in enumerate(player.inventory):
            print(f"  {i}. {item}")

        print("\nEnter item number to sell (or 'back' to return)")
        choice = input("Choice: ").strip().lower()

        if choice == 'back':
            break

        try:
            index = int(choice)
            if index < 0 or index >= len(player.inventory):
                print("Invalid item number!")
                continue

            item = player.inventory[index]
            player.remove_item(index)
            player.add_gold(item.gold_value)
            print(f"✓ Sold {item.name} for {item.gold_value}{game.currency_symbol}!")
            print(f"New {game.currency_name} balance: {player.gold}{game.currency_symbol}")

            if not player.inventory:
                print(f"\n{player.name} has sold all items!")
                break

        except ValueError:
            print("Invalid input! Enter a number or 'back'")


def manage_crafting(game):
    while True:
        show_crafting_menu()
        choice = input("Enter choice: ").strip()

        if choice == "1":
            output_name = input("Enter output item name: ").strip()
            if not output_name:
                print("Name cannot be empty!")
                continue

            output_type = input("Enter output item type: ").strip() or "misc"

            try:
                output_gold = int(input(f"Enter output {game.currency_name} value: ").strip())
                if output_gold < 0:
                    print(f"Invalid {game.currency_name} value!")
                    continue

                recipe = CraftingRecipe(output_name, output_type, output_gold)

                print("\nAdd ingredients (enter item names from loot table)")
                print("Available items from all tables:")
                # Show items from all tables
                all_item_names = set()
                for table in game.loot_tables:
                    for item in table.items:
                        all_item_names.add(item.name)
                for item_name in sorted(all_item_names):
                    print(f"  - {item_name}")

                print("\nType 'done' when finished adding ingredients")
                while True:
                    ingredient = input("Add ingredient: ").strip()
                    if ingredient.lower() == 'done':
                        break
                    if ingredient:
                        recipe.add_ingredient(ingredient)
                        print(f"✓ Added {ingredient}")

                if not recipe.ingredients:
                    print("Recipe must have at least one ingredient!")
                    continue

                game.crafting_recipes.append(recipe)
                print(f"✓ Added recipe: {recipe}")
            except ValueError:
                print("Invalid input!")

        elif choice == "2":
            if not game.crafting_recipes:
                print("No recipes exist!")
                continue

            print("\nCurrent recipes:")
            for i, recipe in enumerate(game.crafting_recipes):
                print(f"  {i}. {recipe}")

            try:
                index = int(input("\nEnter recipe number to delete: ").strip())
                if 0 <= index < len(game.crafting_recipes):
                    deleted = game.crafting_recipes.pop(index)
                    print(f"✓ Deleted recipe: {deleted.output_name}")
                else:
                    print("Invalid recipe number!")
            except ValueError:
                print("Invalid input!")

        elif choice == "3":
            if not game.crafting_recipes:
                print("No recipes exist!")
                continue

            print("\nAll Crafting Recipes:")
            for i, recipe in enumerate(game.crafting_recipes):
                print(f"  {i}. {recipe}")

        elif choice == "4":
            if not game.crafting_recipes:
                print("No recipes exist!")
                continue

            if not game.players:
                print("No players exist!")
                continue

            print("\nAvailable players:")
            for name, player in game.players.items():
                print(f"  - {name}")

            player_name = input("\nEnter player name: ").strip()
            player = game.get_player(player_name)

            if not player:
                print(f"Player '{player_name}' not found!")
                continue

            print("\nAvailable recipes:")
            for i, recipe in enumerate(game.crafting_recipes):
                print(f"  {i}. {recipe}")

            try:
                recipe_index = int(input("\nEnter recipe number to craft: ").strip())
                if recipe_index < 0 or recipe_index >= len(game.crafting_recipes):
                    print("Invalid recipe number!")
                    continue

                recipe = game.crafting_recipes[recipe_index]
                crafted_count = 0

                print(f"\nCrafting {recipe.output_name}...")
                print("Type 'done' to stop crafting, or it will auto-stop when out of ingredients")

                while True:
                    # Check if player has all ingredients
                    player_item_names = [item.name for item in player.inventory]
                    missing_ingredients = []

                    for ingredient in recipe.ingredients:
                        if ingredient not in player_item_names:
                            missing_ingredients.append(ingredient)

                    if missing_ingredients:
                        if crafted_count > 0:
                            print(f"\n❌ Out of ingredients! Missing: {', '.join(missing_ingredients)}")
                        else:
                            print(f"❌ Missing ingredients: {', '.join(missing_ingredients)}")
                        break

                    # Remove ingredients from inventory
                    for ingredient in recipe.ingredients:
                        for i, item in enumerate(player.inventory):
                            if item.name == ingredient:
                                player.remove_item(i)
                                break

                    # Create and add crafted item
                    crafted_item = LootItem(recipe.output_name, 0, recipe.output_gold_value, recipe.output_type)

                    # If Equipment or Upgrade, allow player to roll for effects
                    if recipe.output_type.lower() in ["equipment", "upgrade"]:
                        if not game.effect_templates:
                            print(f"\n⚠️  No effect templates available! Item crafted without effects.")
                            if recipe.output_type.lower() == "equipment":
                                rarity = game.rarity_system.roll_rarity()
                                crafted_item.rarity = rarity
                                print(f"✓ Crafted [{rarity}] {recipe.output_name} (0 effects)")
                            else:
                                print(f"✓ Crafted {recipe.output_name} (0 effects)")
                        else:
                            # For Equipment, roll rarity first
                            max_effects = None
                            if recipe.output_type.lower() == "equipment":
                                rarity = game.rarity_system.roll_rarity()
                                crafted_item.rarity = rarity
                                max_effects = game.rarity_system.get_max_effects(rarity)
                                print(f"\n✨ Rolled [{rarity}] {recipe.output_name}! (Max {max_effects} effects)")
                            else:
                                print(f"\n✓ Crafted {recipe.output_name}!")

                            # Roll for effects
                            print(f"\nRoll for effects? Cost: {game.effect_cost}{game.currency_symbol} per roll")
                            print(f"Your {game.currency_name}: {player.gold}{game.currency_symbol}")

                            effects_added = 0
                            while True:
                                # Check if Equipment has reached max effects
                                if max_effects and effects_added >= max_effects:
                                    print(f"\n✓ Reached maximum effects for {rarity} rarity ({max_effects})!")
                                    break

                                roll_choice = input(f"\nRoll for effect #{effects_added + 1}? (y/n): ").strip().lower()
                                if roll_choice != 'y':
                                    break

                                # Check if player has enough currency
                                if player.gold < game.effect_cost:
                                    print(f"❌ Not enough {game.currency_name}! Need {game.effect_cost}{game.currency_symbol}, have {player.gold}{game.currency_symbol}")
                                    break

                                # Deduct cost and roll for effect
                                player.remove_gold(game.effect_cost)
                                weights = [tmpl.weight for tmpl in game.effect_templates]
                                rolled_template = random.choices(game.effect_templates, weights=weights, k=1)[0]
                                effect = rolled_template.create_effect()
                                crafted_item.add_effect(effect)
                                effects_added += 1

                                print(f"🎲 Rolled: {rolled_template.name}")
                                print(f"   Effect: {effect}")
                                print(f"   {game.currency_name}: {player.gold}{game.currency_symbol}")

                            print(f"\n✓ Final item: {crafted_item.get_display_name()} ({effects_added} effects)")
                    else:
                        print(f"✓ Crafted {recipe.output_name}!")

                    player.add_item(crafted_item)
                    crafted_count += 1

                    # Ask if want to continue
                    continue_craft = input("Craft another? (press Enter to continue, 'done' to stop): ").strip().lower()
                    if continue_craft == 'done':
                        break

                if crafted_count > 0:
                    print(f"\n🎉 Total crafted: {crafted_count}x {recipe.output_name}")
            except ValueError:
                print("Invalid input!")

        elif choice == "5":
            manage_enchantments(game)

        elif choice == "6":
            break


def manage_enchantments(game):
    while True:
        show_enchantment_menu()
        choice = input("Enter choice: ").strip()

        if choice == "1":
            name = input("Enter enchantment name: ").strip()
            if not name:
                print("Name cannot be empty!")
                continue

            enchant_type = input("Enter enchantment type (e.g., weapon, armor): ").strip() or "misc"

            try:
                gold_value = int(input(f"Enter {game.currency_name} value bonus: ").strip())
                if gold_value < 0:
                    print(f"Invalid {game.currency_name} value!")
                    continue

                weight = float(input("Enter weight (default 1000): ").strip() or "1000")
                if weight <= 0:
                    print("Invalid weight!")
                    continue

                enchant = Enchantment(name, enchant_type, gold_value, weight)
                game.enchantments.append(enchant)
                print(f"✓ Added enchantment: {enchant}")
            except ValueError:
                print("Invalid input!")

        elif choice == "2":
            if not game.enchantments:
                print("No enchantments exist!")
                continue

            print("\nCurrent enchantments:")
            for i, ench in enumerate(game.enchantments):
                print(f"  {i}. {ench} (weight: {ench.weight})")

            try:
                index = int(input("\nEnter enchantment number to edit: ").strip())
                if index < 0 or index >= len(game.enchantments):
                    print("Invalid enchantment number!")
                    continue

                ench = game.enchantments[index]
                print(f"\nEditing: {ench.name}")
                print("Leave blank to keep current value")

                new_name = input(f"New name [{ench.name}]: ").strip()
                new_type = input(f"New type [{ench.enchant_type}]: ").strip()
                gold_input = input(f"New {game.currency_name} value [{ench.gold_value}]: ").strip()
                weight_input = input(f"New weight [{ench.weight}]: ").strip()

                if new_name:
                    ench.name = new_name
                if new_type:
                    ench.enchant_type = new_type
                if gold_input:
                    ench.gold_value = int(gold_input)
                if weight_input:
                    ench.weight = float(weight_input)

                print(f"✓ Updated enchantment!")
            except ValueError:
                print("Invalid input!")

        elif choice == "3":
            if not game.enchantments:
                print("No enchantments exist!")
                continue

            print("\nCurrent enchantments:")
            for i, ench in enumerate(game.enchantments):
                print(f"  {i}. {ench}")

            try:
                index = int(input("\nEnter enchantment number to delete: ").strip())
                if 0 <= index < len(game.enchantments):
                    deleted = game.enchantments.pop(index)
                    print(f"✓ Deleted enchantment: {deleted.name}")
                else:
                    print("Invalid enchantment number!")
            except ValueError:
                print("Invalid input!")

        elif choice == "4":
            print(f"\nCurrent global enchantment cost: {game.enchant_cost_amount}x {game.enchant_cost_item or 'None'}")

            print("\nAvailable items from all tables:")
            all_item_names = set()
            for table in game.loot_tables:
                for item in table.items:
                    all_item_names.add(item.name)
            for item_name in sorted(all_item_names):
                print(f"  - {item_name}")

            new_cost = input("Enter enchantment cost item name (leave blank for none): ").strip() or None
            new_amount = 1
            if new_cost:
                new_amount = int(input("How many of this item per enchant? (default 1): ").strip() or "1")

            game.enchant_cost_item = new_cost
            game.enchant_cost_amount = new_amount
            print(f"✓ Set global enchantment cost to: {new_amount}x {new_cost or 'None'}")

        elif choice == "5":
            if not game.enchantments:
                print("No enchantments exist!")
                continue

            print(f"\n{'=' * 50}")
            print(f"Global Enchantment Cost: {game.enchant_cost_amount}x {game.enchant_cost_item or 'None'}")
            print(f"{'=' * 50}")
            print("\nAll Enchantments:")
            total_weight = sum(e.weight for e in game.enchantments)
            for i, ench in enumerate(game.enchantments):
                percentage = (ench.weight / total_weight) * 100
                print(f"  {i}. {ench} (weight: {ench.weight}, {percentage:.2f}%)")

        elif choice == "6":
            if not game.enchantments:
                print("No enchantments exist!")
                continue

            if not game.players:
                print("No players exist!")
                continue

            print("\nAvailable players:")
            for name, player in game.players.items():
                print(f"  - {name}")

            player_name = input("\nEnter player name: ").strip()
            player = game.get_player(player_name)

            if not player:
                print(f"Player '{player_name}' not found!")
                continue

            if not player.inventory:
                print(f"{player.name} has no items!")
                continue

            print(f"\n{player.name}'s inventory:")
            for i, item in enumerate(player.inventory):
                print(f"  {i}. {item} [Type: {item.item_type}]")

            try:
                item_index = int(input("\nEnter item number to enchant: ").strip())
                if item_index < 0 or item_index >= len(player.inventory):
                    print("Invalid item number!")
                    continue

                item = player.inventory[item_index]

                compatible_enchants = [e for e in game.enchantments if e.enchant_type == item.item_type]

                if not compatible_enchants:
                    print(f"No enchantments compatible with type '{item.item_type}'!")
                    continue

                weights = [e.weight for e in compatible_enchants]
                drawn_enchant = random.choices(compatible_enchants, weights=weights, k=1)[0]

                print(f"\n🎲 Drew enchantment: {drawn_enchant}")

                if game.enchant_cost_item:
                    cost_item_count = sum(1 for inv_item in player.inventory if inv_item.name == game.enchant_cost_item)

                    if cost_item_count < game.enchant_cost_amount:
                        print(
                            f"❌ Not enough {game.enchant_cost_item}! Need {game.enchant_cost_amount}, have {cost_item_count}")
                        continue

                    removed_count = 0
                    while removed_count < game.enchant_cost_amount:
                        for i, inv_item in enumerate(player.inventory):
                            if inv_item.name == game.enchant_cost_item:
                                player.remove_item(i)
                                removed_count += 1
                                if i < item_index:
                                    item_index -= 1
                                break

                    print(f"💰 Consumed {game.enchant_cost_amount}x {game.enchant_cost_item}")

                    item = player.inventory[item_index]

                item.add_enchantment(drawn_enchant)

                print(f"✓ Enchanted {item.name} with {drawn_enchant.name}!")
                print(f"New item: {item}")
            except ValueError:
                print("Invalid input!")

        elif choice == "7":
            break


def admin_menu(game):
    while True:
        show_admin_menu(game.currency_name)
        choice = input("Enter choice: ").strip()

        if choice == "1":
            if not game.players:
                print("No players exist!")
                continue

            name = input("Enter player name: ").strip()
            player = game.get_player(name)
            if not player:
                print(f"Player '{name}' not found!")
                continue

            try:
                amount = int(input(f"Amount of {game.currency_name} to give: ").strip())
                if amount <= 0:
                    print("Amount must be greater than 0!")
                    continue

                player.add_gold(amount)
                print(f"✓ Gave {amount}{game.currency_symbol} to {player.name} (now has {player.gold}{game.currency_symbol})")
            except ValueError:
                print("Invalid amount!")

        elif choice == "2":
            if not game.players:
                print("No players exist!")
                continue

            name = input("Enter player name: ").strip()
            player = game.get_player(name)
            if not player:
                print(f"Player '{name}' not found!")
                continue

            try:
                amount = int(input(f"Amount of {game.currency_name} to take (has {player.gold}{game.currency_symbol}): ").strip())
                if amount <= 0:
                    print("Amount must be greater than 0!")
                    continue

                if player.remove_gold(amount):
                    print(f"✓ Took {amount}{game.currency_symbol} from {player.name} (now has {player.gold}{game.currency_symbol})")
                else:
                    print(f"Player doesn't have enough {game.currency_name}!")
            except ValueError:
                print("Invalid amount!")

        elif choice == "3":
            if not game.players:
                print("No players exist!")
                continue

            if not game.loot_tables:
                print("No loot tables exist!")
                continue

            name = input("Enter player name: ").strip()
            player = game.get_player(name)
            if not player:
                print(f"Player '{name}' not found!")
                continue

            print("\nAvailable items from all tables:")
            all_items = []
            for table in game.loot_tables:
                for item in table.items:
                    all_items.append(item)

            for i, item in enumerate(all_items):
                print(f"  {i}. {item}")

            try:
                index = int(input("\nEnter item number to gift: ").strip())
                if index < 0 or index >= len(all_items):
                    print("Invalid item number!")
                    continue

                item = all_items[index]
                player.add_item(item)
                print(f"✓ Gifted {item} to {player.name}")
            except ValueError:
                print("Invalid input!")

        elif choice == "4":
            if not game.players:
                print("No players exist!")
                continue

            name = input("Enter player name: ").strip()
            player = game.get_player(name)
            if not player:
                print(f"Player '{name}' not found!")
                continue

            if not player.inventory:
                print(f"{player.name} has no items!")
                continue

            print(f"\n{player.name}'s inventory:")
            for i, item in enumerate(player.inventory):
                print(f"  {i}. {item}")

            try:
                index = int(input("\nEnter item number to take: ").strip())
                if index < 0 or index >= len(player.inventory):
                    print("Invalid item number!")
                    continue

                item = player.remove_item(index)
                if item:
                    print(f"✓ Took {item} from {player.name}")
            except ValueError:
                print("Invalid input!")

        elif choice == "5":
            # Change currency settings
            print(f"\nCurrent currency: {game.currency_name} (symbol: {game.currency_symbol})")

            new_name = input(f"Enter new currency name (leave blank to keep '{game.currency_name}'): ").strip()
            new_symbol = input(f"Enter new currency symbol (leave blank to keep '{game.currency_symbol}'): ").strip()

            if new_name:
                game.currency_name = new_name
            if new_symbol:
                game.currency_symbol = new_symbol

            print(f"✓ Currency updated: {game.currency_name} (symbol: {game.currency_symbol})")

        elif choice == "6":
            # Configure rarity weights
            print("\n--- RARITY WEIGHT CONFIGURATION ---")
            print("Current rarity weights:")
            total_weight = sum(data['weight'] for data in game.rarity_system.rarities.values())
            for rarity, data in game.rarity_system.rarities.items():
                weight = data['weight']
                max_effects = data['max_effects']
                percentage = (weight / total_weight) * 100
                print(f"  {rarity}: weight {weight} ({percentage:.2f}%) - {max_effects} effect slots")

            print("\nEnter new weights (leave blank to keep current):")
            for rarity in game.rarity_system.rarities.keys():
                current_weight = game.rarity_system.rarities[rarity]['weight']
                new_weight_input = input(f"{rarity} [{current_weight}]: ").strip()
                if new_weight_input:
                    try:
                        new_weight = float(new_weight_input)
                        if new_weight > 0:
                            game.rarity_system.set_weight(rarity, new_weight)
                            print(f"✓ Updated {rarity} weight to {new_weight}")
                        else:
                            print(f"Weight must be greater than 0! Keeping {current_weight}")
                    except ValueError:
                        print(f"Invalid input! Keeping {current_weight}")

            print("\n✓ Rarity weights updated!")

        elif choice == "7":
            # Manage effect pool
            manage_effect_pool(game)

        elif choice == "8":
            break


if __name__ == "__main__":
    game = GameSystem()


    def signal_handler(sig, frame):
        print("\n\n⚠️  Ctrl+C detected! Auto-saving...")
        if game.save_game():
            print("✓ Game saved successfully!")
        else:
            print("❌ Failed to save game.")
        print("Exiting...")
        sys.exit(0)


    signal.signal(signal.SIGINT, signal_handler)

    print("Welcome to the Loot Table RPG System!")
    print("(Tip: Press Ctrl+C anytime to auto-save and exit)")

    if os.path.exists(game.save_file):
        try:
            load_choice = input("\nFound saved game. Load it? (y/n): ").strip().lower()
            if load_choice == 'y':
                if game.load_game():
                    print("✓ Game loaded successfully!")
                else:
                    print("Failed to load game. Starting fresh.")
        except KeyboardInterrupt:
            signal_handler(signal.SIGINT, None)

    while True:
        show_main_menu()
        choice = input("Enter your choice (1-9): ").strip()

        if choice == "1":
            manage_loot_table(game)
        elif choice == "2":
            manage_players(game)
        elif choice == "3":
            draw_items_menu(game)
        elif choice == "4":
            sell_items_menu(game)
        elif choice == "5":
            manage_crafting(game)
        elif choice == "6":
            manage_equipment_upgrades(game)
        elif choice == "7":
            admin_menu(game)
        elif choice == "8":
            if game.save_game():
                print("✓ Game saved successfully!")
            else:
                print("Failed to save game.")
        elif choice == "9":
            print("\nAre you sure you want to exit?")
            save_prompt = input("Save before exiting? (y/n/cancel): ").strip().lower()

            if save_prompt == 'cancel':
                continue
            elif save_prompt == 'y':
                if game.save_game():
                    print("✓ Game saved!")
                else:
                    print("Failed to save.")

            print("Thanks for using the Loot Table RPG System!")
            break
        else:

            print("Invalid choice! Please enter 1-9.")
