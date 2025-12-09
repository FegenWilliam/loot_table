import random
import json
import os
import signal
import sys
import copy


class MasterItem:
    """Defines a master item template with name, type, and base gold value."""
    def __init__(self, name, item_type, gold_value_per_unit, purchase_price=None, recipe=None):
        self.name = name
        self.item_type = item_type
        self.gold_value_per_unit = gold_value_per_unit
        self.purchase_price = purchase_price  # Price to buy from shop (None = not for sale)
        self.recipe = recipe if recipe is not None else []  # List of ingredient names (empty = not craftable)

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
        self.enchantments = []  # List of (enchantment, rolled_value) tuples
        # For monetary: rolled_value is the actual rolled gold modifier
        # For functional: rolled_value is None

    def add_enchantment(self, enchantment, rolled_value=None):
        """Add an enchantment to this item.

        For monetary enchantments: If rolled_value is provided, use it; otherwise roll a new value.
        For functional enchantments: rolled_value should be None (no rolling).
        """
        if enchantment.enchantment_type == "monetary":
            if rolled_value is None:
                rolled_value = enchantment.apply_to_item(self)
            else:
                # Apply the provided rolled value
                if enchantment.is_percentage:
                    change = self.gold_value * (rolled_value / 100.0)
                    self.gold_value = max(0, int(self.gold_value + change))
                else:
                    self.gold_value = max(0, int(self.gold_value + rolled_value))
        # For functional enchantments, rolled_value stays None

        # Store enchantment with its rolled value (or None for functional) as a tuple
        self.enchantments.append((enchantment, rolled_value))

    def get_display_name(self):
        base_name = f"{self.quantity}x {self.name}" if self.quantity > 1 else self.name

        # Add rarity prefix for Equipment items
        if self.rarity:
            base_name = f"[{self.rarity}] {base_name}"

        # Show only monetary enchantments in display name
        if self.enchantments:
            monetary_enchants = [(ench, rv) for ench, rv in self.enchantments if ench.enchantment_type == "monetary"]
            if monetary_enchants:
                enchant_strs = []
                for ench, rolled_value in monetary_enchants:
                    if ench.is_percentage:
                        enchant_strs.append(f"{ench.name} {rolled_value:+.1f}%")
                    else:
                        enchant_strs.append(f"{ench.name} {rolled_value:+.0f}g")
                return f"{base_name} [{', '.join(enchant_strs)}]"
        return base_name

    def get_effects_display(self):
        """Get display string for functional enchantments."""
        functional_enchants = [(ench, rv) for ench, rv in self.enchantments if ench.enchantment_type == "functional"]
        if not functional_enchants:
            return ""
        effect_strs = []
        for ench, _ in functional_enchants:
            if ench.is_percentage:
                effect_strs.append(f"-{ench.value}%")
            else:
                effect_strs.append(f"-{ench.value}")
        return f" (Effects: {', '.join(effect_strs)})"

    def __str__(self):
        return f"{self.get_display_name()} ({self.gold_value}g)"

    def __repr__(self):
        return self.__str__()


class Enchantment:
    """Unified enchantment system supporting both functional and monetary types.

    Monetary enchantments: Modify gold value, applicable to any item type
    Functional enchantments: Provide gameplay effects, only for equipment/upgrades
    """
    def __init__(self, name, enchantment_type, **kwargs):
        """
        Args:
            name: Display name of the enchantment
            enchantment_type: "monetary" or "functional"

            For monetary enchantments:
                enchant_type: Item type compatibility (e.g., "weapon", "armor", "misc")
                min_value: Minimum gold value change
                max_value: Maximum gold value change
                is_percentage: True for %, False for flat
                cost_amount: Cost to apply this enchantment

            For functional enchantments:
                effect_type: Type of effect (e.g., "draw_cost_reduction")
                value: Fixed effect value
                is_percentage: True for %, False for flat
                weight: Weight for random selection when crafting
        """
        self.name = name
        self.enchantment_type = enchantment_type

        if enchantment_type == "monetary":
            self.enchant_type = kwargs.get('enchant_type', 'misc')
            self.min_value = kwargs.get('min_value', 0)
            self.max_value = kwargs.get('max_value', 0)
            self.is_percentage = kwargs.get('is_percentage', False)
            self.cost_amount = kwargs.get('cost_amount', 1)
            # Functional fields not used
            self.effect_type = None
            self.value = None
            self.weight = None
        elif enchantment_type == "functional":
            self.effect_type = kwargs.get('effect_type', 'draw_cost_reduction')
            self.value = kwargs.get('value', 0)
            self.is_percentage = kwargs.get('is_percentage', False)
            self.weight = kwargs.get('weight', 1000)
            # Monetary fields not used
            self.enchant_type = None
            self.min_value = None
            self.max_value = None
            self.cost_amount = None
        else:
            raise ValueError(f"Invalid enchantment_type: {enchantment_type}. Must be 'monetary' or 'functional'")

    def roll_value(self):
        """Roll a random value within the enchantment's range (monetary only)."""
        if self.enchantment_type != "monetary":
            raise ValueError("Cannot roll value for non-monetary enchantments")
        return random.uniform(self.min_value, self.max_value)

    def apply_to_item(self, item):
        """Apply this enchantment to an item and return the rolled value (monetary only)."""
        if self.enchantment_type != "monetary":
            raise ValueError("Cannot apply functional enchantment to item gold value")

        rolled_value = self.roll_value()

        if self.is_percentage:
            # Apply percentage change to gold value
            change = item.gold_value * (rolled_value / 100.0)
            item.gold_value = max(0, int(item.gold_value + change))
        else:
            # Apply flat change to gold value
            item.gold_value = max(0, int(item.gold_value + rolled_value))

        return rolled_value

    def get_effect_string(self):
        """Get display string for functional enchantments."""
        if self.enchantment_type != "functional":
            return ""
        if self.is_percentage:
            return f"{self.effect_type}: -{self.value}%"
        else:
            return f"{self.effect_type}: -{self.value}"

    def __str__(self):
        if self.enchantment_type == "monetary":
            if self.is_percentage:
                return f"{self.name} ({self.enchant_type}, {self.min_value:+.1f}% to {self.max_value:+.1f}%, Cost: {self.cost_amount})"
            else:
                return f"{self.name} ({self.enchant_type}, {self.min_value:+.0f}g to {self.max_value:+.0f}g, Cost: {self.cost_amount})"
        else:  # functional
            if self.is_percentage:
                return f"{self.name}: {self.effect_type} -{self.value}% (weight: {self.weight})"
            else:
                return f"{self.name}: {self.effect_type} -{self.value} (weight: {self.weight})"

    def __repr__(self):
        return self.__str__()


class RaritySystem:
    def __init__(self):
        # Define rarities with their weights and functional enchantment slots
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


class Consumable:
    """Consumable item with temporary effects."""
    def __init__(self, name, effect_type, effect_value=None, gold_value=0, table_name=None):
        self.name = name
        self.item_type = "consumable"
        self.effect_type = effect_type  # e.g., "double_next_draw"
        self.effect_value = effect_value  # Optional value for the effect
        self.gold_value = gold_value  # Base sell value
        self.table_name = table_name  # For free_draw_ticket: which table to draw from

    def __str__(self):
        if self.effect_type == "double_next_draw":
            return f"{self.name} (consumable, {self.gold_value}g) - Doubles quantity on next draw"
        elif self.effect_type == "free_draw_ticket":
            draws = self.effect_value if self.effect_value else 1
            table_info = f" from '{self.table_name}'" if self.table_name else " from selected table"
            return f"{self.name} (consumable, {self.gold_value}g) - Draw {draws} item(s) for free{table_info}"
        elif self.effect_type == "trash_to_treasure":
            return f"{self.name} (consumable, {self.gold_value}g) - Next draw excludes highest weight item"
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
        # Items with enchantments (monetary or functional) or rarity don't stack (they're unique)
        if item.enchantments or item.rarity:
            self.inventory.append(item)
            return

        # Try to find existing stack with same name and type
        for existing_item in self.inventory:
            if (existing_item.name == item.name and
                existing_item.item_type == item.item_type and
                not existing_item.enchantments and
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
            for ench, _ in item.enchantments:
                if ench.enchantment_type == "functional" and ench.effect_type == "draw_cost_reduction":
                    if ench.is_percentage:
                        percentage_reduction += ench.value
                    else:
                        flat_reduction += ench.value

        # Add effects from consumed upgrades
        for item in self.consumed_upgrades:
            for ench, _ in item.enchantments:
                if ench.enchantment_type == "functional" and ench.effect_type == "draw_cost_reduction":
                    if ench.is_percentage:
                        percentage_reduction += ench.value
                    else:
                        flat_reduction += ench.value

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
            for ench, _ in item.enchantments:
                if ench.enchantment_type == "functional" and ench.effect_type == "double_quantity_chance":
                    total_chance += ench.value

        # Add effects from consumed upgrades
        for item in self.consumed_upgrades:
            for ench, _ in item.enchantments:
                if ench.enchantment_type == "functional" and ench.effect_type == "double_quantity_chance":
                    total_chance += ench.value

        return min(100, total_chance)  # Cap at 100%

    def get_sell_price_increase(self):
        """Calculate total sell price increase for non-crafted items from equipment and upgrades."""
        flat_increase = 0
        percentage_increase = 0

        # Add effects from equipped items
        for item in self.equipped_items:
            for ench, _ in item.enchantments:
                if ench.enchantment_type == "functional" and ench.effect_type == "sell_price_increase":
                    if ench.is_percentage:
                        percentage_increase += ench.value
                    else:
                        flat_increase += ench.value

        # Add effects from consumed upgrades
        for item in self.consumed_upgrades:
            for ench, _ in item.enchantments:
                if ench.enchantment_type == "functional" and ench.effect_type == "sell_price_increase":
                    if ench.is_percentage:
                        percentage_increase += ench.value
                    else:
                        flat_increase += ench.value

        return flat_increase, percentage_increase

    def get_crafted_sell_price_increase(self):
        """Calculate total sell price increase for crafted items from equipment and upgrades."""
        flat_increase = 0
        percentage_increase = 0

        # Add effects from equipped items
        for item in self.equipped_items:
            for ench, _ in item.enchantments:
                if ench.enchantment_type == "functional" and ench.effect_type == "crafted_sell_price_increase":
                    if ench.is_percentage:
                        percentage_increase += ench.value
                    else:
                        flat_increase += ench.value

        # Add effects from consumed upgrades
        for item in self.consumed_upgrades:
            for ench, _ in item.enchantments:
                if ench.enchantment_type == "functional" and ench.effect_type == "crafted_sell_price_increase":
                    if ench.is_percentage:
                        percentage_increase += ench.value
                    else:
                        flat_increase += ench.value

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
        self.enchantments = []  # Contains both monetary and functional enchantments
        self.enchant_cost_item = None
        self.enchant_cost_amount = 1
        self.functional_enchant_cost = 100  # Currency cost to roll for a functional enchantment when crafting
        self.rarity_system = RaritySystem()  # Rarity system for equipment
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

    def _load_item_from_data(self, item_data):
        """Helper to load a LootItem from saved data with enchantments (monetary and functional)."""
        item = LootItem(
            item_data['name'],
            item_data['weight'],
            item_data['gold_value'],
            item_data.get('item_type', 'misc'),
            item_data.get('quantity', 1),
            item_data.get('rarity')
        )

        # Load enchantments (both monetary and functional)
        for ench_data in item_data.get('enchantments', []):
            # Check if this is new unified format or old format
            if 'enchantment_type' in ench_data:
                # New unified format
                ench_type = ench_data['enchantment_type']
                if ench_type == "monetary":
                    ench = Enchantment(
                        ench_data['name'],
                        "monetary",
                        enchant_type=ench_data.get('enchant_type', 'misc'),
                        min_value=ench_data.get('min_value', 0),
                        max_value=ench_data.get('max_value', 0),
                        is_percentage=ench_data.get('is_percentage', False),
                        cost_amount=ench_data.get('cost_amount', 1)
                    )
                    rolled_value = ench_data.get('rolled_value', 0)
                else:  # functional
                    ench = Enchantment(
                        ench_data['name'],
                        "functional",
                        effect_type=ench_data.get('effect_type', 'draw_cost_reduction'),
                        value=ench_data.get('value', 0),
                        is_percentage=ench_data.get('is_percentage', False),
                        weight=ench_data.get('weight', 1000)
                    )
                    rolled_value = None  # Functional enchantments don't have rolled values
                item.enchantments.append((ench, rolled_value))
            elif 'min_value' in ench_data:
                # Old monetary enchantment format
                ench = Enchantment(
                    ench_data['name'],
                    "monetary",
                    enchant_type=ench_data.get('enchant_type', 'misc'),
                    min_value=ench_data['min_value'],
                    max_value=ench_data['max_value'],
                    is_percentage=ench_data.get('is_percentage', False),
                    cost_amount=ench_data.get('cost_amount', 1)
                )
                rolled_value = ench_data.get('rolled_value', 0)
                item.enchantments.append((ench, rolled_value))
            else:
                # Very old format - convert to monetary
                gold_value = ench_data.get('gold_value', 0)
                ench = Enchantment(
                    ench_data['name'],
                    "monetary",
                    enchant_type=ench_data.get('enchant_type', 'misc'),
                    min_value=gold_value,
                    max_value=gold_value,
                    is_percentage=False,
                    cost_amount=1
                )
                item.enchantments.append((ench, gold_value))

        # Load old effects and convert to functional enchantments (backward compatibility)
        for eff_data in item_data.get('effects', []):
            ench = Enchantment(
                f"{eff_data['effect_type']}",  # Use effect_type as name
                "functional",
                effect_type=eff_data['effect_type'],
                value=eff_data['value'],
                is_percentage=eff_data.get('is_percentage', False),
                weight=1000  # Default weight
            )
            item.enchantments.append((ench, None))  # No rolled value for functional

        return item

    def save_game(self):
        """Save the game state to a JSON file."""
        try:
            data = {
                'master_items': [
                    {
                        'name': item.name,
                        'item_type': item.item_type,
                        'gold_value_per_unit': item.gold_value_per_unit,
                        'purchase_price': item.purchase_price,
                        'recipe': item.recipe
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
                                        'enchantment_type': ench.enchantment_type,
                                        'enchant_type': ench.enchant_type,
                                        'min_value': ench.min_value,
                                        'max_value': ench.max_value,
                                        'effect_type': ench.effect_type,
                                        'value': ench.value,
                                        'weight': ench.weight,
                                        'is_percentage': ench.is_percentage,
                                        'cost_amount': ench.cost_amount,
                                        'rolled_value': rolled_value
                                    }
                                    for ench, rolled_value in item.enchantments
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
                                'enchantments': [
                                    {
                                        'name': ench.name,
                                        'enchantment_type': ench.enchantment_type,
                                        'enchant_type': ench.enchant_type,
                                        'min_value': ench.min_value,
                                        'max_value': ench.max_value,
                                        'effect_type': ench.effect_type,
                                        'value': ench.value,
                                        'weight': ench.weight,
                                        'is_percentage': ench.is_percentage,
                                        'cost_amount': ench.cost_amount,
                                        'rolled_value': rolled_value
                                    }
                                    for ench, rolled_value in item.enchantments
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
                                'enchantments': [
                                    {
                                        'name': ench.name,
                                        'enchantment_type': ench.enchantment_type,
                                        'enchant_type': ench.enchant_type,
                                        'min_value': ench.min_value,
                                        'max_value': ench.max_value,
                                        'effect_type': ench.effect_type,
                                        'value': ench.value,
                                        'weight': ench.weight,
                                        'is_percentage': ench.is_percentage,
                                        'cost_amount': ench.cost_amount,
                                        'rolled_value': rolled_value
                                    }
                                    for ench, rolled_value in item.enchantments
                                ]
                            }
                            for item in player.consumed_upgrades
                        ],
                        'active_consumable_effects': player.active_consumable_effects
                    }
                    for name, player in self.players.items()
                },
                'enchantments': [
                    {
                        'name': ench.name,
                        'enchantment_type': ench.enchantment_type,
                        'enchant_type': ench.enchant_type,
                        'min_value': ench.min_value,
                        'max_value': ench.max_value,
                        'effect_type': ench.effect_type,
                        'value': ench.value,
                        'weight': ench.weight,
                        'is_percentage': ench.is_percentage,
                        'cost_amount': ench.cost_amount
                    }
                    for ench in self.enchantments
                ],
                'enchant_cost_item': self.enchant_cost_item,
                'enchant_cost_amount': self.enchant_cost_amount,
                'functional_enchant_cost': self.functional_enchant_cost,
                'consumables': [
                    {
                        'name': cons.name,
                        'effect_type': cons.effect_type,
                        'effect_value': cons.effect_value,
                        'gold_value': cons.gold_value,
                        'table_name': cons.table_name
                    }
                    for cons in self.consumables
                ],
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
                        item_data.get('purchase_price'),  # Backward compatible
                        item_data.get('recipe', [])  # Backward compatible
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
                    item = self._load_item_from_data(item_data)
                    player.add_item(item)

                # Load equipped items
                for item_data in player_data.get('equipped_items', []):
                    item = self._load_item_from_data(item_data)
                    player.equip_item(item)

                # Load consumed upgrades
                for item_data in player_data.get('consumed_upgrades', []):
                    item = self._load_item_from_data(item_data)
                    player.consume_upgrade(item)

                # Load active consumable effects
                player.active_consumable_effects = player_data.get('active_consumable_effects', [])

                self.players[name] = player

            # Load enchantments (both monetary and functional)
            self.enchantments = []
            for ench_data in data.get('enchantments', []):
                # Check if this is new unified format or old format
                if 'enchantment_type' in ench_data:
                    # New unified format
                    ench_type = ench_data['enchantment_type']
                    if ench_type == "monetary":
                        ench = Enchantment(
                            ench_data['name'],
                            "monetary",
                            enchant_type=ench_data.get('enchant_type', 'misc'),
                            min_value=ench_data.get('min_value', 0),
                            max_value=ench_data.get('max_value', 0),
                            is_percentage=ench_data.get('is_percentage', False),
                            cost_amount=ench_data.get('cost_amount', 1)
                        )
                    else:  # functional
                        ench = Enchantment(
                            ench_data['name'],
                            "functional",
                            effect_type=ench_data.get('effect_type', 'draw_cost_reduction'),
                            value=ench_data.get('value', 0),
                            is_percentage=ench_data.get('is_percentage', False),
                            weight=ench_data.get('weight', 1000)
                        )
                elif 'min_value' in ench_data:
                    # Old monetary enchantment format
                    ench = Enchantment(
                        ench_data['name'],
                        "monetary",
                        enchant_type=ench_data.get('enchant_type', 'misc'),
                        min_value=ench_data['min_value'],
                        max_value=ench_data['max_value'],
                        is_percentage=ench_data.get('is_percentage', False),
                        cost_amount=ench_data.get('cost_amount', 1)
                    )
                else:
                    # Very old format - convert to monetary
                    gold_value = ench_data.get('gold_value', 0)
                    ench = Enchantment(
                        ench_data['name'],
                        "monetary",
                        enchant_type=ench_data.get('enchant_type', 'misc'),
                        min_value=gold_value,
                        max_value=gold_value,
                        is_percentage=False,
                        cost_amount=1
                    )
                self.enchantments.append(ench)

            # Load old effect_templates and convert to functional enchantments (backward compatibility)
            for eff_tmpl_data in data.get('effect_templates', []):
                ench = Enchantment(
                    eff_tmpl_data['name'],
                    "functional",
                    effect_type=eff_tmpl_data['effect_type'],
                    value=eff_tmpl_data['value'],
                    is_percentage=eff_tmpl_data.get('is_percentage', False),
                    weight=eff_tmpl_data.get('weight', 1000)
                )
                self.enchantments.append(ench)

            # Load global enchantment cost
            self.enchant_cost_item = data.get('enchant_cost_item')
            self.enchant_cost_amount = data.get('enchant_cost_amount', 1)

            # Load functional enchantment cost (fallback to old effect_cost for backward compatibility)
            self.functional_enchant_cost = data.get('functional_enchant_cost', data.get('effect_cost', 100))

            # Load consumables
            self.consumables = []
            for cons_data in data.get('consumables', []):
                consumable = Consumable(
                    cons_data['name'],
                    cons_data['effect_type'],
                    cons_data.get('effect_value'),
                    cons_data.get('gold_value', 0),
                    cons_data.get('table_name')  # Backward compatibility: None if not present
                )
                self.consumables.append(consumable)

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


def show_context_header(game):
    """Display current player and table context."""
    print("\n" + "=" * 60)

    # Current Player info
    if game.current_player_name and game.current_player_name in game.players:
        player = game.players[game.current_player_name]
        print(f"Current Player: {player.name} ({player.gold}g, {len(player.inventory)} items)")
    else:
        print("Current Player: None")

    # Current Table info
    current_table = game.get_current_table()
    if current_table:
        print(f"Current Table: {current_table.name} (Draw Cost: {current_table.draw_cost}g, {len(current_table.items)} items)")
    else:
        print("Current Table: None")

    print("=" * 60)


def show_main_menu():
    print("\n" + "=" * 40)
    print("LOOT TABLE SYSTEM")
    print("=" * 40)
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
                gold_per_unit = int(input(f"Enter gold value per unit (sell price): ").strip())
                if gold_per_unit < 0:
                    print(f"Gold value cannot be negative!")
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
                print(f"Invalid gold value!")

        elif choice == "2":
            # Edit master item
            if not game.master_items:
                print("No master items exist!")
                continue

            print("\nMaster Items:")
            for i, item in enumerate(game.master_items):
                print(f"  {i}. {item.name} ({item.item_type}) - {item.gold_value_per_unit}g each")

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
                new_gold = input(f"New gold per unit [{item.gold_value_per_unit}g]: ").strip()

                purchase_display = f"{item.purchase_price}g" if item.purchase_price is not None else "not for sale"
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
                print(f"  {i}. {item.name} ({item.item_type}) - {item.gold_value_per_unit}g each")

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
                print(f"{i}. {item.name} ({item.item_type}) - {item.gold_value_per_unit}g each")
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


def show_admin_menu():
    print("\n--- ADMIN MENU ---")
    print("1. Give gold to player")
    print("2. Take gold from player")
    print("3. Gift item to player")
    print("4. Take item from player")
    print("5. Configure rarity weights")
    print("6. Manage shop")
    print("7. Back to main menu")


def show_crafting_menu():
    print("\n--- CRAFTING MENU ---")
    print("1. Add/Edit Recipe")
    print("2. Remove Recipe")
    print("3. View All Recipes")
    print("4. Edit Recipe")
    print("5. Back to main menu")


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
                    functional_enchants = [e for e, _ in item.enchantments if e.enchantment_type == "functional"]
                    effects_str = ", ".join([e.get_effect_string() for e in functional_enchants])
                    print(f"  {i}. {item.name} [{effects_str if effects_str else 'No effects'}]")
            else:
                print("  (none)")

            print(f"\nConsumed Upgrades ({len(player.consumed_upgrades)}):")
            if player.consumed_upgrades:
                for item in player.consumed_upgrades:
                    functional_enchants = [e for e, _ in item.enchantments if e.enchantment_type == "functional"]
                    effects_str = ", ".join([e.get_effect_string() for e in functional_enchants])
                    print(f"  - {item.name} [{effects_str if effects_str else 'No effects'}]")
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
                functional_enchants = [e for e, _ in item.enchantments if e.enchantment_type == "functional"]
                effects_str = ", ".join([e.get_effect_string() for e in functional_enchants]) if functional_enchants else "No effects"
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
                functional_enchants = [e for e, _ in item.enchantments if e.enchantment_type == "functional"]
                effects_str = ", ".join([e.get_effect_string() for e in functional_enchants])
                print(f"  {i}. {item.name} [{effects_str if effects_str else 'No effects'}]")

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
                functional_enchants = [e for e, _ in item.enchantments if e.enchantment_type == "functional"]
                effects_str = ", ".join([e.get_effect_string() for e in functional_enchants]) if functional_enchants else "No effects"
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
            print("  2. free_draw_ticket - Draw X items for free from selected table")
            print("  3. trash_to_treasure - Next draw excludes highest weight item")
            effect_choice = input("Choose effect type (1-3): ").strip()

            effect_type = None
            effect_value = None
            table_name = None

            if effect_choice == "1":
                effect_type = "double_next_draw"
                effect_value = None
            elif effect_choice == "2":
                effect_type = "free_draw_ticket"

                # Select table for this ticket
                if not game.loot_tables:
                    print("❌ No loot tables exist! Create a loot table first.")
                    continue

                print("\nAvailable loot tables:")
                for i, table in enumerate(game.loot_tables):
                    print(f"  {i}. {table.name}")

                try:
                    table_idx = int(input("Select table for this ticket: ").strip())
                    if table_idx < 0 or table_idx >= len(game.loot_tables):
                        print("Invalid table number!")
                        continue
                    table_name = game.loot_tables[table_idx].name
                except ValueError:
                    print("Invalid input!")
                    continue

                try:
                    draws = int(input("Enter number of free draws: ").strip())
                    if draws <= 0:
                        print("Number of draws must be greater than 0!")
                        continue
                    effect_value = draws
                except ValueError:
                    print("Invalid number!")
                    continue
            elif effect_choice == "3":
                effect_type = "trash_to_treasure"
                effect_value = None
            else:
                print("Invalid effect type!")
                continue

            try:
                gold_value = int(input(f"Enter sell gold value: ").strip())
                if gold_value < 0:
                    print("Value cannot be negative!")
                    continue

                consumable = Consumable(name, effect_type, effect_value, gold_value, table_name)
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
                new_gold = input(f"New sell value [{cons.gold_value}g]: ").strip()

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
                        print(f"  {i}. {master_item.name} ({master_item.item_type}) - {master_item.gold_value_per_unit}g each")

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
                gold = int(input(f"Enter gold value: ").strip())
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
                print(f"  {i}. {item.get_display_name()} (weight: {item.weight}, value: {item.gold_value}g, type: {item.item_type})")

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
                gold_input = input(f"New gold value [{item.gold_value}]: ").strip()
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
                print(f"  {i}. {item.get_display_name()} (weight: {item.weight}, value: {item.gold_value}g, type: {item.item_type})")

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
                print(f"  - {item.get_display_name()}: weight {item.weight} ({percentage:.2f}%), value {item.gold_value}g")

        elif choice == "10":
            # View rates for players
            if not current_table or not current_table.items:
                print("No items in current table!")
                continue

            print("\n" + "=" * 50)
            print(f"{current_table.name.upper()} - RATES")
            print(f"Draw Cost: {current_table.draw_cost}g")
            print("=" * 50)
            total_weight = sum(item.weight for item in current_table.items)

            sorted_items = sorted(current_table.items, key=lambda x: x.weight)

            for item in sorted_items:
                percentage = (item.weight / total_weight) * 100
                print(f"  {item.get_display_name()}")
                print(f"    Type: {item.item_type}")
                print(f"    Drop Rate: {percentage:.2f}%")
                print(f"    Value: {item.gold_value}g")
                print()

        elif choice == "11":
            # View all tables
            if not game.loot_tables:
                print("No tables exist!")
                continue

            print("\nAll Loot Tables:")
            for i, table in enumerate(game.loot_tables):
                marker = " <-- CURRENT" if i == game.current_table_index else ""
                print(f"  {i}. {table.name} (Draw Cost: {table.draw_cost}g, Items: {len(table.items)}){marker}")

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
                print(f"Gold: {player.gold}g")
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
                print(f"  - {name}: {player.gold}g, {len(player.inventory)} items{current_marker}")

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
                    effect_value = None
                    table_name = None
                else:
                    effect_type = matching_consumable.effect_type
                    effect_value = matching_consumable.effect_value
                    table_name = matching_consumable.table_name

                # Validate ticket table exists
                if effect_type == "free_draw_ticket":
                    if not table_name:
                        print(f"❌ Ticket '{consumable_item.name}' has no table assigned! Cannot use.")
                        continue

                    # Check if table still exists
                    table_exists = any(t.name == table_name for t in game.loot_tables)
                    if not table_exists:
                        print(f"❌ Table '{table_name}' no longer exists! Cannot use ticket.")
                        continue

                # Remove from inventory
                player.remove_item(inv_idx)

                # Add effect to active effects with additional data
                effect_data = {
                    'effect_type': effect_type,
                    'name': consumable_item.name
                }

                if effect_type == "free_draw_ticket":
                    effect_data['table_name'] = table_name
                    effect_data['draws'] = effect_value if effect_value else 1

                player.active_consumable_effects.append(effect_data)

                print(f"\n✨ {player.name} used {consumable_item.name}!")
                if effect_type == "double_next_draw":
                    print("   Effect: Next draw will have DOUBLED quantity (guaranteed)!")
                elif effect_type == "free_draw_ticket":
                    draws = effect_value if effect_value else 1
                    print(f"   Effect: Draw {draws} item(s) for FREE from {table_name}!")
                elif effect_type == "trash_to_treasure":
                    print("   Effect: Next draw will exclude the highest weight item!")

                print(f"\nActive effects: {len(player.active_consumable_effects)}")
                for eff in player.active_consumable_effects:
                    if eff['effect_type'] == 'free_draw_ticket':
                        print(f"  - {eff['name']} ({eff['draws']} draw(s) from {eff['table_name']})")
                    else:
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

    # Check for and process free draw tickets first
    for player_name, player in game.players.items():
        ticket_effects = [eff for eff in player.active_consumable_effects if eff['effect_type'] == 'free_draw_ticket']

        for ticket_effect in ticket_effects:
            table_name = ticket_effect.get('table_name')
            draws = ticket_effect.get('draws', 1)

            # Find the table
            selected_table = None
            for table in game.loot_tables:
                if table.name == table_name:
                    selected_table = table
                    break

            if not selected_table or not selected_table.items:
                print(f"\n⚠️  {player_name}'s ticket for '{table_name}' cannot be used (table not found or empty)!")
                player.active_consumable_effects.remove(ticket_effect)
                continue

            print(f"\n🎟️  {player_name} is using a FREE DRAW TICKET!")
            print(f"   Drawing {draws} item(s) from '{table_name}' for FREE!")

            items = selected_table.draw_multiple(draws)

            # Get double quantity chance and sell price increase
            double_chance = player.get_double_quantity_chance()
            flat_price, percent_price = player.get_sell_price_increase()

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

                # Check for doubling
                doubled = False
                if double_chance > 0 and random.random() * 100 < double_chance:
                    item.quantity *= 2
                    item.gold_value *= 2
                    doubled_count += 1
                    doubled = True

                # Display with indicators
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

            # Remove ticket after use
            player.active_consumable_effects.remove(ticket_effect)
            print(f"🎟️  Ticket used! {draws} free item(s) received.")

            if doubled_count > 0:
                print(f"✨ {doubled_count} item(s) had their quantity doubled! (Chance: {double_chance}%)")
            if price_boosted_count > 0:
                print(f"💰 {price_boosted_count} item(s) had their value increased!")

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
            print(f"  - {name} ({player.gold}g){current_marker}")

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
            reduction_info = f" (Base: {base_cost}g, -{flat} flat, -{percent}%)"

        count = int(input(f"How many items to draw? (Cost: {actual_cost}g per draw{reduction_info}): ").strip())
        if count <= 0:
            print("Count must be greater than 0!")
            return

        total_cost = count * actual_cost

        if player.gold < total_cost:
            print(f"❌ Not enough gold! Need {total_cost}g but {player.name} only has {player.gold}g")
            return

        player.remove_gold(total_cost)

        # Check for active consumable effects before drawing
        has_double_next_draw = False
        has_trash_to_treasure = False
        for effect in player.active_consumable_effects:
            if effect['effect_type'] == 'double_next_draw':
                has_double_next_draw = True
            elif effect['effect_type'] == 'trash_to_treasure':
                has_trash_to_treasure = True

        # Apply trash_to_treasure: temporarily exclude highest weight item
        excluded_item = None
        if has_trash_to_treasure and selected_table.items:
            # Find item with highest weight (lowest value item since high weight = common)
            highest_weight_item = max(selected_table.items, key=lambda x: x.weight)
            excluded_item = highest_weight_item
            selected_table.items.remove(excluded_item)
            print(f"🎯 TRASH TO TREASURE ACTIVE: '{excluded_item.name}' (highest weight) excluded from this draw!")

        items = selected_table.draw_multiple(count)

        # Restore excluded item
        if excluded_item:
            selected_table.items.append(excluded_item)

        print(f"\n💰 Paid {total_cost}g ({count} x {actual_cost}g) to {selected_table.name}")
        print(f"🎲 {player.name} drew {count} items:")

        if has_double_next_draw:
            print(f"🔥 CONSUMABLE EFFECT ACTIVE: Double Next Draw - All items will be DOUBLED!")

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

        # Remove consumable effects after use
        if has_double_next_draw:
            player.active_consumable_effects = [eff for eff in player.active_consumable_effects if eff['effect_type'] != 'double_next_draw']
            print(f"\n🔥 Consumable effect used! {consumable_doubled_count} item(s) DOUBLED from consumable!")

        if has_trash_to_treasure:
            player.active_consumable_effects = [eff for eff in player.active_consumable_effects if eff['effect_type'] != 'trash_to_treasure']
            print(f"🎯 Trash to Treasure effect used! Highest weight item was excluded.")

        if doubled_count > 0:
            print(f"\n✨ {doubled_count} item(s) had their quantity doubled! (Chance: {double_chance}%)")

        if price_boosted_count > 0:
            print(f"💰 {price_boosted_count} item(s) had their value increased! (+{flat_price} flat, +{percent_price}%)")

        net_value = total_value - total_cost
        print(f"\nTotal value: {total_value}g")
        print(f"Net gain/loss: {net_value:+d}g")
        print(f"{player.name}'s gold: {player.gold}g | Inventory: {len(player.inventory)} items")
    except ValueError:
        print("Invalid input!")


def sell_items_menu(game):
    if not game.players:
        print("No players exist! Add players first.")
        return

    print("\nAvailable players:")
    for name, player in game.players.items():
        current_marker = " <-- CURRENT" if name == game.current_player_name else ""
        print(f"  - {name} ({player.gold}g, {len(player.inventory)} items){current_marker}")

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
        print(f"Gold: {player.gold}g")
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
            print(f"✓ Sold {item.name} for {item.gold_value}g!")
            print(f"New gold balance: {player.gold}g")

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

    # Check if there are any items in the shop
    shop_items = [item for item in game.master_items if item.purchase_price is not None]
    if not shop_items:
        print("The shop is empty! Add items to the shop first (Admin Menu > Manage Shop).")
        return

    print("\nAvailable players:")
    for name, player in game.players.items():
        current_marker = " <-- CURRENT" if name == game.current_player_name else ""
        print(f"  - {name} ({player.gold}g){current_marker}")

    player_name = get_player_name_input(game)
    player = game.get_player(player_name)

    if not player:
        print(f"Player '{player_name}' not found!")
        return

    while True:
        print(f"\n{'=' * 60}")
        print("SHOP")
        print(f"{'=' * 60}")
        print(f"{player.name}'s gold: {player.gold}g")
        print()

        # Get items available for purchase (master items with purchase_price set)
        shop_items = [item for item in game.master_items if item.purchase_price is not None]

        if not shop_items:
            print("No items available in shop!")
            print("(Use the admin menu to add items to the shop)")
            input("\nPress Enter to return...")
            break

        # Display shop items
        print("Available items:")
        for i, item in enumerate(shop_items):
            print(f"  {i}. {item.name} ({item.item_type}) - Buy: {item.purchase_price}g, Sells for: {item.gold_value_per_unit}g")

        choice = input("\nEnter item number to buy (or 'back' to return): ").strip().lower()

        if choice == 'back':
            break

        try:
            index = int(choice)
            if index < 0 or index >= len(shop_items):
                print("Invalid item number!")
                continue

            master_item = shop_items[index]

            # Get quantity
            quantity = int(input("How many to buy? ").strip())
            if quantity <= 0:
                print("Quantity must be at least 1!")
                continue

            # Calculate total cost
            total_cost = master_item.purchase_price * quantity

            # Check if player has enough money
            if player.gold < total_cost:
                print(f"❌ Not enough gold! Need {total_cost}g, have {player.gold}g")
                continue

            # Deduct money
            player.remove_gold(total_cost)

            # Add items to inventory
            for _ in range(quantity):
                loot_item = LootItem(master_item.name, 1000, master_item.gold_value_per_unit, master_item.item_type, 1)

                # Roll rarity for Equipment items
                if master_item.item_type.lower() == "equipment":
                    loot_item.rarity = game.rarity_system.roll_rarity()

                player.add_item(loot_item)

            print(f"\n✓ Purchased {quantity}x {master_item.name} for {total_cost}g!")
            print(f"New gold balance: {player.gold}g")

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
        print(f"Gold: {player.gold}g")

        # Show available tables
        print("\nAvailable loot tables:")
        for i, table in enumerate(game.loot_tables):
            print(f"  {i}. {table.name} (Cost: {table.draw_cost}g per draw, Items: {len(table.items)})")

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
                print(f"❌ Not enough gold! Need {total_cost}g but {player.name} only has {player.gold}g")
                print("Skipping this player.")
                continue

            # Deduct cost
            player.remove_gold(total_cost)

            # Draw items
            items = selected_table.draw_multiple(draws_per_player)
            print(f"\n💰 Paid {total_cost}g ({draws_per_player} x {actual_cost}g) to {selected_table.name}")
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
            print(f"\nTotal value: {total_value}g")
            print(f"Net gain/loss: {net_value:+d}g")
            print(f"{player.name}'s gold: {player.gold}g | Inventory: {len(player.inventory)} items")

        except ValueError:
            print("Invalid input! Skipping this player.")
            continue

    # Phase 2: Show all inventories
    print("\n" + "=" * 60)
    print("📋 PHASE 2: INVENTORY SUMMARY")
    print("=" * 60)

    for player_name, player in game.players.items():
        print(f"\n--- {player_name} ---")
        print(f"Gold: {player.gold}g | Items: {len(player.inventory)}")

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
                    print(f"  • {item_name} x{total_quantity} ({count} stack(s), {total_value}g total)")
        else:
            print("  (No items)")

    # Phase 3: Crafting phase
    print("\n" + "=" * 60)
    print("🔨 PHASE 3: CRAFTING")
    print("=" * 60)

    # Get craftable items (master items with recipes)
    craftable_items = [item for item in game.master_items if item.recipe]

    if not craftable_items:
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
                for i, master_item in enumerate(craftable_items):
                    ingredient_counts = {}
                    for ing in master_item.recipe:
                        ingredient_counts[ing] = ingredient_counts.get(ing, 0) + 1
                    ingredient_parts = [f"{count}x {name}" if count > 1 else name
                                       for name, count in ingredient_counts.items()]
                    print(f"  {i}. {master_item.name} ({master_item.item_type}, {master_item.gold_value_per_unit}g) = [{', '.join(ingredient_parts)}]")

                try:
                    recipe_index = int(input("\nEnter recipe number to craft (or -1 to skip): ").strip())
                    if recipe_index == -1:
                        break

                    if recipe_index < 0 or recipe_index >= len(craftable_items):
                        print("Invalid recipe number!")
                        continue

                    master_item = craftable_items[recipe_index]

                    # Count required quantities for each ingredient
                    required_ingredients = {}
                    for ingredient in master_item.recipe:
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
                    for ingredient in master_item.recipe:
                        player.consume_item_by_name(ingredient, 1)

                    # Create and add crafted item
                    crafted_item = LootItem(master_item.name, 0, master_item.gold_value_per_unit, master_item.item_type)

                    # If Equipment or Upgrade, allow player to roll for functional enchantments
                    if master_item.item_type.lower() in ["equipment", "upgrade"]:
                        # Get functional enchantments from the unified enchantments list
                        functional_enchants = [e for e in game.enchantments if e.enchantment_type == "functional"]

                        if not functional_enchants:
                            print(f"\n⚠️  No functional enchantments available! Item crafted without effects.")
                            if master_item.item_type.lower() == "equipment":
                                rarity = game.rarity_system.roll_rarity()
                                crafted_item.rarity = rarity
                                print(f"✓ Crafted [{rarity}] {master_item.name} (0 effects)")
                            else:
                                print(f"✓ Crafted {master_item.name} (0 effects)")
                        else:
                            # For Equipment, roll rarity first
                            max_effects = None
                            if master_item.item_type.lower() == "equipment":
                                rarity = game.rarity_system.roll_rarity()
                                crafted_item.rarity = rarity
                                max_effects = game.rarity_system.get_max_effects(rarity)
                                print(f"\n✨ Rolled [{rarity}] {master_item.name}! (Max {max_effects} effects)")
                            else:
                                print(f"\n✓ Crafted {master_item.name}!")

                            # Roll for functional enchantments
                            print(f"\nRoll for effects? Cost: {game.functional_enchant_cost}g per roll")
                            print(f"Your gold: {player.gold}g")

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
                                if player.gold < game.functional_enchant_cost:
                                    print(f"❌ Not enough gold! Need {game.functional_enchant_cost}g, have {player.gold}g")
                                    break

                                # Deduct cost and roll for functional enchantment
                                player.remove_gold(game.functional_enchant_cost)
                                weights = [ench.weight for ench in functional_enchants]
                                rolled_enchant = random.choices(functional_enchants, weights=weights, k=1)[0]
                                crafted_item.add_enchantment(rolled_enchant, rolled_value=None)  # No rolled value for functional
                                effects_added += 1

                                print(f"🎲 Rolled: {rolled_enchant.name}")
                                print(f"   Effect: {rolled_enchant.get_effect_string()}")
                                print(f"   gold: {player.gold}g")

                            print(f"\n✓ Final item: {crafted_item.get_display_name()} ({effects_added} effects)")
                    else:
                        print(f"✓ Crafted {master_item.name}!")

                    # Apply crafted sell price increase
                    flat_craft_price, percent_craft_price = player.get_crafted_sell_price_increase()
                    if flat_craft_price > 0 or percent_craft_price > 0:
                        original_craft_value = crafted_item.gold_value
                        crafted_item.gold_value = player.calculate_item_value(original_craft_value, is_crafted=True)
                        if crafted_item.gold_value > original_craft_value:
                            print(f"💰 Crafted item value increased: {original_craft_value}g → {crafted_item.gold_value}g (+{flat_craft_price} flat, +{percent_craft_price}%)")

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
            print(f"Gold: {player.gold}g")
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
                print(f"✓ Sold {item.name} for {item.gold_value}g!")
                print(f"New gold balance: {player.gold}g")

                if not player.inventory:
                    print(f"\n{player.name} has sold all items!")
                    break

            except ValueError:
                print("Invalid input! Enter a number or 'done'")

    print("\n" + "=" * 60)
    print("✅ QUICK TURN COMPLETE!")
    print("=" * 60)


def manage_crafting(game):
    """Manage crafting recipes stored in master items."""
    while True:
        show_crafting_menu()
        choice = input("Enter choice: ").strip()

        if choice == "1":
            # Add recipe to a master item
            if not game.master_items:
                print("No master items exist! Create items in the Master Items menu first.")
                continue

            print("\nAvailable master items:")
            for i, item in enumerate(game.master_items):
                recipe_status = f"Recipe: {len(item.recipe)} ingredients" if item.recipe else "No recipe"
                print(f"  {i}. {item.name} ({item.item_type}) [{recipe_status}]")

            try:
                index = int(input("\nEnter item number to add/edit recipe: ").strip())
                if index < 0 or index >= len(game.master_items):
                    print("Invalid item number!")
                    continue

                master_item = game.master_items[index]
                master_item.recipe = []  # Reset recipe

                print(f"\nAdding recipe to {master_item.name}")
                print("Type 'done' when finished adding ingredients")
                
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
                                master_item.recipe.append(ingredient)
                            print(f"✓ Added {quantity}x {ingredient}")
                        except ValueError:
                            print("Invalid quantity! Please enter a number.")

                if not master_item.recipe:
                    print("Recipe must have at least one ingredient!")
                    continue

                # Display recipe
                ingredient_counts = {}
                for ing in master_item.recipe:
                    ingredient_counts[ing] = ingredient_counts.get(ing, 0) + 1
                ingredient_parts = [f"{count}x {name}" if count > 1 else name
                                   for name, count in ingredient_counts.items()]
                print(f"✓ Recipe set for {master_item.name}: [{', '.join(ingredient_parts)}]")
            except ValueError:
                print("Invalid input!")

        elif choice == "2":
            # Remove recipe from master item
            craftable_items = [item for item in game.master_items if item.recipe]

            if not craftable_items:
                print("No items have recipes!")
                continue

            print("\nItems with recipes:")
            for i, item in enumerate(craftable_items):
                ingredient_counts = {}
                for ing in item.recipe:
                    ingredient_counts[ing] = ingredient_counts.get(ing, 0) + 1
                ingredient_parts = [f"{count}x {name}" if count > 1 else name
                                   for name, count in ingredient_counts.items()]
                print(f"  {i}. {item.name} = [{', '.join(ingredient_parts)}]")

            try:
                index = int(input("\nEnter item number to remove recipe: ").strip())
                if index < 0 or index >= len(craftable_items):
                    print("Invalid item number!")
                    continue

                item = craftable_items[index]
                item.recipe = []
                print(f"✓ Removed recipe from {item.name}")
            except ValueError:
                print("Invalid input!")

        elif choice == "3":
            # View all recipes
            craftable_items = [item for item in game.master_items if item.recipe]

            if not craftable_items:
                print("No recipes exist!")
                continue

            print("\nAll Crafting Recipes:")
            for i, item in enumerate(craftable_items):
                ingredient_counts = {}
                for ing in item.recipe:
                    ingredient_counts[ing] = ingredient_counts.get(ing, 0) + 1
                ingredient_parts = [f"{count}x {name}" if count > 1 else name
                                   for name, count in ingredient_counts.items()]
                print(f"  {i}. {item.name} ({item.item_type}, {item.gold_value_per_unit}g) = [{', '.join(ingredient_parts)}]")

        elif choice == "4":
            # Edit existing recipe (same as add)
            if not game.master_items:
                print("No master items exist!")
                continue

            craftable_items = [item for item in game.master_items if item.recipe]

            if not craftable_items:
                print("No items have recipes!")
                continue

            print("\nItems with recipes:")
            for i, item in enumerate(craftable_items):
                ingredient_counts = {}
                for ing in item.recipe:
                    ingredient_counts[ing] = ingredient_counts.get(ing, 0) + 1
                ingredient_parts = [f"{count}x {name}" if count > 1 else name
                                   for name, count in ingredient_counts.items()]
                print(f"  {i}. {item.name} = [{', '.join(ingredient_parts)}]")

            try:
                index = int(input("\nEnter item number to edit recipe: ").strip())
                if index < 0 or index >= len(craftable_items):
                    print("Invalid item number!")
                    continue

                master_item = craftable_items[index]
                master_item.recipe = []  # Reset recipe

                print(f"\nEditing recipe for {master_item.name}")
                print("Type 'done' when finished adding ingredients")
                
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
                            for _ in range(quantity):
                                master_item.recipe.append(ingredient)
                            print(f"✓ Added {quantity}x {ingredient}")
                        except ValueError:
                            print("Invalid quantity! Please enter a number.")

                if master_item.recipe:
                    ingredient_counts = {}
                    for ing in master_item.recipe:
                        ingredient_counts[ing] = ingredient_counts.get(ing, 0) + 1
                    ingredient_parts = [f"{count}x {name}" if count > 1 else name
                                       for name, count in ingredient_counts.items()]
                    print(f"✓ Recipe updated for {master_item.name}: [{', '.join(ingredient_parts)}]")
            except ValueError:
                print("Invalid input!")

        elif choice == "5":
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
                    print(f"\nEnter flat gold range (can be negative for penalty, positive for bonus)")
                    print("Example: -100 to 200 means it could reduce value by 100g or increase by 200g")
                    min_value = float(input(f"Minimum gold value: ").strip())
                    max_value = float(input(f"Maximum gold value: ").strip())

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
        print("1. Add item to shop (set purchase price)")
        print("2. Remove item from shop (clear purchase price)")
        print("3. View all shop items")
        print("4. Back to admin menu")

        choice = input("Enter choice: ").strip()

        if choice == "1":
            # Add item to shop - select a master item and set its purchase price
            if not game.master_items:
                print("No master items exist! Create items in the Master Items menu first.")
                continue

            print("\nAvailable master items:")
            for i, item in enumerate(game.master_items):
                shop_status = f"In shop: {item.purchase_price}g" if item.purchase_price is not None else "Not in shop"
                print(f"  {i}. {item.name} ({item.item_type}) - Sells for: {item.gold_value_per_unit}g [{shop_status}]")

            try:
                index = int(input("\nEnter item number to add to shop: ").strip())
                if index < 0 or index >= len(game.master_items):
                    print("Invalid item number!")
                    continue

                master_item = game.master_items[index]

                purchase_price = int(input(f"Enter purchase price for {master_item.name}: ").strip())
                if purchase_price < 0:
                    print("Purchase price cannot be negative!")
                    continue

                master_item.purchase_price = purchase_price
                print(f"✓ Added {master_item.name} to shop at {purchase_price}g")
            except ValueError:
                print("Invalid input!")

        elif choice == "2":
            # Remove item from shop - clear purchase price
            shop_items = [item for item in game.master_items if item.purchase_price is not None]

            if not shop_items:
                print("Shop is empty!")
                continue

            print("\nShop items:")
            for i, item in enumerate(shop_items):
                print(f"  {i}. {item.name} ({item.item_type}) - Buy: {item.purchase_price}g, Sells for: {item.gold_value_per_unit}g")

            try:
                index = int(input("\nEnter item number to remove from shop: ").strip())
                if index < 0 or index >= len(shop_items):
                    print("Invalid item number!")
                    continue

                item = shop_items[index]
                item.purchase_price = None
                print(f"✓ Removed {item.name} from shop")
            except ValueError:
                print("Invalid input!")

        elif choice == "3":
            # View all shop items
            shop_items = [item for item in game.master_items if item.purchase_price is not None]

            if not shop_items:
                print("Shop is empty!")
                continue

            print(f"\n{'=' * 60}")
            print("SHOP CATALOG")
            print(f"{'=' * 60}")
            for i, item in enumerate(shop_items):
                print(f"{i}. {item.name} ({item.item_type}) - Buy: {item.purchase_price}g, Sells for: {item.gold_value_per_unit}g")
            print(f"{'=' * 60}")

        elif choice == "4":
            break


def admin_menu(game):
    while True:
        show_admin_menu()
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
                amount = int(input(f"Amount of gold to give: ").strip())
                if amount <= 0:
                    print("Amount must be greater than 0!")
                    continue

                player.add_gold(amount)
                print(f"✓ Gave {amount}g to {player.name} (now has {player.gold}g)")
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
                amount = int(input(f"Amount of gold to take (has {player.gold}g): ").strip())
                if amount <= 0:
                    print("Amount must be greater than 0!")
                    continue

                if player.remove_gold(amount):
                    print(f"✓ Took {amount}g from {player.name} (now has {player.gold}g)")
                else:
                    print(f"Player doesn't have enough gold!")
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

        elif choice == "6":
            # Manage shop
            manage_shop(game)

        elif choice == "7":
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
        choice = input("Enter your choice (1-11): ").strip()

        if choice == "1":
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
