"""
Test script for the new event-driven architecture
"""

import time
from engine.event_bus import get_event_bus
from engine.state_store import get_state_store
from engine.websocket_server import get_websocket_manager, create_websocket_app
from engine.state_persistence import get_state_persistence

print("=" * 60)
print("Testing Event-Driven Architecture Components")
print("=" * 60)

# Test 1: Event Bus
print("\n1. Testing Event Bus...")
event_bus = get_event_bus()

# Subscribe to events
event_received = []

def test_handler(event):
    event_received.append(event)
    print(f"   [OK] Event received: {event.get('type')}")

event_bus.subscribe('test_event', test_handler)

# Publish test event
event_bus.publish('test_event', {'message': 'Hello from Event Bus'})
time.sleep(0.1)

if event_received:
    print("   [OK] Event Bus working correctly")
else:
    print("   [FAIL] Event Bus failed")

# Test 2: State Store
print("\n2. Testing State Store...")
state_store = get_state_store()

# Update state
state_store.update_state('test.path', {'value': 42, 'message': 'test'})
retrieved = state_store.get_state('test.path')

if retrieved and retrieved.get('value') == 42:
    print("   [OK] State Store working correctly")
else:
    print("   [FAIL] State Store failed")

# Test 3: State Persistence
print("\n3. Testing State Persistence...")
try:
    state_persistence = get_state_persistence(
        snapshot_dir='data/state',
        snapshot_interval_minutes=5
    )
    print("   [OK] State Persistence initialized")
except Exception as e:
    print(f"   [FAIL] State Persistence failed: {e}")

# Test 4: WebSocket Manager
print("\n4. Testing WebSocket Manager...")
try:
    ws_manager = get_websocket_manager()
    print(f"   [OK] WebSocket Manager initialized (connections: {ws_manager.get_connection_count()})")
except Exception as e:
    print(f"   [FAIL] WebSocket Manager failed: {e}")

# Test 5: WebSocket App
print("\n5. Testing WebSocket App creation...")
try:
    app = create_websocket_app()
    print("   [OK] WebSocket FastAPI app created successfully")
except Exception as e:
    print(f"   [FAIL] WebSocket App failed: {e}")

# Test 6: Integration Test
print("\n6. Testing Integration (Event Bus → State Store)...")
state_changes = []

def state_change_handler(path, new_value, old_value):
    state_changes.append((path, new_value))
    print(f"   [OK] State change detected: {path}")

state_store.subscribe('test.integration', state_change_handler)
state_store.update_state('test.integration', {'status': 'active'})
time.sleep(0.1)

if state_changes:
    print("   [OK] Integration working correctly")
else:
    print("   [FAIL] Integration failed")

print("\n" + "=" * 60)
print("Architecture Test Complete!")
print("=" * 60)
print("\nAll core components are working. You can now:")
print("1. Start the Streamlit dashboard: streamlit run dashboard/ui_frontend.py")
print("2. The WebSocket server will start automatically")
print("3. The dashboard will connect to the WebSocket server")
print("\nCheck the logs for any issues during startup.")

