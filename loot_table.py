import random
import json
import os
import signal
import sys
import copy


class MasterItem:
    """Defines a master item template with name, type, and base gold value."""
    def __init__(self, name, item_type, gold_value_per_unit, purchase_price=None):
        self.name = name
        self.item_type = item_type
        self.gold_value_per_unit = gold_value_per_unit
        self.purchase_price = purchase_price  # Price to buy from shop (None = not for sale)

    def create_loot_item(self, quantity=1, weight=1000):
        """Create a LootItem instance from this master item."""
        total_value = self.gold_value_per_unit * quantity
        return LootItem(self.name, weight, total_value, self.item_type, quantity)

    def __str__(self):
        if self.purchase_price is not None:
            return f"{self.name} ({self.item_type}) - {self.gold_value_per_unit}g sell / {self.purchase_price}g buy"
        return f"{self.name} ({self.item_type}) - {self.gold_value_per_unit}g each"

    def __repr__(self):
        return self.__str__()


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

    def add_enchantment(self, enchantment, rolled_value=None):
        """Add an enchantment to this item. If rolled_value is provided, use it; otherwise roll a new value."""
        if rolled_value is None:
            rolled_value = enchantment.apply_to_item(self)
        else:
            # Apply the provided rolled value
            if enchantment.is_percentage:
                change = self.gold_value * (rolled_value / 100.0)
                self.gold_value = max(0, int(self.gold_value + change))
            else:
                self.gold_value = max(0, int(self.gold_value + rolled_value))

        # Store enchantment with its rolled value as a tuple
        self.enchantments.append((enchantment, rolled_value))

    def add_effect(self, effect):
        self.effects.append(effect)

    def get_display_name(self):
        base_name = f"{self.quantity}x {self.name}" if self.quantity > 1 else self.name

        # Add rarity prefix for Equipment items
        if self.rarity:
            base_name = f"[{self.rarity}] {base_name}"

        if self.enchantments:
            enchant_strs = []
            for ench, rolled_value in self.enchantments:
                if ench.is_percentage:
                    enchant_strs.append(f"{ench.name} {rolled_value:+.1f}%")
                else:
                    enchant_strs.append(f"{ench.name} {rolled_value:+.0f}g")
            return f"{base_name} [{', '.join(enchant_strs)}]"
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
    def __init__(self, name, enchant_type, min_value, max_value, is_percentage=False, cost_amount=1):
        self.name = name
        self.enchant_type = enchant_type
        self.min_value = min_value  # Can be negative for penalty
        self.max_value = max_value  # Can be positive for bonus
        self.is_percentage = is_percentage  # True for %, False for flat
        self.cost_amount = cost_amount  # Individual cost for this enchantment

    def roll_value(self):
        """Roll a random value within the enchantment's range."""
        return random.uniform(self.min_value, self.max_value)

    def apply_to_item(self, item):
        """Apply this enchantment to an item and return the rolled value."""
        rolled_value = self.roll_value()

        if self.is_percentage:
            # Apply percentage change to gold value
            change = item.gold_value * (rolled_value / 100.0)
            item.gold_value = max(0, int(item.gold_value + change))
        else:
            # Apply flat change to gold value
            item.gold_value = max(0, int(item.gold_value + rolled_value))

        return rolled_value

    def __str__(self):
        if self.is_percentage:
            return f"{self.name} ({self.enchant_type}, {self.min_value:+.1f}% to {self.max_value:+.1f}%, Cost: {self.cost_amount})"
        else:
            return f"{self.name} ({self.enchant_type}, {self.min_value:+.0f}g to {self.max_value:+.0f}g, Cost: {self.cost_amount})"

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
    def __init__(self, output_name, output_type, output_gold_value, purchase_price=None):
        self.output_name = output_name
        self.output_type = output_type
        self.output_gold_value = output_gold_value
        self.purchase_price = purchase_price  # Price to buy from shop (None = not for sale)
        self.ingredients = []
        self.effects = []  # Effects for Equipment/Upgrade items

    def add_ingredient(self, item_name):
        self.ingredients.append(item_name)

    def add_effect(self, effect):
        self.effects.append(effect)

    def __str__(self):
        if not self.ingredients:
            ingredient_list = "No ingredients"
        else:
            # Count ingredients and display as "Nx Item"
            ingredient_counts = {}
            for ingredient in self.ingredients:
                ingredient_counts[ingredient] = ingredient_counts.get(ingredient, 0) + 1
            ingredient_parts = [f"{count}x {name}" if count > 1 else name
                               for name, count in ingredient_counts.items()]
            ingredient_list = ", ".join(ingredient_parts)

        effects_str = f" [Effects: {len(self.effects)}]" if self.effects else ""
        price_str = f" / {self.purchase_price}g buy" if self.purchase_price is not None else ""
        return f"{self.output_name} ({self.output_type}, {self.output_gold_value}g{price_str}){effects_str} = [{ingredient_list}]"

    def __repr__(self):
        return self.__str__()


class ShopItem:
    """Simple shop item with name, type, sell value, and purchase price."""
    def __init__(self, name, item_type, gold_value, purchase_price):
        self.name = name
        self.item_type = item_type
        self.gold_value = gold_value
        self.purchase_price = purchase_price

    def __str__(self):
        return f"{self.name} ({self.item_type}) - Buy: {self.purchase_price}g, Sells for: {self.gold_value}g"

    def __repr__(self):
        return self.__str__()


class Consumable:
    """Consumable item with temporary effects."""
    def __init__(self, name, effect_type, effect_value=None, gold_value=0):
        self.name = name
        self.item_type = "consumable"
        self.effect_type = effect_type  # e.g., "double_next_draw"
        self.effect_value = effect_value  # Optional value for the effect
        self.gold_value = gold_value  # Base sell value

    def __str__(self):
        if self.effect_type == "double_next_draw":
            return f"{self.name} (consumable, {self.gold_value}g) - Doubles quantity on next draw"
        return f"{self.name} (consumable, {self.gold_value}g) - {self.effect_type}"

    def __repr__(self):
        return self.__str__()


class Player:
    def __init__(self, name):
        self.name = name
        self.gold = 0
        self.inventory = []
        self.equipped_items = []  # Items currently equipped
        self.consumed_upgrades = []  # Upgrades that have been consumed
        self.active_consumable_effects = []  # Active temporary effects from consumables

    def add_item(self, item):
        """Add item to inventory with automatic stacking."""
        # Items with enchantments, effects, or rarity don't stack (they're unique)
        if item.enchantments or item.effects or item.rarity:
            self.inventory.append(item)
            return

        # Try to find existing stack with same name and type
        for existing_item in self.inventory:
            if (existing_item.name == item.name and
                existing_item.item_type == item.item_type and
                not existing_item.enchantments and
                not existing_item.effects and
                not existing_item.rarity):
                # Stack found - combine quantities and values
                existing_item.quantity += item.quantity
                existing_item.gold_value += item.gold_value
                return

        # No stack found - add as new item
        self.inventory.append(item)

    def remove_item(self, index):
        if 0 <= index < len(self.inventory):
            return self.inventory.pop(index)
        return None

    def consume_item_by_name(self, item_name, count=1):
        """
        Consume a specific count of items by name from stacks.
        Returns True if successful, False if not enough items.
        """
        # Find all matching items
        total_available = 0
        matching_items = []

        for i, item in enumerate(self.inventory):
            if item.name == item_name:
                total_available += item.quantity
                matching_items.append((i, item))

        if total_available < count:
            return False

        # Consume from stacks
        remaining_to_consume = count
        items_to_remove = []

        for idx, (inv_idx, item) in enumerate(matching_items):
            if remaining_to_consume <= 0:
                break

            if item.quantity <= remaining_to_consume:
                # Consume entire stack
                remaining_to_consume -= item.quantity
                items_to_remove.append(inv_idx)
            else:
                # Consume partial stack
                # Calculate value per unit
                value_per_unit = item.gold_value / item.quantity
                item.quantity -= remaining_to_consume
                item.gold_value -= value_per_unit * remaining_to_consume
                remaining_to_consume = 0

        # Remove consumed stacks (in reverse order to maintain indices)
        for inv_idx in sorted(items_to_remove, reverse=True):
            self.inventory.pop(inv_idx)

        return True

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

    def get_sell_price_increase(self):
        """Calculate total sell price increase for non-crafted items from equipment and upgrades."""
        flat_increase = 0
        percentage_increase = 0

        # Add effects from equipped items
        for item in self.equipped_items:
            for effect in item.effects:
                if effect.effect_type == "sell_price_increase":
                    if effect.is_percentage:
                        percentage_increase += effect.value
                    else:
                        flat_increase += effect.value

        # Add effects from consumed upgrades
        for item in self.consumed_upgrades:
            for effect in item.effects:
                if effect.effect_type == "sell_price_increase":
                    if effect.is_percentage:
                        percentage_increase += effect.value
                    else:
                        flat_increase += effect.value

        return flat_increase, percentage_increase

    def get_crafted_sell_price_increase(self):
        """Calculate total sell price increase for crafted items from equipment and upgrades."""
        flat_increase = 0
        percentage_increase = 0

        # Add effects from equipped items
        for item in self.equipped_items:
            for effect in item.effects:
                if effect.effect_type == "crafted_sell_price_increase":
                    if effect.is_percentage:
                        percentage_increase += effect.value
                    else:
                        flat_increase += effect.value

        # Add effects from consumed upgrades
        for item in self.consumed_upgrades:
            for effect in item.effects:
                if effect.effect_type == "crafted_sell_price_increase":
                    if effect.is_percentage:
                        percentage_increase += effect.value
                    else:
                        flat_increase += effect.value

        return flat_increase, percentage_increase

    def calculate_item_value(self, base_value, is_crafted=False):
        """Calculate the actual item value after sell price increases."""
        if is_crafted:
            flat, percent = self.get_crafted_sell_price_increase()
        else:
            flat, percent = self.get_sell_price_increase()

        # Apply percentage increase first
        value = base_value * (1 + percent / 100)

        # Then apply flat increase
        value = value + flat

        return int(value)

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
        drawn_item = random.choices(self.items, weights=weights, k=1)[0]
        return copy.deepcopy(drawn_item)

    def draw_multiple(self, count):
        if not self.items:
            return []
        weights = [item.weight for item in self.items]
        drawn_items = random.choices(self.items, weights=weights, k=count)
        return [copy.deepcopy(item) for item in drawn_items]


class GameSystem:
    def __init__(self):
        self.master_items = []  # Master item registry
        self.loot_tables = []  # List of LootTable objects
        self.current_table_index = 0  # Currently selected table
        self.current_player_name = None  # Currently selected player
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
        self.shop_items = []  # Shop catalog of items players can buy
        self.consumables = []  # Consumable items with temporary effects
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
            # Clear current player if they were removed
            if self.current_player_name == name:
                self.current_player_name = None
            return True
        return False

    def add_master_item(self, name, item_type, gold_value_per_unit, purchase_price=None):
        """Add a new master item to the registry."""
        # Check if item already exists
        for item in self.master_items:
            if item.name.lower() == name.lower():
                return None  # Item already exists
        master_item = MasterItem(name, item_type, gold_value_per_unit, purchase_price)
        self.master_items.append(master_item)
        return master_item

    def get_master_item(self, name):
        """Get a master item by name."""
        for item in self.master_items:
            if item.name.lower() == name.lower():
                return item
        return None

    def remove_master_item(self, index):
        """Remove a master item by index."""
        if 0 <= index < len(self.master_items):
            return self.master_items.pop(index)
        return None

    def save_game(self):
        """Save the game state to a JSON file."""
        try:
            data = {
                'master_items': [
                    {
                        'name': item.name,
                        'item_type': item.item_type,
                        'gold_value_per_unit': item.gold_value_per_unit,
                        'purchase_price': item.purchase_price
                    }
                    for item in self.master_items
                ],
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
                'current_player_name': self.current_player_name,
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
                                        'min_value': ench.min_value,
                                        'max_value': ench.max_value,
                                        'is_percentage': ench.is_percentage,
                                        'cost_amount': ench.cost_amount,
                                        'rolled_value': rolled_value
                                    }
                                    for ench, rolled_value in item.enchantments
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
                        ],
                        'active_consumable_effects': player.active_consumable_effects
                    }
                    for name, player in self.players.items()
                },
                'crafting_recipes': [
                    {
                        'output_name': recipe.output_name,
                        'output_type': recipe.output_type,
                        'output_gold_value': recipe.output_gold_value,
                        'purchase_price': recipe.purchase_price,
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
                        'min_value': ench.min_value,
                        'max_value': ench.max_value,
                        'is_percentage': ench.is_percentage,
                        'cost_amount': ench.cost_amount
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
                'shop_items': [
                    {
                        'name': item.name,
                        'item_type': item.item_type,
                        'gold_value': item.gold_value,
                        'purchase_price': item.purchase_price
                    }
                    for item in self.shop_items
                ],
                'consumables': [
                    {
                        'name': cons.name,
                        'effect_type': cons.effect_type,
                        'effect_value': cons.effect_value,
                        'gold_value': cons.gold_value
                    }
                    for cons in self.consumables
                ],
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

            # Load master items
            self.master_items = []
            if 'master_items' in data:
                for item_data in data['master_items']:
                    master_item = MasterItem(
                        item_data['name'],
                        item_data['item_type'],
                        item_data['gold_value_per_unit'],
                        item_data.get('purchase_price')  # Backward compatible
                    )
                    self.master_items.append(master_item)

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
                self.current_player_name = data.get('current_player_name')
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
                        # Handle both old and new format
                        if 'min_value' in ench_data:
                            # New format
                            ench = Enchantment(
                                ench_data['name'],
                                ench_data['enchant_type'],
                                ench_data['min_value'],
                                ench_data['max_value'],
                                ench_data.get('is_percentage', False),
                                ench_data.get('cost_amount', 1)
                            )
                            rolled_value = ench_data.get('rolled_value', 0)
                            item.enchantments.append((ench, rolled_value))
                        else:
                            # Old format - convert to new format
                            gold_value = ench_data.get('gold_value', 0)
                            ench = Enchantment(
                                ench_data['name'],
                                ench_data['enchant_type'],
                                gold_value,  # min_value
                                gold_value,  # max_value (same as min for old format)
                                False,  # is_percentage
                                1  # cost_amount
                            )
                            item.enchantments.append((ench, gold_value))
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

                # Load active consumable effects
                player.active_consumable_effects = player_data.get('active_consumable_effects', [])

                self.players[name] = player

            # Load crafting recipes
            self.crafting_recipes = []
            for recipe_data in data.get('crafting_recipes', []):
                recipe = CraftingRecipe(
                    recipe_data['output_name'],
                    recipe_data['output_type'],
                    recipe_data['output_gold_value'],
                    recipe_data.get('purchase_price')  # Backward compatible
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
                # Handle both old and new format
                if 'min_value' in ench_data:
                    # New format
                    ench = Enchantment(
                        ench_data['name'],
                        ench_data['enchant_type'],
                        ench_data['min_value'],
                        ench_data['max_value'],
                        ench_data.get('is_percentage', False),
                        ench_data.get('cost_amount', 1)
                    )
                else:
                    # Old format - convert to new format
                    gold_value = ench_data.get('gold_value', 0)
                    ench = Enchantment(
                        ench_data['name'],
                        ench_data['enchant_type'],
                        gold_value,  # min_value
                        gold_value,  # max_value (same as min for old format)
                        False,  # is_percentage
                        1  # cost_amount
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

            # Load shop items
            self.shop_items = []
            for shop_item_data in data.get('shop_items', []):
                shop_item = ShopItem(
                    shop_item_data['name'],
                    shop_item_data['item_type'],
                    shop_item_data['gold_value'],
                    shop_item_data['purchase_price']
                )
                self.shop_items.append(shop_item)

            # Load consumables
            self.consumables = []
            for cons_data in data.get('consumables', []):
                consumable = Consumable(
                    cons_data['name'],
                    cons_data['effect_type'],
                    cons_data.get('effect_value'),
                    cons_data.get('gold_value', 0)
                )
                self.consumables.append(consumable)

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


def get_player_name_input(game, prompt="Enter player name"):
    """Get player name from user, defaulting to current player if set."""
    if game.current_player_name and game.current_player_name in game.players:
        default_prompt = f"{prompt} (default: {game.current_player_name}): "
        player_name = input(default_prompt).strip()
        # If empty, use current player
        if not player_name:
            return game.current_player_name
        return player_name
    else:
        return input(f"{prompt}: ").strip()


def quick_commands_menu(game):
    """Quick command interface for common actions."""
    print("\n" + "=" * 60)
    print("QUICK COMMANDS")
    print("=" * 60)
    print("Type 'help' for available commands, 'back' to return to main menu")
    print()

    while True:
        cmd_input = input(">>> ").strip()

        if not cmd_input:
            continue

        if cmd_input.lower() == 'back':
            break

        if cmd_input.lower() == 'help':
            show_quick_commands_help(game)
            continue

        # Parse and execute command
        execute_quick_command(game, cmd_input)


def show_quick_commands_help(game):
    """Show help for quick commands."""
    print("\n" + "=" * 60)
    print("AVAILABLE QUICK COMMANDS")
    print("=" * 60)
    print("\n📦 DRAWING:")
    print("  draw <count> [player] [table]")
    print("    Examples:")
    print("      draw 10              - Draw 10 items for current player from current table")
    print("      draw 5 bob           - Draw 5 items for bob from current table")
    print("      draw 10 bob dungeon  - Draw 10 items for bob from 'dungeon' table")
    print()
    print("💰 SELLING:")
    print("  sell <index> [player]")
    print("  sell all [player]")
    print("  sell all <itemname> [player]")
    print("  sell <itemname> <count> [player]")
    print("    Examples:")
    print("      sell 0            - Sell item at index 0 for current player")
    print("      sell 0 bob        - Sell item 0 for bob")
    print("      sell all          - Sell all items for current player")
    print("      sell all sword    - Sell all swords for current player")
    print("      sell sword 5      - Sell 5 swords for current player")
    print("      sell sword 3 bob  - Sell 3 swords for bob")
    print()
    print("🔨 CRAFTING:")
    print("  craft <recipe_name> [count] [player]")
    print("    Examples:")
    print("      craft sword           - Craft 1 sword for current player")
    print("      craft sword 5         - Craft 5 swords for current player")
    print("      craft sword 5 bob     - Craft 5 swords for bob")
    print()
    print("📋 VIEWING:")
    print("  inv [player]      - Show inventory")
    print("  stats [player]    - Show equipment stats")
    print("  gold [player]     - Show gold amount")
    print()
    print("⚔️  EQUIPMENT:")
    print("  equip <index> [player]   - Equip item at index")
    print("  consume <index> [player] - Consume upgrade at index")
    print()
    print("👑 ADMIN:")
    print("  give <amount> [player]  - Give gold to player")
    print("  take <amount> [player]  - Take gold from player")
    print()
    print("Other: back, help")
    print("=" * 60)


def execute_quick_command(game, cmd_input):
    """Parse and execute a quick command."""
    parts = cmd_input.split()
    if not parts:
        return

    command = parts[0].lower()
    args = parts[1:]

    try:
        if command == "draw":
            quick_draw(game, args)
        elif command == "sell":
            quick_sell(game, args)
        elif command == "craft":
            quick_craft(game, args)
        elif command == "inv" or command == "inventory":
            quick_inventory(game, args)
        elif command == "stats":
            quick_stats(game, args)
        elif command == "gold":
            quick_gold(game, args)
        elif command == "equip":
            quick_equip(game, args)
        elif command == "consume":
            quick_consume(game, args)
        elif command == "give":
            quick_give_gold(game, args)
        elif command == "take":
            quick_take_gold(game, args)
        else:
            print(f"Unknown command: '{command}'. Type 'help' for available commands.")
    except Exception as e:
        print(f"Error executing command: {e}")


def quick_draw(game, args):
    """Quick draw command: draw <count> [player] [table]"""
    if not args:
        print("Usage: draw <count> [player] [table]")
        return

    try:
        count = int(args[0])
    except ValueError:
        print("Error: count must be a number")
        return

    # Determine player
    player_name = None
    table_name = None

    if len(args) >= 2:
        player_name = args[1]
    else:
        player_name = game.current_player_name

    if len(args) >= 3:
        table_name = args[2]

    if not player_name:
        print("Error: No player specified and no current player set")
        return

    player = game.get_player(player_name)
    if not player:
        print(f"Error: Player '{player_name}' not found")
        return

    # Determine table
    if table_name:
        # Find table by name
        selected_table = None
        for table in game.loot_tables:
            if table.name.lower() == table_name.lower():
                selected_table = table
                break
        if not selected_table:
            print(f"Error: Table '{table_name}' not found")
            return
    else:
        selected_table = game.get_current_table()
        if not selected_table:
            print("Error: No current table set")
            return

    if not selected_table.items:
        print(f"Error: Table '{selected_table.name}' has no items")
        return

    # Calculate cost
    base_cost = selected_table.draw_cost
    actual_cost = player.calculate_draw_cost(base_cost)
    total_cost = count * actual_cost

    if player.gold < total_cost:
        print(f"❌ Not enough {game.currency_name}! Need {total_cost}{game.currency_symbol} but {player.name} only has {player.gold}{game.currency_symbol}")
        return

    # Draw items
    player.remove_gold(total_cost)
    items = selected_table.draw_multiple(count)

    print(f"💰 Paid {total_cost}{game.currency_symbol} ({count} x {actual_cost}{game.currency_symbol}) to {selected_table.name}")
    print(f"🎲 {player.name} drew {count} items:")

    # Get bonuses
    double_chance = player.get_double_quantity_chance()
    flat_price, percent_price = player.get_sell_price_increase()

    total_value = 0
    doubled_count = 0
    price_boosted_count = 0

    for i, item in enumerate(items, 1):
        # Roll rarity for Equipment items
        if item.item_type.lower() == "equipment" and not item.rarity:
            item.rarity = game.rarity_system.roll_rarity()

        # Apply sell price increase
        price_boosted = False
        if flat_price > 0 or percent_price > 0:
            original_value = item.gold_value
            item.gold_value = player.calculate_item_value(original_value, is_crafted=False)
            if item.gold_value > original_value:
                price_boosted_count += 1
                price_boosted = True

        # Apply double quantity chance
        doubled = False
        if double_chance > 0 and random.random() * 100 < double_chance:
            item.quantity *= 2
            item.gold_value *= 2
            doubled_count += 1
            doubled = True

        # Display
        indicators = []
        if doubled:
            indicators.append("✨ DOUBLED!")
        if price_boosted:
            indicators.append("💰 PRICE BOOST!")

        if indicators:
            print(f"  {i}. {item} {' '.join(indicators)}")
        else:
            print(f"  {i}. {item}")

        player.add_item(item)
        total_value += item.gold_value

    if doubled_count > 0:
        print(f"\n✨ {doubled_count} item(s) had their quantity doubled! (Chance: {double_chance}%)")

    if price_boosted_count > 0:
        print(f"💰 {price_boosted_count} item(s) had their value increased! (+{flat_price} flat, +{percent_price}%)")

    net_value = total_value - total_cost
    print(f"\nTotal value: {total_value}{game.currency_symbol}")
    print(f"Net gain/loss: {net_value:+d}{game.currency_symbol}")
    print(f"{player.name}'s {game.currency_name}: {player.gold}{game.currency_symbol} | Inventory: {len(player.inventory)} items")


def quick_sell(game, args):
    """Quick sell command: sell <index|all|itemname> [count] [player]"""
    if not args:
        print("Usage: sell <index|all|all itemname|itemname count> [player]")
        return

    # Parse command variants
    # Variant 1: sell all [itemname] [player]
    if args[0].lower() == "all":
        player_name = None
        item_name = None

        if len(args) == 1:
            # sell all - sell all items for current player
            player_name = game.current_player_name
        elif len(args) == 2:
            # sell all X - could be "sell all bob" (player) or "sell all sword" (item name)
            # Check if args[1] is a player
            if game.get_player(args[1]):
                player_name = args[1]
            else:
                # It's an item name
                player_name = game.current_player_name
                item_name = args[1]
        elif len(args) >= 3:
            # sell all sword bob
            item_name = args[1]
            player_name = args[2]

        if not player_name:
            print("Error: No player specified and no current player set")
            return

        player = game.get_player(player_name)
        if not player:
            print(f"Error: Player '{player_name}' not found")
            return

        if not player.inventory:
            print(f"{player.name} has no items to sell!")
            return

        # Sell all or sell all matching item name
        if item_name:
            # Sell all items matching the name
            items_to_sell = [item for item in player.inventory if item.name.lower() == item_name.lower()]
            if not items_to_sell:
                print(f"Error: No items named '{item_name}' found in inventory")
                return

            total_gold = sum(item.gold_value for item in items_to_sell)
            count = len(items_to_sell)

            # Remove items from inventory
            player.inventory = [item for item in player.inventory if item.name.lower() != item_name.lower()]
            player.add_gold(total_gold)

            print(f"✓ Sold {count}x {item_name} for {total_gold}{game.currency_symbol}!")
            print(f"{player.name}'s {game.currency_name}: {player.gold}{game.currency_symbol}")
        else:
            # Sell all items
            total_gold = sum(item.gold_value for item in player.inventory)
            item_count = len(player.inventory)
            player.inventory.clear()
            player.add_gold(total_gold)
            print(f"✓ Sold all {item_count} items for {total_gold}{game.currency_symbol}!")
            print(f"{player.name}'s {game.currency_name}: {player.gold}{game.currency_symbol}")
        return

    # Variant 2: sell <index> [player] - sell by index
    try:
        index = int(args[0])

        # Determine player
        player_name = args[1] if len(args) >= 2 else game.current_player_name

        if not player_name:
            print("Error: No player specified and no current player set")
            return

        player = game.get_player(player_name)
        if not player:
            print(f"Error: Player '{player_name}' not found")
            return

        if not player.inventory:
            print(f"{player.name} has no items to sell!")
            return

        if index < 0 or index >= len(player.inventory):
            print(f"Error: Invalid item index. Player has {len(player.inventory)} items (0-{len(player.inventory)-1})")
            return

        item = player.remove_item(index)
        if item:
            player.add_gold(item.gold_value)
            print(f"✓ Sold {item.name} for {item.gold_value}{game.currency_symbol}!")
            print(f"{player.name}'s {game.currency_name}: {player.gold}{game.currency_symbol}")
        return
    except ValueError:
        pass  # Not a number, continue to item name logic

    # Variant 3: sell <itemname> <count> [player]
    item_name = args[0]

    if len(args) < 2:
        print("Usage: sell <itemname> <count> [player]")
        return

    try:
        count = int(args[1])
    except ValueError:
        print("Error: count must be a number")
        return

    player_name = args[2] if len(args) >= 3 else game.current_player_name

    if not player_name:
        print("Error: No player specified and no current player set")
        return

    player = game.get_player(player_name)
    if not player:
        print(f"Error: Player '{player_name}' not found")
        return

    if not player.inventory:
        print(f"{player.name} has no items to sell!")
        return

    # Find matching items and count total quantity across stacks
    matching_items = []
    total_quantity = 0

    for i, item in enumerate(player.inventory):
        if item.name.lower() == item_name.lower():
            matching_items.append((i, item))
            total_quantity += item.quantity

    if not matching_items:
        print(f"Error: No items named '{item_name}' found in inventory")
        return

    if total_quantity < count:
        print(f"Error: Player only has {total_quantity}x {item_name}, cannot sell {count}")
        return

    # Sell the requested count from stacks
    total_gold = 0
    remaining_to_sell = count
    items_to_remove = []

    for idx, (inv_idx, item) in enumerate(matching_items):
        if remaining_to_sell <= 0:
            break

        if item.quantity <= remaining_to_sell:
            # Sell entire stack
            total_gold += item.gold_value
            remaining_to_sell -= item.quantity
            items_to_remove.append(inv_idx)
        else:
            # Sell partial stack
            value_per_unit = item.gold_value / item.quantity
            gold_from_partial = value_per_unit * remaining_to_sell
            total_gold += gold_from_partial
            item.quantity -= remaining_to_sell
            item.gold_value -= gold_from_partial
            remaining_to_sell = 0

    # Remove sold stacks (in reverse order to maintain indices)
    for inv_idx in sorted(items_to_remove, reverse=True):
        player.inventory.pop(inv_idx)

    player.add_gold(int(total_gold))
    print(f"✓ Sold {count}x {item_name} for {int(total_gold)}{game.currency_symbol}!")
    print(f"{player.name}'s {game.currency_name}: {player.gold}{game.currency_symbol}")


def quick_craft(game, args):
    """Quick craft command: craft <recipe_name> [count] [player]"""
    if not args:
        print("Usage: craft <recipe_name> [count] [player]")
        return

    recipe_name = args[0]
    count = 1
    player_name = None

    # Parse optional count and player
    if len(args) >= 2:
        try:
            count = int(args[1])
            if len(args) >= 3:
                player_name = args[2]
        except ValueError:
            # args[1] is player name, not count
            player_name = args[1]
            count = 1

    if not player_name:
        player_name = game.current_player_name

    if not player_name:
        print("Error: No player specified and no current player set")
        return

    player = game.get_player(player_name)
    if not player:
        print(f"Error: Player '{player_name}' not found")
        return

    # Find recipe
    recipe = None
    for r in game.crafting_recipes:
        if r.output_name.lower() == recipe_name.lower():
            recipe = r
            break

    if not recipe:
        print(f"Error: Recipe '{recipe_name}' not found")
        return

    # Craft items
    crafted_count = 0
    for _ in range(count):
        # Count required quantities for each ingredient
        required_ingredients = {}
        for ingredient in recipe.ingredients:
            required_ingredients[ingredient] = required_ingredients.get(ingredient, 0) + 1

        # Check if player has all ingredients in required quantities
        missing_ingredients = []

        for ingredient, required_count in required_ingredients.items():
            # Count total quantity of this ingredient across all stacks
            total_quantity = sum(item.quantity for item in player.inventory if item.name == ingredient)
            if total_quantity < required_count:
                missing_ingredients.append(f"{ingredient} ({total_quantity}/{required_count})")

        if missing_ingredients:
            if crafted_count > 0:
                print(f"\n❌ Out of ingredients after crafting {crafted_count}! Missing: {', '.join(missing_ingredients)}")
            else:
                print(f"❌ Missing ingredients: {', '.join(missing_ingredients)}")
            break

        # Remove ingredients (consumes from stacks)
        for ingredient in recipe.ingredients:
            player.consume_item_by_name(ingredient, 1)

        # Create crafted item
        crafted_item = LootItem(recipe.output_name, 0, recipe.output_gold_value, recipe.output_type)

        # Apply crafted sell price increase
        flat_craft_price, percent_craft_price = player.get_crafted_sell_price_increase()
        if flat_craft_price > 0 or percent_craft_price > 0:
            original_craft_value = crafted_item.gold_value
            crafted_item.gold_value = player.calculate_item_value(original_craft_value, is_crafted=True)

        player.add_item(crafted_item)
        crafted_count += 1
        print(f"✓ Crafted {recipe.output_name} ({crafted_item.gold_value}{game.currency_symbol})")

    if crafted_count > 0:
        print(f"\n🎉 Total crafted: {crafted_count}x {recipe.output_name}")


def quick_inventory(game, args):
    """Quick inventory command: inv [player]"""
    player_name = args[0] if args else game.current_player_name

    if not player_name:
        print("Error: No player specified and no current player set")
        return

    player = game.get_player(player_name)
    if not player:
        print(f"Error: Player '{player_name}' not found")
        return

    print(f"\n--- {player.name}'s Inventory ---")
    print(f"{game.currency_name.capitalize()}: {player.gold}{game.currency_symbol}")
    print(f"Items ({len(player.inventory)}):")
    if player.inventory:
        for i, item in enumerate(player.inventory):
            print(f"  {i}. {item}")
    else:
        print("  (empty)")


def quick_stats(game, args):
    """Quick stats command: stats [player]"""
    player_name = args[0] if args else game.current_player_name

    if not player_name:
        print("Error: No player specified and no current player set")
        return

    player = game.get_player(player_name)
    if not player:
        print(f"Error: Player '{player_name}' not found")
        return

    print(f"\n--- {player.name}'s Equipment & Upgrades ---")

    flat, percent = player.get_total_draw_cost_reduction()
    print(f"Total Draw Cost Reduction: -{flat} flat, -{percent}%")

    double_chance = player.get_double_quantity_chance()
    print(f"Total Double Quantity Chance: {double_chance}%")

    flat_sell, percent_sell = player.get_sell_price_increase()
    print(f"Total Sell Price Increase (Non-Crafted): +{flat_sell} flat, +{percent_sell}%")

    flat_craft_sell, percent_craft_sell = player.get_crafted_sell_price_increase()
    print(f"Total Sell Price Increase (Crafted): +{flat_craft_sell} flat, +{percent_craft_sell}%")

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


def quick_gold(game, args):
    """Quick gold command: gold [player]"""
    player_name = args[0] if args else game.current_player_name

    if not player_name:
        print("Error: No player specified and no current player set")
        return

    player = game.get_player(player_name)
    if not player:
        print(f"Error: Player '{player_name}' not found")
        return

    print(f"{player.name}: {player.gold}{game.currency_symbol}")


def quick_equip(game, args):
    """Quick equip command: equip <index> [player]"""
    if not args:
        print("Usage: equip <index> [player]")
        return

    try:
        index = int(args[0])
    except ValueError:
        print("Error: index must be a number")
        return

    player_name = args[1] if len(args) >= 2 else game.current_player_name

    if not player_name:
        print("Error: No player specified and no current player set")
        return

    player = game.get_player(player_name)
    if not player:
        print(f"Error: Player '{player_name}' not found")
        return

    # Filter for Equipment items
    equipment_items = [(i, item) for i, item in enumerate(player.inventory) if item.item_type.lower() == "equipment"]

    if not equipment_items:
        print(f"{player.name} has no equipment items to equip!")
        return

    if index < 0 or index >= len(equipment_items):
        print(f"Error: Invalid equipment index. Player has {len(equipment_items)} equipment items (0-{len(equipment_items)-1})")
        return

    inv_idx, item = equipment_items[index]
    player.remove_item(inv_idx)
    player.equip_item(item)
    print(f"✓ Equipped {item.name}!")


def quick_consume(game, args):
    """Quick consume command: consume <index> [player]"""
    if not args:
        print("Usage: consume <index> [player]")
        return

    try:
        index = int(args[0])
    except ValueError:
        print("Error: index must be a number")
        return

    player_name = args[1] if len(args) >= 2 else game.current_player_name

    if not player_name:
        print("Error: No player specified and no current player set")
        return

    player = game.get_player(player_name)
    if not player:
        print(f"Error: Player '{player_name}' not found")
        return

    # Filter for Upgrade items
    upgrade_items = [(i, item) for i, item in enumerate(player.inventory) if item.item_type.lower() == "upgrade"]

    if not upgrade_items:
        print(f"{player.name} has no upgrade items to consume!")
        return

    if index < 0 or index >= len(upgrade_items):
        print(f"Error: Invalid upgrade index. Player has {len(upgrade_items)} upgrade items (0-{len(upgrade_items)-1})")
        return

    inv_idx, item = upgrade_items[index]
    player.remove_item(inv_idx)
    player.consume_upgrade(item)
    print(f"✓ Consumed {item.name}! Effects are now permanently applied.")


def quick_give_gold(game, args):
    """Quick give gold command: give <amount> [player]"""
    if not args:
        print("Usage: give <amount> [player]")
        return

    try:
        amount = int(args[0])
    except ValueError:
        print("Error: amount must be a number")
        return

    player_name = args[1] if len(args) >= 2 else game.current_player_name

    if not player_name:
        print("Error: No player specified and no current player set")
        return

    player = game.get_player(player_name)
    if not player:
        print(f"Error: Player '{player_name}' not found")
        return

    player.add_gold(amount)
    print(f"✓ Gave {amount}{game.currency_symbol} to {player.name} (now has {player.gold}{game.currency_symbol})")


def quick_take_gold(game, args):
    """Quick take gold command: take <amount> [player]"""
    if not args:
        print("Usage: take <amount> [player]")
        return

    try:
        amount = int(args[0])
    except ValueError:
        print("Error: amount must be a number")
        return

    player_name = args[1] if len(args) >= 2 else game.current_player_name

    if not player_name:
        print("Error: No player specified and no current player set")
        return

    player = game.get_player(player_name)
    if not player:
        print(f"Error: Player '{player_name}' not found")
        return

    if player.remove_gold(amount):
        print(f"✓ Took {amount}{game.currency_symbol} from {player.name} (now has {player.gold}{game.currency_symbol})")
    else:
        print(f"Error: Player doesn't have enough {game.currency_name}!")


def show_context_header(game):
    """Display current player and table context."""
    print("\n" + "=" * 60)

    # Current Player info
    if game.current_player_name and game.current_player_name in game.players:
        player = game.players[game.current_player_name]
        print(f"Current Player: {player.name} ({player.gold}{game.currency_symbol}, {len(player.inventory)} items)")
    else:
        print("Current Player: None")

    # Current Table info
    current_table = game.get_current_table()
    if current_table:
        print(f"Current Table: {current_table.name} (Draw Cost: {current_table.draw_cost}{game.currency_symbol}, {len(current_table.items)} items)")
    else:
        print("Current Table: None")

    print("=" * 60)


def show_main_menu():
    print("\n" + "=" * 40)
    print("LOOT TABLE SYSTEM")
    print("=" * 40)
    print("0. Quick Commands")
    print("1. Quick Turn")
    print("2. Manage Loot Table")
    print("3. Manage Players")
    print("4. Draw Items")
    print("5. Shop")
    print("6. Sell Items")
    print("7. Crafting Menu")
    print("8. Equipment & Upgrades")
    print("9. Admin Menu")
    print("10. Save Game")
    print("11. Exit")
    print("=" * 40)


def show_master_items_menu():
    print("\n--- MASTER ITEMS REGISTRY ---")
    print("1. Add master item")
    print("2. Edit master item")
    print("3. Delete master item")
    print("4. View all master items")
    print("5. Back to loot table menu")


def manage_master_items(game):
    """Manage the master items registry."""
    while True:
        show_master_items_menu()
        choice = input("Enter choice: ").strip()

        if choice == "1":
            # Add master item
            name = input("Enter item name: ").strip()
            if not name:
                print("Name cannot be empty!")
                continue

            item_type = input("Enter item type (misc/equipment/upgrade/consumable): ").strip()
            if not item_type:
                item_type = "misc"

            try:
                gold_per_unit = int(input(f"Enter {game.currency_name} value per unit (sell price): ").strip())
                if gold_per_unit < 0:
                    print(f"{game.currency_name.capitalize()} value cannot be negative!")
                    continue

                purchase_input = input(f"Enter shop purchase price (leave blank for not for sale): ").strip()
                purchase_price = None
                if purchase_input:
                    purchase_price = int(purchase_input)
                    if purchase_price < 0:
                        print("Purchase price cannot be negative!")
                        continue

                result = game.add_master_item(name, item_type, gold_per_unit, purchase_price)
                if result:
                    print(f"✓ Added master item: {result}")
                else:
                    print(f"Item '{name}' already exists in the registry!")
            except ValueError:
                print(f"Invalid {game.currency_name} value!")

        elif choice == "2":
            # Edit master item
            if not game.master_items:
                print("No master items exist!")
                continue

            print("\nMaster Items:")
            for i, item in enumerate(game.master_items):
                print(f"  {i}. {item.name} ({item.item_type}) - {item.gold_value_per_unit}{game.currency_symbol} each")

            try:
                index = int(input("\nEnter item number to edit: ").strip())
                if index < 0 or index >= len(game.master_items):
                    print("Invalid item number!")
                    continue

                item = game.master_items[index]
                print(f"\nEditing: {item.name}")
                print("Leave blank to keep current value")

                new_name = input(f"New name [{item.name}]: ").strip()
                new_type = input(f"New type [{item.item_type}]: ").strip()
                new_gold = input(f"New {game.currency_name} per unit [{item.gold_value_per_unit}{game.currency_symbol}]: ").strip()

                purchase_display = f"{item.purchase_price}{game.currency_symbol}" if item.purchase_price is not None else "not for sale"
                new_purchase = input(f"New shop purchase price [{purchase_display}]: ").strip()

                if new_name:
                    item.name = new_name
                if new_type:
                    item.item_type = new_type
                if new_gold:
                    item.gold_value_per_unit = int(new_gold)
                if new_purchase:
                    if new_purchase.lower() == 'none':
                        item.purchase_price = None
                    else:
                        item.purchase_price = int(new_purchase)

                print(f"✓ Updated: {item}")
            except ValueError:
                print("Invalid input!")

        elif choice == "3":
            # Delete master item
            if not game.master_items:
                print("No master items exist!")
                continue

            print("\nMaster Items:")
            for i, item in enumerate(game.master_items):
                print(f"  {i}. {item.name} ({item.item_type}) - {item.gold_value_per_unit}{game.currency_symbol} each")

            try:
                index = int(input("\nEnter item number to delete: ").strip())
                deleted = game.remove_master_item(index)
                if deleted:
                    print(f"✓ Deleted: {deleted.name}")
                else:
                    print("Invalid item number!")
            except ValueError:
                print("Invalid input!")

        elif choice == "4":
            # View all master items
            if not game.master_items:
                print("No master items exist!")
                continue

            print(f"\n{'=' * 60}")
            print("MASTER ITEMS REGISTRY")
            print(f"{'=' * 60}")
            for i, item in enumerate(game.master_items):
                print(f"{i}. {item.name} ({item.item_type}) - {item.gold_value_per_unit}{game.currency_symbol} each")
            print(f"{'=' * 60}")

        elif choice == "5":
            break
        else:
            print("Invalid choice!")


def show_loot_menu():
    print("\n--- LOOT TABLE MENU ---")
    print("1. Select/Create loot table")
    print("2. Manage Master Items Registry")
    print("3. Manage Consumables")
    print("4. Add item to current table")
    print("5. Edit item in current table")
    print("6. Delete item from current table")
    print("7. Edit table settings (name, draw cost)")
    print("8. Delete current table")
    print("9. View all items in current table (with weights)")
    print("10. View rates for players (percentages only)")
    print("11. View all tables")
    print("12. Back to main menu")


def show_player_menu():
    print("\n--- PLAYER MENU ---")
    print("1. Add player")
    print("2. Remove player")
    print("3. View player info")
    print("4. View all players")
    print("5. Set current player")
    print("6. Use consumable")
    print("7. Back to main menu")


def show_admin_menu(currency_name="gold"):
    print("\n--- ADMIN MENU ---")
    print(f"1. Give {currency_name} to player")
    print(f"2. Take {currency_name} from player")
    print("3. Gift item to player")
    print("4. Take item from player")
    print("5. Change currency settings")
    print("6. Configure rarity weights")
    print("7. Manage effect pool")
    print("8. Manage shop")
    print("9. Back to main menu")


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
            print("  3. sell_price_increase (for non-crafted items)")
            print("  4. crafted_sell_price_increase (for crafted items)")
            effect_type_choice = input("Choose effect type (1-4): ").strip()

            if effect_type_choice == '1':
                effect_type = "draw_cost_reduction"
            elif effect_type_choice == '2':
                effect_type = "double_quantity_chance"
            elif effect_type_choice == '3':
                effect_type = "sell_price_increase"
            elif effect_type_choice == '4':
                effect_type = "crafted_sell_price_increase"
            else:
                print("Invalid effect type!")
                continue

            try:
                value = float(input("Enter effect value: ").strip())
                if value <= 0:
                    print("Value must be greater than 0!")
                    continue

                # double_quantity_chance is always percentage
                if effect_type == "double_quantity_chance":
                    is_percentage = True
                    print("(Note: double_quantity_chance is always a percentage value)")
                else:
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

            name = get_player_name_input(game)
            player = game.get_player(name)
            if not player:
                print(f"Player '{name}' not found!")
                continue

            print(f"\n--- {player.name}'s Equipment & Upgrades ---")

            flat, percent = player.get_total_draw_cost_reduction()
            print(f"Total Draw Cost Reduction: -{flat} flat, -{percent}%")

            double_chance = player.get_double_quantity_chance()
            print(f"Total Double Quantity Chance: {double_chance}%")

            flat_sell, percent_sell = player.get_sell_price_increase()
            print(f"Total Sell Price Increase (Non-Crafted): +{flat_sell} flat, +{percent_sell}%")

            flat_craft_sell, percent_craft_sell = player.get_crafted_sell_price_increase()
            print(f"Total Sell Price Increase (Crafted): +{flat_craft_sell} flat, +{percent_craft_sell}%")

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

            name = get_player_name_input(game)
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

            name = get_player_name_input(game)
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

            name = get_player_name_input(game)
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


def manage_consumables(game):
    """Manage consumable items with temporary effects."""
    while True:
        print("\n--- CONSUMABLES MENU ---")
        print("1. Add consumable")
        print("2. Edit consumable")
        print("3. Delete consumable")
        print("4. View all consumables")
        print("5. Back to loot table menu")

        choice = input("Enter choice: ").strip()

        if choice == "1":
            # Add consumable
            name = input("Enter consumable name: ").strip()
            if not name:
                print("Name cannot be empty!")
                continue

            print("\nAvailable effect types:")
            print("  1. double_next_draw - Doubles quantity on next draw (guaranteed)")
            effect_choice = input("Choose effect type (1): ").strip()

            if effect_choice == "1":
                effect_type = "double_next_draw"
            else:
                print("Invalid effect type!")
                continue

            try:
                gold_value = int(input(f"Enter sell {game.currency_name} value: ").strip())
                if gold_value < 0:
                    print("Value cannot be negative!")
                    continue

                consumable = Consumable(name, effect_type, None, gold_value)
                game.consumables.append(consumable)
                print(f"✓ Added consumable: {consumable}")
            except ValueError:
                print("Invalid input!")

        elif choice == "2":
            # Edit consumable
            if not game.consumables:
                print("No consumables exist!")
                continue

            print("\nConsumables:")
            for i, cons in enumerate(game.consumables):
                print(f"  {i}. {cons}")

            try:
                index = int(input("\nEnter consumable number to edit: ").strip())
                if index < 0 or index >= len(game.consumables):
                    print("Invalid consumable number!")
                    continue

                cons = game.consumables[index]
                print(f"\nEditing: {cons.name}")
                print("Leave blank to keep current value")

                new_name = input(f"New name [{cons.name}]: ").strip()
                new_gold = input(f"New sell value [{cons.gold_value}{game.currency_symbol}]: ").strip()

                if new_name:
                    cons.name = new_name
                if new_gold:
                    cons.gold_value = int(new_gold)

                print(f"✓ Updated: {cons}")
            except ValueError:
                print("Invalid input!")

        elif choice == "3":
            # Delete consumable
            if not game.consumables:
                print("No consumables exist!")
                continue

            print("\nConsumables:")
            for i, cons in enumerate(game.consumables):
                print(f"  {i}. {cons}")

            try:
                index = int(input("\nEnter consumable number to delete: ").strip())
                if 0 <= index < len(game.consumables):
                    deleted = game.consumables.pop(index)
                    print(f"✓ Deleted consumable: {deleted.name}")
                else:
                    print("Invalid consumable number!")
            except ValueError:
                print("Invalid input!")

        elif choice == "4":
            # View all consumables
            if not game.consumables:
                print("No consumables exist!")
                continue

            print(f"\n{'=' * 60}")
            print("ALL CONSUMABLES")
            print(f"{'=' * 60}")
            for i, cons in enumerate(game.consumables):
                print(f"{i}. {cons}")
            print(f"{'=' * 60}")

        elif choice == "5":
            break


def manage_loot_table(game):
    while True:
        current_table = game.get_current_table()
        if current_table:
            print(
                f"\n[Current Table: {current_table.name} (Draw Cost: {current_table.draw_cost}{game.currency_symbol}, Items: {len(current_table.items)})]")
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
                    print(f"  {i}. {table.name} (Draw Cost: {table.draw_cost}{game.currency_symbol}, Items: {len(table.items)}){marker}")

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
            # Manage Master Items Registry
            manage_master_items(game)

        elif choice == "3":
            # Manage Consumables
            manage_consumables(game)

        elif choice == "4":
            # Add item
            if not current_table:
                print("No table selected!")
                continue

            # Check if master items exist
            if game.master_items:
                print("\nChoose how to add item:")
                print("1. From Master Items Registry")
                print("2. Create custom item (not in registry)")
                add_choice = input("Choice: ").strip()

                if add_choice == "1":
                    # Add from master items
                    print("\nMaster Items:")
                    for i, master_item in enumerate(game.master_items):
                        print(f"  {i}. {master_item.name} ({master_item.item_type}) - {master_item.gold_value_per_unit}{game.currency_symbol} each")

                    try:
                        item_index = int(input("\nEnter item number: ").strip())
                        if item_index < 0 or item_index >= len(game.master_items):
                            print("Invalid item number!")
                            continue

                        master_item = game.master_items[item_index]
                        quantity = int(input("Enter quantity (default 1): ").strip() or "1")
                        weight = float(input("Enter weight: ").strip())

                        if weight <= 0 or quantity < 1:
                            print("Invalid values!")
                            continue

                        loot_item = master_item.create_loot_item(quantity, weight)
                        current_table.items.append(loot_item)
                        display_name = f"{quantity}x {master_item.name}" if quantity > 1 else master_item.name
                        print(f"✓ Added '{display_name}' to {current_table.name}")
                    except ValueError:
                        print("Invalid input!")
                    continue
                elif add_choice != "2":
                    print("Invalid choice!")
                    continue

            # Create custom item
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

        elif choice == "4":
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

        elif choice == "6":
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

        elif choice == "7":
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

        elif choice == "8":
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

        elif choice == "9":
            # View all items
            if not current_table or not current_table.items:
                print("No items in current table!")
                continue

            print(f"\n{current_table.name} (Admin View):")
            total_weight = sum(item.weight for item in current_table.items)
            for item in current_table.items:
                percentage = (item.weight / total_weight) * 100
                print(f"  - {item.get_display_name()}: weight {item.weight} ({percentage:.2f}%), value {item.gold_value}{game.currency_symbol}")

        elif choice == "10":
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

        elif choice == "11":
            # View all tables
            if not game.loot_tables:
                print("No tables exist!")
                continue

            print("\nAll Loot Tables:")
            for i, table in enumerate(game.loot_tables):
                marker = " <-- CURRENT" if i == game.current_table_index else ""
                print(f"  {i}. {table.name} (Draw Cost: {table.draw_cost}{game.currency_symbol}, Items: {len(table.items)}){marker}")

        elif choice == "12":
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
                current_marker = " <-- CURRENT" if name == game.current_player_name else ""
                print(f"  - {name}: {player.gold}{game.currency_symbol}, {len(player.inventory)} items{current_marker}")

        elif choice == "5":
            # Set current player
            if not game.players:
                print("No players exist!")
                continue

            print("\nAvailable players:")
            for name, player in game.players.items():
                current_marker = " <-- CURRENT" if name == game.current_player_name else ""
                print(f"  - {name}{current_marker}")

            player_name = input("\nEnter player name to set as current (or 'none' to clear): ").strip()

            if player_name.lower() == 'none':
                game.current_player_name = None
                print("✓ Cleared current player")
            elif player_name in game.players:
                game.current_player_name = player_name
                print(f"✓ Set current player to '{player_name}'")
            else:
                print(f"Player '{player_name}' not found!")

        elif choice == "6":
            # Use consumable
            if not game.players:
                print("No players exist!")
                continue

            print("\nAvailable players:")
            for name, player in game.players.items():
                current_marker = " <-- CURRENT" if name == game.current_player_name else ""
                print(f"  - {name}{current_marker}")

            player_name = get_player_name_input(game)
            player = game.get_player(player_name)

            if not player:
                print(f"Player '{player_name}' not found!")
                continue

            # Find consumables in inventory
            consumable_items = [(i, item) for i, item in enumerate(player.inventory) if item.item_type == "consumable"]

            if not consumable_items:
                print(f"{player.name} has no consumables!")
                continue

            print(f"\n{player.name}'s Consumables:")
            for idx, (inv_idx, item) in enumerate(consumable_items):
                print(f"  {idx}. {item}")

            try:
                choice_idx = int(input("\nEnter consumable number to use: ").strip())
                if choice_idx < 0 or choice_idx >= len(consumable_items):
                    print("Invalid consumable number!")
                    continue

                inv_idx, consumable_item = consumable_items[choice_idx]

                # Find the consumable definition
                matching_consumable = None
                for cons in game.consumables:
                    if cons.name == consumable_item.name:
                        matching_consumable = cons
                        break

                if not matching_consumable:
                    print(f"Warning: Consumable '{consumable_item.name}' not found in definitions! Using as-is.")
                    # Still allow consumption if it's in inventory even if not in definitions
                    effect_type = "double_next_draw"  # Default for now
                else:
                    effect_type = matching_consumable.effect_type

                # Remove from inventory
                player.remove_item(inv_idx)

                # Add effect to active effects
                player.active_consumable_effects.append({
                    'effect_type': effect_type,
                    'name': consumable_item.name
                })

                print(f"\n✨ {player.name} used {consumable_item.name}!")
                if effect_type == "double_next_draw":
                    print("   Effect: Next draw will have DOUBLED quantity (guaranteed)!")
                print(f"\nActive effects: {len(player.active_consumable_effects)}")
                for eff in player.active_consumable_effects:
                    print(f"  - {eff['name']} ({eff['effect_type']})")

            except ValueError:
                print("Invalid input!")

        elif choice == "7":
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
            current_marker = " <-- CURRENT" if name == game.current_player_name else ""
            print(f"  - {name} ({player.gold}{game.currency_symbol}){current_marker}")

        player_name = get_player_name_input(game)
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

        # Check for active consumable effects
        has_double_next_draw = False
        for effect in player.active_consumable_effects:
            if effect['effect_type'] == 'double_next_draw':
                has_double_next_draw = True
                print(f"🔥 CONSUMABLE EFFECT ACTIVE: {effect['name']} - All items will be DOUBLED!")
                break

        # Get double quantity chance
        double_chance = player.get_double_quantity_chance()

        # Get sell price increase for non-crafted items
        flat_price, percent_price = player.get_sell_price_increase()

        total_value = 0
        doubled_count = 0
        price_boosted_count = 0
        consumable_doubled_count = 0

        for i, item in enumerate(items, 1):
            # Roll rarity for Equipment items
            if item.item_type.lower() == "equipment" and not item.rarity:
                item.rarity = game.rarity_system.roll_rarity()

            # Apply sell price increase to non-crafted items
            price_boosted = False
            if flat_price > 0 or percent_price > 0:
                original_value = item.gold_value
                item.gold_value = player.calculate_item_value(original_value, is_crafted=False)
                if item.gold_value > original_value:
                    price_boosted_count += 1
                    price_boosted = True

            # Check if we should double the quantity
            doubled = False
            consumable_doubled = False

            # Apply consumable effect (guaranteed double)
            if has_double_next_draw:
                item.quantity *= 2
                item.gold_value *= 2
                consumable_doubled_count += 1
                consumable_doubled = True
            # Otherwise check for chance-based double
            elif double_chance > 0 and random.random() * 100 < double_chance:
                item.quantity *= 2
                item.gold_value *= 2
                doubled_count += 1
                doubled = True

            # Display item with indicators
            indicators = []
            if consumable_doubled:
                indicators.append("🔥 CONSUMABLE DOUBLED!")
            elif doubled:
                indicators.append("✨ DOUBLED!")
            if price_boosted:
                indicators.append("💰 PRICE BOOST!")

            if indicators:
                print(f"  {i}. {item} {' '.join(indicators)}")
            else:
                print(f"  {i}. {item}")

            player.add_item(item)
            total_value += item.gold_value

        # Remove consumable effect after use
        if has_double_next_draw:
            player.active_consumable_effects = [eff for eff in player.active_consumable_effects if eff['effect_type'] != 'double_next_draw']
            print(f"\n🔥 Consumable effect used! {consumable_doubled_count} item(s) DOUBLED from consumable!")

        if doubled_count > 0:
            print(f"\n✨ {doubled_count} item(s) had their quantity doubled! (Chance: {double_chance}%)")

        if price_boosted_count > 0:
            print(f"💰 {price_boosted_count} item(s) had their value increased! (+{flat_price} flat, +{percent_price}%)")

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
        current_marker = " <-- CURRENT" if name == game.current_player_name else ""
        print(f"  - {name} ({player.gold}{game.currency_symbol}, {len(player.inventory)} items){current_marker}")

    player_name = get_player_name_input(game)
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


def shop_menu(game):
    """Shop where players can buy items from the shop catalog."""
    if not game.players:
        print("No players exist! Add players first.")
        return

    if not game.shop_items:
        print("The shop is empty! Add items to the shop first (Admin Menu > Manage Shop).")
        return

    print("\nAvailable players:")
    for name, player in game.players.items():
        current_marker = " <-- CURRENT" if name == game.current_player_name else ""
        print(f"  - {name} ({player.gold}{game.currency_symbol}){current_marker}")

    player_name = get_player_name_input(game)
    player = game.get_player(player_name)

    if not player:
        print(f"Player '{player_name}' not found!")
        return

    while True:
        print(f"\n{'=' * 60}")
        print("SHOP")
        print(f"{'=' * 60}")
        print(f"{player.name}'s {game.currency_name}: {player.gold}{game.currency_symbol}")
        print()

        # Display shop items
        print("Available items:")
        for i, shop_item in enumerate(game.shop_items):
            print(f"  {i}. {shop_item}")

        choice = input("\nEnter item number to buy (or 'back' to return): ").strip().lower()

        if choice == 'back':
            break

        try:
            index = int(choice)
            if index < 0 or index >= len(game.shop_items):
                print("Invalid item number!")
                continue

            shop_item = game.shop_items[index]

            # Get quantity
            quantity = int(input("How many to buy? ").strip())
            if quantity <= 0:
                print("Quantity must be at least 1!")
                continue

            # Calculate total cost
            total_cost = shop_item.purchase_price * quantity

            # Check if player has enough money
            if player.gold < total_cost:
                print(f"❌ Not enough {game.currency_name}! Need {total_cost}{game.currency_symbol}, have {player.gold}{game.currency_symbol}")
                continue

            # Deduct money
            player.remove_gold(total_cost)

            # Add items to inventory
            for _ in range(quantity):
                loot_item = LootItem(shop_item.name, 1000, shop_item.gold_value, shop_item.item_type, 1)
                player.add_item(loot_item)

            print(f"\n✓ Purchased {quantity}x {shop_item.name} for {total_cost}{game.currency_symbol}!")
            print(f"New {game.currency_name} balance: {player.gold}{game.currency_symbol}")

        except ValueError:
            print("Invalid input!")


def quick_turn_menu(game):
    """Execute a quick turn: draw, show results, craft, sell for all players."""
    if not game.loot_tables:
        print("No loot tables exist! Create one first.")
        return

    if not game.players:
        print("No players exist! Add players first.")
        return

    print("\n" + "=" * 60)
    print("QUICK TURN MODE")
    print("=" * 60)

    # Phase 1: Draw phase
    print("\n📦 PHASE 1: DRAWING")
    print("-" * 60)

    # Get number of draws per player
    try:
        draws_per_player = int(input("How many draws per player? ").strip())
        if draws_per_player <= 0:
            print("Number of draws must be greater than 0!")
            return
    except ValueError:
        print("Invalid input!")
        return

    # Iterate through all players for drawing
    for player_name, player in game.players.items():
        print(f"\n--- {player_name}'s Turn to Draw ---")
        print(f"{game.currency_name.capitalize()}: {player.gold}{game.currency_symbol}")

        # Show available tables
        print("\nAvailable loot tables:")
        for i, table in enumerate(game.loot_tables):
            print(f"  {i}. {table.name} (Cost: {table.draw_cost}{game.currency_symbol} per draw, Items: {len(table.items)})")

        try:
            table_index = int(input(f"\n{player_name}, select table number: ").strip())
            if table_index < 0 or table_index >= len(game.loot_tables):
                print("Invalid table number! Skipping this player.")
                continue

            selected_table = game.loot_tables[table_index]

            if not selected_table.items:
                print(f"Table '{selected_table.name}' has no items! Skipping this player.")
                continue

            # Calculate actual draw cost with reductions
            base_cost = selected_table.draw_cost
            actual_cost = player.calculate_draw_cost(base_cost)
            total_cost = draws_per_player * actual_cost

            # Check if player has enough currency
            if player.gold < total_cost:
                print(f"❌ Not enough {game.currency_name}! Need {total_cost}{game.currency_symbol} but {player.name} only has {player.gold}{game.currency_symbol}")
                print("Skipping this player.")
                continue

            # Deduct cost
            player.remove_gold(total_cost)

            # Draw items
            items = selected_table.draw_multiple(draws_per_player)
            print(f"\n💰 Paid {total_cost}{game.currency_symbol} ({draws_per_player} x {actual_cost}{game.currency_symbol}) to {selected_table.name}")
            print(f"🎲 {player.name} drew {draws_per_player} items:")

            # Get double quantity chance
            double_chance = player.get_double_quantity_chance()

            # Get sell price increase for non-crafted items
            flat_price, percent_price = player.get_sell_price_increase()

            total_value = 0
            doubled_count = 0
            price_boosted_count = 0

            for i, item in enumerate(items, 1):
                # Roll rarity for Equipment items
                if item.item_type.lower() == "equipment" and not item.rarity:
                    item.rarity = game.rarity_system.roll_rarity()

                # Apply sell price increase to non-crafted items
                price_boosted = False
                if flat_price > 0 or percent_price > 0:
                    original_value = item.gold_value
                    item.gold_value = player.calculate_item_value(original_value, is_crafted=False)
                    if item.gold_value > original_value:
                        price_boosted_count += 1
                        price_boosted = True

                # Check if we should double the quantity
                doubled = False
                if double_chance > 0 and random.random() * 100 < double_chance:
                    item.quantity *= 2
                    item.gold_value *= 2
                    doubled_count += 1
                    doubled = True

                # Display item with indicators
                indicators = []
                if doubled:
                    indicators.append("✨ DOUBLED!")
                if price_boosted:
                    indicators.append("💰 PRICE BOOST!")

                if indicators:
                    print(f"  {i}. {item} {' '.join(indicators)}")
                else:
                    print(f"  {i}. {item}")

                player.add_item(item)
                total_value += item.gold_value

            if doubled_count > 0:
                print(f"\n✨ {doubled_count} item(s) had their quantity doubled! (Chance: {double_chance}%)")

            if price_boosted_count > 0:
                print(f"💰 {price_boosted_count} item(s) had their value increased! (+{flat_price} flat, +{percent_price}%)")

            net_value = total_value - total_cost
            print(f"\nTotal value: {total_value}{game.currency_symbol}")
            print(f"Net gain/loss: {net_value:+d}{game.currency_symbol}")
            print(f"{player.name}'s {game.currency_name}: {player.gold}{game.currency_symbol} | Inventory: {len(player.inventory)} items")

        except ValueError:
            print("Invalid input! Skipping this player.")
            continue

    # Phase 2: Show all inventories
    print("\n" + "=" * 60)
    print("📋 PHASE 2: INVENTORY SUMMARY")
    print("=" * 60)

    for player_name, player in game.players.items():
        print(f"\n--- {player_name} ---")
        print(f"{game.currency_name.capitalize()}: {player.gold}{game.currency_symbol} | Items: {len(player.inventory)}")

        if player.inventory:
            # Group items by name for compact display
            item_groups = {}
            for item in player.inventory:
                key = item.name
                if key not in item_groups:
                    item_groups[key] = []
                item_groups[key].append(item)

            print("Items:")
            for item_name, items in sorted(item_groups.items()):
                total_quantity = sum(item.quantity for item in items)
                total_value = sum(item.gold_value for item in items)
                count = len(items)
                if count == 1 and items[0].quantity == 1:
                    print(f"  • {items[0]}")
                else:
                    print(f"  • {item_name} x{total_quantity} ({count} stack(s), {total_value}{game.currency_symbol} total)")
        else:
            print("  (No items)")

    # Phase 3: Crafting phase
    print("\n" + "=" * 60)
    print("🔨 PHASE 3: CRAFTING")
    print("=" * 60)

    if not game.crafting_recipes:
        print("No crafting recipes available. Skipping crafting phase.")
    else:
        for player_name, player in game.players.items():
            print(f"\n--- {player_name}'s Crafting Turn ---")

            if not player.inventory:
                print(f"{player_name} has no items to craft with. Skipping.")
                continue

            while True:
                craft_choice = input(f"\n{player_name}, craft an item? (y/n or 'done'): ").strip().lower()

                if craft_choice in ['n', 'done']:
                    break

                if craft_choice != 'y':
                    print("Please enter 'y', 'n', or 'done'")
                    continue

                # Show available recipes
                print("\nAvailable recipes:")
                for i, recipe in enumerate(game.crafting_recipes):
                    print(f"  {i}. {recipe}")

                try:
                    recipe_index = int(input("\nEnter recipe number to craft (or -1 to skip): ").strip())
                    if recipe_index == -1:
                        break

                    if recipe_index < 0 or recipe_index >= len(game.crafting_recipes):
                        print("Invalid recipe number!")
                        continue

                    recipe = game.crafting_recipes[recipe_index]

                    # Count required quantities for each ingredient
                    required_ingredients = {}
                    for ingredient in recipe.ingredients:
                        required_ingredients[ingredient] = required_ingredients.get(ingredient, 0) + 1

                    # Check if player has all ingredients in required quantities
                    missing_ingredients = []
                    for ingredient, required_count in required_ingredients.items():
                        total_quantity = sum(item.quantity for item in player.inventory if item.name == ingredient)
                        if total_quantity < required_count:
                            missing_ingredients.append(f"{ingredient} ({total_quantity}/{required_count})")

                    if missing_ingredients:
                        print(f"❌ Missing ingredients: {', '.join(missing_ingredients)}")
                        continue

                    # Remove ingredients from inventory
                    for ingredient in recipe.ingredients:
                        player.consume_item_by_name(ingredient, 1)

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

                    # Apply crafted sell price increase
                    flat_craft_price, percent_craft_price = player.get_crafted_sell_price_increase()
                    if flat_craft_price > 0 or percent_craft_price > 0:
                        original_craft_value = crafted_item.gold_value
                        crafted_item.gold_value = player.calculate_item_value(original_craft_value, is_crafted=True)
                        if crafted_item.gold_value > original_craft_value:
                            print(f"💰 Crafted item value increased: {original_craft_value}{game.currency_symbol} → {crafted_item.gold_value}{game.currency_symbol} (+{flat_craft_price} flat, +{percent_craft_price}%)")

                    player.add_item(crafted_item)
                    print(f"\nAdded to inventory: {crafted_item}")

                except ValueError:
                    print("Invalid input!")
                    continue

    # Phase 4: Selling phase
    print("\n" + "=" * 60)
    print("💰 PHASE 4: SELLING")
    print("=" * 60)

    for player_name, player in game.players.items():
        print(f"\n--- {player_name}'s Selling Turn ---")

        if not player.inventory:
            print(f"{player_name} has no items to sell. Skipping.")
            continue

        while True:
            print(f"\n{player_name}'s Inventory:")
            print(f"{game.currency_name.capitalize()}: {player.gold}{game.currency_symbol}")
            print("Items:")
            for i, item in enumerate(player.inventory):
                print(f"  {i}. {item}")

            sell_choice = input(f"\n{player_name}, enter item number to sell (or 'done' to finish): ").strip().lower()

            if sell_choice == 'done':
                break

            try:
                index = int(sell_choice)
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
                print("Invalid input! Enter a number or 'done'")

    print("\n" + "=" * 60)
    print("✅ QUICK TURN COMPLETE!")
    print("=" * 60)


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
                output_gold = int(input(f"Enter output {game.currency_name} value (sell price): ").strip())
                if output_gold < 0:
                    print(f"Invalid {game.currency_name} value!")
                    continue

                purchase_input = input(f"Enter shop purchase price (leave blank for not for sale): ").strip()
                purchase_price = None
                if purchase_input:
                    purchase_price = int(purchase_input)
                    if purchase_price < 0:
                        print("Purchase price cannot be negative!")
                        continue

                recipe = CraftingRecipe(output_name, output_type, output_gold, purchase_price)

                print("\nAdd ingredients (enter item names)")
                print("\nAvailable from Master Items:")
                if game.master_items:
                    for master_item in sorted(game.master_items, key=lambda x: x.name):
                        print(f"  - {master_item.name} ({master_item.item_type})")
                else:
                    print("  (No master items)")

                print("\nAvailable from Crafting Recipes:")
                if game.crafting_recipes:
                    for recipe_item in sorted(game.crafting_recipes, key=lambda x: x.output_name):
                        print(f"  - {recipe_item.output_name} ({recipe_item.output_type})")
                else:
                    print("  (No recipes yet)")

                print("\nType 'done' when finished adding ingredients")
                while True:
                    ingredient = input("Add ingredient (or 'done' to finish): ").strip()
                    if ingredient.lower() == 'done':
                        break
                    if ingredient:
                        try:
                            quantity = int(input(f"How many {ingredient}? ").strip())
                            if quantity <= 0:
                                print("Quantity must be at least 1!")
                                continue
                            # Add the ingredient the specified number of times
                            for _ in range(quantity):
                                recipe.add_ingredient(ingredient)
                            print(f"✓ Added {quantity}x {ingredient}")
                        except ValueError:
                            print("Invalid quantity! Please enter a number.")

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
                current_marker = " <-- CURRENT" if name == game.current_player_name else ""
                print(f"  - {name}{current_marker}")

            player_name = get_player_name_input(game)
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
                    # Count required quantities for each ingredient
                    required_ingredients = {}
                    for ingredient in recipe.ingredients:
                        required_ingredients[ingredient] = required_ingredients.get(ingredient, 0) + 1

                    # Check if player has all ingredients in required quantities
                    missing_ingredients = []

                    for ingredient, required_count in required_ingredients.items():
                        # Count total quantity of this ingredient across all stacks
                        total_quantity = sum(item.quantity for item in player.inventory if item.name == ingredient)
                        if total_quantity < required_count:
                            missing_ingredients.append(f"{ingredient} ({total_quantity}/{required_count})")

                    if missing_ingredients:
                        if crafted_count > 0:
                            print(f"\n❌ Out of ingredients! Missing: {', '.join(missing_ingredients)}")
                        else:
                            print(f"❌ Missing ingredients: {', '.join(missing_ingredients)}")
                        break

                    # Remove ingredients from inventory (consumes from stacks)
                    for ingredient in recipe.ingredients:
                        player.consume_item_by_name(ingredient, 1)

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

                    # Apply crafted sell price increase
                    flat_craft_price, percent_craft_price = player.get_crafted_sell_price_increase()
                    if flat_craft_price > 0 or percent_craft_price > 0:
                        original_craft_value = crafted_item.gold_value
                        crafted_item.gold_value = player.calculate_item_value(original_craft_value, is_crafted=True)
                        if crafted_item.gold_value > original_craft_value:
                            print(f"💰 Crafted item value increased: {original_craft_value}{game.currency_symbol} → {crafted_item.gold_value}{game.currency_symbol} (+{flat_craft_price} flat, +{percent_craft_price}%)")

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

            enchant_type = input("Enter enchantment type (e.g., weapon, armor, misc): ").strip() or "misc"

            is_percentage_input = input("Is this a percentage-based enchantment? (y/n): ").strip().lower()
            is_percentage = is_percentage_input == 'y'

            try:
                if is_percentage:
                    print("\nEnter percentage range (can be negative for penalty, positive for bonus)")
                    print("Example: -50 to 50 means it could reduce value by 50% or increase by 50%")
                    min_value = float(input("Minimum percentage: ").strip())
                    max_value = float(input("Maximum percentage: ").strip())
                else:
                    print(f"\nEnter flat {game.currency_name} range (can be negative for penalty, positive for bonus)")
                    print("Example: -100 to 200 means it could reduce value by 100g or increase by 200g")
                    min_value = float(input(f"Minimum {game.currency_name} value: ").strip())
                    max_value = float(input(f"Maximum {game.currency_name} value: ").strip())

                if min_value > max_value:
                    print("Minimum value cannot be greater than maximum value!")
                    continue

                cost_amount = int(input(f"Enter cost (number of {game.enchant_cost_item or 'cost items'} required): ").strip() or "1")
                if cost_amount < 0:
                    print("Cost cannot be negative!")
                    continue

                enchant = Enchantment(name, enchant_type, min_value, max_value, is_percentage, cost_amount)
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
                print(f"  {i}. {ench}")

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

                value_type = "percentage" if ench.is_percentage else "flat"
                min_input = input(f"New minimum {value_type} [{ench.min_value}]: ").strip()
                max_input = input(f"New maximum {value_type} [{ench.max_value}]: ").strip()
                cost_input = input(f"New cost [{ench.cost_amount}]: ").strip()

                if new_name:
                    ench.name = new_name
                if new_type:
                    ench.enchant_type = new_type
                if min_input:
                    new_min = float(min_input)
                    if new_min <= ench.max_value:
                        ench.min_value = new_min
                    else:
                        print("Minimum cannot be greater than maximum!")
                if max_input:
                    new_max = float(max_input)
                    if new_max >= ench.min_value:
                        ench.max_value = new_max
                    else:
                        print("Maximum cannot be less than minimum!")
                if cost_input:
                    ench.cost_amount = int(cost_input)

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

            print(f"\n{'=' * 60}")
            print(f"Global Enchantment Cost Item: {game.enchant_cost_item or 'None'}")
            print(f"{'=' * 60}")
            print("\nAll Enchantments:")
            for i, ench in enumerate(game.enchantments):
                print(f"  {i}. {ench}")

        elif choice == "6":
            if not game.enchantments:
                print("No enchantments exist!")
                continue

            if not game.players:
                print("No players exist!")
                continue

            print("\nAvailable players:")
            for name, player in game.players.items():
                current_marker = " <-- CURRENT" if name == game.current_player_name else ""
                print(f"  - {name}{current_marker}")

            player_name = get_player_name_input(game)
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

                # Show all enchantments compatible with this item type
                compatible_enchants = [e for e in game.enchantments if e.enchant_type == item.item_type or e.enchant_type == "misc"]

                if not compatible_enchants:
                    print(f"No enchantments compatible with type '{item.item_type}'!")
                    continue

                print(f"\nCompatible enchantments for {item.name}:")
                for i, ench in enumerate(compatible_enchants):
                    print(f"  {i}. {ench}")

                ench_index = int(input("\nSelect enchantment number: ").strip())
                if ench_index < 0 or ench_index >= len(compatible_enchants):
                    print("Invalid enchantment number!")
                    continue

                selected_enchant = compatible_enchants[ench_index]

                # Check if player has enough cost items
                if game.enchant_cost_item:
                    # Count total quantity of cost item
                    cost_item_count = sum(inv_item.quantity for inv_item in player.inventory if inv_item.name == game.enchant_cost_item)

                    if cost_item_count < selected_enchant.cost_amount:
                        print(f"❌ Not enough {game.enchant_cost_item}! Need {selected_enchant.cost_amount}, have {cost_item_count}")
                        continue

                    # Consume the cost items
                    player.consume_item_by_name(game.enchant_cost_item, selected_enchant.cost_amount)
                    print(f"💰 Consumed {selected_enchant.cost_amount}x {game.enchant_cost_item}")

                    # Update item_index if items were removed before it
                    new_item_index = 0
                    for i, inv_item in enumerate(player.inventory):
                        if inv_item is item:
                            item_index = i
                            break

                # Apply the enchantment and get the rolled value
                original_value = item.gold_value
                rolled_value = selected_enchant.apply_to_item(item)

                # Store the enchantment with its rolled value
                item.enchantments.append((selected_enchant, rolled_value))

                print(f"\n✨ Applied enchantment: {selected_enchant.name}")
                if selected_enchant.is_percentage:
                    print(f"   Rolled: {rolled_value:+.1f}%")
                else:
                    print(f"   Rolled: {rolled_value:+.0f}g")
                print(f"   Item value: {original_value}g → {item.gold_value}g")
                print(f"\n✓ New item: {item}")
            except ValueError:
                print("Invalid input!")

        elif choice == "7":
            break


def manage_shop(game):
    """Manage shop items that players can purchase."""
    while True:
        print("\n--- SHOP MANAGEMENT ---")
        print("1. Add item to shop")
        print("2. Remove item from shop")
        print("3. View all shop items")
        print("4. Back to admin menu")

        choice = input("Enter choice: ").strip()

        if choice == "1":
            # Add item to shop
            name = input("Enter item name: ").strip()
            if not name:
                print("Name cannot be empty!")
                continue

            item_type = input("Enter item type (misc/equipment/upgrade/consumable): ").strip() or "misc"

            try:
                sell_value = int(input(f"Enter sell value (what players get when they sell it): ").strip())
                if sell_value < 0:
                    print("Sell value cannot be negative!")
                    continue

                purchase_price = int(input(f"Enter purchase price (what players pay to buy it): ").strip())
                if purchase_price < 0:
                    print("Purchase price cannot be negative!")
                    continue

                shop_item = ShopItem(name, item_type, sell_value, purchase_price)
                game.shop_items.append(shop_item)
                print(f"✓ Added to shop: {shop_item}")
            except ValueError:
                print("Invalid input!")

        elif choice == "2":
            # Remove item from shop
            if not game.shop_items:
                print("Shop is empty!")
                continue

            print("\nShop items:")
            for i, item in enumerate(game.shop_items):
                print(f"  {i}. {item}")

            try:
                index = int(input("\nEnter item number to remove: ").strip())
                if 0 <= index < len(game.shop_items):
                    removed = game.shop_items.pop(index)
                    print(f"✓ Removed from shop: {removed.name}")
                else:
                    print("Invalid item number!")
            except ValueError:
                print("Invalid input!")

        elif choice == "3":
            # View all shop items
            if not game.shop_items:
                print("Shop is empty!")
                continue

            print(f"\n{'=' * 60}")
            print("SHOP CATALOG")
            print(f"{'=' * 60}")
            for i, item in enumerate(game.shop_items):
                print(f"{i}. {item}")
            print(f"{'=' * 60}")

        elif choice == "4":
            break


def admin_menu(game):
    while True:
        show_admin_menu(game.currency_name)
        choice = input("Enter choice: ").strip()

        if choice == "1":
            if not game.players:
                print("No players exist!")
                continue

            name = get_player_name_input(game)
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

            name = get_player_name_input(game)
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

            name = get_player_name_input(game)
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
                item_copy = copy.deepcopy(item)

                # Roll rarity for Equipment items
                if item_copy.item_type.lower() == "equipment" and not item_copy.rarity:
                    item_copy.rarity = game.rarity_system.roll_rarity()
                    print(f"✨ Rolled [{item_copy.rarity}] rarity!")

                player.add_item(item_copy)
                print(f"✓ Gifted {item_copy} to {player.name}")
            except ValueError:
                print("Invalid input!")

        elif choice == "4":
            if not game.players:
                print("No players exist!")
                continue

            name = get_player_name_input(game)
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
            # Manage shop
            manage_shop(game)

        elif choice == "9":
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
        show_context_header(game)
        show_main_menu()
        choice = input("Enter your choice (0-11): ").strip()

        if choice == "0":
            quick_commands_menu(game)
        elif choice == "1":
            quick_turn_menu(game)
        elif choice == "2":
            manage_loot_table(game)
        elif choice == "3":
            manage_players(game)
        elif choice == "4":
            draw_items_menu(game)
        elif choice == "5":
            shop_menu(game)
        elif choice == "6":
            sell_items_menu(game)
        elif choice == "7":
            manage_crafting(game)
        elif choice == "8":
            manage_equipment_upgrades(game)
        elif choice == "9":
            admin_menu(game)
        elif choice == "10":
            if game.save_game():
                print("✓ Game saved successfully!")
            else:
                print("Failed to save game.")
        elif choice == "11":
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

            print("Invalid choice! Please enter 0-11.")
