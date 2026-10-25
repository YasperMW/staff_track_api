"""
Script to fix incorrectly marked shift types in attendance records.
Corrects records that were wrongly marked as Night Shift Extended, Day Shift Extended,
or the wrong shift type due to the checkout logic bug.
"""

import os
import sys
from datetime import datetime, time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent / "staff_track_api"
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.db_models import AttendanceLog, ShiftConfiguration, User


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")


def get_shift_type_from_time(check_time: datetime) -> str:
    """Determine shift type based on check-in time (hour only)."""
    hour = check_time.hour
    minute = check_time.minute
    
    # Day shift: 06:00 to 16:29
    if (hour > 6) or (hour == 6 and minute >= 0):
        if (hour < 16) or (hour == 16 and minute < 30):
            return "Day Shift"
    
    # Night shift: 16:30 to 05:59
    return "Night Shift"


def is_extended(check_out_time: datetime, shift_type: str, config: dict) -> bool:
    """Check if checkout time extends beyond normal shift end."""
    if not check_out_time or not config:
        return False
    
    check_out_hour = check_out_time.hour
    check_out_minute = check_out_time.minute
    check_out_t = time(check_out_hour, check_out_minute)
    
    return check_out_t > config.get('check_out_latest', time(17, 30))


def fix_attendance_records():
    """Fix all incorrectly marked attendance records."""
    
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # Load shift configurations
        configs = db.query(ShiftConfiguration).filter(
            ShiftConfiguration.is_active == True
        ).all()
        
        config_dict = {}
        for config in configs:
            config_dict[config.shift_type] = {
                'check_out_earliest': config.check_out_earliest,
                'check_out_latest': config.check_out_latest,
                'check_in_earliest': config.check_in_earliest,
                'check_in_latest': config.check_in_latest,
            }
        
        print("Loaded shift configurations:")
        for shift_type, cfg in config_dict.items():
            print(f"  {shift_type}: check_out_latest={cfg['check_out_latest']}")
        
        # Query all attendance records with check-out times
        records = db.query(AttendanceLog).filter(
            AttendanceLog.check_out_time.isnot(None)
        ).order_by(AttendanceLog.check_in_time).all()
        
        print(f"\nFound {len(records)} attendance records with check-out times")
        
        fixed_count = 0
        corrected_shift_count = 0
        corrected_extended_count = 0
        already_correct_count = 0
        
        for record in records:
            # Get actual stored shift type (without extended suffix)
            stored_shift = record.shift_type
            if not stored_shift:
                continue
                
            base_shift = stored_shift.split(" → ")[0] if " → " in stored_shift else stored_shift
            
            # Determine correct shift type from check-in time
            correct_shift = get_shift_type_from_time(record.check_in_time)
            
            # Check if should be extended
            config = config_dict.get(correct_shift, config_dict.get('Day Shift', {}))
            extended = is_extended(record.check_out_time, correct_shift, config)
            
            # Build expected shift_type
            if extended:
                expected_shift = f"{correct_shift} → Extended"
            else:
                expected_shift = correct_shift
            
            # Check if record needs fixing
            if record.shift_type != expected_shift:
                old_shift = record.shift_type
                
                # Update the record
                record.shift_type = expected_shift
                
                print(f"\n[ FIXING ] User: {record.user_id}")
                print(f"    Check-in: {record.check_in_time}")
                print(f"    Check-out: {record.check_out_time}")
                print(f"    OLD shift_type: '{old_shift}'")
                print(f"    NEW shift_type: '{expected_shift}'")
                
                if base_shift != correct_shift:
                    corrected_shift_count += 1
                    print(f"    -> Corrected shift type ({base_shift} → {correct_shift})")
                elif extended and "→ Extended" not in old_shift:
                    corrected_extended_count += 1
                    print(f"    -> Added Extended status")
                elif not extended and "→ Extended" in old_shift:
                    corrected_extended_count += 1
                    print(f"    -> Removed Extended status (was early)")
                
                fixed_count += 1
            else:
                already_correct_count += 1
        
        print(f"\n{'='*60}")
        print(f"SUMMARY:")
        print(f"  Total records processed: {len(records)}")
        print(f"  Already correct: {already_correct_count}")
        print(f"  Fixed records: {fixed_count}")
        print(f"    - Corrected shift type: {corrected_shift_count}")
        print(f"    - Corrected extended status: {corrected_extended_count}")
        
        # Commit all changes
        if fixed_count > 0:
            response = input(f"\nCommit {fixed_count} changes? (y/n): ")
            if response.lower() == 'y':
                db.commit()
                print("Changes committed!")
            else:
                db.rollback()
                print("Changes rolled back.")
        else:
            print("\nNo changes to commit.")
            
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    fix_attendance_records()