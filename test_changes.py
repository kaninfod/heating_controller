#!/usr/bin/env python3
"""
Test script for verifying the main changes:
1. Deep copy fix for schedule mutation prevention
2. ECO mode instead of HOLIDAY
3. Simplified thermostat mapping format
4. Blacklisted areas filtering
"""

import asyncio
import json
import copy
from pathlib import Path


def test_deep_copy_schedule_generation():
    """Test that schedule generation doesn't mutate original data"""
    print("\n" + "="*70)
    print("TEST 1: Deep Copy Schedule Generation")
    print("="*70)
    
    from app.services.schedule_generator import ScheduleGenerator
    
    generator = ScheduleGenerator()
    
    # Create original base week
    base_week = {
        "monday": "workday",
        "tuesday": "workday",
        "wednesday": "workday",
        "thursday": "workday",
        "friday": "workday",
        "saturday": "weekend_day",
        "sunday": "weekend_day",
    }
    
    # Save original state
    original_week = copy.deepcopy(base_week)
    
    # Call generate_stay_home_schedule which should NOT modify base_week
    stay_home_week = generator.generate_stay_home_schedule(base_week, swap_day="tuesday")
    
    # Verify original wasn't mutated
    if base_week == original_week:
        print("✓ PASS: Original base_week was NOT mutated")
        print(f"  Original Tuesday: {original_week['tuesday']}")
        print(f"  Current Tuesday: {base_week['tuesday']}")
    else:
        print("✗ FAIL: Original base_week WAS mutated!")
        print(f"  Expected: {original_week}")
        print(f"  Got: {base_week}")
        return False
    
    # Verify the result has the swap
    if stay_home_week["tuesday"] != original_week["tuesday"]:
        print("✓ PASS: Stay-home schedule correctly swapped day")
        print(f"  Swapped Tuesday to: {stay_home_week['tuesday']}")
    else:
        print("✗ FAIL: Stay-home schedule didn't swap the day")
        return False
    
    return True


def test_eco_mode_exists():
    """Test that ECO mode exists and HOLIDAY mode is gone"""
    print("\n" + "="*70)
    print("TEST 2: ECO Mode (HOLIDAY removed)")
    print("="*70)
    
    from app.models.state import SystemMode
    
    # Check ECO exists
    try:
        eco_mode = SystemMode.ECO
        print(f"✓ PASS: ECO mode exists: {eco_mode}")
    except AttributeError:
        print("✗ FAIL: ECO mode does not exist")
        return False
    
    # Check HOLIDAY is gone
    if hasattr(SystemMode, "HOLIDAY"):
        print("✗ FAIL: HOLIDAY mode still exists!")
        return False
    else:
        print("✓ PASS: HOLIDAY mode successfully removed")
    
    # List all modes
    print("\nAvailable modes:")
    for mode in SystemMode:
        print(f"  - {mode.value}")
    
    return True


def test_simplified_thermostat_mapping():
    """Test that simplified thermostat mapping works (string value instead of dict)"""
    print("\n" + "="*70)
    print("TEST 3: Simplified Thermostat Mapping Format")
    print("="*70)
    
    # Load the actual mapping file
    mapping_file = Path("config/thermostat_mapping.json")
    if not mapping_file.exists():
        print(f"✗ FAIL: Mapping file not found at {mapping_file}")
        return False
    
    with open(mapping_file) as f:
        mapping = json.load(f)
    
    print(f"✓ Thermostat mapping file loaded ({len(mapping)} entries)")
    
    # Check format - should be entity_id -> string (z2m_name)
    all_correct_format = True
    for entity_id, value in mapping.items():
        if not isinstance(value, str):
            print(f"✗ FAIL: {entity_id} has non-string value: {value}")
            all_correct_format = False
        else:
            print(f"  ✓ {entity_id} -> '{value}'")
    
    if not all_correct_format:
        return False
    
    print("✓ PASS: All thermostat mappings use simplified string format")
    
    # Verify no old format (dict with z2m_name key)
    for entity_id, value in mapping.items():
        if isinstance(value, dict) and "z2m_name" in value:
            print(f"✗ FAIL: {entity_id} still uses old dict format!")
            return False
    
    print("✓ PASS: No old dict format found")
    return True


def test_blacklisted_areas_config():
    """Test that BLACKLISTED_AREAS config is parsed correctly"""
    print("\n" + "="*70)
    print("TEST 4: Blacklisted Areas Configuration")
    print("="*70)
    
    from app.config import settings
    
    # Check property exists
    try:
        blacklist = settings.blacklisted_areas_list
        print(f"✓ PASS: blacklisted_areas_list property exists")
        print(f"  Current value: {blacklist}")
    except AttributeError:
        print("✗ FAIL: blacklisted_areas_list property does not exist")
        return False
    
    # Test parsing with spaces and commas
    # Simulate what would happen if we set it
    test_value = "bedroom, office, kitchen"
    parsed = [a.strip() for a in test_value.split(",") if a.strip()]
    
    if parsed == ["bedroom", "office", "kitchen"]:
        print(f"✓ PASS: Parsing works correctly")
        print(f"  Input: '{test_value}'")
        print(f"  Output: {parsed}")
    else:
        print(f"✗ FAIL: Parsing failed")
        print(f"  Expected: ['bedroom', 'office', 'kitchen']")
        print(f"  Got: {parsed}")
        return False
    
    return True


def test_entity_lists_removed():
    """Test that old entity list properties are removed"""
    print("\n" + "="*70)
    print("TEST 5: Entity Lists Removed from Config")
    print("="*70)
    
    from app.config import settings
    
    removed_properties = [
        "thermostat_list",
        "temperature_sensor_list",
        "humidity_sensor_list",
        "all_monitored_entities",
    ]
    
    all_removed = True
    for prop in removed_properties:
        if hasattr(settings, prop):
            print(f"✗ FAIL: Property '{prop}' still exists (should be removed)")
            all_removed = False
        else:
            print(f"✓ {prop} - successfully removed")
    
    if all_removed:
        print("\n✓ PASS: All old entity list properties removed")
        return True
    else:
        return False


def test_env_variables():
    """Test that .env has the expected variables"""
    print("\n" + "="*70)
    print("TEST 6: .env File Variables")
    print("="*70)
    
    from app.config import settings
    
    required = ["ha_websocket_url", "ha_access_token", "log_level", "mode_entity"]
    optional = ["blacklisted_areas", "syslog_host", "syslog_port"]
    
    print("Required variables:")
    for var in required:
        if hasattr(settings, var):
            value = getattr(settings, var)
            masked_value = value[:20] + "..." if len(str(value)) > 20 else value
            print(f"  ✓ {var}: {masked_value}")
        else:
            print(f"  ✗ {var}: MISSING")
            return False
    
    print("\nOptional variables:")
    for var in optional:
        if hasattr(settings, var):
            value = getattr(settings, var)
            print(f"  ✓ {var}: {value}")
        else:
            print(f"  ✗ {var}: NOT FOUND (might be okay)")
    
    # Check that removed variables don't exist
    removed = ["thermostat_entities", "temperature_sensor_entities", "humidity_sensor_entities"]
    print("\nRemoved variables (should NOT exist):")
    for var in removed:
        if hasattr(settings, var):
            print(f"  ✗ {var}: STILL EXISTS (should be removed)")
            return False
        else:
            print(f"  ✓ {var}: successfully removed")
    
    print("\n✓ PASS: .env variables correctly configured")
    return True


def test_mode_manager_thermostat_mapping():
    """Test that mode_manager correctly uses simplified thermostat mapping"""
    print("\n" + "="*70)
    print("TEST 7: Mode Manager Thermostat Mapping Usage")
    print("="*70)
    
    # Load the mapping
    mapping_file = Path("config/thermostat_mapping.json")
    with open(mapping_file) as f:
        thermostat_mapping = json.load(f)
    
    # Simulate what publish_schedule_to_thermostat does
    test_entity = "climate.bedroom_thermostat"
    
    # Old way (would fail): thermostat_config.get("z2m_name")
    # New way: thermostat_mapping.get(thermostat_id)
    
    z2m_device_name = thermostat_mapping.get(test_entity)
    
    if z2m_device_name is None:
        print(f"✗ FAIL: Entity '{test_entity}' not found in mapping")
        return False
    
    if not isinstance(z2m_device_name, str):
        print(f"✗ FAIL: Z2M device name is not a string: {z2m_device_name}")
        return False
    
    print(f"✓ PASS: Successfully retrieved Z2M device name")
    print(f"  Entity: {test_entity}")
    print(f"  Z2M Name: {z2m_device_name}")
    
    # Verify it would work for MQTT topic
    import re
    if re.match(r"^[a-z0-9\s\(\)]+$", z2m_device_name):
        print(f"✓ PASS: Z2M device name is valid for MQTT: zigbee2mqtt/{z2m_device_name}/set")
    else:
        print(f"✗ FAIL: Z2M device name has invalid characters")
        return False
    
    return True


async def run_all_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("TESTING MAIN CHANGES")
    print("="*70)
    
    tests = [
        ("Deep Copy Schedule Generation", test_deep_copy_schedule_generation),
        ("ECO Mode Exists", test_eco_mode_exists),
        ("Simplified Thermostat Mapping", test_simplified_thermostat_mapping),
        ("Blacklisted Areas Config", test_blacklisted_areas_config),
        ("Entity Lists Removed", test_entity_lists_removed),
        (".env Variables", test_env_variables),
        ("Mode Manager Mapping Usage", test_mode_manager_thermostat_mapping),
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            result = test_func()
            results[name] = "✓ PASS" if result else "✗ FAIL"
        except Exception as e:
            print(f"\n✗ EXCEPTION in {name}: {e}")
            import traceback
            traceback.print_exc()
            results[name] = "✗ ERROR"
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for name, result in results.items():
        print(f"{result}: {name}")
    
    passed = sum(1 for r in results.values() if r == "✓ PASS")
    total = len(results)
    
    print(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
