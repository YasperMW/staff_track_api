#!/usr/bin/env python3
"""
Test script to verify timezone configuration is working correctly
"""

import sys
import os
sys.path.append('.')

from datetime import datetime
from timezone_config import get_current_time, to_app_timezone, to_utc, APP_TIMEZONE

def test_timezone_functions():
    """Test all timezone functions"""
    print("🧪 Testing Timezone Configuration")
    print("=" * 50)
    
    # Test 1: Basic timezone setup
    print(f"✅ APP_TIMEZONE: {APP_TIMEZONE.zone}")
    
    # Test 2: Get current time
    current_time = get_current_time()
    print(f"✅ Current time: {current_time}")
    print(f"✅ Timezone info: {current_time.tzinfo}")
    
    # Test 3: Conversion functions
    utc_time = to_utc(current_time)
    app_time = to_app_timezone(utc_time)
    print(f"✅ UTC time: {utc_time}")
    print(f"✅ Converted back to app timezone: {app_time}")
    
    # Test 4: Import attendance endpoints (this was failing before)
    try:
        from endpoints.attendance_endpoints import router
        print("✅ Attendance endpoints imported successfully")
    except Exception as e:
        print(f"❌ Error importing attendance endpoints: {e}")
        return False
    
    # Test 5: Test my-profile-metrics function (without database)
    try:
        from endpoints.attendance_endpoints import get_my_profile_metrics
        print("✅ get_my_profile_metrics function imported successfully")
    except Exception as e:
        print(f"❌ Error importing get_my_profile_metrics: {e}")
        return False
    
    print("\n🎉 All timezone tests passed!")
    return True

if __name__ == "__main__":
    success = test_timezone_functions()
    sys.exit(0 if success else 1)
