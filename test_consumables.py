#!/usr/bin/env python3
"""Test consumables system functionality"""

import json
import os
from loot_table import GameSystem, Player, Consumable, LootItem

def test_consumables():
    print("Testing Consumables System")
    print("=" * 60)

    # Create a new game
    game = GameSystem()

    # Test 1: Create a consumable
    print("\n1. Creating a consumable...")
    consumable = Consumable("Lucky Charm", "double_next_draw", None, 50)
    game.consumables.append(consumable)
    assert consumable.name == "Lucky Charm"
    assert consumable.item_type == "consumable"
    assert consumable.effect_type == "double_next_draw"
    assert consumable.gold_value == 50
    print("✓ Consumable created successfully")

    # Test 2: Create a player
    print("\n2. Creating a player...")
    player = Player("TestPlayer")
    game.players["TestPlayer"] = player
    print("✓ Player created successfully")

    # Test 3: Give consumable to player
    print("\n3. Adding consumable to player inventory...")
    consumable_item = LootItem("Lucky Charm", 0, 50, "consumable", 1)
    player.add_item(consumable_item)
    assert len(player.inventory) == 1
    assert player.inventory[0].item_type == "consumable"
    print("✓ Consumable added to inventory")

    # Test 4: Check active effects (should be empty)
    print("\n4. Checking active effects (should be empty)...")
    assert len(player.active_consumable_effects) == 0
    print("✓ No active effects initially")

    # Test 5: Consume the item (simulate player menu action)
    print("\n5. Consuming the item...")
    consumed_item = player.inventory[0]
    player.remove_item(0)
    player.active_consumable_effects.append({
        'effect_type': 'double_next_draw',
        'name': consumed_item.name
    })
    assert len(player.inventory) == 0
    assert len(player.active_consumable_effects) == 1
    assert player.active_consumable_effects[0]['effect_type'] == 'double_next_draw'
    print("✓ Item consumed and effect activated")

    # Test 6: Save game
    print("\n6. Saving game...")
    test_save_file = "test_consumables_save.json"
    game.save_file = test_save_file
    game.save_game()
    assert os.path.exists(test_save_file)
    print("✓ Game saved successfully")

    # Test 7: Load game
    print("\n7. Loading game...")
    new_game = GameSystem()
    new_game.save_file = test_save_file
    new_game.load_game()

    # Verify consumables loaded
    assert len(new_game.consumables) == 1
    assert new_game.consumables[0].name == "Lucky Charm"
    assert new_game.consumables[0].effect_type == "double_next_draw"
    print("✓ Consumables loaded correctly")

    # Verify player active effects loaded
    loaded_player = new_game.players["TestPlayer"]
    assert len(loaded_player.active_consumable_effects) == 1
    assert loaded_player.active_consumable_effects[0]['effect_type'] == 'double_next_draw'
    print("✓ Active effects loaded correctly")

    # Test 8: Verify save file structure
    print("\n8. Verifying save file structure...")
    with open(test_save_file, 'r') as f:
        save_data = json.load(f)

    assert 'consumables' in save_data
    assert len(save_data['consumables']) == 1
    assert save_data['consumables'][0]['name'] == "Lucky Charm"

    assert 'players' in save_data
    assert 'TestPlayer' in save_data['players']
    assert 'active_consumable_effects' in save_data['players']['TestPlayer']
    print("✓ Save file structure correct")

    # Cleanup
    print("\n9. Cleaning up...")
    os.remove(test_save_file)
    print("✓ Test file removed")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED! ✓")
    print("=" * 60)

if __name__ == "__main__":
    test_consumables()
